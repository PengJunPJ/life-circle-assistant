"""真实任务编排跨应用实例的检查点、预算及取消恢复契约。"""

import asyncio

import httpx
import pytest
from test_geospatial_report import ContractProvider

from app.main import create_app, execute_analysis_task
from app.schemas import AnalyzeRequest


class ProcessInterrupted(BaseException):
    """模拟进程离开；不能被业务层的一般 Exception 处理吞掉。"""


class CountingContractProvider(ContractProvider):
    def __init__(self, *, truncated=False):
        super().__init__(truncated=truncated)
        self.reverse_calls = 0
        self.search_calls = 0
        self.walking_calls = 0

    async def reverse_geocode(self, lng, lat):
        self.reverse_calls += 1
        return await super().reverse_geocode(lng, lat)

    async def search_facilities(self, category, center, radius_m):
        self.search_calls += 1
        return await super().search_facilities(category, center, radius_m)

    async def walking_matrix(self, origins, destinations):
        self.walking_calls += 1
        return await super().walking_matrix(origins, destinations)


def analysis_request():
    return AnalyzeRequest(lng=113.4872, lat=23.1068, categories=["market"], minutes=15, mode="demo")


async def finished_task(client, task_id):
    # 等待异步 lifespan 恢复任务，使用有界等待而非依赖固定完成时延。
    async with asyncio.timeout(5):
        while True:
            response = await client.get(f"/api/analyze/{task_id}")
            assert response.status_code == 200
            task = response.json()
            if task["status"] in {"completed", "failed", "cancelled"}:
                return task
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("truncated", "adapter_budget"),
    [(False, 64), (True, 64), (False, 2)],
    ids=["complete-inventory", "truncated-metadata", "exhausted-original-budget"],
)
async def test_new_application_recovers_successful_calls_metadata_and_original_budget(
    tmp_path, monkeypatch, truncated, adapter_budget
):
    monkeypatch.setenv("LIFE_CIRCLE_SEED_WALKING_CACHE", "0")
    database_path = tmp_path / "checkpoint-recovery.db"
    original_provider = CountingContractProvider(truncated=truncated)
    original = create_app(original_provider, database_path)
    request = analysis_request()
    task = original.state.task_repository.create(request.model_dump())
    task_id = task["id"]
    budget = {"map_adapter_calls": adapter_budget, "route_pairs": 2000}
    original.state.execution_repository.ensure(task_id, "analysis_task", budget)
    update_stage = original.state.task_repository.update_stage

    def interrupt_before_walking(identifier, code, label, progress):
        if code == "walking_calculation":
            raise ProcessInterrupted()
        update_stage(identifier, code, label, progress)

    monkeypatch.setattr(original.state.task_repository, "update_stage", interrupt_before_walking)
    async with original.router.lifespan_context(original):
        with pytest.raises(ProcessInterrupted):
            await execute_analysis_task(original, task_id, request)

    assert original.state.task_repository.get(task_id)["status"] == "running"
    assert original.state.execution_repository.uncertain(task_id) == []
    assert original_provider.reverse_calls == original_provider.search_calls == 1
    assert original_provider.walking_calls == 0
    before = original.state.execution_repository.get(task_id)
    assert before["usage"]["map_adapter_calls"] == 2

    # 一个全新提供方自称未截断；恢复必须保留之前保存的截断元数据。
    recovered_provider = CountingContractProvider(truncated=False)
    recovered = create_app(recovered_provider, database_path)
    assert [item["id"] for item in recovered.state.resumable_tasks] == [task_id]
    async with recovered.router.lifespan_context(recovered):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=recovered), base_url="http://test") as client:
            completed = await finished_task(client, task_id)
            ledger_response = await client.get(f"/api/executions/{task_id}")
            assert ledger_response.status_code == 200
            ledger = ledger_response.json()
            uncertain = await client.get(f"/api/executions/{task_id}/uncertain-checkpoints")
            assert uncertain.json() == {"items": []}

    assert completed["status"] == "completed"
    assert completed["id"] == task_id
    assert recovered_provider.reverse_calls == recovered_provider.search_calls == 0
    report = completed["result"]
    assert report["facility_search"][0]["truncated"] is truncated
    assert ledger["status"] == "completed"
    assert ledger["budget"] == budget
    assert ledger["created_at"] == before["created_at"]
    assert ledger["usage"]["checkpoint_hits"] >= 2
    assert ledger["usage"]["map_adapter_calls"] == 2 + recovered_provider.walking_calls
    assert report["execution_ledger"]["usage"] == ledger["usage"]
    if truncated or adapter_budget == 2:
        assert report["summary"]["score"] is None
        assert {feature["properties"]["kind"] for feature in report["service_areas"]["features"]} == {"unknown"}
        assert all(group["properties"]["gap_kind"] == "scarcity" for group in report["gap_groups"]["features"])
    else:
        assert report["summary"]["score"] is not None
    if truncated:
        assert report["gap_groups"]["features"] == []
        assert any(
            failure["code"] == "facility_search_truncated" for failure in report["data_quality"]["partial_failures"]
        )
        assert all(feature["properties"]["nearby_scarcity"] is None for feature in report["service_areas"]["features"])
    if adapter_budget == 2:
        assert recovered_provider.walking_calls == 0
        assert ledger["usage"]["map_adapter_calls"] == 2
    else:
        assert recovered_provider.walking_calls > 0


class WaitingContractProvider(CountingContractProvider):
    def __init__(self):
        super().__init__()
        self.request_started = asyncio.Event()
        self.allow_response = asyncio.Event()

    async def reverse_geocode(self, lng, lat):
        self.reverse_calls += 1
        self.request_started.set()
        await self.allow_response.wait()
        return await ContractProvider.reverse_geocode(self, lng, lat)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["user_cancel", "application_shutdown"])
async def test_cancelled_user_task_stays_cancelled_and_shutdown_does_not_replay_unresolved_call(
    tmp_path, monkeypatch, reason
):
    monkeypatch.setenv("LIFE_CIRCLE_SEED_WALKING_CACHE", "0")
    database_path = tmp_path / "cancel-recovery.db"
    provider = WaitingContractProvider()
    original = create_app(provider, database_path)
    request = analysis_request()
    task_id = original.state.task_repository.create(request.model_dump())["id"]
    async with original.router.lifespan_context(original):
        worker = asyncio.create_task(execute_analysis_task(original, task_id, request))
        await asyncio.wait_for(provider.request_started.wait(), timeout=5)
        if reason == "user_cancel":
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=original), base_url="http://test") as client:
                response = await client.post(f"/api/analyze/{task_id}/cancel")
                assert response.status_code == 200
                assert response.json()["status"] == "cancelled"
            await asyncio.wait_for(worker, timeout=5)
        # 应用停机由真实 lifespan 取消仍等待提供方响应的工作协程。

    assert worker.done()
    assert provider.reverse_calls == 1
    ledger_before = original.state.execution_repository.get(task_id)
    assert ledger_before["status"] == ("cancelled" if reason == "user_cancel" else "interrupted")
    assert len(original.state.execution_repository.uncertain(task_id)) == 1

    replacement_provider = CountingContractProvider()
    replacement = create_app(replacement_provider, database_path)
    assert len(replacement.state.resumable_tasks) == (0 if reason == "user_cancel" else 1)
    async with replacement.router.lifespan_context(replacement):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=replacement), base_url="http://test") as client:
            recovered = await finished_task(client, task_id)
            ledger = (await client.get(f"/api/executions/{task_id}")).json()
            if reason == "user_cancel":
                assert recovered["status"] == ledger["status"] == "cancelled"
            else:
                assert recovered["status"] == ledger["status"] == "failed"
                assert "计费状态未决" in recovered["error"]
            assert recovered["report_id"] is None
            assert ledger["usage"]["map_adapter_calls"] == 1
            assert len((await client.get(f"/api/executions/{task_id}/uncertain-checkpoints")).json()["items"]) == 1

    assert (
        replacement_provider.reverse_calls
        == replacement_provider.search_calls
        == replacement_provider.walking_calls
        == 0
    )
