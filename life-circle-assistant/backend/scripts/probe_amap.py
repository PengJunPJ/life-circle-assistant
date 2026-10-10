#!/usr/bin/env python3
"""只验证高德 Key 和 POI 权限，不输出或保存原始 POI 字段。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.amap import AmapError, AmapPoiClient  # noqa: E402


async def run(args: argparse.Namespace) -> dict:
    client = AmapPoiClient()
    try:
        center = (args.lng, args.lat)
        converted = await client.convert_from_baidu([center])
        pois, audit = await client.search_around(
            location_gcj02=converted[0], keyword=args.keyword, radius_m=args.radius
        )
        return {
            "configured": True,
            "verified": True,
            "provider": "amap",
            "keyword": args.keyword,
            "returned_count": len(pois),
            "pages": audit["pages"],
            "truncated": audit["truncated"],
            "request_count": client.request_count,
        }
    except AmapError as exc:
        return {
            "configured": client.configured,
            "verified": False,
            "provider": "amap",
            "error_code": exc.code,
            "message": str(exc),
        }
    finally:
        await client.aclose()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="探测高德 Web 服务 Key 和 POI 搜索权限")
    parser.add_argument("--lng", type=float, default=113.4872)
    parser.add_argument("--lat", type=float, default=23.1068)
    parser.add_argument("--radius", type=int, default=3000)
    parser.add_argument("--keyword", default="药店")
    print(json.dumps(asyncio.run(run(parser.parse_args())), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
