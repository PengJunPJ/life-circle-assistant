"""在百度 Web 服务可用时，抓取一次体检报告并保存为本地快照。"""

import asyncio
import json
import uuid

from app.analysis import AnalysisApplicationService
from app.baidu import BaiduMapClient
from app.local_snapshot import SNAPSHOT_PATH
from app.maps.baidu import BaiduMapProvider
from app.schemas import AnalyzeRequest


async def main() -> None:
    client = BaiduMapClient()
    if not client.real_available:
        raise SystemExit("百度数据抓取失败，未启用真实模式或缺少 BAIDU_MAP_AK；旧快照保持不变")
    try:
        report = await AnalysisApplicationService(BaiduMapProvider(client)).run(str(uuid.uuid4()), AnalyzeRequest())
    except Exception as exc:
        raise SystemExit(f"百度数据抓取失败，未覆盖旧快照：{exc}") from exc
    if report["completeness"] != "complete" or report["source"] != "baidu":
        raise SystemExit("百度数据抓取返回部分结果或非实时来源，未覆盖旧快照")
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {key: report[key] for key in ("center", "isochrone", "pois", "zones")}
    snapshot.update({"schema_version": 1, "source": "baidu_web_service", "captured_at": report["created_at"]})
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已保存百度地图本地快照：{SNAPSHOT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
