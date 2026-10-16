import asyncio
import os
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai_assistant import build_ai_interpretation
from app.llm import LLMSettings, OpenAICompatibleProvider, enhance_interpretation, llm_configuration


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


def test_structured_llm_selects_typed_facts_and_server_renders_values():
    report = report_fixture()
    deterministic = build_ai_interpretation(report)
    result = asyncio.run(
        enhance_interpretation(
            FakeProvider(
                {
                    "claims": [
                        {
                            "report_id": "report-llm-1",
                            "type": "category_score",
                            "id": "market",
                            "slot": "score",
                        }
                    ],
                    "recommendation_indexes": [0],
                    "uncertainty_codes": ["field_verification"],
                }
            ),
            report,
            deterministic,
        )
    )

    assert result["mode"] == "llm_structured"
    assert result["model"] == "test-model"
    assert result["summary"] == "菜市场评分：54。"
    assert result["claims"][0]["value"] == 54
    assert result["recommendations"] == deterministic["recommendations"]
    assert result["claims"][0]["report_id"] == report["report_id"]


@pytest.mark.parametrize(
    "model_result",
    [
        {"summary": "本次总分99，药店步行1分钟", "evidence_refs": [{"type": "report", "id": "report-llm-1"}]},
        {"summary": "本社区已经具备医院，选址完全可行。", "evidence_refs": [{"type": "report", "id": "report-llm-1"}]},
        {"claims": [{"report_id": "other-report", "type": "report", "id": "report-llm-1", "slot": "score"}]},
        {"claims": [{"report_id": "report-llm-1", "type": "report", "id": "report-llm-1", "slot": "walk_minutes"}]},
        {"claims": [{"report_id": "report-llm-1", "type": "facility", "id": "invented", "slot": "walk_minutes"}]},
        {
            "claims": [
                {"report_id": "report-llm-1", "type": "report", "id": "report-llm-1", "slot": "score", "value": 99}
            ]
        },
        {
            "claims": [{"report_id": "report-llm-1", "type": "report", "id": "report-llm-1", "slot": "score"}],
            "recommendation_indexes": [True],
        },
        {
            "claims": [{"report_id": "report-llm-1", "type": "report", "id": "report-llm-1", "slot": "score"}],
            "uncertainty_codes": ["已有医院"],
        },
    ],
)
def test_fabricated_text_or_invalid_claim_falls_back_without_mutating_report(model_result):
    report = report_fixture()
    original = deepcopy(report)
    deterministic = build_ai_interpretation(report)
    result = asyncio.run(enhance_interpretation(FakeProvider(model_result), report, deterministic))
    assert result["mode"] == "rule_template_degraded"
    assert result["summary"] == deterministic["summary"]
    assert result["claims"] == deterministic["claims"]
    assert report == original


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


def test_llm_configuration_does_not_expose_api_key():
    with patch.dict(
        os.environ,
        {
            "LLM_ENABLED": "true",
            "LLM_API_KEY": "secret-value",
            "LLM_MODEL": "test-model",
            "LLM_BASE_URL": "https://example.test/v1",
        },
        clear=False,
    ):
        config = llm_configuration()

    assert config["available"] is True
    assert config["model"] == "test-model"
    assert "secret-value" not in str(config)


def test_llm_provider_retries_and_records_failure():
    settings = LLMSettings(
        enabled=True,
        provider="openai_compatible",
        base_url="https://example.test/v1",
        api_key="secret",
        model="test-model",
        timeout_seconds=3,
        max_tokens=256,
        max_concurrency=1,
        max_retries=1,
        retry_base_seconds=0.01,
    )
    provider = OpenAICompatibleProvider(settings)
    response = MagicMock()
    response.raise_for_status.side_effect = RuntimeError("bad response")

    async def run():
        with patch.object(provider._client, "post", new_callable=AsyncMock, return_value=response):
            try:
                await provider.generate(system="system", user="user")
            except Exception as exc:
                assert "模型调用或解析失败" in str(exc)
        health = provider.health()
        await provider.close()
        return health

    health = asyncio.run(run())
    assert health["calls"] == 1
    assert health["failures"] == 1
