from __future__ import annotations

import asyncio
import copy
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from test_simulations import SimulationFixtureProvider

from app.analysis.simulations import ReportSimulationService
from app.llm import LLMError, LLMSettings, OpenAICompatibleProvider
from app.main import create_app
from app.planning_assistant import PlanningTools, _rules, run_planning_assistant
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
            },
            ensure_ascii=False,
        ),
    }


class ScriptedModel:
    model = "scripted-tool-model"

    def __init__(self, script):
        self.script = list(script)
        self.messages = []
        self.json_messages = []

    async def generate_tools(self, *, messages, tools):
        self.messages.append(copy.deepcopy(messages))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step(messages) if callable(step) else step

    async def generate(self, *, system, user):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        self.messages.append(copy.deepcopy(messages))
        self.json_messages.append(copy.deepcopy(messages))
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


@pytest.mark.parametrize("prompt_version", ["tool-planner-v1", "tool-planner-v2"])
def test_followup_uses_server_saved_context_and_rejects_foreign_turn(setup_report, prompt_version):
    app, client, _, report = setup_report
    url = f"/api/reports/{report['report_id']}/ai/plan"
    previous = client.post(url, json={"message": "查询菜市场"}).json()
    previous.pop("id")
    previous = app.state.report_repository.save_ai_interpretation(
        report["report_id"], {**previous, "prompt_version": prompt_version}, question="查询菜市场"
    )

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


def test_compare_planning_options_executes_independent_simulations_and_ranks(setup_report):
    app, client, provider, report = setup_report
    candidates = {
        recommendation["category"]: recommendation["candidate_locations"][0]["id"]
        for recommendation in report["recommendations"]
        if recommendation.get("candidate_locations")
    }
    model = ScriptedModel(
        [
            call(
                "compare_planning_options",
                {
                    "goal": "improve_overall_score",
                    "options": [
                        {"category": "market", "location_id": candidates["market"]},
                        {"category": "school", "location_id": candidates["school"]},
                    ],
                },
                "compare",
            ),
            lambda messages: answer("这些独立位置可作为进一步核验的候选。", last_result(messages)["evidence_refs"]),
        ]
    )
    app.state.llm_provider = model
    with patch.object(provider, "walking_matrix", wraps=provider.walking_matrix) as walking:
        result = client.post(
            f"/api/reports/{report['report_id']}/ai/plan",
            json={"message": "比较新增菜市场与小学，优先提高综合指数"},
        ).json()
    assert walking.call_count >= 2
    comparison = result["comparisons"][0]
    assert len(comparison["options"]) == 2
    assert all(option["eligible"] for option in comparison["options"]), comparison["options"]
    assert all(option["rank"] in (1, 2) for option in comparison["options"]), comparison["options"]
    baseline_scores = {item["category"]: item["score"] for item in report["category_scores"]}
    assert all(
        option["simulation"]["before"]["category_score"] == baseline_scores[option["category"]]
        for option in comparison["options"]
    )
    assert len(result["simulations"]) == 2
    assert client.get(f"/api/reports/{report['report_id']}").json() == report


def test_duplicate_comparison_options_are_rejected_before_route_calls(setup_report):
    _, _, provider, report = setup_report
    candidate = next(rec for rec in report["recommendations"] if rec["category"] == "market")["candidate_locations"][0]
    tools = PlanningTools(report, provider, PlanningRequest(message="比较", comparison_goal="increase_coverage"))
    with patch.object(provider, "walking_matrix", wraps=provider.walking_matrix) as walking:
        result = asyncio.run(
            tools.execute(
                "compare_planning_options",
                {
                    "goal": "increase_coverage",
                    "options": [
                        {"category": "market", "location_id": candidate["id"]},
                        {"category": "market", "location_id": candidate["id"]},
                    ],
                },
                "duplicate",
            )
        )
    assert "不可重复" in result["error"]
    assert walking.call_count == 0
    assert not tools.simulations


def test_rules_comparison_uses_multiple_candidates_for_a_single_category():
    candidates = [
        {"id": f"candidate-{index}", "category": "market", "lng": 113.5 + index / 1000, "lat": 23.1}
        for index in range(3)
    ]
    tools = MagicMock()
    tools.request = PlanningRequest(message="比较方案", comparison_goal="increase_coverage")
    tools.categories = ["market"]
    tools.features = []

    async def execute(name, arguments, call_id):
        if name == "get_planning_candidates":
            return {"items": candidates}
        if name == "compare_planning_options":
            tools.comparison_arguments = arguments
        return {}

    tools.execute = AsyncMock(side_effect=execute)
    asyncio.run(_rules(tools, None))

    options = tools.comparison_arguments["options"]
    assert len(options) == 3
    assert {item["location_id"] for item in options} == {item["id"] for item in candidates}


def test_timed_out_comparison_keeps_completed_options_and_marks_pending(setup_report):
    _, _, provider, report = setup_report
    candidates = {
        recommendation["category"]: recommendation["candidate_locations"][0]["id"]
        for recommendation in report["recommendations"]
        if recommendation.get("candidate_locations")
    }
    tools = PlanningTools(report, provider, PlanningRequest(message="比较方案"))
    original_run = ReportSimulationService.run
    calls = 0

    async def delayed_run(service, source_report, simulation_request):
        nonlocal calls
        calls += 1
        if calls > 1:
            await asyncio.sleep(0.1)
        return await original_run(service, source_report, simulation_request)

    async def invoke():
        async with asyncio.timeout(0.05):
            await tools.execute(
                "compare_planning_options",
                {
                    "goal": "improve_overall_score",
                    "options": [
                        {"category": "market", "location_id": candidates["market"]},
                        {"category": "school", "location_id": candidates["school"]},
                    ],
                },
                "timeout",
            )

    with patch.object(ReportSimulationService, "run", delayed_run), pytest.raises(TimeoutError):
        asyncio.run(invoke())
    partial = tools.trace[0]["result"]["comparison"]
    assert partial["options"][0]["status"] == "completed"
    assert partial["options"][1]["status"] == "pending"
    assert len(tools.simulations) == 1


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


@pytest.mark.parametrize("language", ["json", "JSON", ""])
def test_fenced_final_answer_keeps_model_mode_and_canonical_evidence(setup_report, language):
    _, _, provider, report = setup_report

    def final(messages):
        result = last_result(messages)
        response = answer("菜市场服务仍需结合现场通行条件核验。", result["evidence_refs"])
        response["content"] = f" \n```{language}\n{response['content']}\n```\n "
        return response

    model = ScriptedModel([call("query_facilities", {"category": "market"}), final])
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询菜市场")))

    assert result["mode"] == "llm_tools"
    assert result["evidence_refs"] == result["tool_calls"][0]["result"]["evidence_refs"]
    assert len(result["tool_calls"]) == 1
    assert len(model.messages) == 2
    assert not model.json_messages


@pytest.mark.parametrize("summary", ["匹配到一处菜市场设施。", "匹配到两处菜市场设施。", "步行需要8分钟。"])
def test_numeric_final_answer_is_corrected_once_using_existing_evidence(setup_report, summary):
    _, _, provider, report = setup_report

    def final(messages):
        response = answer(summary, last_result(messages)["evidence_refs"])
        response["content"] = f"```json\n{response['content']}\n```"
        return response

    def corrected(messages):
        context = last_result(messages)
        assert summary in context["answer"]
        assert context["question"] == "查询菜市场"
        assert context["tool_results"][0]["evidence_refs"]
        return {
            "summary": "菜市场服务仍需结合现场通行条件核验。",
            "evidence_refs": context["allowed_evidence_refs"],
            "needs_clarification": False,
        }

    model = ScriptedModel([call("query_facilities", {"category": "market"}), final, corrected])
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询菜市场")))

    assert result["mode"] == "llm_tools"
    assert result["summary"] == " ".join(ref["detail"] for ref in result["evidence_refs"])
    assert all(claim["slot"] == "detail" for claim in result["claims"])
    assert result["evidence_refs"] == result["tool_calls"][0]["result"]["evidence_refs"]
    assert len(result["tool_calls"]) == 1
    assert len(model.messages) == 3
    assert len(model.json_messages) == 1


def test_non_numeric_fabrication_is_replaced_by_server_evidence(setup_report):
    _, _, provider, report = setup_report
    fabricated = "本社区的医院已经获批新址，所有居民均能抵达。"
    model = ScriptedModel(
        [
            call("query_facilities", {"category": "market"}),
            lambda messages: answer(fabricated, last_result(messages)["evidence_refs"]),
        ]
    )
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询菜市场")))
    assert fabricated not in result["summary"]
    assert result["summary"] == " ".join(ref["detail"] for ref in result["evidence_refs"])
    assert result["mode"] == "llm_tools"
    assert result["claims"] and all(item["report_id"] == report["report_id"] for item in result["claims"])


def test_native_final_can_select_exact_fact_slots_without_echoing_values(setup_report):
    _, _, provider, report = setup_report

    def final(messages):
        claim = last_result(messages)["claims"][0]
        return {
            "content": json.dumps(
                {
                    "summary": "核查当前设施证据。",
                    "claims": [{key: claim[key] for key in ("report_id", "type", "id", "slot")}],
                },
                ensure_ascii=False,
            )
        }

    model = ScriptedModel([call("query_facilities", {"category": "market"}), final])
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询菜市场")))
    assert result["mode"] == "llm_tools"
    assert len(result["claims"]) == 1
    assert result["summary"] == result["claims"][0]["text"]


@pytest.mark.parametrize(
    "override",
    [
        {"report_id": "foreign"},
        {"slot": "score"},
        {"value": 99},
        {"id": "invented"},
    ],
)
def test_native_claim_scope_slot_and_value_fabrication_degrade(setup_report, override):
    _, _, provider, report = setup_report

    def final(messages):
        claim = last_result(messages)["claims"][0]
        return {
            "content": json.dumps(
                {
                    "summary": "依据事实回答。",
                    "claims": [{**{key: claim[key] for key in ("report_id", "type", "id", "slot")}, **override}],
                },
                ensure_ascii=False,
            )
        }

    model = ScriptedModel([call("query_facilities", {"category": "market"}), final])
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询菜市场")))
    assert result["mode"] == "tool_rules_degraded"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["status"] == "completed"
    assert result["claims"]


def test_answer_correction_preserves_simulation_without_executing_it_again(setup_report):
    _, _, provider, report = setup_report

    def final(messages):
        return answer("类别评分增加99分。", last_result(messages)["evidence_refs"])

    def corrected(messages):
        context = last_result(messages)
        assert context["tool_results"][0]["simulation"]["delta"]["category_score"] > 0
        return {
            "summary": "候选位置有助于改善菜市场服务，仍需现场核验。",
            "evidence_refs": context["allowed_evidence_refs"],
        }

    model = ScriptedModel(
        [
            call("simulate_facility", {"category": "market", "location_id": "selected_map_point"}),
            final,
            corrected,
        ]
    )
    with patch.object(
        ReportSimulationService, "run", autospec=True, side_effect=ReportSimulationService.run
    ) as simulate:
        result = asyncio.run(
            run_planning_assistant(
                model,
                provider,
                report,
                PlanningRequest(message="模拟新增菜市场", selected_location={"lng": 113.5, "lat": 23.1}),
            )
        )
    assert result["mode"] == "llm_tools"
    assert simulate.call_count == 1
    assert len(result["simulations"]) == 1
    simulation = result["simulations"][0]
    tool_simulation = result["tool_calls"][0]["result"]["simulation"]
    assert simulation["id"] == tool_simulation["id"]
    assert simulation["delta"] == tool_simulation["delta"]
    assert simulation["hypothetical_facility"] == tool_simulation["hypothetical_facility"]
    assert len(result["tool_calls"]) == 1


@pytest.mark.parametrize(
    "repair",
    [
        {"summary": "评分增加九十九分。", "evidence_refs": [], "needs_clarification": True},
        {"summary": "改善很明显。", "evidence_refs": [{"type": "simulation", "id": "invented"}]},
        RuntimeError("provider error with sk-private-value"),
    ],
)
def test_failed_answer_correction_degrades_and_keeps_completed_tools(setup_report, repair):
    _, _, provider, report = setup_report
    model = ScriptedModel(
        [
            call("query_facilities", {"category": "market"}),
            lambda messages: answer("匹配到一处菜市场设施。", last_result(messages)["evidence_refs"]),
            repair,
        ]
    )
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询菜市场")))
    assert result["mode"] == "tool_rules_degraded"
    assert len(model.json_messages) == 1
    assert len(model.messages) == 3
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["status"] == "completed"
    assert result["evidence_refs"] == result["tool_calls"][0]["result"]["evidence_refs"]
    assert "sk-private-value" not in json.dumps(result)
    assert "invented" not in {ref["id"] for ref in result["evidence_refs"]}


def test_fenced_fabricated_evidence_is_not_repaired_or_accepted(setup_report):
    _, _, provider, report = setup_report
    final = answer("匹配到一处菜市场设施。", [{"type": "facility", "id": "invented"}])
    final["content"] = f"```json\n{final['content']}\n```"
    model = ScriptedModel([call("query_facilities", {"category": "market"}), final])
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询菜市场")))
    assert result["mode"] == "tool_rules_degraded"
    assert not model.json_messages
    assert len(result["tool_calls"]) == 1
    assert "invented" not in {ref["id"] for ref in result["evidence_refs"]}


def test_answer_correction_respects_model_round_limit(setup_report):
    _, _, provider, report = setup_report
    model = ScriptedModel(
        [
            *[call("query_facilities", {"category": "market"}, str(index)) for index in range(4)],
            lambda messages: answer("匹配到一处菜市场设施。", last_result(messages)["evidence_refs"]),
        ]
    )
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询菜市场")))
    assert result["mode"] == "tool_rules_degraded"
    assert len(model.messages) == 5
    assert not model.json_messages
    assert len(result["tool_calls"]) == 4
    assert all(item["status"] == "completed" for item in result["tool_calls"])
    assert "轮次达到上限" in result["data_quality_notice"]


def test_answer_correction_timeout_keeps_tools_and_uses_total_request_budget(setup_report, monkeypatch):
    _, _, provider, report = setup_report
    monkeypatch.setattr("app.planning_assistant.REQUEST_TIMEOUT_SECONDS", 0.01)

    class SlowCorrectionModel(ScriptedModel):
        async def generate(self, **kwargs):
            await asyncio.sleep(1)

    model = SlowCorrectionModel(
        [
            call("query_facilities", {"category": "market"}),
            lambda messages: answer("匹配到一处菜市场设施。", last_result(messages)["evidence_refs"]),
        ]
    )
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询菜市场")))
    assert result["mode"] == "tool_rules_degraded"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["status"] == "completed"
    assert result["evidence_refs"] == result["tool_calls"][0]["result"]["evidence_refs"]
    assert "超时" in result["data_quality_notice"]


@pytest.mark.parametrize("template", ["说明：\n```json\n%s\n```", "```json\n%s\n```\n额外说明", "```json\n%s"])
def test_only_complete_json_fence_is_accepted(setup_report, template):
    _, _, provider, report = setup_report

    def final(messages):
        response = answer("菜市场服务仍需现场核验。", last_result(messages)["evidence_refs"])
        response["content"] = template % response["content"]
        return response

    model = ScriptedModel([call("query_facilities", {"category": "market"}), final])
    result = asyncio.run(run_planning_assistant(model, provider, report, PlanningRequest(message="查询菜市场")))
    assert result["mode"] == "tool_rules_degraded"
    assert len(result["tool_calls"]) == 1
    assert not model.json_messages


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
