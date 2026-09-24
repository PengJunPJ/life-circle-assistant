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
        "category_scores": [
            {"category": "market", "label": "菜市场", "score": 54, "status_explanation": "设施数量偏少"},
            {"category": "school", "label": "小学", "score": 82, "status_explanation": "覆盖较完整"},
        ],
        "service_areas": {"type": "FeatureCollection", "features": [{
            "type": "Feature",
            "properties": {
                "grid_id": "market-r1c1", "category": "market", "category_label": "菜市场",
                "label": "重点服务盲区", "kind": "critical", "basis": "最近同类设施步行18.0分钟，超过15分钟阈值，且周边1000米内无同类设施。",
            },
            "geometry": {"type": "Polygon", "coordinates": [[[113.4, 23.1], [113.41, 23.1], [113.41, 23.11], [113.4, 23.11], [113.4, 23.1]]]},
        }]},
        "recommendations": [{"title": "优先补充菜市场", "category": "market", "priority": "high", "rationale": "优先覆盖重点服务盲区", "target_region_ids": ["market-r1c1"]}],
        "parameters": {"minutes": 15},
        "center": {"address": "广州市黄埔区红山街道海韵东路"},
    }


def report_with_simulation_fixture() -> dict:
    report = report_fixture()
    report["simulations"] = [{
        "id": "sim-market-1",
        "report_id": "report-ai-1",
        "category": "market",
        "category_label": "菜市场",
        "selection_method": "recommendation",
        "candidate_id": "cand-1",
        "hypothetical_facility": {
            "id": "hypothetical-market-1",
            "name": "假设菜市场",
            "category": "market",
            "lng": 113.405,
            "lat": 23.105,
            "walk_minutes": 9.5,
            "walk_distance_m": 720,
            "source": "hypothetical",
            "calculation_method": "provider_walking_matrix",
            "is_hypothetical": True,
        },
        "before": {"category_score": 54, "overall_score": 68, "coverage_area_sqm": 120000, "critical_zone_count": 1, "sparse_zone_count": 2},
        "after": {"category_score": 78, "overall_score": 74, "coverage_area_sqm": 165000, "critical_zone_count": 0, "sparse_zone_count": 1},
        "delta": {"category_score": 24, "overall_score": 6, "coverage_area_sqm": 45000, "critical_zone_count": -1, "sparse_zone_count": -1},
        "data_quality": {"source": "baidu", "events": [], "partial_failures": [], "disclosure": "模拟结果仅用于方案比较，不修改来源设施或原始体检报告。"},
    }]
    return report


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


def test_priority_ranks_by_report_scores_only():
    result = build_ai_interpretation(report_fixture(), intent="priority")
    assert result["intent"] == "priority"
    titles = [item["title"] for item in result["recommendations"]]
    # 菜市场评分 54 最低，必须排在小学（82）之前
    assert any("菜市场" in title for title in titles[:1])
    assert all("菜市场" in titles[0] or "优先" in titles[0] for _ in [0])
    # 证据只允许引用报告已有实体
    allowed_ids = {"report-ai-1", "market", "school", "market-r1c1"}
    assert {ref["id"] for ref in result["evidence_refs"]} <= allowed_ids
    assert any(ref["type"] == "category_score" and ref["id"] == "market" for ref in result["evidence_refs"])


def test_priority_rejects_unknown_category():
    try:
        build_ai_interpretation(report_fixture(), intent="priority", category="hospital")
    except ValueError as exc:
        assert "不存在" in str(exc)
    else:
        raise AssertionError("unknown category should be rejected")


def test_simulation_intent_without_results_does_not_invent_numbers():
    result = build_ai_interpretation(report_fixture(), intent="simulation")
    assert result["intent"] == "simulation"
    assert "还没有已完成的新增设施模拟" in result["summary"]
    assert result["recommendations"] == []


def test_simulation_intent_uses_reported_delta_only():
    result = build_ai_interpretation(report_with_simulation_fixture(), intent="simulation")
    assert result["intent"] == "simulation"
    assert "+24" in result["summary"]  # category_score delta
    assert "+6" in result["summary"]   # overall_score delta
    assert "-1" in result["summary"]   # critical zone delta
    assert "9.5" in result["summary"]  # hypothetical walk minutes
    assert any(ref["type"] == "simulation" and ref["id"] == "sim-market-1" for ref in result["evidence_refs"])


def test_simulation_intent_rejects_unknown_id():
    try:
        build_ai_interpretation(report_with_simulation_fixture(), intent="simulation", simulation_id="sim-missing")
    except ValueError as exc:
        assert "不存在" in str(exc)
    else:
        raise AssertionError("unknown simulation_id should be rejected")


def test_brief_intent_includes_center_and_top_priority():
    result = build_ai_interpretation(report_fixture(), intent="brief")
    assert result["intent"] == "brief"
    assert "海韵东路" in result["summary"]
    assert "综合指数为 68" in result["summary"]
    assert "菜市场" in result["summary"]
    assert "不会修改原始评分" in result["summary"]


def test_ask_routes_to_priority_intent():
    result = build_ai_interpretation(report_fixture(), intent="ask", question="最应该优先补什么设施？")
    assert result["intent"] == "priority"


def test_ask_routes_to_brief_intent():
    result = build_ai_interpretation(report_fixture(), intent="ask", question="帮我生成一份街道汇报摘要")
    assert result["intent"] == "brief"


def test_unsupported_intent_is_rejected():
    try:
        build_ai_interpretation(report_fixture(), intent="chat")
    except ValueError as exc:
        assert "不支持" in str(exc)
    else:
        raise AssertionError("unsupported intent should be rejected")


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
    priority_response = client.post(f"/api/reports/{report_id}/ai/interpret", json={"intent": "priority"})
    assert priority_response.status_code == 200
    assert priority_response.json()["intent"] == "priority"
    brief_response = client.post(f"/api/reports/{report_id}/ai/interpret", json={"intent": "brief"})
    assert brief_response.status_code == 200
    assert brief_response.json()["intent"] == "brief"
    history = client.get(f"/api/reports/{report_id}/ai/interpretations")
    assert history.status_code == 200
    intents = {item["intent"] for item in history.json()["items"]}
    assert {"summary", "priority", "brief"} <= intents


def test_ai_interpretation_api_rejects_unsupported_intent(tmp_path):
    client = TestClient(create_app(database_path=tmp_path / "ai-reject.db"))
    created = client.post("/api/analyze", json={"minutes": 15, "mode": "demo", "categories": ["market"]})
    task = client.get(f"/api/analyze/{created.json()['id']}").json()
    report_id = task["result"]["report_id"]
    response = client.post(f"/api/reports/{report_id}/ai/interpret", json={"intent": "chat"})
    assert response.status_code == 422
