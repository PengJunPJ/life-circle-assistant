import pytest
from test_gap_groups import cell

from app.analysis.gap_groups import build_gap_groups
from app.analysis.recommendations import build_planning_recommendations
from app.storage.database import Database
from app.storage.spatial_evidence import SpatialEvidenceRepository


def test_verified_obstacle_roundtrips_and_splits_all_gap_kinds_and_candidate_chain(tmp_path):
    db = Database(tmp_path / "spatial.db")
    db.migrate()
    repository = SpatialEvidenceRepository(db)
    repository.record_edge(
        center=(113.4, 23.1),
        first_grid_id="r1c1",
        second_grid_id="r1c2",
        blocked=True,
        source="field_verification",
        reviewer="reviewer",
        evidence_ref="field-1",
    )
    evidence = repository.get_verified_edges((113.4, 23.1))
    assert repository.get_verified_edges((113.5, 23.1)) == []
    areas = {"features": [cell("r1c1"), cell("r1c2")]}
    for feature in areas["features"]:
        feature["properties"]["basis"] = "已测路线超过阈值"
    groups = build_gap_groups(areas, adjacency_evidence=evidence)
    assert len(groups["features"]) == 6
    score = {"category": "market", "label": "菜市场", "count": 1, "score": 20}
    recommendations = build_planning_recommendations([score], areas, gap_groups=groups)
    candidates = recommendations["recommendations"][0]["candidate_locations"]
    assert len(candidates) == 2
    assert all(len(candidate["related_region_ids"]) == 1 for candidate in candidates)
    assert all(candidate["gap_group_id"] for candidate in candidates)


def test_resident_unreviewed_or_nonadjacent_obstacles_are_rejected(tmp_path):
    db = Database(tmp_path / "spatial.db")
    db.migrate()
    repository = SpatialEvidenceRepository(db)
    for first, second, source in [("r1c1", "r1c3", "field_verification"), ("r1c1", "r1c2", "resident")]:
        with pytest.raises(ValueError):
            repository.record_edge(
                center=(113.4, 23.1),
                first_grid_id=first,
                second_grid_id=second,
                blocked=True,
                source=source,
                reviewer="reviewer",
                evidence_ref="field-1",
            )


def test_category_specific_ids_share_one_spatial_edge_and_upsert_preserves_stored_identifier(tmp_path):
    database = Database(tmp_path / "spatial.db")
    database.migrate()
    repository = SpatialEvidenceRepository(database)
    args = dict(
        center=(113.4, 23.1), blocked=True, source="field_verification", reviewer="reviewer", evidence_ref="field-1"
    )
    first = repository.record_edge(first_grid_id="market-r1c1", second_grid_id="market-r1c2", **args)
    second = repository.record_edge(
        first_grid_id="pharmacy-r1c2", second_grid_id="pharmacy-r1c1", **{**args, "blocked": False}
    )
    stored = repository.get_verified_edges(args["center"])
    assert first["id"] == second["id"] == stored[0]["id"]
    assert len(stored) == 1
    assert stored[0]["blocked"] is False
    assert (stored[0]["first_grid_id"], stored[0]["second_grid_id"]) == ("r1c1", "r1c2")
