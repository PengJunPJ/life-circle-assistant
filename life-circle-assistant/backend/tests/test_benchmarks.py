from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.validation.benchmarks import evaluate_benchmark, generate_benchmark_template, render_markdown_report


def report(kinds: dict[str, str]) -> dict:
    return {
        "report_id": "report-1",
        "center": {"lng": 113.48, "lat": 23.10, "address": "测试社区"},
        "parameters": {"minutes": 15},
        "service_areas": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"grid_id": grid_id, "kind": kind},
                    "geometry": {"type": "Polygon", "coordinates": []},
                }
                for grid_id, kind in kinds.items()
            ],
        },
    }


def benchmark(status: str = "verified") -> dict:
    labels = [
        {"grid_id": "market-r1c1", "category": "market", "expected_kind": "normal", "evidence": {}},
        {"grid_id": "market-r1c2", "category": "market", "expected_kind": "sparse", "evidence": {}},
        {"grid_id": "market-r2c1", "category": "market", "expected_kind": "critical", "evidence": {}},
        {"grid_id": "market-r2c2", "category": "market", "expected_kind": "normal", "evidence": {}},
    ]
    return {
        "schema_version": "1.0",
        "benchmark_id": "community-a-20260921",
        "status": status,
        "community": {"name": "测试社区", "center_lng": 113.48, "center_lat": 23.10},
        "coordinate_system": "BD-09",
        "threshold_minutes": 15,
        "grid_size": 2,
        "categories": ["market"],
        "labels": labels,
    }


def test_generate_template_covers_every_grid_without_prediction_leakage():
    source_report = report(
        {
            "market-r1c1": "normal",
            "market-r1c2": "sparse",
            "market-r2c1": "critical",
            "market-r2c2": "unknown",
        }
    )

    result = generate_benchmark_template(source_report, benchmark_id="community-a")

    assert result["status"] == "draft"
    assert result["grid_size"] == 2
    assert len(result["labels"]) == 4
    assert all(item["expected_kind"] is None for item in result["labels"])
    assert "predicted_kind" not in result["labels"][0]


def test_perfect_predictions_produce_complete_metrics():
    evaluation = evaluate_benchmark(
        report(
            {
                "market-r1c1": "normal",
                "market-r1c2": "sparse",
                "market-r2c1": "critical",
                "market-r2c2": "normal",
            }
        ),
        benchmark(),
    )

    assert evaluation["completeness"]["is_verified_full_grid"] is True
    assert evaluation["metrics"]["accuracy"] == 1.0
    assert evaluation["metrics"]["macro_recall"] == 1.0
    assert evaluation["metrics"]["prediction_coverage"] == 1.0
    assert evaluation["mismatches"] == []


def test_unknown_and_wrong_predictions_affect_recall_and_coverage():
    evaluation = evaluate_benchmark(
        report(
            {
                "market-r1c1": "normal",
                "market-r1c2": "critical",
                "market-r2c1": "unknown",
                "market-r2c2": "normal",
            }
        ),
        benchmark(),
    )

    assert evaluation["confusion_matrix"]["sparse"]["critical"] == 1
    assert evaluation["confusion_matrix"]["critical"]["unknown"] == 1
    assert evaluation["metrics"]["accuracy"] == 0.5
    assert evaluation["metrics"]["prediction_coverage"] == 0.75
    assert evaluation["metrics"]["per_kind"]["critical"]["recall"] == 0.0
    assert evaluation["metrics"]["macro_f1"] == 0.3333
    assert len(evaluation["mismatches"]) == 2


def test_draft_only_evaluates_reviewed_labels_and_warns_in_markdown():
    draft = benchmark(status="draft")
    draft["labels"][2]["expected_kind"] = None
    evaluation = evaluate_benchmark(
        report(
            {
                "market-r1c1": "normal",
                "market-r1c2": "sparse",
                "market-r2c1": "critical",
                "market-r2c2": "normal",
            }
        ),
        draft,
    )

    assert evaluation["metrics"]["evaluated_count"] == 3
    assert evaluation["completeness"]["review_completion_rate"] == 0.75
    assert evaluation["completeness"]["is_verified_full_grid"] is False
    assert "不得宣称为全网格准确率" in render_markdown_report(evaluation)


def test_missing_report_grid_is_counted_as_unknown_and_disclosed():
    evaluation = evaluate_benchmark(
        report(
            {
                "market-r1c1": "normal",
                "market-r1c2": "sparse",
                "market-r2c2": "normal",
            }
        ),
        benchmark(),
    )

    assert evaluation["completeness"]["missing_prediction_grid_ids"] == ["market-r2c1"]
    assert evaluation["confusion_matrix"]["critical"]["unknown"] == 1
    assert evaluation["metrics"]["prediction_coverage"] == 0.75


def test_verified_benchmark_rejects_unreviewed_grid():
    invalid = benchmark()
    invalid["labels"][0]["expected_kind"] = None

    with pytest.raises(ValidationError, match="未标注"):
        evaluate_benchmark(report({"market-r1c1": "normal"}), invalid)


def test_benchmark_rejects_incomplete_grid_inventory():
    invalid = deepcopy(benchmark())
    invalid["labels"].pop()

    with pytest.raises(ValidationError, match="网格清单不完整"):
        evaluate_benchmark(report({"market-r1c1": "normal"}), invalid)
