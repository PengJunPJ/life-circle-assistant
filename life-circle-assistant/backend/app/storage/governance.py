from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any


def timestamp():
    return datetime.now(UTC).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class GovernanceConflict(ValueError):
    pass


class GovernanceRepository:
    """Optimistic catalog versions and review/audit writes in one transaction."""

    def __init__(self, database):
        self.database = database

    def ensure_catalog(self, report: dict) -> dict:
        report_id = report["report_id"]
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT catalog_json FROM facility_catalog_versions WHERE report_id=? ORDER BY version DESC LIMIT 1",
                (report_id,),
            ).fetchone()
            if row:
                return json.loads(row[0])
            records = deepcopy(report.get("facilities") or report.get("pois") or [])
            sources = deepcopy(report.get("raw_facility_records") or records)
            secondary = report.get("multisource_validation", {}).get("raw_records", [])
            sources.extend(deepcopy(secondary))
            seen = set()
            for index, item in enumerate(sources):
                original_id = str(item.get("id") or item.get("source_record_id") or f"source-{index}")
                item["original_id"] = original_id
                if original_id in seen:
                    original_id = f"{item.get('source') or 'raw'}:{original_id}:{index}"
                item["id"] = original_id
                item["coordinate_system"] = str(item.get("coordinate_system") or "BD09").upper().replace("-", "")
                seen.add(original_id)
            for item in records:
                item["member_ids"] = list(
                    dict.fromkeys(item.get("normalization", {}).get("merged_facility_ids") or [item["id"]])
                )
            catalog = {
                "report_id": report_id,
                "version": 1,
                "created_at": timestamp(),
                "records": records,
                "source_records": sources,
                "relationships": [],
                "verified_observations": [],
                "excluded_source_ids": [],
                "provenance": "immutable_report_source_snapshot",
                "rules_version": "reviewed-catalog-v1",
            }
            connection.execute(
                "INSERT INTO facility_catalog_versions VALUES(?,?,?,?)",
                (report_id, 1, catalog["created_at"], dump(catalog)),
            )
            connection.commit()
            return catalog

    def state(self, report: dict) -> dict:
        catalog = self.ensure_catalog(report)
        with self.database.connect() as connection:
            reviews = [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT review_json FROM semantic_reviews WHERE report_id=? ORDER BY created_at",
                    (report["report_id"],),
                )
            ]
            observations = [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT observation_json FROM resident_observations WHERE report_id=? ORDER BY created_at",
                    (report["report_id"],),
                )
            ]
            audit = [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT event_json FROM governance_audit WHERE report_id=? ORDER BY created_at",
                    (report["report_id"],),
                )
            ]
        return {
            "report_id": report["report_id"],
            "catalog_version": catalog["version"],
            "catalog": catalog,
            "reviews": reviews,
            "observations": observations,
            "audit": audit,
        }

    def save_review(self, report: dict, review: dict) -> dict:
        catalog = self.ensure_catalog(report)
        result = {
            **deepcopy(review),
            "review_id": str(uuid.uuid4()),
            "report_id": report["report_id"],
            "catalog_version": catalog["version"],
            "created_at": timestamp(),
        }
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO semantic_reviews VALUES(?,?,?,?)",
                (result["review_id"], report["report_id"], result["created_at"], dump(result)),
            )
            connection.commit()
        return result

    def save_observation(self, report: dict, observation: dict, image_base64: str | None = None) -> dict:
        catalog = self.ensure_catalog(report)
        result = {
            **deepcopy(observation),
            "id": str(uuid.uuid4()),
            "report_id": report["report_id"],
            "catalog_version": catalog["version"],
            "created_at": timestamp(),
            "status": "pending_human_review",
            "has_image": bool(image_base64),
            "affects_official_facts": False,
        }
        result["image_url"] = (
            f"/api/reports/{report['report_id']}/observations/{result['id']}/image" if image_base64 else None
        )
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO resident_observations VALUES(?,?,?,?,?)",
                (result["id"], report["report_id"], result["created_at"], dump(result), image_base64),
            )
            connection.commit()
        return result

    def observation_image(self, report_id: str, observation_id: str):
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT observation_json,image_base64 FROM resident_observations WHERE report_id=? AND id=?",
                (report_id, observation_id),
            ).fetchone()
        if row is None or not row["image_base64"]:
            return None
        return {"mime_type": json.loads(row["observation_json"])["mime_type"], "image_base64": row["image_base64"]}

    def decide(
        self,
        report_id: str,
        expected_version: int,
        *,
        target_type: str,
        target_id: str,
        mutate,
        event: dict,
        after_mutate=None,
    ) -> dict:
        table, column = {
            "review": ("semantic_reviews", "review_json"),
            "observation": ("resident_observations", "observation_json"),
        }[target_type]
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT catalog_json FROM facility_catalog_versions WHERE report_id=? ORDER BY version DESC LIMIT 1",
                (report_id,),
            ).fetchone()
            if row is None:
                raise ValueError("设施目录不存在")
            catalog = json.loads(row[0])
            if catalog["version"] != expected_version:
                raise GovernanceConflict("目录版本已更新，请重新读取后审核")
            target_row = connection.execute(
                f"SELECT {column} FROM {table} WHERE id=? AND report_id=?", (target_id, report_id)
            ).fetchone()
            if target_row is None:
                raise ValueError("待审核记录不存在")
            target = json.loads(target_row[0])
            mutate(catalog, target)
            if after_mutate:
                after_mutate(connection, catalog, target)
            catalog.update(version=expected_version + 1, created_at=timestamp())
            connection.execute(
                "INSERT INTO facility_catalog_versions VALUES(?,?,?,?)",
                (report_id, catalog["version"], catalog["created_at"], dump(catalog)),
            )
            connection.execute(f"UPDATE {table} SET {column}=? WHERE id=?", (dump(target), target_id))
            audit = {
                **event,
                "id": str(uuid.uuid4()),
                "target_type": target_type,
                "target_id": target_id,
                "catalog_version": catalog["version"],
                "created_at": catalog["created_at"],
            }
            connection.execute(
                "INSERT INTO governance_audit VALUES(?,?,?,?,?)",
                (audit["id"], report_id, catalog["version"], audit["created_at"], dump(audit)),
            )
            connection.commit()
        return {
            "report_id": report_id,
            "catalog_version": catalog["version"],
            "catalog": catalog,
            "target": target,
            "audit_event": audit,
            "requires_recompute": True,
            "affects_original_report": False,
        }

    def save_audience_report(self, report_id: str, document: dict) -> dict:
        result = {**document, "id": str(uuid.uuid4()), "created_at": timestamp()}
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO audience_reports VALUES(?,?,?,?,?)",
                (result["id"], report_id, result["audience"], result["created_at"], dump(result)),
            )
            connection.commit()
        return result

    def versions(self, report_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            return [
                {"version": row[0], "created_at": row[1]}
                for row in connection.execute(
                    "SELECT version,created_at FROM facility_catalog_versions WHERE report_id=? ORDER BY version",
                    (report_id,),
                )
            ]
