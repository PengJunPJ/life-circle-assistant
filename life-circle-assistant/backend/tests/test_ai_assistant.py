from app.ai_assistant import build_ai_interpretation
from fastapi.testclient import TestClient
from app.main import create_app


def report_fixture() -> dict:
    return {
        "report_id": "report-ai-1",
        "id": "report-ai-1",
        "status": "completed",
        "completeness": "complete",
        "data_quality": {"overall_status": "good"},
        "summary": {"score": 68, "critical_zone_count": 1, "sparse_zone_count": 2},
        "category_scores": [{"category": "market", "label": "菜市场", "score": 54, "status_explanation": "设施数量偏少"}],
        "service_areas": {"type": "FeatureCollection", "features": [{
            "type": "Feature",
            "properties": {
                "grid_id": "market-r1c1", "category": "market", "category_label": "菜市场",
                "label": "重点服务盲区", "kind": "critical", "basis": "最近同类设施步行18.0分钟，超过15分钟阈值，且周边1000米内无同类设施。",
            },
            "geometry": {"type": "Polygon", "coordinates": [[[113.4, 23.1], [113.41, 23.1], [113.41, 23.11], [113.4, 23.11], [113.4, 23.1]]]},
        }]},
        "recommendations": [{"title": "优先补充菜市场", "category": "market", "priority": "high", "rationale": "优先覆盖重点服务盲区", "target_region_ids": ["market-r1c1"]}],
    }


def test_summary_uses_report_evidence_and_rule_mode():
    result = build_ai_interpretation(report_fixture())
    assert result["mode"] == "rule_template"
    assert result["model"] == "规则模板"
    assert result["summary"].startswith("本次生活圈体检综合指数为 68")
    assert {item["id"] for item in result["evidence_refs"]} >= {"report-ai-1", "market-r1c1", "market"}
    assert "不会修改原始评分" in result["boundary_notice"]


def test_area_explanation_rejects_unknown_grid():
    try:
        build_ai_interpretation(report_fixture(), intent="area_explanation", grid_id="market-r9c9")
    except ValueError as exc:
        assert "不存在" in str(exc)
    else:
        raise AssertionError("unknown grid should be rejected")


def test_ask_with_simulation_question_does_not_invent_improvement():
    result = build_ai_interpretation(report_fixture(), intent="ask", question="增加一个设施后改善多少？")
    assert "还没有已完成的新增设施模拟" in result["summary"]


def test_ai_interpretation_api_persists_and_reopens_result(tmp_path):
    client = TestClient(create_app(database_path=tmp_path / "ai.db"))
    created = client.post("/api/analyze", json={"minutes": 15, "mode": "demo", "categories": ["market"]})
    assert created.status_code == 200
    task = client.get(f"/api/analyze/{created.json()['id']}").json()
    assert task["status"] == "completed"
    report_id = task["result"]["report_id"]
    response = client.post(f"/api/reports/{report_id}/ai/interpret", json={"intent": "summary"})
    assert response.status_code == 200
    assert response.json()["mode"] == "rule_template"
    history = client.get(f"/api/reports/{report_id}/ai/interpretations")
    assert history.status_code == 200
    assert history.json()["items"][0]["summary"] == response.json()["summary"]
