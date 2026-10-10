from app.validation.multisource_poi import evaluate_labeled_pairs


def record(source: str, identifier: str, name: str, *, lng: float = 113.4872, category: str = "market") -> dict:
    return {
        "source": source,
        "source_record_id": identifier,
        "name": name,
        "category": category,
        "lng": lng,
        "lat": 23.1068,
        "address": "广州市黄埔区红山街测试路 1 号",
        "coordinate_system": "bd09",
        "retrieved_at": "2026-10-10T00:00:00Z",
    }


def test_evaluator_reports_match_precision_recall_and_conflict_recall():
    pairs = [
        {
            "pair_id": "p-1",
            "left": record("baidu", "b-1", "红山菜市场"),
            "right": record("amap", "a-1", "红山农贸市场", lng=113.48745),
            "label": "match",
        },
        {
            "pair_id": "p-2",
            "left": record("baidu", "b-2", "安康药店", category="pharmacy"),
            "right": record("amap", "a-2", "安康药店", category="pharmacy", lng=113.4972),
            "label": "non_match",
        },
        {
            "pair_id": "p-3",
            "left": record("baidu", "b-3", "红山菜市场"),
            "right": record("amap", "a-3", "红山便利店", category="convenience", lng=113.4873),
            "label": "conflict",
        },
    ]

    result = evaluate_labeled_pairs(pairs)

    assert result["sample_count"] == 3
    assert result["match_metrics"] == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    assert result["human_conflict_recall"] == 1.0
    assert result["unresolved_rate"] == 0.0
    assert result["confusion_matrix"]["match"]["match"] == 1
    assert result["decisions"][2]["prediction"] == "conflict"


def test_evaluator_counts_needs_review_as_unresolved_not_automatic_match():
    left = record("baidu", "b-1", "红山菜市场")
    right = record("amap", "a-1", "红山菜市场", lng=113.48805)
    result = evaluate_labeled_pairs([{"pair_id": "ambiguous-1", "left": left, "right": right, "label": "match"}])

    assert result["decisions"][0]["prediction"] == "needs_review"
    assert result["match_metrics"]["recall"] == 0.0
    assert result["unresolved_rate"] == 1.0


def test_evaluator_accepts_feature_only_fixture_without_retaining_raw_poi_fields():
    result = evaluate_labeled_pairs(
        [
            {
                "pair_id": "sha256:short-test-pair-id",
                "features": {
                    "distance_m": 18.5,
                    "name_score": 0.91,
                    "address_score": 0.88,
                    "category_match": True,
                },
                "label": "match",
            }
        ]
    )

    assert result["decisions"][0]["prediction"] == "match"
    assert "name" not in result["decisions"][0]
    assert "address" not in result["decisions"][0]
