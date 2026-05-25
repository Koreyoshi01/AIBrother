"""Markdown-backed AIBrother knowledge retrieval."""

from __future__ import annotations

import re
import shutil
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from nanobot.utils.document import extract_text
from nanobot.utils.helpers import safe_filename


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

_ASSET_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"})
_KNOWLEDGE_DOC_EXTENSIONS = frozenset({".md", ".pdf"})
_SERVEABLE_EXTENSIONS = _ASSET_EXTENSIONS | {".pdf"}


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
        self._sync_paper_summaries()
        for doc in self._markdown_files():
            self._index_text_file(doc)
        for pdf in self._pdf_files():
            self._index_pdf_file(pdf)
        self._conn.commit()

    def _index_text_file(self, doc: Path) -> None:
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

    def _index_pdf_file(self, pdf: Path) -> None:
        extracted = extract_text(pdf)
        if not extracted or extracted.startswith("[error:"):
            return
        title = _title_from_filename(pdf.stem)
        category = _category_for(self.knowledge_dir, pdf)
        category_label = _CATEGORY_LABELS.get(category, category)
        for line, chunk in _chunks(extracted):
            self._conn.execute(
                """
                INSERT INTO chunks(path, title, category, category_label, line, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _rel(pdf, self.root),
                    title,
                    category,
                    category_label,
                    line,
                    chunk,
                ),
            )

    def documents(self) -> list[KnowledgeDocument]:
        docs: list[KnowledgeDocument] = []
        for path in self._markdown_files():
            docs.append(self._document_for_path(path))
        for path in self._pdf_files():
            docs.append(self._document_for_path(path))
        return docs

    def _document_for_path(self, path: Path) -> KnowledgeDocument:
        category = _category_for(self.knowledge_dir, path)
        if path.suffix.lower() == ".pdf":
            extracted = extract_text(path)
            preview = _preview(extracted) if extracted and not extracted.startswith("[error:") else "PDF 文档"
            title = _title_from_filename(path.stem)
        else:
            text = path.read_text(encoding="utf-8", errors="replace")
            preview = _preview(text)
            title = _title_from_text(text, path.stem)
        return KnowledgeDocument(
            path=_rel(path, self.root),
            title=title,
            category=category,
            category_label=_CATEGORY_LABELS.get(category, category),
            preview=preview,
        )

    def read_file(self, relative_path: str) -> dict[str, str]:
        path = self._resolve_knowledge_path(relative_path)
        category = _category_for(self.knowledge_dir, path)
        if path.suffix.lower() == ".pdf":
            return {
                "path": _rel(path, self.root),
                "title": _title_from_filename(path.stem),
                "category": category,
                "category_label": _CATEGORY_LABELS.get(category, category),
                "content": "",
                "media_type": "application/pdf",
            }
        text = path.read_text(encoding="utf-8", errors="replace")
        return {
            "path": _rel(path, self.root),
            "title": _title_from_text(text, path.stem),
            "category": category,
            "category_label": _CATEGORY_LABELS.get(category, category),
            "content": text,
            "media_type": "text/markdown",
        }

    def import_file(self, source: Path, *, original_name: str | None = None) -> KnowledgeDocument:
        """Import an uploaded file into ``knowledge/group_knowledge/uploads``."""
        if not isinstance(source, Path):
            source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(str(source))

        display_name = original_name or source.name
        ext = Path(display_name).suffix.lower()
        uploads_dir = self.knowledge_dir / "group_knowledge" / "uploads"
        assets_dir = uploads_dir / "assets"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(parents=True, exist_ok=True)

        slug = _safe_slug(Path(display_name).stem)
        suffix = uuid.uuid4().hex[:8]
        imported_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            asset_name = safe_filename(f"{suffix}_{Path(display_name).name}")
            asset_path = assets_dir / asset_name
            shutil.copy2(source, asset_path)
            asset_rel = f"assets/{asset_name}"
            title = Path(display_name).stem.replace("_", " ").strip() or display_name
            md_path = uploads_dir / f"{slug}_{suffix}.md"
            md_path.write_text(
                "\n".join(
                    [
                        f"# {title}",
                        "",
                        f"> 来源文件：{display_name} · 导入于 {imported_at}",
                        "",
                        f"![{display_name}]({asset_rel})",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            stored_path = md_path
        elif ext == ".pdf":
            pdf_name = safe_filename(f"{slug}_{suffix}.pdf")
            stored_path = uploads_dir / pdf_name
            shutil.copy2(source, stored_path)
            self._append_paper_summary(
                pdf_path=stored_path,
                original_name=display_name,
                imported_at=imported_at,
            )
        else:
            extracted = extract_text(source)
            if extracted is None:
                raise ValueError(f"unsupported file type: {display_name}")
            if extracted.startswith("[error:"):
                raise ValueError(extracted)
            title = Path(display_name).stem.replace("_", " ").strip() or display_name
            stored_path = uploads_dir / f"{slug}_{suffix}.md"
            stored_path.write_text(
                "\n".join(
                    [
                        f"# {title}",
                        "",
                        f"> 来源文件：{display_name} · 导入于 {imported_at}",
                        "",
                        extracted.strip(),
                        "",
                    ]
                ),
                encoding="utf-8",
            )

        self.reindex()
        return self._document_for_path(stored_path)

    def resolve_asset_path(self, relative_path: str) -> Path:
        """Resolve a knowledge asset path and ensure it stays inside ``knowledge/``."""
        cleaned = relative_path.replace("\\", "/").lstrip("/")
        path = (self.root / cleaned).resolve(strict=False)
        knowledge_root = self.knowledge_dir.resolve(strict=False)
        if not path.is_relative_to(knowledge_root):
            raise ValueError("path must stay inside aibrother/knowledge")
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        if path.suffix.lower() not in _SERVEABLE_EXTENSIONS:
            raise ValueError(f"unsupported asset type: {path.suffix}")
        return path

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

    def _pdf_files(self) -> list[Path]:
        uploads = self.knowledge_dir / "group_knowledge" / "uploads"
        if not uploads.is_dir():
            return []
        return sorted(
            path
            for path in uploads.rglob("*.pdf")
            if path.is_file() and not any(part.startswith(".") for part in path.parts)
        )

    def _resolve_knowledge_path(self, relative_path: str) -> Path:
        cleaned = relative_path.replace("\\", "/").lstrip("/")
        path = (self.root / cleaned).resolve(strict=False)
        knowledge_root = self.knowledge_dir.resolve(strict=False)
        if not path.is_relative_to(knowledge_root):
            raise ValueError("path must stay inside aibrother/knowledge")
        if not path.is_file() or path.suffix.lower() not in _KNOWLEDGE_DOC_EXTENSIONS:
            raise FileNotFoundError(relative_path)
        return path


    def _summaries_path(self) -> Path:
        return self.knowledge_dir / "papers" / "summaries.md"

    def _sync_paper_summaries(self) -> None:
        """Append auto-generated entries for uploaded PDFs missing from summaries.md."""
        summaries_path = self._summaries_path()
        existing = (
            summaries_path.read_text(encoding="utf-8")
            if summaries_path.is_file()
            else ""
        )
        for pdf in self._pdf_files():
            rel_pdf = _rel(pdf, self.root)
            if _paper_summary_present(existing, rel_pdf):
                if not _paper_summary_needs_refresh(existing, rel_pdf):
                    continue
                existing = _remove_paper_summary_block(existing, rel_pdf)
            imported_at = datetime.fromtimestamp(
                pdf.stat().st_mtime,
                tz=UTC,
            ).strftime("%Y-%m-%d %H:%M UTC")
            section = self._build_paper_summary_section(
                pdf_path=pdf,
                original_name=pdf.name,
                imported_at=imported_at,
            )
            existing = _append_paper_summary_text(existing, section, summaries_path)

    def _append_paper_summary(
        self,
        *,
        pdf_path: Path,
        original_name: str,
        imported_at: str,
    ) -> None:
        summaries_path = self._summaries_path()
        existing = (
            summaries_path.read_text(encoding="utf-8")
            if summaries_path.is_file()
            else ""
        )
        rel_pdf = _rel(pdf_path, self.root)
        if _paper_summary_present(existing, rel_pdf):
            return
        section = self._build_paper_summary_section(
            pdf_path=pdf_path,
            original_name=original_name,
            imported_at=imported_at,
        )
        _append_paper_summary_text(existing, section, summaries_path)

    def _build_paper_summary_section(
        self,
        *,
        pdf_path: Path,
        original_name: str,
        imported_at: str,
    ) -> str:
        extracted = extract_text(pdf_path)
        if not extracted or extracted.startswith("[error:"):
            extracted = ""
        analysis_text = _paper_analysis_text(extracted)
        title = _paper_title_from_text(extracted) or _paper_heading(original_name, extracted)
        key_findings = _paper_key_findings_from_abstract(analysis_text)
        tags = _paper_tags_from_text(title, analysis_text)
        summary = _paper_brief_summary(analysis_text, key_findings)
        if not summary and analysis_text:
            summary = re.sub(r"\s+", " ", analysis_text).strip()[:1200]
        if not summary:
            summary = "未能从 PDF 中抽取可用正文，请人工补充摘要。"
        return _format_paper_summary_section(
            heading=title,
            original_name=original_name,
            pdf_rel=_rel(pdf_path, self.root),
            imported_at=imported_at,
            summary=summary,
            key_findings=key_findings,
            tags=tags,
        )


def _paper_summary_present(summaries_text: str, pdf_rel: str) -> bool:
    return _paper_summary_block(summaries_text, pdf_rel) is not None


def _paper_summary_block(summaries_text: str, pdf_rel: str) -> str | None:
    marker = f"`{pdf_rel}`"
    if marker not in summaries_text and pdf_rel not in summaries_text:
        return None
    parts = re.split(r"(?=^## )", summaries_text, flags=re.MULTILINE)
    for part in parts:
        if marker in part or pdf_rel in part:
            return part
    return None


def _paper_summary_needs_refresh(summaries_text: str, pdf_rel: str) -> bool:
    block = _paper_summary_block(summaries_text, pdf_rel)
    if not block:
        return False
    if "自动生成摘要" not in block:
        return False
    weak_markers = (
        "Accuracy (%)",
        "Pages(Images)",
        "query_update",
        "1 Introduction",
        "1. Introduction",
        "@",
        "Our APE",
        "Tip-Adapter",
        "--- Page 1 ---",
        "未识别到明确结论",
        "Proceedings of the",
        "Not All Features Matter:",
        "**关键结论**:",
        "Shengyu Dai",
        "arXiv:",
        "Xiangyu Yin",
    )
    return any(marker in block for marker in weak_markers) or (
        "**要点**: 未识别到明确结论" in block
    )


def _remove_paper_summary_block(summaries_text: str, pdf_rel: str) -> str:
    block = _paper_summary_block(summaries_text, pdf_rel)
    if not block:
        return summaries_text
    updated = summaries_text.replace(block, "", 1)
    return re.sub(r"\n{3,}", "\n\n", updated).strip() + "\n"


def _append_paper_summary_text(
    existing: str,
    section: str,
    summaries_path: Path,
) -> str:
    summaries_path.parent.mkdir(parents=True, exist_ok=True)
    if not existing.strip():
        body = "# 相关论文摘要\n\n" + section.strip() + "\n"
    else:
        body = existing.rstrip() + "\n\n" + section.strip() + "\n"
    summaries_path.write_text(body, encoding="utf-8")
    return body


def _paper_heading(original_name: str, extracted: str = "") -> str:
    title = _paper_title_from_text(extracted)
    if title:
        return title
    stem = Path(original_name).stem
    match = re.match(
        r"^(?P<id>\d{4}[._-]\d{4,5}(?:v\d+)?)",
        stem,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group("id").replace("_", ".").replace("-", ".")
    return _title_from_filename(stem)


def _paper_title_from_text(text: str) -> str:
    """Best-effort title from the first page of an academic PDF."""
    if not text:
        return ""
    normalized = _normalize_pdf_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    abstract_idx = next(
        (index for index, line in enumerate(lines) if line.lower().startswith("abstract")),
        len(lines),
    )
    title_lines: list[str] = []
    for line in lines[:abstract_idx]:
        if _is_venue_boilerplate(line) or _is_author_line(line):
            continue
        title_lines.append(line)
    return _merge_title_lines(title_lines)


def _is_venue_boilerplate(line: str) -> bool:
    lowered = line.lower()
    patterns = (
        "proceedings of the",
        "conference on",
        "association for computational linguistics",
        "pages ",
        "©",
        "copyright",
        "equal contribution",
        "workshop on",
        "transactions on",
        "journal of",
        "accepted at",
        "under review",
        "preprint",
        "arxiv:",
    )
    if any(token in lowered for token in patterns):
        return True
    if re.search(r"\bpages?\s+\d", lowered):
        return True
    if re.fullmatch(r"\d{4,5}", line.strip()):
        return True
    if re.search(r"\[[a-z\.]+\]", lowered) and re.search(r"\d{4}", line):
        return True
    return False


def _is_author_line(line: str) -> bool:
    lowered = line.lower()
    if "@" in line:
        return True
    if re.search(r"[A-Za-z'\-]+\d+[,\*]", line):
        return True
    if re.search(r"\b(university|institute|laboratory|college|inc\.|ltd\.|corporation)\b", lowered):
        return True
    if re.search(r"\b\d{1,2}\s*,\s*\*", line):
        return True
    if re.match(r"^[\{\[].*[\}\]]@", line):
        return True
    if re.match(r"^[A-Z][A-Za-z\-']+(?:,\s*[A-Z][A-Za-z\-']+){2,}", line) and re.search(r"\d", line):
        return True
    tokens = line.split()
    if len(tokens) >= 4 and ":" not in line:
        name_like = sum(1 for token in tokens if re.match(r"^[A-Z][A-Za-z'\-]+$", token))
        if name_like >= 4 and len(line) < 220:
            return True
    return False


def _merge_title_lines(lines: list[str]) -> str:
    if not lines:
        return ""
    title = lines[0]
    merged_count = 1
    for extra in lines[1:4]:
        if extra.lower().startswith(("abstract", "keywords", "index terms")):
            break
        if _is_author_line(extra) or _is_venue_boilerplate(extra):
            break
        if len(title) >= 160:
            break
        if merged_count >= 2 and ":" in title:
            break
        title = f"{title} {extra}"
        merged_count += 1
    return re.sub(r"\s+", " ", title).strip()


def _paper_key_findings_from_abstract(text: str) -> list[str]:
    if not text:
        return []
    normalized = re.sub(r"\s+", " ", text).strip()
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if sentence.strip()
    ]
    boost_patterns = (
        r"\bwe introduce\b",
        r"\bwe propose\b",
        r"\bwe present\b",
        r"\bwe collect\b",
        r"\bwe study\b",
        r"\boutperform",
        r"\bachieve[sd]?\b",
        r"\bimprov",
        r"\b\d+(?:\.\d+)?%",
        r"\bstate-of-the-art\b",
        r"\bnovel\b",
        r"\bframework\b",
        r"\bdataset\b",
        r"\bbenchmark\b",
        r"\bresults?\b",
    )
    scored: list[tuple[int, str]] = []
    for sentence in sentences:
        if len(sentence) < 30 or len(sentence) > 260:
            continue
        score = sum(1 for pattern in boost_patterns if re.search(pattern, sentence, re.I))
        if score <= 0:
            continue
        scored.append((score, sentence))
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    findings = [sentence for _, sentence in scored[:4]]
    if findings:
        return findings
    fallback = [sentence for sentence in sentences if 40 <= len(sentence) <= 260]
    if len(fallback) >= 2:
        return [fallback[0], fallback[min(2, len(fallback) - 1)]]
    if fallback:
        return [fallback[0]]
    return []


def _paper_tags_from_text(title: str, text: str) -> list[str]:
    combined = f"{title}\n{text}"
    tags: list[str] = []
    if ":" in title:
        method = title.split(":", 1)[0].strip()
        if 2 <= len(method) <= 40:
            tags.append(method)
    for acronym in re.findall(r"\b[A-Z]{2,}[A-Z0-9]*\b", combined):
        if acronym in {"PDF", "URL", "UTC", "ACL", "DOI", "ET", "AL", "AI"}:
            continue
        if len(acronym) <= 12:
            tags.append(acronym)
    keyword_map = (
        ("document visual question answering", "DocVQA"),
        ("retrieval augmented generation", "RAG"),
        ("retrieval-augmented generation", "RAG"),
        ("visual language model", "VLM"),
        ("multi-modal", "Multi-modal"),
        ("multimodal", "Multi-modal"),
        ("instructional video", "Instructional Video"),
        ("document understanding", "Document Understanding"),
        ("contrastive language-image", "CLIP"),
        ("few-shot", "Few-shot"),
        ("gait", "Gait Analysis"),
        ("prosthetic", "Prosthetics"),
        ("co2", "CO2"),
    )
    lowered = combined.lower()
    for phrase, label in keyword_map:
        if phrase in lowered and label not in tags:
            tags.append(label)
    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tag)
    return deduped[:8] or ["Paper"]


def _paper_brief_summary(text: str, key_findings: list[str]) -> str:
    if key_findings:
        return " ".join(key_findings[:3])[:900]
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text).strip()
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if len(sentence.strip()) >= 40
    ]
    if len(sentences) >= 2:
        return f"{sentences[0]} {sentences[1]}"[:900]
    return normalized[:900]


def _normalize_pdf_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"--- Page \d+ ---\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", cleaned)
    return cleaned


def _paper_analysis_text(text: str) -> str:
    """Prefer abstract/introduction blocks when building auto summaries."""
    if not text:
        return ""
    normalized = _normalize_pdf_text(text)
    patterns = (
        r"(?is)\babstract\b[:\s-]*\n(.{120,5000}?)(?:\n\s*(?:keywords|index terms|1[\.\s]+introduction)\b)",
        r"(?is)\b摘要\b[：:\s-]*\n(.{80,5000}?)(?:\n\s*(?:关键词|1[\.\s、]+引言)\b)",
        r"(?is)\b1[\.\s]+introduction\b[:\s-]*\n(.{120,3000}?)(?:\n\s*2[\.\s]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            block = re.sub(r"\s+", " ", match.group(1)).strip()
            if len(block) >= 80:
                return block[:6000]
    return normalized[:6000]


def _format_paper_summary_section(
    *,
    heading: str,
    original_name: str,
    pdf_rel: str,
    imported_at: str,
    summary: str,
    key_findings: list[str],
    tags: list[str],
) -> str:
    lines = [
        f"## {heading.strip()}",
        f"- **标题**: {heading.strip()}",
        f"- **来源文件**: {original_name}",
        f"- **原文路径**: `{pdf_rel}`",
        f"- **导入时间**: {imported_at}",
        f"- **要点**: {summary.strip()}",
    ]
    if key_findings:
        for idx, finding in enumerate(key_findings[:4], start=1):
            lines.append(f"- **结论{idx}**: {finding.strip()}")
    if tags:
        lines.append(f"- **标签**: {', '.join(tags[:8])}")
    lines.append("- **状态**: 自动生成摘要，建议人工核对")
    return "\n".join(lines)


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
    return _title_from_filename(fallback)


def _title_from_filename(stem: str) -> str:
    cleaned = re.sub(r"_[0-9a-f]{8}$", "", stem, flags=re.IGNORECASE)
    return cleaned.replace("_", " ").replace("-", " ").strip() or stem


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


def _safe_slug(name: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", name.strip(), flags=re.UNICODE)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned[:80] or "upload"
