"""在同一 SQLite 事务内预留消息、验证版本并消费确认，防止重复副作用。"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from .database import Database
from .repositories import _dump, now


class WorkspaceError(ValueError):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


class WorkspaceRepository:
    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def _workspace(row) -> dict:
        return {
            "id": row["id"],
            "revision": row["revision"],
            "state": json.loads(row["state_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def create(self, state: dict) -> dict:
        identifier, timestamp = str(uuid4()), now()
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO conversation_workspaces(id,state_json,created_at,updated_at) VALUES(?,?,?,?)",
                (identifier, _dump(state), timestamp, timestamp),
            )
            connection.commit()
        return self.get(identifier)

    def get(self, identifier: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM conversation_workspaces WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise WorkspaceError("对话工作区不存在", 404)
        return self._workspace(row)

    def update(self, identifier: str, revision: int, state: dict) -> dict:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """UPDATE conversation_workspaces
                SET state_json=?,revision=revision+1,pending_json=NULL,updated_at=?
                WHERE id=? AND revision=? AND inflight_id IS NULL""",
                (_dump(state), now(), identifier, revision),
            )
            if not cursor.rowcount:
                self.get(identifier)
                raise WorkspaceError("工作区已变化或对话正在执行，请读取最新状态后重试")
            connection.commit()
        return self.get(identifier)

    def begin(self, identifier: str, request: Any) -> tuple[dict, dict | None, dict | None]:
        fingerprint = hashlib.sha256(
            _dump({"message": request.message, "confirm_token": request.confirm_token}).encode()
        ).hexdigest()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM conversation_workspaces WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise WorkspaceError("对话工作区不存在", 404)
            existing = connection.execute(
                "SELECT * FROM conversation_turns WHERE workspace_id=? AND request_id=?",
                (identifier, request.request_id),
            ).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise WorkspaceError("同一请求标识不能用于不同消息")
                if existing["result_json"] is None:
                    raise WorkspaceError("这条消息正在执行，请稍后用相同请求标识重试")
                return self._workspace(row), json.loads(existing["result_json"]), None
            if row["revision"] != request.expected_revision or row["inflight_id"]:
                raise WorkspaceError("工作区已变化或对话正在执行，请读取最新状态后重试")
            pending = json.loads(row["pending_json"]) if row["pending_json"] else None
            if request.confirm_token and (
                not pending or pending["token"] != request.confirm_token or pending["revision"] != row["revision"]
            ):
                raise WorkspaceError("确认已失效，请重新提出操作并核对当前参数")
            turn_id, timestamp = str(uuid4()), now()
            connection.execute(
                "INSERT INTO conversation_turns(id,workspace_id,request_id,fingerprint,created_at) VALUES(?,?,?,?,?)",
                (turn_id, identifier, request.request_id, fingerprint, timestamp),
            )
            connection.execute(
                "UPDATE conversation_workspaces SET revision=revision+1,inflight_id=?,pending_json=NULL,updated_at=? WHERE id=?",
                (turn_id, timestamp, identifier),
            )
            connection.commit()
        workspace = self._workspace(row)
        workspace["revision"] += 1
        workspace["turn_id"] = turn_id
        return workspace, None, pending if request.confirm_token else None

    def finish(self, workspace: dict, result: dict, state: dict, pending: dict | None = None) -> dict:
        result = {
            "id": workspace["turn_id"],
            "workspace_id": workspace["id"],
            "revision": workspace["revision"],
            "created_at": now(),
            **result,
        }
        if pending:
            pending = {**pending, "revision": workspace["revision"]}
            result["pending"] = pending
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """UPDATE conversation_workspaces SET state_json=?,pending_json=?,inflight_id=NULL,updated_at=?
                WHERE id=? AND revision=? AND inflight_id=?""",
                (
                    _dump(state),
                    _dump(pending) if pending else None,
                    now(),
                    workspace["id"],
                    workspace["revision"],
                    workspace["turn_id"],
                ),
            )
            if cursor.rowcount != 1:
                raise WorkspaceError("对话执行版本已失效")
            connection.execute(
                "UPDATE conversation_turns SET result_json=? WHERE id=?", (_dump(result), workspace["turn_id"])
            )
            connection.commit()
        return result

    def messages(self, identifier: str) -> list[dict]:
        self.get(identifier)
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT result_json FROM conversation_turns WHERE workspace_id=? AND result_json IS NOT NULL ORDER BY rowid DESC LIMIT 100",
                (identifier,),
            ).fetchall()
        return [json.loads(row["result_json"]) for row in reversed(rows)]

    def recover_interrupted(self) -> int:
        # 显式失败记录保留历史，不在启动时自动重放可能收费的命令。
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT w.*,t.request_id FROM conversation_workspaces w JOIN conversation_turns t ON t.id=w.inflight_id"
            ).fetchall()
            for row in rows:
                result = {
                    "id": row["inflight_id"],
                    "workspace_id": row["id"],
                    "request_id": row["request_id"],
                    "revision": row["revision"],
                    "status": "failed",
                    "message": "",
                    "answer": "服务重启中断了本轮对话，请检查任务历史后重新发起。",
                    "actions": [],
                    "created_at": now(),
                }
                connection.execute(
                    "UPDATE conversation_turns SET result_json=? WHERE id=?", (_dump(result), row["inflight_id"])
                )
                connection.execute(
                    "UPDATE conversation_workspaces SET inflight_id=NULL,pending_json=NULL WHERE id=?", (row["id"],)
                )
            connection.commit()
        return len(rows)
