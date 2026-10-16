import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.analysis_intent import parse_analysis_intent
from app.main import create_app
from app.maps.snapshot import SnapshotMapProvider
from app.schemas import AnalysisIntentDraft, AnalysisIntentRequest


class FakeProvider:
    model = "intent-test-model"

    def __init__(self, result):
        self.result = result
        self.user = ""

    async def generate(self, *, system, user):
        self.user = user
        return self.result


def parse(message, previous=None, provider=None):
    return asyncio.run(parse_analysis_intent(AnalysisIntentRequest(message=message, previous=previous), provider))


def test_rules_extract_location_time_and_multiple_interests():
    result = parse("帮我看看沙涌长盛花园，步行十分钟，老人买药和看病是否方便，正式分析")
    assert result.parser == "rules"
    assert result.draft.address == "沙涌长盛花园"
    assert result.draft.minutes == 10
    assert result.draft.mode == "analysis"
    assert set(result.draft.categories) == {"elderly", "pharmacy", "medical"}
    assert not result.missing_fields
    assert not result.draft.defaulted_fields


def test_followup_preserves_location_and_applies_additions_and_exclusions():
    first = parse("体检红山街道海韵东路，关注买菜和买药")
    assert first.draft.address == "红山街道海韵东路"
    second = parse("改为20分钟，加上公园，不要药店", first.draft)
    assert second.draft.address == first.draft.address
    assert second.draft.minutes == 20
    assert second.draft.categories == ["market", "park"]
    assert second.draft.defaulted_fields == ["mode"]


def test_missing_location_asks_followup_without_reusing_default_center():
    first = parse("步行15分钟买药")
    assert first.missing_fields == ["location"]
    assert not first.draft.use_current_center
    second = parse("地址是红山街道海韵东路", first.draft)
    assert second.draft.categories == ["pharmacy"]
    assert not second.missing_fields


@pytest.mark.parametrize("time", ["30分钟", "12分钟", "半小时", "一小时", "15.5分钟"])
def test_unsupported_time_is_never_silently_rounded(time):
    result = parse(f"当前选点，{time}，买菜", provider=FakeProvider({"minutes": 20, "categories": ["market"]}))
    assert result.draft.minutes is None
    assert "minutes" in result.missing_fields


def test_current_center_requires_explicit_user_reference():
    result = parse("当前选点，二十分钟，全面体检")
    assert result.draft.use_current_center
    assert not result.draft.address
    assert len(result.draft.categories) == 7
    assert not result.missing_fields


def test_llm_uses_structured_patch_and_receives_previous_draft():
    previous = AnalysisIntentDraft(address="沙涌长盛花园", categories=["medical"])
    provider = FakeProvider({"minutes": 10, "categories": ["pharmacy", "medical"]})
    result = parse("改成十分钟，关注买药和看病", previous, provider)
    assert result.parser == "llm"
    assert result.model == provider.model
    assert result.draft.address == previous.address
    assert result.draft.minutes == 10
    assert "沙涌长盛花园" in provider.user


def test_llm_accepts_grounded_address_and_rules_keep_explicit_current_selection():
    result = parse(
        "想知道黄埔区沙涌长盛花园买药是否方便",
        provider=FakeProvider(
            {
                "address": "黄埔区沙涌长盛花园",
                "categories": ["pharmacy"],
            }
        ),
    )
    assert result.parser == "llm"
    assert result.draft.address == "黄埔区沙涌长盛花园"
    assert result.draft.categories == ["pharmacy"]
    current = parse("当前选点，20分钟，买药", provider=FakeProvider({"categories": ["pharmacy"]}))
    assert current.parser == "llm"
    assert current.draft.use_current_center
    assert current.draft.minutes == 20
    assert not current.missing_fields


@pytest.mark.parametrize(
    "output",
    [
        {},
        {"address": "凭空生成的社区"},
        {"use_current_center": True},
        {"categories": ["unknown"]},
        {"minutes": 30},
        {"lng": 113.4872, "lat": 23.1068},
    ],
)
def test_invalid_or_ungrounded_model_output_falls_back(output):
    result = parse("沙涌长盛花园，步行15分钟，买药", provider=FakeProvider(output))
    assert result.parser == "rules_degraded"
    assert result.model is None
    assert result.draft.address == "沙涌长盛花园"
    assert result.draft.categories == ["pharmacy"]
    assert "坐标" not in result.draft.model_dump()


def test_model_network_failure_does_not_leak_errors_or_credentials():
    provider = FakeProvider({})
    provider.generate = AsyncMock(side_effect=RuntimeError("private-secret-key"))
    result = parse("当前选点，买菜", provider=provider)
    assert result.parser == "rules_degraded"
    assert "private-secret-key" not in result.model_dump_json()


def test_defaults_are_disclosed_and_empty_categories_need_followup():
    result = parse("地址是红山街道海韵东路")
    assert result.draft.defaulted_fields == ["minutes", "mode", "categories"]
    previous = AnalysisIntentDraft(address="红山街道海韵东路", categories=["pharmacy"])
    result = parse("不要药店", previous)
    assert result.draft.categories == []
    assert result.missing_fields == ["categories"]


@pytest.mark.parametrize("message", [" ", "x" * 1001])
def test_request_rejects_blank_and_oversized_messages(message):
    with pytest.raises(ValidationError):
        AnalysisIntentRequest(message=message)


def test_endpoint_only_prepares_intent_then_existing_analysis_runs_after_confirmation(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    provider = SnapshotMapProvider()
    app = create_app(provider, tmp_path / "intent.db")
    with TestClient(app) as client:
        with patch.object(app.state.task_repository, "create", wraps=app.state.task_repository.create) as create:
            with patch.object(provider, "geocode", wraps=provider.geocode) as geocode:
                response = client.post("/api/analysis/intent", json={"message": "体检沙涌长盛花园，10分钟，买菜和买药"})
                assert response.status_code == 200
                create.assert_not_called()
                geocode.assert_not_called()
            draft = response.json()["draft"]
            location = client.get("/api/geocode", params={"address": draft["address"]}).json()["candidates"][0]
            task = client.post(
                "/api/analyze",
                json={
                    "lng": location["lng"],
                    "lat": location["lat"],
                    "minutes": draft["minutes"],
                    "mode": draft["mode"],
                    "categories": draft["categories"],
                    "center_address": location["address"],
                    "center_selection_method": "address",
                },
            )
            assert task.status_code == 200
            create.assert_called_once()
            completed = client.get(f"/api/analyze/{task.json()['id']}").json()
            assert completed["status"] == "completed"
            assert completed["result"]["parameters"]["minutes"] == 10
            assert completed["result"]["parameters"]["categories"] == ["market", "pharmacy"]
        assert client.post("/api/analysis/intent", json={"message": " "}).status_code == 422
