"""在百度 Web 服务可用时，抓取一次体检报告并保存为本地快照。"""

import asyncio
import json

from app.baidu import BaiduMapError
from app.local_snapshot import SNAPSHOT_PATH
from app.main import build_report
from app.schemas import AnalyzeRequest


async def main() -> None:
    try:
        report = await build_report(AnalyzeRequest())
    except BaiduMapError as exc:
        raise SystemExit(f"百度数据抓取失败，未覆盖旧快照：{exc}") from exc
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {key: report[key] for key in ("center", "isochrone", "pois", "zones")}
    snapshot.update({"schema_version": 1, "source": "baidu_web_service", "captured_at": report["created_at"]})
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已保存百度地图本地快照：{SNAPSHOT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
