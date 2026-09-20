from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .database import Database


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, request_parameters: dict[str, Any], *, rerun_of_report_id: str | None = None) -> dict[str, Any]:
        task_id = str(uuid.uuid4())
        created_at = now()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO analysis_tasks(
                    id, status, stage, stage_label, progress, request_json,
                    rerun_of_report_id, created_at, updated_at
                ) VALUES (?, 'queued', 'request_validation', '请求校验', 12, ?, ?, ?, ?)
                """,
                (task_id, _dump(request_parameters), rerun_of_report_id, created_at, created_at),
            )
            connection.commit()
        return self.get(task_id) or {}

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM analysis_tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def mark_running(self, task_id: str) -> None:
        timestamp = now()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE analysis_tasks
                SET status = 'running', started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (timestamp, timestamp, task_id),
            )
            connection.commit()

    def update_stage(self, task_id: str, code: str, label: str, progress: int) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE analysis_tasks
                SET stage = ?, stage_label = ?, progress = ?, updated_at = ?
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (code, label, progress, now(), task_id),
            )
            connection.commit()

    def update_request(self, task_id: str, request_parameters: dict[str, Any]) -> None:
        """保存任务执行期间补全的规范化请求参数，例如中心点反查地址。"""
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE analysis_tasks
                SET request_json = ?, updated_at = ?
                WHERE id = ? AND status IN ('queued', 'running')
                """,
                (_dump(request_parameters), now(), task_id),
            )
            connection.commit()

    def fail(self, task_id: str, error: str, *, stage_label: str = "分析失败") -> None:
        timestamp = now()
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE analysis_tasks
                SET status = 'failed', stage = 'failed', stage_label = ?, progress = 100,
                    error = ?, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (stage_label, error, timestamp, timestamp, task_id),
            )
            connection.commit()

    def recover_interrupted(self) -> int:
        timestamp = now()
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE analysis_tasks
                SET status = 'failed', stage = 'failed', stage_label = '服务重启已中断', progress = 100,
                    error = '服务异常重启，原分析任务已中断，请使用历史参数重新运行。',
                    completed_at = ?, updated_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (timestamp, timestamp),
            )
            connection.commit()
            return cursor.rowcount

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "status": row["status"],
            "stage": row["stage"],
            "stage_label": row["stage_label"],
            "progress": row["progress"],
            "request": json.loads(row["request_json"]),
            "report_id": row["report_id"],
            "rerun_of_report_id": row["rerun_of_report_id"],
            "error": row["error"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
        }


class ReportRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_for_task(self, task_id: str, report: dict[str, Any]) -> None:
        report_id = report["report_id"]
        center = report["analysis_center"]
        parameters = report["request"]
        completed_at = report["completed_at"]
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO analysis_reports(
                    id, task_id, schema_version, created_at, completed_at,
                    center_address, center_lng, center_lat, minutes, mode,
                    categories_json, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    task_id,
                    report["schema_version"],
                    report["created_at"],
                    completed_at,
                    center.get("address") or "未命名分析中心",
                    center["lng"],
                    center["lat"],
                    parameters["minutes"],
                    parameters["mode"],
                    _dump(parameters["categories"]),
                    _dump(report),
                ),
            )
            connection.execute(
                """
                UPDATE analysis_tasks
                SET status = 'completed', stage = 'completed', stage_label = '分析完成', progress = 100,
                    report_id = ?, error = NULL, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (report_id, completed_at, completed_at, task_id),
            )
            connection.commit()

    def get(self, report_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT report_json FROM analysis_reports WHERE id = ?", (report_id,)).fetchone()
        return json.loads(row["report_json"]) if row else None

    def get_by_task_id(self, task_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT report_json FROM analysis_reports WHERE task_id = ?", (task_id,)).fetchone()
        return json.loads(row["report_json"]) if row else None

    def list_history(self, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        with self.database.connect() as connection:
            total = connection.execute("SELECT COUNT(*) AS total FROM analysis_reports").fetchone()["total"]
            rows = connection.execute(
                """
                SELECT id, task_id, schema_version, created_at, completed_at,
                       center_address, center_lng, center_lat, minutes, mode, categories_json
                FROM analysis_reports
                ORDER BY completed_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return {
            "items": [
                {
                    "report_id": row["id"],
                    "task_id": row["task_id"],
                    "schema_version": row["schema_version"],
                    "created_at": row["created_at"],
                    "completed_at": row["completed_at"],
                    "center": {
                        "address": row["center_address"],
                        "lng": row["center_lng"],
                        "lat": row["center_lat"],
                    },
                    "minutes": row["minutes"],
                    "mode": row["mode"],
                    "categories": json.loads(row["categories_json"]),
                }
                for row in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
