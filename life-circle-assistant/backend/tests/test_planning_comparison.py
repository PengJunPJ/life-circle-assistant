from app.planning_comparison import finalize_comparison


def comparison(values):
    return {
        "id": "comparison-test",
        "report_id": "report-test",
        "goal": "increase_coverage",
        "options": [
            {
                "id": f"option-{index}",
                "title": f"方案 {index}",
                "eligible": eligible,
                "delta": {"coverage_area_sqm": value},
            }
            for index, (value, eligible) in enumerate(values, start=1)
        ],
    }


def test_comparison_preserves_ties_and_only_prefers_positive_improvement():
    result = finalize_comparison(comparison([(120, True), (120, True), (-40, True)]))

    assert [option["rank"] for option in result["options"]] == [1, 1, 3]
    assert result["preferred_option_ids"] == ["option-1", "option-2"]


def test_comparison_does_not_declare_a_winner_when_results_are_insufficient_or_nonpositive():
    insufficient = finalize_comparison(comparison([(120, True), (80, False)]))
    nonpositive = finalize_comparison(comparison([(-120, True), (-80, True)]))

    assert insufficient["preferred_option_ids"] == []
    assert "不足" in insufficient["summary"]
    assert nonpositive["preferred_option_ids"] == []
    assert "未改善" in nonpositive["summary"]
