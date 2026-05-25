"""Persist WebUI chat turns into the AIBrother knowledge base."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.aibrother.knowledge import KnowledgeIndex, resolve_aibrother_root
from nanobot.session.manager import Session

CHAT_DB_NAME = "chat_archive.db"
CONVERSATION_HISTORY_REL = "knowledge/group_knowledge/conversation_history.md"
_HISTORY_HEADER = "# 组内问答历史记录"


def extract_latest_turn(session: Session) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return the latest completed user/assistant pair from a session."""
    messages = session.messages
    assistant: dict[str, Any] | None = None
    assistant_idx: int | None = None
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("role") != "assistant":
            continue
        if message.get("tool_calls"):
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            assistant = message
            assistant_idx = index
            break
    if assistant is None or assistant_idx is None:
        return None

    user: dict[str, Any] | None = None
    for index in range(assistant_idx - 1, -1, -1):
        message = messages[index]
        role = message.get("role")
        if role == "tool":
            continue
        if role == "assistant":
            # Intermediate tool-calling assistant turns belong to the same user turn.
            continue
        if role == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                text = _strip_message_time_prefix(content.strip())
                if text.startswith("/"):
                    return None
                user = message
                break
        break
    if user is None:
        return None
    return user, assistant


def archive_session_turn(session: Session, *, workspace: Path | None = None) -> int | None:
    """Archive the latest session turn into SQLite and conversation_history.md."""
    pair = extract_latest_turn(session)
    if pair is None:
        return None
    user_message, assistant_message = pair
    user_text = _strip_message_time_prefix(str(user_message.get("content") or "").strip())
    assistant_text = str(assistant_message.get("content") or "").strip()
    if not user_text or not assistant_text:
        return None

    store = ChatKnowledgeStore(workspace)
    try:
        session_title = session.metadata.get("title")
        title = session_title.strip() if isinstance(session_title, str) else ""
        knowledge_refs = user_message.get("knowledge_imports")
        refs = knowledge_refs if isinstance(knowledge_refs, list) else None
        return store.archive_turn(
            session_key=session.key,
            chat_id=session.key.split(":", 1)[-1],
            user_message=user_text,
            assistant_message=assistant_text,
            session_title=title or None,
            knowledge_refs=refs,
        )
    finally:
        store.close()


def format_turn_index_body(row: sqlite3.Row | dict[str, Any]) -> str:
    return "\n".join(
        [
            f"## 问：{_first_line(str(row['user_message']))}",
            f"答：{row['assistant_message']}",
        ]
    )


class ChatKnowledgeStore:
    """SQLite-backed archive for searchable chat knowledge."""

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.root = resolve_aibrother_root(workspace)
        self.knowledge_dir = self.root / "knowledge" / "group_knowledge"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.knowledge_dir / CHAT_DB_NAME
        self.history_path = self.root / CONVERSATION_HISTORY_REL
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        self._conn.close()

    def _ensure_schema(self) -> None:
        self._conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS chat_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT NOT NULL UNIQUE,
                session_key TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                session_title TEXT,
                user_message TEXT NOT NULL,
                assistant_message TEXT NOT NULL,
                knowledge_refs TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_turns_session
                ON chat_turns(session_key, created_at);
            CREATE VIRTUAL TABLE IF NOT EXISTS chat_turns_fts USING fts5(
                session_title,
                user_message,
                assistant_message,
                content='chat_turns',
                content_rowid='id',
                tokenize='unicode61'
            );
            """
        )
        self._conn.commit()
        self._backfill_fts()

    def _backfill_fts(self) -> None:
        count = self._conn.execute("SELECT COUNT(*) FROM chat_turns_fts").fetchone()[0]
        if count:
            return
        rows = self._conn.execute(
            "SELECT id, session_title, user_message, assistant_message FROM chat_turns",
        ).fetchall()
        if not rows:
            return
        self._conn.executemany(
            """
            INSERT INTO chat_turns_fts(rowid, session_title, user_message, assistant_message)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    row["id"],
                    row["session_title"] or "",
                    row["user_message"],
                    row["assistant_message"],
                )
                for row in rows
            ],
        )
        self._conn.commit()

    def archive_turn(
        self,
        *,
        session_key: str,
        chat_id: str,
        user_message: str,
        assistant_message: str,
        session_title: str | None = None,
        knowledge_refs: list[Any] | None = None,
    ) -> int | None:
        content_hash = _content_hash(session_key, user_message, assistant_message)
        if self._turn_exists(content_hash):
            return None

        created_at = datetime.now(UTC).replace(microsecond=0).isoformat()
        refs_json = (
            json.dumps(knowledge_refs, ensure_ascii=False)
            if knowledge_refs
            else None
        )
        cursor = self._conn.execute(
            """
            INSERT INTO chat_turns(
                content_hash, session_key, chat_id, session_title,
                user_message, assistant_message, knowledge_refs, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                content_hash,
                session_key,
                chat_id,
                session_title,
                user_message,
                assistant_message,
                refs_json,
                created_at,
            ),
        )
        row_id = cursor.lastrowid
        self._conn.execute(
            """
            INSERT INTO chat_turns_fts(rowid, session_title, user_message, assistant_message)
            VALUES (?, ?, ?, ?)
            """,
            (row_id, session_title or "", user_message, assistant_message),
        )
        self._conn.commit()
        self._append_history_markdown(
            user_message=user_message,
            assistant_message=assistant_message,
            session_title=session_title,
            session_key=session_key,
            knowledge_refs=knowledge_refs,
            created_at=created_at,
        )
        logger.info("Archived chat turn to knowledge base: {}", session_key)
        return int(row_id)

    def get_turn(self, turn_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            """
            SELECT id, session_title, user_message, assistant_message, created_at
            FROM chat_turns WHERE id = ?
            """,
            (turn_id,),
        ).fetchone()

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, str]]:
        query = query.strip()
        if not query:
            return []
        fts_query = " OR ".join(
            token for token in re.findall(r"[\w\u4e00-\u9fff]+", query, flags=re.UNICODE)
        ) or query
        try:
            rows = self._conn.execute(
                """
                SELECT
                    t.session_key,
                    t.session_title,
                    t.user_message,
                    t.assistant_message,
                    t.created_at,
                    snippet(chat_turns_fts, 2, '', '', ' ... ', 24) AS snippet
                FROM chat_turns_fts
                JOIN chat_turns t ON t.id = chat_turns_fts.rowid
                WHERE chat_turns_fts MATCH ?
                ORDER BY bm25(chat_turns_fts)
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = self._conn.execute(
                """
                SELECT session_key, session_title, user_message, assistant_message, created_at
                FROM chat_turns
                WHERE user_message LIKE ? OR assistant_message LIKE ?
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            return [
                {
                    "session_key": row["session_key"],
                    "session_title": row["session_title"] or "",
                    "user_message": row["user_message"],
                    "assistant_message": row["assistant_message"],
                    "created_at": row["created_at"],
                    "snippet": _preview(row["assistant_message"]),
                }
                for row in rows
            ]
        return [
            {
                "session_key": row["session_key"],
                "session_title": row["session_title"] or "",
                "user_message": row["user_message"],
                "assistant_message": row["assistant_message"],
                "created_at": row["created_at"],
                "snippet": _clean_snippet(row["snippet"]),
            }
            for row in rows
        ]

    def index_into(self, knowledge_index: KnowledgeIndex) -> None:
        """Push archived chat turns into the in-memory knowledge FTS index."""
        rows = self._conn.execute(
            """
            SELECT id, session_title, user_message, assistant_message, created_at
            FROM chat_turns
            ORDER BY id
            """,
        ).fetchall()
        for row in rows:
            title = row["session_title"] or f"聊天记录 {row['created_at'][:10]}"
            knowledge_index.index_external_text(
                path=f"knowledge/group_knowledge/{CHAT_DB_NAME}#turn-{row['id']}",
                title=title,
                category="group_knowledge",
                text=format_turn_index_body(row),
            )

    def _turn_exists(self, content_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM chat_turns WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        return row is not None

    def _append_history_markdown(
        self,
        *,
        user_message: str,
        assistant_message: str,
        session_title: str | None,
        session_key: str,
        knowledge_refs: list[Any] | None,
        created_at: str,
    ) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_path.is_file():
            self.history_path.write_text(f"{_HISTORY_HEADER}\n", encoding="utf-8")

        question = _first_line(user_message)
        answer = _first_line(assistant_message, limit=1200)
        block_lines = [
            "",
            f"## 问：{question}",
            f"答：{answer}",
        ]
        meta_bits = [f"时间：{created_at}"]
        if session_title:
            meta_bits.append(f"会话：{session_title}")
        else:
            meta_bits.append(f"会话：{session_key}")
        filenames = _knowledge_filenames(knowledge_refs)
        if filenames:
            meta_bits.append(f"相关文件：{', '.join(filenames)}")
        block_lines.append(f"> {' · '.join(meta_bits)}")
        block_lines.append("")

        with self.history_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(block_lines))


def _content_hash(session_key: str, user_message: str, assistant_message: str) -> str:
    payload = f"{session_key}\0{user_message}\0{assistant_message}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _strip_message_time_prefix(content: str) -> str:
    return re.sub(r"^\[Message Time: [^\]]+\]\n?", "", content, count=1).strip()


def _first_line(text: str, *, limit: int = 240) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1].rstrip() + "…"


def _knowledge_filenames(knowledge_refs: list[Any] | None) -> list[str]:
    if not isinstance(knowledge_refs, list):
        return []
    names: list[str] = []
    for item in knowledge_refs:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        if isinstance(filename, str) and filename.strip():
            names.append(filename.strip())
    return names


def _preview(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:180]


def _clean_snippet(snippet: str) -> str:
    return re.sub(r"\s+", " ", snippet).strip()
