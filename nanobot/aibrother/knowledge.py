"""Markdown-backed AIBrother knowledge retrieval."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


_CATEGORY_LABELS = {
    "lab_manual": "实验手册",
    "group_knowledge": "组内经验",
    "papers": "论文摘要",
    "public": "外部资料",
    "cards": "知识卡片",
}

_CATEGORY_PRIORITY = {
    "lab_manual": 0,
    "group_knowledge": 1,
    "papers": 2,
    "public": 3,
    "cards": 4,
}


@dataclass(frozen=True)
class KnowledgeDocument:
    path: str
    title: str
    category: str
    category_label: str
    preview: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceItem:
    path: str
    title: str
    category: str
    category_label: str
    line: int
    snippet: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


def resolve_aibrother_root(workspace: str | Path | None = None) -> Path:
    """Resolve the AIBrother workspace root containing ``knowledge/``."""
    candidates: list[Path] = []
    if workspace is not None:
        ws = Path(workspace).expanduser()
        candidates.extend([ws, ws / "aibrother"])

    repo_root = Path(__file__).resolve().parents[2]
    candidates.extend([repo_root / "aibrother", repo_root])

    for candidate in candidates:
        resolved = candidate.resolve(strict=False)
        if (resolved / "knowledge").is_dir():
            return resolved
    return (repo_root / "aibrother").resolve(strict=False)


class KnowledgeIndex:
    """Small SQLite FTS index over ``aibrother/knowledge`` Markdown files."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = resolve_aibrother_root(root)
        self.knowledge_dir = self.root / "knowledge"
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self.reindex()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE VIRTUAL TABLE chunks USING fts5(
                path UNINDEXED,
                title,
                category UNINDEXED,
                category_label UNINDEXED,
                line UNINDEXED,
                content,
                tokenize='unicode61'
            );
            """
        )

    def reindex(self) -> None:
        self._conn.execute("DELETE FROM chunks")
        for doc in self._markdown_files():
            text = doc.read_text(encoding="utf-8", errors="replace")
            title = _title_from_text(text, doc.stem)
            category = _category_for(self.knowledge_dir, doc)
            category_label = _CATEGORY_LABELS.get(category, category)
            for line, chunk in _chunks(text):
                self._conn.execute(
                    """
                    INSERT INTO chunks(path, title, category, category_label, line, content)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _rel(doc, self.root),
                        title,
                        category,
                        category_label,
                        line,
                        chunk,
                    ),
                )
        self._conn.commit()

    def documents(self) -> list[KnowledgeDocument]:
        docs: list[KnowledgeDocument] = []
        for path in self._markdown_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            category = _category_for(self.knowledge_dir, path)
            docs.append(
                KnowledgeDocument(
                    path=_rel(path, self.root),
                    title=_title_from_text(text, path.stem),
                    category=category,
                    category_label=_CATEGORY_LABELS.get(category, category),
                    preview=_preview(text),
                )
            )
        return docs

    def read_file(self, relative_path: str) -> dict[str, str]:
        path = self._resolve_knowledge_path(relative_path)
        text = path.read_text(encoding="utf-8", errors="replace")
        category = _category_for(self.knowledge_dir, path)
        return {
            "path": _rel(path, self.root),
            "title": _title_from_text(text, path.stem),
            "category": category,
            "category_label": _CATEGORY_LABELS.get(category, category),
            "content": text,
        }

    def search(self, query: str, *, limit: int = 8) -> list[EvidenceItem]:
        query = query.strip()
        if not query:
            return []

        items: list[EvidenceItem] = []
        fts_query = _fts_query(query)
        try:
            rows = self._conn.execute(
                """
                SELECT path, title, category, category_label, line,
                       snippet(chunks, 5, '', '', ' ... ', 18) AS snippet
                FROM chunks
                WHERE chunks MATCH ?
                ORDER BY bm25(chunks)
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = self._conn.execute(
                """
                SELECT path, title, category, category_label, line, content AS snippet
                FROM chunks
                WHERE content LIKE ?
                LIMIT ?
                """,
                (f"%{query}%", limit),
            ).fetchall()

        items.extend(
            EvidenceItem(
                path=row["path"],
                title=row["title"],
                category=row["category"],
                category_label=row["category_label"],
                line=int(row["line"]),
                snippet=_clean_snippet(row["snippet"]),
            )
            for row in rows
        )

        seen = {(item.path, item.line) for item in items}
        for term in _like_terms(query):
            if len(items) >= limit:
                break
            like_rows = self._conn.execute(
                """
                SELECT path, title, category, category_label, line, content AS snippet
                FROM chunks
                WHERE content LIKE ?
                LIMIT ?
                """,
                (f"%{term}%", limit),
            ).fetchall()
            for row in like_rows:
                key = (row["path"], int(row["line"]))
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    EvidenceItem(
                        path=row["path"],
                        title=row["title"],
                        category=row["category"],
                        category_label=row["category_label"],
                        line=int(row["line"]),
                        snippet=_clean_snippet(row["snippet"]),
                    )
                )
                if len(items) >= limit:
                    break
        items.sort(key=lambda item: _CATEGORY_PRIORITY.get(item.category, 99))
        return items[:limit]

    def answer(self, query: str, mode: str = "experiment") -> dict[str, object]:
        evidence = self.search(query, limit=6)
        mode_label = {
            "experiment": "做实验",
            "paper": "写论文",
            "presentation": "做汇报",
            "journal": "做日记",
        }.get(mode, "做实验")
        if not evidence:
            answer = (
                f"我暂时没有在课题组知识库里检索到和「{query}」直接相关的内容。"
                "建议补充实验手册、组会记录或论文摘要后再问。"
            )
        else:
            bullets = "\n".join(
                f"- [{item.category_label}] {item.title}:{item.line} - {item.snippet}"
                for item in evidence[:4]
            )
            answer = (
                f"按「{mode_label}」场景，我先从课题组知识库里找到了这些证据：\n\n"
                f"{bullets}\n\n"
                "初步建议：优先依据实验室手册和组内记录；如果结论来自论文或外部资料，"
                "需要在正式实验/写作前再核对原文。"
            )
        return {
            "mode": mode,
            "query": query,
            "answer": answer,
            "evidence": [item.to_dict() for item in evidence],
        }

    def _markdown_files(self) -> list[Path]:
        if not self.knowledge_dir.is_dir():
            return []
        return sorted(
            path
            for path in self.knowledge_dir.rglob("*.md")
            if path.is_file() and not any(part.startswith(".") for part in path.parts)
        )

    def _resolve_knowledge_path(self, relative_path: str) -> Path:
        cleaned = relative_path.replace("\\", "/").lstrip("/")
        path = (self.root / cleaned).resolve(strict=False)
        knowledge_root = self.knowledge_dir.resolve(strict=False)
        if not path.is_relative_to(knowledge_root):
            raise ValueError("path must stay inside aibrother/knowledge")
        if not path.is_file() or path.suffix.lower() != ".md":
            raise FileNotFoundError(relative_path)
        return path


def _chunks(text: str, *, max_chars: int = 900) -> list[tuple[int, str]]:
    chunks: list[tuple[int, str]] = []
    current: list[str] = []
    current_start = 1
    current_len = 0
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            if current:
                current.append("")
            continue
        if current and (stripped.startswith("#") or current_len + len(stripped) > max_chars):
            chunks.append((current_start, "\n".join(current).strip()))
            current = []
            current_len = 0
        if not current:
            current_start = line_no
        current.append(line)
        current_len += len(line) + 1
    if current:
        chunks.append((current_start, "\n".join(current).strip()))
    return [(line, chunk) for line, chunk in chunks if chunk]


def _title_from_text(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback.replace("_", " ").strip()


def _category_for(knowledge_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(knowledge_dir).parts[0]
    except (ValueError, IndexError):
        return "knowledge"


def _preview(text: str) -> str:
    body = re.sub(r"\s+", " ", text).strip()
    return body[:180]


def _rel(path: Path, root: Path) -> str:
    return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query, flags=re.UNICODE)
    return " OR ".join(tokens) if tokens else query


def _like_terms(query: str) -> list[str]:
    terms = [query]
    terms.extend(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", query, flags=re.UNICODE))
    deduped: list[str] = []
    for term in terms:
        cleaned = term.strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _clean_snippet(snippet: str) -> str:
    return re.sub(r"\s+", " ", snippet).strip()
