"""公共对话实际服务集成，覆盖审核、澄清、计划与恢复的完整用户路径。"""

import copy
import itertools

import pytest
from fastapi.testclient import TestClient
from test_geospatial_report import ContractProvider
from test_workspaces import make_workspace

from app.main import create_app
from app.maps.provider import LocationResult, WalkingResult
from app.mock_data import CENTER
from app.schemas import AnalyzeRequest


def speaker(client, workspace):
    sequence = itertools.count()

    def say(message, **kwargs):
        current = client.get(f"/api/workspaces/{workspace['id']}").json()
        response = client.post(
            f"/api/workspaces/{workspace['id']}/messages",
            json={
                "message": message,
                "request_id": f"turn-{next(sequence)}",
                "expected_revision": current["revision"],
                **kwargs,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    return say


def bind_report(client, workspace):
    task = client.post("/api/analyze", json={"mode": "demo", "categories": ["pharmacy"]}).json()
    report = client.get(f"/api/report/{task['id']}").json()
    response = client.post(
        f"/api/workspaces/{workspace['id']}/state",
        json={
            "expected_revision": workspace["revision"],
            "state": {**workspace["state"], "report_id": report["report_id"]},
        },
    )
    assert response.status_code == 200, response.text
    return report


def confirm(say, proposal):
    assert proposal["status"] == "awaiting_confirmation", proposal.get("answer", proposal)
    result = say("确认", confirm_token=proposal["pending"]["token"])
    assert result["status"] == "completed", result
    return result


@pytest.mark.parametrize(
    ("message", "export_format", "coordinate_system"),
    [
        ("导出标准GeoJSON", "geojson-wgs84", "WGS84"),
        ("下载WGS84 GeoJSON", "geojson-wgs84", "WGS84"),
        ("导出GeoJSON", "geojson", "BD-09"),
    ],
)
def test_conversation_export_download_preserves_report_and_uses_requested_coordinates(
    tmp_path, message, export_format, coordinate_system
):
    class ValidGeometryProvider(ContractProvider):
        async def walking_matrix(self, origins, destinations):
            return [
                [
                    WalkingResult(origin, destination, True, 400, 300, "real_api", "fixture")
                    for destination in destinations
                ]
                for origin in origins
            ]

    with TestClient(
        create_app(provider=ValidGeometryProvider(), database_path=tmp_path / "export-dialogue.db")
    ) as client:
        workspace = make_workspace(client)
        report = bind_report(client, workspace)
        say = speaker(client, workspace)
        response = confirm(say, say(message))
        export = next(action for action in response["actions"] if action["type"] == "download_report")
        assert export["format"] == export_format
        assert export["report_id"] == report["report_id"]
        downloaded = client.get(f"/api/reports/{report['report_id']}/exports/{export['format']}")
        assert downloaded.status_code == 200
        assert downloaded.headers["x-coordinate-system"] == coordinate_system
        assert downloaded.json()["coordinate_system"] == coordinate_system
        assert client.get(f"/api/reports/{report['report_id']}").json() == report


def test_conversation_governance_review_and_recompute_are_auditable_and_immutable(tmp_path):
    with TestClient(create_app(provider=ContractProvider(), database_path=tmp_path / "governance.db")) as client:
        workspace = make_workspace(client)
        report = bind_report(client, workspace)
        original = copy.deepcopy(report)
        say = speaker(client, workspace)
        review = confirm(say, say("生成设施语义审核建议"))["semantic_review"]
        assert review["category_proposals"]
        listed = say("查看审核目录")
        assert "第1个分类建议" in listed["answer"]
        assert say("接受第一个分类建议")["status"] == "failed"
        decided = confirm(say, say("修正第一个分类建议为菜市场"))
        assert decided["governance_state"]["catalog_version"] == 2
        observed = say("居民留言：该设施疑似关闭")
        assert observed["observation"]["status"] == "pending_human_review"
        missing = say("接受第一个居民观察")
        assert missing["status"] == "failed"
        assert "设施标识" in missing["answer"]
        catalog = client.get(f"/api/reports/{report['report_id']}/governance").json()["catalog"]
        facility_id = catalog["records"][0]["id"]
        accepted = confirm(say, say(f"接受第一个居民观察，设施ID {facility_id}"))
        assert accepted["governance_state"]["catalog_version"] == 3
        recalculated = confirm(say, say("按审核目录重算"))
        assert recalculated["recomputation"]["report_id"] != report["report_id"]
        assert client.get(f"/api/reports/{report['report_id']}").json() == original
        role = say("查看居民报告")
        assert role["role_report"]["audience"] == "resident"


def test_address_history_directions_layers_and_multi_step_export_survive_restart(tmp_path):
    class Locations(ContractProvider):
        async def geocode(self, address, city):
            return [
                LocationResult(CENTER["lng"], CENTER["lat"], "候选一"),
                LocationResult(CENTER["lng"] + 0.001, CENTER["lat"], "候选二"),
            ]

    database = tmp_path / "plan.db"
    with TestClient(create_app(provider=Locations(), database_path=database)) as client:
        workspace = make_workspace(client)
        say = speaker(client, workspace)
        assert say("地址是沙涌长盛花园")["actions"][-1]["type"] == "show_address_candidates"
        assert say("选择第二个地址")["actions"][0]["candidate"]["address"] == "候选二"
        client.post("/api/analyze", json={"mode": "demo", "categories": ["pharmacy"]})
        client.post("/api/analyze", json={"mode": "demo", "minutes": 10, "categories": ["pharmacy"]})
        history = say("历史报告")
        second_id = history["actions"][0]["items"][1]["report_id"]
        assert say("打开第二份历史报告")["actions"][0]["report_id"] == second_id
        planned = say("只看稀缺图层然后聚焦东南角然后导出JSON报告")
        assert planned["remaining_steps"] == 2
        assert planned["actions"][-1]["layers"]["scarcity"] is True
        focus = say("继续")
        assert focus["actions"][0]["type"] == "focus_grid"
        assert focus["remaining_steps"] == 1
    with TestClient(create_app(provider=Locations(), database_path=database)) as client:
        say = speaker(client, workspace)
        # 换请求ID前缀，避免跨进程重复标识触发预期的幂等冲突。
        current = client.get(f"/api/workspaces/{workspace['id']}").json()
        proposal = client.post(
            f"/api/workspaces/{workspace['id']}/messages",
            json={"message": "继续", "request_id": "restarted-export", "expected_revision": current["revision"]},
        ).json()
        current = client.get(f"/api/workspaces/{workspace['id']}").json()
        exported = client.post(
            f"/api/workspaces/{workspace['id']}/messages",
            json={
                "message": "确认",
                "request_id": "restarted-confirm",
                "expected_revision": current["revision"],
                "confirm_token": proposal["pending"]["token"],
            },
        ).json()
        assert exported["status"] == "completed", exported
        assert exported["actions"][0]["format"] == "json"
        assert exported["remaining_steps"] == 0


def test_constraints_clarify_then_resume_without_relaxing_budget(tmp_path):
    with TestClient(create_app(provider=ContractProvider(), database_path=tmp_path / "clarify.db")) as client:
        workspace = make_workspace(client)
        report = bind_report(client, workspace)
        say = speaker(client, workspace)
        result = say("覆盖优化，预算100元；只考虑parcel-a；必须选parcel-a；最多1家药店")
        assert result["status"] == "awaiting_clarification", result
        candidate = {
            "id": "parcel-a",
            "category": "pharmacy",
            "lng": CENTER["lng"],
            "lat": CENTER["lat"],
            "cost": 80,
            "source": "核验台账",
            "verified": True,
        }
        assert (
            client.post(
                f"/api/reports/{report['report_id']}/planning/candidates", json={"candidates": [candidate]}
            ).status_code
            == 200
        )
        result = confirm(say, say("继续覆盖优化"))
        assert result["optimization"]["constraints"]["budget"] == 100
        assert result["optimization"]["selected_candidate_ids"] == ["parcel-a"]
        assert result["optimization"]["constraint_violations"] == 0


def test_progress_cancel_retry_are_available_in_conversation(tmp_path):
    with TestClient(create_app(provider=ContractProvider(), database_path=tmp_path / "cancel.db")) as client:
        workspace = make_workspace(client)
        task = client.app.state.task_repository.create(
            AnalyzeRequest(mode="demo", categories=["pharmacy"]).model_dump()
        )
        bound = client.post(
            f"/api/workspaces/{workspace['id']}/state",
            json={"expected_revision": 0, "state": {**workspace["state"], "analysis_task_id": task["id"]}},
        )
        assert bound.status_code == 200
        say = speaker(client, workspace)
        assert say("当前任务进度")["task"]["status"] == "queued"
        assert say("取消体检")["task"]["status"] == "cancelled"
        retried = confirm(say, say("重试体检"))
        assert retried["task"]["id"] != task["id"]
        assert client.get(f"/api/analyze/{retried['task']['id']}").json()["status"] == "completed"
