"""经人工/权威核验的网格障碍邻接，不把居民原始留言当空间事实。"""

from __future__ import annotations

import math
import re
import uuid
from datetime import UTC, datetime

from .database import Database

GRID_SCHEMA = "service-grid-v1"
VERIFIED_SOURCES = {"field_verification", "official_inventory", "resident_reviewed", "real_api"}


def center_key(center) -> str:
    if len(center) != 2 or any(not math.isfinite(value) for value in center):
        raise ValueError("空间证据中心点必须为有限经纬度")
    return f"{center[0]:.6f},{center[1]:.6f}"


class SpatialEvidenceRepository:
    def __init__(self, database: Database):
        self.database = database

    def record_edge(
        self,
        *,
        center,
        first_grid_id: str,
        second_grid_id: str,
        blocked: bool,
        source: str,
        reviewer: str,
        evidence_ref: str,
        grid_schema: str = GRID_SCHEMA,
        connection=None,
    ) -> dict:
        if source not in VERIFIED_SOURCES or not reviewer.strip() or not evidence_ref.strip():
            raise ValueError("空间邻接必须有可信来源、复核人和证据引用")
        if type(blocked) is not bool:
            raise ValueError("障碍状态必须为布尔值")
        ids = sorted((first_grid_id, second_grid_id))
        # 障碍属于同一空间网格；统一为无类别ID，避免一类设施障碍只影响一类分组。
        if any(not re.fullmatch(r"(?:[a-z]+-)?r\d+c\d+", value) for value in ids):
            raise ValueError("空间证据网格标识不合法")
        ids = sorted(value.split("-")[-1] for value in ids)
        positions = [re.search(r"(?:^|-)r(\d+)c(\d+)$", value) for value in ids]
        if (
            not all(positions)
            or abs(int(positions[0][1]) - int(positions[1][1])) + abs(int(positions[0][2]) - int(positions[1][2])) != 1
            or any(not 1 <= int(match[group]) <= 4 for match in positions for group in (1, 2))
            or grid_schema != GRID_SCHEMA
        ):
            raise ValueError("空间证据仅支持当前4×4网格的直接邻格")
        if any(not -180 <= value <= 180 for value in center) or not -90 <= center[1] <= 90:
            raise ValueError("空间证据中心点超出经纬度范围")
        record = {
            "id": str(uuid.uuid4()),
            "center_key": center_key(center),
            "grid_schema": grid_schema,
            "first_grid_id": ids[0],
            "second_grid_id": ids[1],
            "blocked": blocked,
            "source": source,
            "reviewer": reviewer.strip(),
            "evidence_ref": evidence_ref.strip(),
            "reviewed_at": datetime.now(UTC).isoformat(),
        }

        def insert(database_connection):
            database_connection.execute(
                "INSERT INTO verified_spatial_edges VALUES (:id,:center_key,:grid_schema,:first_grid_id,:second_grid_id,:blocked,:source,:reviewer,:evidence_ref,:reviewed_at) "
                "ON CONFLICT(center_key,grid_schema,first_grid_id,second_grid_id) DO UPDATE SET "
                "blocked=excluded.blocked,source=excluded.source,reviewer=excluded.reviewer,evidence_ref=excluded.evidence_ref,reviewed_at=excluded.reviewed_at",
                record,
            )
            stored = database_connection.execute(
                "SELECT id FROM verified_spatial_edges WHERE center_key=? AND grid_schema=? AND first_grid_id=? AND second_grid_id=?",
                (record["center_key"], grid_schema, ids[0], ids[1]),
            ).fetchone()
            record["id"] = stored["id"]

        if connection is not None:
            insert(connection)
        else:
            with self.database.connect() as owned_connection:
                insert(owned_connection)
                owned_connection.commit()
        return record

    def get_verified_edges(self, center, grid_schema: str = GRID_SCHEMA) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM verified_spatial_edges WHERE center_key=? AND grid_schema=? ORDER BY first_grid_id,second_grid_id",
                (center_key(center), grid_schema),
            ).fetchall()
        return [{**dict(row), "blocked": bool(row["blocked"]), "verified": True} for row in rows]
