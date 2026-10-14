"""独立消融产物检验：泄漏、预算和约束错误不能伪装成收益。"""

import asyncio
from copy import deepcopy

import pytest

from app.validation.ablations import ARMS, compare_ablation_artifacts, run_fixture_ablations


@pytest.fixture(scope="module")
def fixture_result():
    return asyncio.run(run_fixture_ablations())


def test_fixture_runs_all_five_components_without_inventing_live_effects(fixture_result):
    result = fixture_result
    assert result["dataset_kind"] == "synthetic"
    assert result["effect_strength"] == "fixture_contract_validation_only"
    assert result["community_count"] == 2
    assert result["same_budget"] is True
    assert result["cost_cny"] is None
    assert {item["arm"] for item in result["arms"]} == set(ARMS)
    assert all(item["route_pairs"] == 32 and item["tokens"] is None for item in result["arms"])
    assert all(item["constraint_violations"] == 0 for item in result["arms"])
    assert all(row["usage"]["physical_http_requests"] == 0 for row in result["rows"])
    by_arm = {item["arm"]: item for item in result["arms"]}
    assert by_arm["no_model"]["model_calls"] == 0
    assert by_arm["full_system"]["model_calls"] == 4
    assert by_arm["semantic_review"]["missed_merges"] == 0
    assert by_arm["no_model"]["missed_merges"] == 2
    assert by_arm["full_system"]["category_accuracy"] == 1
    assert by_arm["active_sampling"]["heldout_mae_minutes"] < by_arm["no_model"]["heldout_mae_minutes"]
    for community in result["artifacts"]["communities"]:
        heldout = {frozenset(arm["sampling"]["validation_ids"]) for arm in community["arms"].values()}
        assert len(heldout) == 1
        assert all(
            not set(arm["sampling"]["training_ids"]) & set(arm["sampling"]["validation_ids"])
            for arm in community["arms"].values()
        )


def test_saved_artifacts_reproduce_evaluation(fixture_result):
    again = compare_ablation_artifacts(deepcopy(fixture_result["artifacts"]))
    assert again == {key: value for key, value in fixture_result.items() if key != "artifacts"}


@pytest.mark.parametrize(
    "corruption",
    [
        "training_leak",
        "different_budget",
        "different_holdout",
        "duplicate_route",
        "duplicate_entity",
        "numeric_bool_label",
        "wrong_threshold",
    ],
)
def test_invalid_evidence_is_rejected_before_comparison(fixture_result, corruption):
    dataset = deepcopy(fixture_result["artifacts"])
    community = dataset["communities"][0]
    arm = community["arms"]["full_system"]
    if corruption == "training_leak":
        arm["sampling"]["training_ids"].append(arm["sampling"]["validation_ids"][0])
    elif corruption == "different_budget":
        arm["sampling"]["route_pair_budget"] += 1
    elif corruption == "different_holdout":
        arm["sampling"]["validation_ids"] = arm["sampling"]["validation_ids"][:-1]
    elif corruption == "duplicate_route":
        arm["sampling"]["predictions"].append(deepcopy(arm["sampling"]["predictions"][0]))
    elif corruption == "duplicate_entity":
        community["truth"]["entity_labels"].append({"left_id": "b", "right_id": "a", "same_entity": True})
    elif corruption == "numeric_bool_label":
        community["truth"]["entity_labels"][0]["same_entity"] = 1
    else:
        arm["sampling"]["threshold_minutes"] = 10
    with pytest.raises(ValueError):
        compare_ablation_artifacts(dataset)


def test_bad_selected_ids_official_predictions_and_overbudget_are_violations(fixture_result):
    dataset = deepcopy(fixture_result["artifacts"])
    arm = dataset["communities"][0]["arms"]["full_system"]
    arm["selected_ids"] = ["plot-a", "plot-a", "unknown", "plot-c"]
    arm["predictions_used_for_official_score"] = True
    arm["usage"]["route_pairs"] = 17
    result = compare_ablation_artifacts(dataset)
    row = next(
        item
        for item in result["rows"]
        if item["arm"] == "full_system" and item["community_id"] == "synthetic-community-1"
    )
    assert row["constraint_violations"] >= 6


@pytest.mark.parametrize(
    "constraint,field", [("minimum_capacity", "capacity"), ("budget", "cost"), ("allowed_land_only", "land_allowed")]
)
def test_missing_candidate_evidence_does_not_satisfy_hard_constraints(fixture_result, constraint, field):
    dataset = deepcopy(fixture_result["artifacts"])
    community = dataset["communities"][0]
    community["truth"]["constraints"][constraint] = True if constraint == "allowed_land_only" else 100000.0
    for candidate in community["candidates"]:
        candidate[field] = None
    result = compare_ablation_artifacts(dataset)
    assert all(
        row["constraint_violations"] >= 1 for row in result["rows"] if row["community_id"] == community["community_id"]
    )


def test_route_abstention_remains_unknown_instead_of_zero_error(fixture_result):
    dataset = deepcopy(fixture_result["artifacts"])
    arm = dataset["communities"][0]["arms"]["full_system"]
    validation_ids = set(arm["sampling"]["validation_ids"])
    for prediction in arm["sampling"]["predictions"]:
        if prediction["point_id"] in validation_ids:
            prediction["mean_minutes"] = None
    result = compare_ablation_artifacts(dataset)
    row = next(
        item
        for item in result["rows"]
        if item["arm"] == "full_system" and item["community_id"] == "synthetic-community-1"
    )
    assert row["heldout_mae_minutes"] is None
    assert row["unknown_prediction_count"] == len(validation_ids)


def test_population_constraint_requires_independent_grid_labels_and_deduplicates(fixture_result):
    dataset = deepcopy(fixture_result["artifacts"])
    community = dataset["communities"][0]
    community["truth"]["constraints"]["minimum_population"] = 1000.0
    missing = compare_ablation_artifacts(dataset)
    assert all(
        row["constraint_violations"] >= 1 for row in missing["rows"] if row["community_id"] == community["community_id"]
    )
    community["truth"]["candidate_coverage"] = {"plot-a": ["g1"], "plot-b": ["g1"], "plot-c": ["g1", "g2"]}
    community["truth"]["population_by_grid"] = {"g1": 600.0, "g2": 600.0}
    community["arms"]["full_system"]["selected_ids"] = ["plot-a", "plot-b"]
    evaluated = compare_ablation_artifacts(dataset)
    row = next(
        item
        for item in evaluated["rows"]
        if item["arm"] == "full_system" and item["community_id"] == community["community_id"]
    )
    assert row["constraint_violations"] == 1  # 两个候选覆盖同一网格，600人不能算成1200人。
