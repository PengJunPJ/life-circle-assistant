import asyncio

from app.ai_assistant import build_ai_interpretation
from app.llm import enhance_interpretation


class FakeProvider:
    model = "test-model"

    def __init__(self, result):
        self.result = result

    async def generate(self, *, system, user):
        return self.result

    async def close(self):
        return None


def report_fixture():
    return {
        "report_id": "report-llm-1",
        "status": "completed",
        "completeness": "complete",
        "data_quality": {"overall_status": "good"},
        "summary": {"score": 68, "critical_zone_count": 1, "sparse_zone_count": 0},
        "category_scores": [
            {"category": "market", "label": "菜市场", "score": 54, "status_explanation": "设施数量偏少"}
        ],
        "service_areas": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "grid_id": "market-r1c1",
                        "category": "market",
                        "category_label": "菜市场",
                        "label": "重点服务盲区",
                        "kind": "critical",
                        "basis": "最近同类设施步行18分钟，超过15分钟阈值。",
                    },
                    "geometry": {"type": "Polygon", "coordinates": []},
                }
            ],
        },
        "recommendations": [],
        "parameters": {"minutes": 15},
        "center": {"address": "黄埔区样例社区"},
    }


def test_structured_llm_result_uses_only_canonical_evidence():
    report = report_fixture()
    deterministic = build_ai_interpretation(report)
    result = asyncio.run(
        enhance_interpretation(
            FakeProvider(
                {
                    "summary": "这里的菜市场服务需要优先关注。",
                    "recommendations": [
                        {
                            "title": "优先核查菜市场补充方案",
                            "text": "先复核现场通行和用地条件。",
                            "priority": "high",
                            "evidence_refs": [
                                {"type": "category_score", "id": "market"},
                                {"type": "service_area", "id": "fake-grid"},
                            ],
                        }
                    ],
                    "evidence_refs": [{"type": "report", "id": "report-llm-1"}],
                    "uncertainties": ["需要现场核验"],
                }
            ),
            report,
            deterministic,
        )
    )

    assert result["mode"] == "llm_structured"
    assert result["model"] == "test-model"
    assert "fake-grid" not in {ref["id"] for ref in result["evidence_refs"]}
    assert result["recommendations"][0]["evidence_refs"][0]["id"] == "market"


def test_llm_failure_falls_back_to_deterministic_result():
    report = report_fixture()
    deterministic = build_ai_interpretation(report)

    class BrokenProvider(FakeProvider):
        async def generate(self, *, system, user):
            raise RuntimeError("network down")

    result = asyncio.run(enhance_interpretation(BrokenProvider({}), report, deterministic))

    assert result["mode"] == "rule_template_degraded"
    assert result["summary"] == deterministic["summary"]
    assert "大模型暂时不可用" in result["data_quality_notice"]
