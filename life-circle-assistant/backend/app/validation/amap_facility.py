from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..amap import AmapError, AmapPoi, AmapPoiClient
from ..analysis.facility_reconciliation import reconcile_facilities
from ..baidu import BaiduMapClient, BaiduMapError

AMAP_FACILITY_QUERIES = {
    "market": ("菜市场", "农贸市场", "生鲜超市"),
    "pharmacy": ("药店",),
    "school": ("小学",),
    "medical": ("社区卫生服务中心", "医院", "诊所"),
    "elderly": ("养老院", "敬老院", "日间照料中心", "养老服务中心"),
    "park": ("公园", "口袋公园", "社区花园"),
    "convenience": ("便利店", "超市", "综合超市"),
}


class AmapFacilityValidator:
    """使用高德作为只读观察源，不改变百度主分析。"""

    def __init__(self, amap_client: AmapPoiClient, baidu_client: BaiduMapClient) -> None:
        self.amap_client = amap_client
        self.baidu_client = baidu_client

    async def validate(
        self,
        facilities: list[dict[str, Any]],
        *,
        center_bd09: tuple[float, float],
        categories: list[str],
        radius_m: int,
    ) -> dict[str, Any]:
        started_at = datetime.now(UTC).isoformat()
        if not self.amap_client.configured or not self.baidu_client.real_available:
            return self._failed("not_configured", "高德或百度真实 Web 服务未配置", started_at)
        try:
            center_gcj02 = (await self.amap_client.convert_from_baidu([center_bd09]))[0]
            amap_records_by_id: dict[str, dict[str, Any]] = {}
            query_audit: list[dict[str, Any]] = []
            for category in categories:
                for keyword in AMAP_FACILITY_QUERIES.get(category, (category,)):
                    pois, audit = await self.amap_client.search_around(
                        location_gcj02=center_gcj02, keyword=keyword, radius_m=radius_m
                    )
                    query_audit.append({**audit, "category": category})
                    for record in await self._to_reconciliation_records(pois, category):
                        amap_records_by_id.setdefault(record["source_record_id"], record)
            baidu_records = [self._baidu_record(item) for item in facilities]
            result = reconcile_facilities([*baidu_records, *amap_records_by_id.values()], as_of=started_at)
            return self._summary(result, query_audit, started_at)
        except AmapError as exc:
            return self._failed(exc.code, str(exc), started_at)
        except BaiduMapError as exc:
            return self._failed(exc.code, "辅助验证坐标转换失败", started_at)
        except Exception:
            return self._failed("validation_error", "高德辅助验证处理失败", started_at)

    async def _to_reconciliation_records(self, pois: list[AmapPoi], category: str) -> list[dict[str, Any]]:
        converted = await self.baidu_client.convert_coordinates([(poi.lng, poi.lat) for poi in pois], model=1)
        now = datetime.now(UTC).isoformat()
        return [
            {
                "source": "amap",
                "source_record_id": poi.source_record_id,
                "name": poi.name,
                "category": category,
                "lng": item["lng"],
                "lat": item["lat"],
                "address": poi.address,
                "coordinate_system": "bd09",
                "retrieved_at": now,
                "source_updated_at": "",
                "source_priority": 0,
            }
            for poi, item in zip(pois, converted, strict=True)
        ]

    @staticmethod
    def _baidu_record(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": "baidu",
            "source_record_id": str(item.get("id") or item.get("provider_id") or "unknown"),
            "name": item.get("canonical_name") or item.get("name") or "",
            "category": item.get("category") or "unknown",
            "lng": item["lng"],
            "lat": item["lat"],
            "address": item.get("address") or "",
            "coordinate_system": "bd09",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "source_updated_at": "",
            "source_priority": 0,
        }

    @staticmethod
    def _summary(result: Any, query_audit: list[dict[str, Any]], started_at: str) -> dict[str, Any]:
        decisions = result.decisions
        return {
            "status": "complete",
            "provider": "amap",
            "affects_primary_analysis": False,
            "rules_version": result.summary["rules_version"],
            "started_at": started_at,
            "query_count": len(query_audit),
            "returned_count": sum(item["returned_count"] for item in query_audit),
            "truncated_query_count": sum(item["truncated"] for item in query_audit),
            "matched_count": result.summary["matched_group_count"],
            "review_count": result.summary["review_count"],
            "conflict_count": result.summary["conflict_count"],
            "unmatched_count": result.summary["unmatched_count"],
            "decision_counts": {
                decision: sum(item["decision"] == decision for item in decisions)
                for decision in {
                    "matched",
                    "needs_review",
                    "category_conflict",
                    "coordinate_system_conflict",
                    "multiple_cluster_candidates",
                }
            },
            "query_audit": query_audit,
        }

    @staticmethod
    def _failed(code: str, message: str, started_at: str) -> dict[str, Any]:
        return {
            "status": "failed",
            "provider": "amap",
            "affects_primary_analysis": False,
            "started_at": started_at,
            "error_code": code,
            "message": message,
            "query_count": 0,
            "returned_count": 0,
            "truncated_query_count": 0,
            "matched_count": 0,
            "review_count": 0,
            "conflict_count": 0,
            "unmatched_count": 0,
        }
