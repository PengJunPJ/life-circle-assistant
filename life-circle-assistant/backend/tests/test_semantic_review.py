import asyncio
import json
from copy import deepcopy

import pytest

from app.analysis.semantic_review import review_facility_semantics


def records():
    return [
        {"id": "a", "name": "仁和药店", "category": "pharmacy", "address": "海韵路1号", "lng": 113.4, "lat": 23.1},
        {"id": "b", "name": "仁和药房", "category": "pharmacy", "address": "海韵路1号", "lng": 113.4001, "lat": 23.1},
    ]


class Model:
    model = "test-model"

    def __init__(self, result):
        self.result = result
        self.context = None

    async def generate(self, *, system, user):
        self.context = json.loads(user)
        return self.result


def run_review(source=None, provider=None, **kwargs):
    return asyncio.run(
        review_facility_semantics(
            source if source is not None else records(), provider, coordinate_system="BD09", **kwargs
        )
    )


def test_category_and_identity_reviews_are_separate_and_never_apply_changes():
    source = records()
    original = deepcopy(source)
    model = Model(
        {
            "category_proposals": [
                {"record_id": "a", "category": "pharmacy", "confidence": 0.95, "evidence_fields": ["name"]}
            ],
            "entity_proposals": [
                {
                    "left_id": "b",
                    "right_id": "a",
                    "relation": "same_entity",
                    "confidence": 0.98,
                    "evidence_fields": ["name", "address"],
                }
            ],
        }
    )
    review = run_review(source, model)
    assert review["mode"] == "llm_review"
    assert review["apply_policy"] == "human_review_only"
    assert review["category_proposals"][0]["proposed_category"] == "pharmacy"
    assert review["entity_proposals"][0]["relation"] == "same_entity"
    assert review["entity_proposals"][0]["status"] == "pending_human_review"
    assert len(review["records"]) == 2
    assert source == original
    assert "lng" not in model.context["records"][0]
    review["records"][0]["name"] = "修改审核快照"
    assert source == original


def test_embedding_recalls_aliases_only_within_compatible_spatial_candidates():
    source = records()
    source[0]["name"], source[1]["name"] = "华润万家", "天天超市"
    source.append({**source[1], "id": "c", "lng": 114.4})

    class Embedder:
        async def embed(self, texts):
            return [[1.0, 0.0]] * len(texts)

    review = run_review(source, embedder=Embedder())
    assert len(review["entity_proposals"]) == 1
    assert review["entity_proposals"][0]["recall_method"] == "embedding_and_spatial"
    assert review["entity_proposals"][0]["relation"] == "uncertain"
    source[1]["coordinate_system"] = "WGS84"
    assert run_review(source, embedder=Embedder())["entity_proposals"] == []


def test_unknown_coordinate_system_has_no_identity_proposals():
    review = asyncio.run(review_facility_semantics(records()))
    assert review["entity_proposals"] == []
    assert review["category_proposals"][0]["candidate_categories"] == ["pharmacy"]
    assert "unknown_coordinate_system_identity_review_skipped" in review["diagnostics"]


@pytest.mark.parametrize(
    "invalid",
    [
        {
            "category_proposals": [
                {"record_id": "foreign", "category": "pharmacy", "confidence": 0.9, "evidence_fields": ["name"]}
            ]
        },
        {
            "category_proposals": [
                {"record_id": "a", "category": "made_up", "confidence": 0.9, "evidence_fields": ["name"]}
            ]
        },
        {
            "category_proposals": [
                {"record_id": "a", "category": "pharmacy", "confidence": 0.9, "evidence_fields": ["provider_category"]}
            ]
        },
        {
            "entity_proposals": [
                {
                    "left_id": "a",
                    "right_id": "foreign",
                    "relation": "same_entity",
                    "confidence": 0.9,
                    "evidence_fields": ["name"],
                }
            ]
        },
        {
            "entity_proposals": [
                {
                    "left_id": "a",
                    "right_id": "a",
                    "relation": "same_entity",
                    "confidence": 0.9,
                    "evidence_fields": ["name"],
                }
            ]
        },
        {
            "category_proposals": [
                {"record_id": "a", "category": "pharmacy", "confidence": True, "evidence_fields": ["name"]}
            ]
        },
        {"summary": "已完成设施合并并提高评分"},
        {
            "category_proposals": [
                {"record_id": "a", "category": "pharmacy", "confidence": 0.9, "evidence_fields": ["name"], "lng": 1}
            ]
        },
    ],
)
def test_invalid_model_batch_is_rejected_without_partial_application(invalid):
    original = records()
    review = run_review(original, Model(invalid))
    assert review["mode"] == "rules_degraded"
    assert review["category_proposals"][0]["proposed_category"] is None
    assert review["entity_proposals"][0]["relation"] == "uncertain"
    assert original == records()


def test_valid_first_proposal_is_not_applied_when_later_candidate_is_invalid():
    review = run_review(
        provider=Model(
            {
                "category_proposals": [
                    {"record_id": "a", "category": "pharmacy", "confidence": 0.9, "evidence_fields": ["name"]}
                ],
                "entity_proposals": [
                    {
                        "left_id": "a",
                        "right_id": "foreign",
                        "relation": "same_entity",
                        "confidence": 0.9,
                        "evidence_fields": ["name"],
                    }
                ],
            }
        )
    )
    assert review["category_proposals"][0]["proposed_category"] is None
    assert review["mode"] == "rules_degraded"


@pytest.mark.parametrize(
    "names,flag,action",
    [
        (("仁和医院", "仁和医院急诊科"), "department_record", "review_relationship"),
        (("仁和医院", "仁和医院东门"), "entrance_record", "review_relationship"),
        (("仁和药店（海韵店）", "仁和药店（红山店）"), "different_branch", "keep_distinct"),
    ],
)
def test_relationship_guards_override_models_high_confidence_identity(names, flag, action):
    source = records()
    source[0]["name"], source[1]["name"] = names
    model = Model(
        {
            "entity_proposals": [
                {
                    "left_id": "a",
                    "right_id": "b",
                    "relation": "same_entity",
                    "confidence": 0.99,
                    "evidence_fields": ["name"],
                }
            ]
        }
    )
    result = run_review(source, model)
    assert flag in result["entity_proposals"][0]["flags"]
    assert result["entity_proposals"][0]["action"] == action
    assert result["entity_proposals"][0]["relation"] != "same_entity"
    assert result["entity_proposals"][0]["proposed_relation"] == "same_entity"
    assert result["entity_proposals"][0]["status"] == "pending_human_review"


def test_low_confidence_and_different_identity_require_review_and_keep_records():
    model = Model(
        {
            "entity_proposals": [
                {
                    "left_id": "a",
                    "right_id": "b",
                    "relation": "different_entity",
                    "confidence": 0.6,
                    "evidence_fields": ["name"],
                }
            ]
        }
    )
    proposal = run_review(provider=model)["entity_proposals"][0]
    assert proposal["low_confidence"] is True
    assert proposal["action"] == "keep_distinct"


@pytest.mark.parametrize("vectors", [[[float("nan")], [1.0]], [[1.0], [1.0, 2.0]], None])
def test_invalid_embedding_degrades_to_spatial_name_rules(vectors):
    class Embedder:
        async def embed(self, texts):
            return vectors

    result = run_review(embedder=Embedder())
    assert len(result["entity_proposals"]) == 1
    assert result["entity_proposals"][0]["embedding_similarity"] is None
    assert "embedding_unavailable_rule_candidates_used" in result["diagnostics"]


def test_huge_finite_embeddings_do_not_produce_nan_or_infinity():
    class Embedder:
        async def embed(self, texts):
            return [[1e308, 1e308]] * len(texts)

    result = run_review(embedder=Embedder())
    assert result["entity_proposals"][0]["embedding_similarity"] == 1.0
    json.dumps(result, allow_nan=False)


def test_input_bounds_coordinate_values_and_unique_ids_are_enforced():
    for source in (
        [records()[0]] * 201,
        [records()[0], records()[0]],
        [{**records()[0], "lng": float("nan")}],
        [{**records()[0], "lat": True}],
        [{**records()[0], "id": ""}],
    ):
        with pytest.raises(ValueError):
            run_review(source)
    with pytest.raises(ValueError):
        run_review(categories=["made_up"])


def test_candidate_cap_is_disclosed_and_isolated_records_are_retained():
    source = [{**records()[0], "id": str(index)} for index in range(20)]
    source.append({**records()[1], "id": "isolated", "lng": 114.4})
    result = run_review(source)
    assert result["candidate_count"] == 100
    assert result["candidates_truncated"] is True
    assert len(result["records"]) == len(source)
    assert len(result["category_proposals"]) == len(source)


def test_model_timeout_falls_back_without_applying_partial_decisions(monkeypatch):
    monkeypatch.setattr("app.analysis.semantic_review.MODEL_TIMEOUT_SECONDS", 0.01)

    class SlowModel:
        async def generate(self, **kwargs):
            await asyncio.sleep(1)

    result = run_review(provider=SlowModel())
    assert result["mode"] == "rules_degraded"
    assert result["category_proposals"][0]["proposed_category"] is None
    assert result["entity_proposals"][0]["relation"] == "uncertain"


def test_embedding_timeout_retains_rule_review_candidates(monkeypatch):
    monkeypatch.setattr("app.analysis.semantic_review.EMBEDDING_TIMEOUT_SECONDS", 0.01)

    class SlowEmbedder:
        async def embed(self, texts):
            await asyncio.sleep(1)

    result = run_review(embedder=SlowEmbedder())
    assert result["mode"] == "rules"
    assert len(result["entity_proposals"]) == 1
    assert "embedding_unavailable_rule_candidates_used" in result["diagnostics"]
