from __future__ import annotations

import asyncio
import copy
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from test_simulations import SimulationFixtureProvider

from app.llm import LLMError, LLMSettings, OpenAICompatibleProvider
from app.main import create_app
from app.planning_assistant import PlanningTools, run_planning_assistant
from app.schemas import PlanningRequest


def call(name, arguments, identifier="call-1"):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
        ],
    }


def answer(summary, refs, *, clarification=False):
    return {
        "role": "assistant",
        "content": json.dumps(
            {
                "summary": summary,
                "evidence_refs": refs,
                "needs_clarification": clarification,
            }
        ),
    }


class ScriptedModel:
    model = "scripted-tool-model"

    def __init__(self, script):
        self.script = list(script)
        self.messages = []

    async def generate_tools(self, *, messages, tools):
        self.messages.append(copy.deepcopy(messages))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(messages) if callable(step) else step

    async def close(self):
        pass


@pytest.fixture
def setup_report(tmp_path):
    provider = SimulationFixtureProvider()
    app = create_app(provider, tmp_path / "planning.db")
    app.state.llm_provider = None
    client = TestClient(app)
    created = client.post(
        "/api/analyze",
        json={
            "lng": 113.5,
            "lat": 23.1,
            "minutes": 15,
            "categories": ["market", "school"],
        },
    ).json()
    report = client.get(f"/api/report/{created['id']}").json()
    return app, client, provider, report


def last_result(messages):
    return json.loads(messages[-1]["content"])


def test_native_model_executes_full_chain_with_real_simulation_and_persists(setup_report):
    app, client, provider, report = setup_report
    candidate = next(rec for rec in report["recommendations"] if rec["category"] == "market")["candidate_locations"][0]

    def simulation_step(messages):
        result = last_result(messages)
        assert candidate["id"] in {item["id"] for item in result["items"]}
        return call("simulate_facility", {"category": "market", "location_id": candidate["id"]}, "sim")

    def final_step(messages):
        result = last_result(messages)
        assert result["simulation"]["delta"]["category_score"] > 0
        return answer("该候选位置有助于改善菜市场服务，但仍应核验现场步行条件。", result["evidence_refs"])

    model = ScriptedModel(
        [
            call("query_facilities", {"category": "market"}, "facilities"),
            call("get_grid_evidence", {"category": "market", "kind": "critical"}, "grids"),
            call("get_planning_candidates", {"category": "market"}, "candidates"),
            simulation_step,
            final_step,
        ]
    )
    app.state.llm_provider = model
    with patch.object(provider, "walking_matrix", wraps=provider.walking_matrix) as walking:
        response = client.post(f"/api/reports/{report['report_id']}/ai/plan", json={"message": "模拟新增菜市场的效果"})
        assert walking.call_count > 0, "must execute the existing simulation computation"
    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "llm_tools"
    assert result["model"] == model.model
    assert [item["name"] for item in result["tool_calls"]] == [
        "query_facilities",
        "get_grid_evidence",
        "get_planning_candidates",
        "simulate_facility",
    ]
    assert all(item["status"] == "completed" for item in result["tool_calls"])
    simulation = result["simulations"][0]
    assert result["evidence_refs"][0]["id"] == simulation["id"]
    assert simulation["hypothetical_facility"]["is_hypothetical"] is True
    assert client.get(f"/api/reports/{report['report_id']}").json() == report
    saved = client.get(f"/api/reports/{report['report_id']}/ai/interpretations").json()["items"][0]
    assert saved == result
    exported = client.get(f"/api/reports/{report['report_id']}/exports/json").json()
    assert exported["ai_interpretations"][0]["simulations"][0]["id"] == simulation["id"]
    assert len(model.messages) == 5
    assert model.messages[1][-1]["role"] == "tool"
    assert model.messages[1][-1]["tool_call_id"] == "facilities"


def test_followup_uses_server_saved_context_and_rejects_foreign_turn(setup_report):
    app, client, _, report = setup_report
    url = f"/api/reports/{report['report_id']}/ai/plan"
    previous = client.post(url, json={"message": "查询菜市场"}).json()

    def final(messages):
        context = json.loads(messages[1]["content"])
        assert context["previous_turn"]["question"] == "查询菜市场"
        assert context["previous_turn"]["planning_context"]["category"] == "market"
        assert context["previous_turn"]["tool_results"]
        return answer("需要结合上述网格的步行证据判断。", [previous["evidence_refs"][0]])

    app.state.llm_provider = ScriptedModel([final])
    response = client.post(url, json={"message": "为什么？", "previous_turn_id": previous["id"]})
    assert response.json()["mode"] == "llm_tools"
    assert response.json()["planning_context"]["category"] == "market"
    assert response.json()["tool_calls"] == []
    assert client.post(url, json={"message": "继续", "previous_turn_id": "foreign-turn"}).status_code == 422
    # Even a valid turn cannot be read from another report.
    created = client.post("/api/analyze", json={"lng": 113.5, "lat": 23.1}).json()
    other = client.get(f"/api/report/{created['id']}").json()
    assert (
        client.post(
            f"/api/reports/{other['report_id']}/ai/plan",
            json={
                "message": "继续",
                "previous_turn_id": previous["id"],
            },
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    ("name", "arguments", "error"),
    [
        ("delete_report", {}, "允许列表"),
        ("query_facilities", {"category": "park"}, "已分析"),
        ("query_facilities", {"limit": 200}, "格式或范围"),
        ("get_grid_evidence", {"grid_id": "made-up"}, "不存在"),
        ("simulate_facility", {"category": "market", "location_id": "fabricated"}, "不存在"),
        ("simulate_facility", {"category": "market", "location_id": "selected_map_point", "lng": 113.5}, "格式或范围"),
        ("simulate_facility", {"category": "market", "location_id": "selected_map_point"}, "地图"),
    ],
)
def test_tools_reject_invalid_arguments_without_simulation(setup_report, name, arguments, error):
    _, _, provider, report = setup_report
    tools = PlanningTools(report, provider, PlanningRequest(message="测试工具"))
    with patch.object(provider, "walking_matrix", wraps=provider.walking_matrix) as walking:
        result = asyncio.run(tools.execute(name, arguments, "invalid"))
        assert error in result["error"]
        assert result["evidence_refs"] == []
        assert walking.call_count == 0
    assert tools.trace[0]["status"] == "failed"
    assert not tools.simulations


def test_selected_map_point_runs_once_and_second_simulation_is_blocked(setup_report):
    _, _, provider, report = setup_report
    tools = PlanningTools(
        report, provider, PlanningRequest(message="模拟", selected_location={"lng": 113.5, "lat": 23.1})
    )

    async def run():
        first = await tools.execute(
            "simulate_facility", {"category": "market", "location_id": "selected_map_point"}, "one"
        )
        second = await tools.execute(
            "simulate_facility", {"category": "market", "location_id": "selected_map_point"}, "two"
        )
        return first, second

    first, second = asyncio.run(run())
    assert first["simulation"]["delta"]["category_score"] > 0
    assert "已经尝试" in second["error"]
    assert len(tools.simulations) == 1
    assert tools.simulations[0]["hypothetical_facility"]["lng"] == 113.5


@pytest.mark.parametrize(
    "final",
    [
        answer("改善非常明显。", [{"type": "simulation", "id": "invented"}]),
        answer("类别评分增加99分。", [{"type": "report", "id": "irrelevant"}]),
        answer("评分增加九十九分。", []),
    ],
)
def test_fabricated_claims_degrade_to_actual_results(setup_report, final):
    app, client, _, report = setup_report
    app.state.llm_provider = ScriptedModel([call("query_facilities", {"category": "market"}), final])
    result = client.post(f"/api/reports/{report['report_id']}/ai/plan", json={"message": "查询菜市场"}).json()
    assert result["mode"] == "tool_rules_degraded"
    assert result["tool_calls"][0]["status"] == "completed"
    assert "99" not in result["summary"]
    assert "invented" not in {item["id"] for item in result["evidence_refs"]}
    assert "证据校验" in result["data_quality_notice"]


def test_model_failure_after_simulation_keeps_computed_result_without_rerun(setup_report):
    app, client, provider, report = setup_report
    app.state.llm_provider = ScriptedModel(
        [
            call("simulate_facility", {"category": "market", "location_id": "selected_map_point"}),
            RuntimeError("network down with secret"),
        ]
    )
    with patch.object(provider, "walking_matrix", wraps=provider.walking_matrix) as walking:
        result = client.post(
            f"/api/reports/{report['report_id']}/ai/plan",
            json={
                "message": "模拟新增菜市场",
                "selected_location": {"lng": 113.5, "lat": 23.1},
            },
        ).json()
        assert walking.call_count > 0
    assert result["mode"] == "tool_rules_degraded"
    assert len(result["simulations"]) == 1
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "simulate_facility"
    assert "secret" not in json.dumps(result)


def test_call_and_round_budgets_preserve_completed_tools(setup_report):
    _, _, provider, report = setup_report
    model = ScriptedModel([call("query_facilities", {}, str(index)) for index in range(5)])
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询设施")))
    assert result["mode"] == "tool_rules_degraded"
    assert len(result["tool_calls"]) == 5
    assert "轮次达到上限" in result["data_quality_notice"]
    excessive = call("query_facilities", {})
    excessive["tool_calls"] *= 7
    result = asyncio.run(
        run_planning_assistant(ScriptedModel([excessive]), provider, report, PlanningRequest(message="查询设施"))
    )
    assert result["mode"] == "tool_rules_degraded"
    assert len(result["tool_calls"]) <= 6


def test_timeout_returns_failure_without_claiming_completion(setup_report, monkeypatch):
    _, _, provider, report = setup_report
    monkeypatch.setattr("app.planning_assistant.REQUEST_TIMEOUT_SECONDS", 0.01)

    class SlowModel(ScriptedModel):
        async def generate_tools(self, **kwargs):
            await asyncio.sleep(1)

    result = asyncio.run(
        run_planning_assistant(SlowModel([]), provider, report, PlanningRequest(message="模拟新增菜市场"))
    )
    assert result["mode"] == "tool_rules_degraded"
    assert result["simulations"] == []
    assert result["tool_calls"] == []
    assert "超时" in result["data_quality_notice"]
    assert "已完成" not in result["summary"]


def test_rules_mode_and_request_validation(setup_report):
    _, client, _, report = setup_report
    url = f"/api/reports/{report['report_id']}/ai/plan"
    result = client.post(url, json={"message": "查询菜市场盲区，再模拟新增菜市场"}).json()
    assert result["mode"] == "tool_rules"
    assert "模型未启用" in result["data_quality_notice"]
    assert result["simulations"]
    for payload in [
        {"message": " "},
        {"message": "x" * 1001},
        {"message": "查询", "grid_id": "unknown"},
        {"message": "模拟", "selected_location": {"lng": 0, "lat": 0}},
        {"message": "模拟", "selected_location": {"lng": 113.6, "lat": 23.1}},
        {"message": "查询", "previous": {"fake": "data"}},
    ]:
        assert client.post(url, json=payload).status_code == 422
    assert client.post("/api/reports/missing/ai/plan", json={"message": "查询"}).status_code == 404


def test_native_transport_preserves_function_call_messages():
    settings = LLMSettings(
        enabled=True,
        provider="openai_compatible",
        base_url="https://example.test/v1",
        api_key="secret",
        model="test",
        timeout_seconds=3,
        max_tokens=500,
        max_concurrency=1,
        max_retries=0,
        retry_base_seconds=0.1,
    )
    provider = OpenAICompatibleProvider(settings)
    message = call("query_facilities", {})
    response = MagicMock()
    response.json.return_value = {"choices": [{"message": message}]}
    messages = [{"role": "tool", "tool_call_id": "previous", "content": "{}"}]

    async def run():
        with patch.object(provider._client, "post", new_callable=AsyncMock, return_value=response) as post:
            result = await provider.generate_tools(messages=messages, tools=[{"type": "function"}])
            body = post.call_args.kwargs["json"]
            assert body["messages"] == messages
            assert body["parallel_tool_calls"] is False
            assert body["tool_choice"] == "auto"
            assert "response_format" not in body
            assert result == message
        await provider.close()

    asyncio.run(run())


def test_repeated_followups_keep_bounded_server_tool_evidence(setup_report):
    app, client, _, report = setup_report
    url = f"/api/reports/{report['report_id']}/ai/plan"
    first = client.post(url, json={"message": "查询菜市场"}).json()

    def followup(messages):
        context = json.loads(messages[1]["content"])["previous_turn"]
        assert context["tool_results"][0]["items"]
        assert len(context["tool_results"]) <= 6
        return answer("请继续核验网格可达性。", [first["evidence_refs"][0]])

    app.state.llm_provider = ScriptedModel([followup, followup])
    second = client.post(url, json={"message": "为什么？", "previous_turn_id": first["id"]}).json()
    third = client.post(url, json={"message": "再解释一下", "previous_turn_id": second["id"]}).json()
    assert third["mode"] == "llm_tools"
    assert third["planning_context"]["tool_results"] == first["planning_context"]["tool_results"]


def test_provider_llm_error_never_exposes_credentials(setup_report):
    app, client, _, report = setup_report
    app.state.llm_provider = ScriptedModel([LLMError("Authorization failed: sk-private-value")])
    result = client.post(f"/api/reports/{report['report_id']}/ai/plan", json={"message": "查询菜市场"}).json()
    assert result["mode"] == "tool_rules_degraded"
    assert "sk-private" not in json.dumps(result)
    assert "模型服务暂不可用" in result["data_quality_notice"]


def test_simulation_timeout_records_failure_without_result(setup_report, monkeypatch):
    _, _, provider, report = setup_report
    monkeypatch.setattr("app.planning_assistant.REQUEST_TIMEOUT_SECONDS", 0.01)
    model = ScriptedModel([call("simulate_facility", {"category": "market", "location_id": "selected_map_point"})])

    async def slow_simulation(*args, **kwargs):
        await asyncio.sleep(1)

    with patch("app.planning_assistant.ReportSimulationService.run", side_effect=slow_simulation):
        result = asyncio.run(
            run_planning_assistant(
                model,
                provider,
                report,
                PlanningRequest(message="模拟菜市场", selected_location={"lng": 113.5, "lat": 23.1}),
            )
        )
    assert result["simulations"] == []
    assert result["tool_calls"][0]["status"] == "failed"
    assert "超时" in result["tool_calls"][0]["error"]
    assert "已完成" not in result["summary"]


def test_shared_json_adapter_retries_invalid_json():
    settings = LLMSettings(True, "openai_compatible", "https://example.test/v1", "secret", "test", 3, 500, 1, 1, 0.1)
    provider = OpenAICompatibleProvider(settings)
    invalid, valid = MagicMock(), MagicMock()
    invalid.json.return_value = {"choices": [{"message": {"content": "invalid JSON"}}]}
    valid.json.return_value = {"choices": [{"message": {"content": '{"summary":"可用结果"}'}}]}

    async def run():
        with patch.object(provider._client, "post", new_callable=AsyncMock, side_effect=[invalid, valid]) as post:
            result = await provider.generate(system="返回 JSON", user="查询")
            assert result == {"summary": "可用结果"}
            assert post.call_count == 2
        await provider.close()

    asyncio.run(run())
