import copy

from app.analysis.gap_groups import build_gap_groups, spatial_statistics


def cell(grid_id, *, category="market", kind="critical", unknown=False, failed=0):
    return {
        "type": "Feature",
        "properties": {
            "grid_id": f"{category}-{grid_id}",
            "category": category,
            "kind": kind,
            "classification_status": "calculation_incomplete" if unknown else "valid",
            "walk_threshold_exceeded": None if unknown else True,
            "source": "real_api",
            "failed_route_count": failed,
            "nearby_scarcity": kind == "critical",
            "walking_reachable": None if unknown else False,
        },
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
    }


def test_gap_groups_preserve_islands_unknown_holes_categories_and_source_geometry():
    features = [
        cell("r1c1"),
        cell("r1c2"),
        cell("r2c3"),
        cell("r1c3", unknown=True),
        cell("r1c1", category="school"),
        cell("r3c3", failed=1),
    ]
    areas = {"type": "FeatureCollection", "features": features}
    before = copy.deepcopy(areas)
    groups = build_gap_groups(areas, gap_kinds=("walking_timeout",))["features"]
    assert sorted(item["properties"]["grid_count"] for item in groups) == [1, 1, 2]
    assert sum(item["properties"]["grid_count"] for item in groups) == 4
    assert all(item["geometry"]["type"] == "MultiPolygon" for item in groups)
    assert all(len(item["geometry"]["coordinates"]) == item["properties"]["grid_count"] for item in groups)
    assert areas == before


def test_blocked_edge_never_gets_bridged_by_grouping():
    areas = {"features": [cell("r1c1"), cell("r1c2")]}
    groups = build_gap_groups(
        areas, blocked_edges={frozenset({"market-r1c1", "market-r1c2"})}, gap_kinds=("walking_timeout",)
    )
    assert len(groups["features"]) == 2


def test_independent_statistics_distinguish_straight_line_scarcity_from_walk_time():
    nearby_but_slow = cell("r1c1", kind="sparse")
    far_but_reachable = cell("r1c2", kind="sparse")
    far_but_reachable["properties"].update(nearby_scarcity=True, walking_reachable=True)
    result = spatial_statistics({"features": [nearby_but_slow, far_but_reachable]})["categories"][0]
    assert result["nearby_scarcity_count"] == 1
    assert result["walking_gap_count"] == 1
    assert result["walking_reachable_count"] == 1


def test_scarcity_timeout_and_critical_are_separate_and_unknown_walk_still_has_search_scarcity():
    far_reachable = cell("r1c1", kind="sparse")
    far_reachable["properties"].update(nearby_scarcity=True, walking_reachable=True, walk_threshold_exceeded=False)
    unknown = cell("r1c2", unknown=True)
    unknown["properties"]["nearby_scarcity_status"] = "observed_search_results"
    nearby_slow = cell("r2c1", kind="sparse")
    critical = cell("r3c1")
    groups = build_gap_groups({"features": [far_reachable, unknown, nearby_slow, critical]})["features"]
    ids_by_kind = {
        kind: {
            grid_id
            for group in groups
            if group["properties"]["gap_kind"] == kind
            for grid_id in group["properties"]["grid_ids"]
        }
        for kind in ("scarcity", "walking_timeout", "critical")
    }
    assert ids_by_kind["scarcity"] == {"market-r1c1", "market-r1c2", "market-r3c1"}
    assert ids_by_kind["walking_timeout"] == {"market-r2c1", "market-r3c1"}
    assert ids_by_kind["critical"] == {"market-r3c1"}
