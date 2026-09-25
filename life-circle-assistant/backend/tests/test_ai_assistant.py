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


def test_evidence_validation_filters_unknown_refs():
    """防幻觉：无效证据引用应被过滤，只保留报告中真实存在的实体。"""
    from app.ai_assistant import _build_report_index, _validate_evidence_refs

    report = report_fixture()
    index = _build_report_index(report)

    # 构造包含有效和无效引用的列表
    refs = [
        {"type": "report", "id": "report-ai-1", "label": "体检报告", "detail": "综合指数 68"},
        {"type": "category_score", "id": "market", "label": "菜市场评分", "detail": "评分 54"},
        {"type": "service_area", "id": "unknown-grid", "label": "未知网格", "detail": "虚构"},
        {"type": "facility", "id": "unknown-poi", "label": "未知设施", "detail": "虚构"},
        {"type": "unknown_type", "id": "xyz", "label": "未知类型", "detail": "虚构"},
    ]

    valid, invalid = _validate_evidence_refs(refs, index)
    assert len(valid) == 2
    assert len(invalid) == 3
    assert {ref["id"] for ref in valid} == {"report-ai-1", "market"}


def test_hallucinated_evidence_triggers_degradation():
    """防幻觉：当所有证据引用都无效时，结果应标记为降级模式。"""
    from app.ai_assistant import _filter_hallucinated_content

    report = report_fixture()
    # 构造一个所有证据都无效的结果
    fake_result = {
        "intent": "summary",
        "summary": "虚构摘要",
        "recommendations": [],
        "evidence_refs": [
            {"type": "service_area", "id": "fake-grid-1", "label": "虚构网格", "detail": "不存在"},
            {"type": "facility", "id": "fake-poi-1", "label": "虚构设施", "detail": "不存在"},
        ],
        "model": "规则模板",
        "mode": "rule_template",
        "prompt_version": "test",
        "generated_at": "2026-01-01T00:00:00Z",
        "data_quality_notice": "原始提示",
        "boundary_notice": "边界提示",
    }

    filtered = _filter_hallucinated_content(fake_result, report)
    assert filtered["mode"] == "rule_template_degraded"
    assert filtered["evidence_refs"] == []
    assert "降级" in filtered["data_quality_notice"]


def test_valid_evidence_passes_through():
    """防幻觉：有效证据引用应完整保留，不触发降级。"""
    from app.ai_assistant import _filter_hallucinated_content

    report = report_fixture()
    valid_result = {
        "intent": "summary",
        "summary": "有效摘要",
        "recommendations": [],
        "evidence_refs": [
            {"type": "report", "id": "report-ai-1", "label": "体检报告", "detail": "综合指数 68"},
            {"type": "category_score", "id": "market", "label": "菜市场评分", "detail": "评分 54"},
        ],
        "model": "规则模板",
        "mode": "rule_template",
        "prompt_version": "test",
        "generated_at": "2026-01-01T00:00:00Z",
        "data_quality_notice": "原始提示",
        "boundary_notice": "边界提示",
    }

    filtered = _filter_hallucinated_content(valid_result, report)
    assert filtered["mode"] == "rule_template"
    assert len(filtered["evidence_refs"]) == 2
    assert "降级" not in filtered["data_quality_notice"]


def test_mixed_evidence_keeps_only_valid():
    """防幻觉：混合有效和无效引用时，只保留有效部分，不触发完全降级。"""
    from app.ai_assistant import _filter_hallucinated_content

    report = report_fixture()
    mixed_result = {
        "intent": "summary",
        "summary": "混合摘要",
        "recommendations": [],
        "evidence_refs": [
            {"type": "report", "id": "report-ai-1", "label": "体检报告", "detail": "综合指数 68"},
            {"type": "service_area", "id": "fake-grid", "label": "虚构网格", "detail": "不存在"},
        ],
        "model": "规则模板",
        "mode": "rule_template",
        "prompt_version": "test",
        "generated_at": "2026-01-01T00:00:00Z",
        "data_quality_notice": "原始提示",
        "boundary_notice": "边界提示",
    }

    filtered = _filter_hallucinated_content(mixed_result, report)
    assert filtered["mode"] == "rule_template"  # 不是完全降级
    assert len(filtered["evidence_refs"]) == 1
    assert filtered["evidence_refs"][0]["id"] == "report-ai-1"


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


def _create_demo_report(client: TestClient) -> str:
    created = client.post("/api/analyze", json={"minutes": 15, "mode": "demo", "categories": ["market"]})
    assert created.status_code == 200
    task = client.get(f"/api/analyze/{created.json()['id']}").json()
    assert task["status"] == "completed"
    return task["result"]["report_id"]


def test_json_export_includes_ai_interpretations_after_generation(tmp_path):
    """JSON 导出在生成 AI 解读后应附带 ai_interpretations 字段。"""
    client = TestClient(create_app(database_path=tmp_path / "ai-json-export.db"))
    report_id = _create_demo_report(client)

    # 生成一条 AI 解读
    interpret_response = client.post(f"/api/reports/{report_id}/ai/interpret", json={"intent": "summary"})
    assert interpret_response.status_code == 200
    saved = interpret_response.json()
    assert saved["intent"] == "summary"

    # 导出 JSON 并验证包含 AI 结果
    export_response = client.get(f"/api/reports/{report_id}/exports/json")
    assert export_response.status_code == 200
    exported = export_response.json()
    assert "ai_interpretations" in exported
    assert len(exported["ai_interpretations"]) >= 1
    latest = exported["ai_interpretations"][0]
    assert latest["intent"] == "summary"
    assert latest["summary"] == saved["summary"]
    assert latest["mode"] == saved["mode"]
    assert latest["prompt_version"] == saved["prompt_version"]
    # 原始报告字段仍然完整
    assert exported["report_id"] == report_id
    assert "category_scores" in exported
    assert "data_quality" in exported


def test_json_export_without_ai_omits_interpretations_key(tmp_path):
    """未生成 AI 解读时，JSON 导出不应注入 ai_interpretations 键，保持与原始报告等值。"""
    client = TestClient(create_app(database_path=tmp_path / "ai-json-noai.db"))
    report_id = _create_demo_report(client)

    export_response = client.get(f"/api/reports/{report_id}/exports/json")
    assert export_response.status_code == 200
    exported = export_response.json()
    assert "ai_interpretations" not in exported

    # 与 GET /api/reports/{id} 返回的原始报告等值
    original = client.get(f"/api/reports/{report_id}").json()
    assert exported == original


def test_pdf_export_includes_ai_section_after_generation(tmp_path):
    """PDF 导出在生成 AI 解读后应渲染「AI 解读与证据」章节。"""
    from io import BytesIO
    from pypdf import PdfReader

    client = TestClient(create_app(database_path=tmp_path / "ai-pdf-export.db"))
    report_id = _create_demo_report(client)

    interpret_response = client.post(f"/api/reports/{report_id}/ai/interpret", json={"intent": "brief"})
    assert interpret_response.status_code == 200
    saved = interpret_response.json()

    export_response = client.get(f"/api/reports/{report_id}/exports/pdf")
    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == "application/pdf"
    assert export_response.content.startswith(b"%PDF-")

    reader = PdfReader(BytesIO(export_response.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "AI 解读与证据" in text
    assert "生成方式" in text
    # AI 摘要文本应出现在 PDF 中
    assert saved["summary"][:20] in text


def test_pdf_export_without_ai_has_no_ai_section(tmp_path):
    """未生成 AI 解读时，PDF 不应包含 AI 章节。"""
    from io import BytesIO
    from pypdf import PdfReader

    client = TestClient(create_app(database_path=tmp_path / "ai-pdf-noai.db"))
    report_id = _create_demo_report(client)

    export_response = client.get(f"/api/reports/{report_id}/exports/pdf")
    assert export_response.status_code == 200
    reader = PdfReader(BytesIO(export_response.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "AI 解读与证据" not in text


def test_history_reopen_returns_latest_interpretation_first(tmp_path):
    """历史报告重开：列表端点按生成时间倒序返回，前端取 items[0] 即最新解读。"""
    client = TestClient(create_app(database_path=tmp_path / "ai-history.db"))
    report_id = _create_demo_report(client)

    # 依次生成三条不同 intent 的解读
    first = client.post(f"/api/reports/{report_id}/ai/interpret", json={"intent": "summary"}).json()
    second = client.post(f"/api/reports/{report_id}/ai/interpret", json={"intent": "priority"}).json()
    third = client.post(f"/api/reports/{report_id}/ai/interpret", json={"intent": "brief"}).json()

    history = client.get(f"/api/reports/{report_id}/ai/interpretations")
    assert history.status_code == 200
    items = history.json()["items"]
    assert len(items) == 3
    # 倒序：最新生成的 brief 在最前
    assert items[0]["intent"] == "brief"
    assert items[0]["summary"] == third["summary"]
    assert items[1]["intent"] == "priority"
    assert items[1]["summary"] == second["summary"]
    assert items[2]["intent"] == "summary"
    assert items[2]["summary"] == first["summary"]
    # 每条都带 id 和生成时间，便于审计
    for item in items:
        assert "id" in item
        assert "generated_at" in item
        assert "prompt_version" in item


def test_history_reopen_after_rerun_does_not_leak_old_interpretations(tmp_path):
    """报告重跑生成新 report_id 后，旧解读不会关联到新报告。"""
    client = TestClient(create_app(database_path=tmp_path / "ai-rerun.db"))
    original_id = _create_demo_report(client)
    client.post(f"/api/reports/{original_id}/ai/interpret", json={"intent": "summary"})

    # 重跑生成新报告
    rerun_response = client.post(f"/api/reports/{original_id}/rerun")
    assert rerun_response.status_code == 200
    new_task_id = rerun_response.json()["id"]
    new_task = client.get(f"/api/analyze/{new_task_id}").json()
    assert new_task["status"] == "completed"
    new_report_id = new_task["result"]["report_id"]
    assert new_report_id != original_id

    # 新报告没有继承旧解读
    new_history = client.get(f"/api/reports/{new_report_id}/ai/interpretations")
    assert new_history.status_code == 200
    assert new_history.json()["items"] == []

    # 旧报告解读仍可读取
    old_history = client.get(f"/api/reports/{original_id}/ai/interpretations")
    assert len(old_history.json()["items"]) == 1
