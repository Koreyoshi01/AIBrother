"""Resource import and indexing workflow for AI Brother.

The resource library keeps uploaded files as immutable originals and writes
human-readable Markdown summaries plus a machine-readable JSONL index.  The
index is deliberately rebuildable from local files so later RAG work can use
the same source of truth without changing the import flow.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


ResourceCategory = Literal["group_meeting_ppt", "experiment_records", "read_papers"]
ResourceStatus = Literal["draft", "ready", "needs_review"]

RESOURCE_CATEGORY_LABELS: dict[ResourceCategory, str] = {
    "group_meeting_ppt": "组会PPT",
    "experiment_records": "实验记录",
    "read_papers": "已读文章",
}

RESOURCE_CATEGORY_TAGS: dict[ResourceCategory, list[str]] = {
    "group_meeting_ppt": ["组会", "PPT", "汇报"],
    "experiment_records": ["实验记录", "实验", "数据"],
    "read_papers": ["论文", "文献", "已读文章"],
}

RESOURCE_LIBRARY_DIR = Path(__file__).with_name("knowledge") / "resources"
RESOURCE_ORIGINALS_DIR = RESOURCE_LIBRARY_DIR / "originals"
RESOURCE_INDEX_MD = RESOURCE_LIBRARY_DIR / "RESOURCE_INDEX.md"
RESOURCE_INDEX_JSONL = RESOURCE_LIBRARY_DIR / "resources.jsonl"

_MAX_ANALYSIS_CHARS = 60_000
_MAX_SUMMARY_CHARS = 1_200
_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".log",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
}


@dataclass(slots=True)
class ResourceRecord:
    id: str
    category: ResourceCategory
    title: str
    original_filename: str
    original_path: str
    summary_md_path: str
    tags: list[str]
    key_findings: list[str]
    source_type: str
    imported_at: str
    content_hash: str = ""
    status: ResourceStatus = "draft"
    summary: str = ""
    questions: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "original_filename": self.original_filename,
            "original_path": self.original_path,
            "summary_md_path": self.summary_md_path,
            "tags": self.tags,
            "key_findings": self.key_findings,
            "source_type": self.source_type,
            "imported_at": self.imported_at,
            "content_hash": self.content_hash,
            "status": self.status,
            "summary": self.summary,
            "questions": self.questions,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ResourceRecord":
        return cls(
            id=str(data["id"]),
            category=_validate_category(str(data["category"])),
            title=str(data.get("title") or data["id"]),
            original_filename=str(data.get("original_filename") or ""),
            original_path=str(data.get("original_path") or ""),
            summary_md_path=str(data.get("summary_md_path") or ""),
            tags=[str(item) for item in data.get("tags", [])],
            key_findings=[str(item) for item in data.get("key_findings", [])],
            source_type=str(data.get("source_type") or ""),
            imported_at=str(data.get("imported_at") or ""),
            content_hash=str(data.get("content_hash") or ""),
            status=_validate_status(str(data.get("status") or "draft")),
            summary=str(data.get("summary") or ""),
            questions=[str(item) for item in data.get("questions", [])],
        )


def ensure_resource_library(root: str | Path = RESOURCE_LIBRARY_DIR) -> Path:
    """Create the resource library directory layout if it does not exist."""

    base = Path(root)
    base.mkdir(parents=True, exist_ok=True)
    for category in RESOURCE_CATEGORY_LABELS:
        (base / category).mkdir(parents=True, exist_ok=True)
        (base / "originals" / category).mkdir(parents=True, exist_ok=True)
    if not (base / "RESOURCE_INDEX.md").exists():
        (base / "RESOURCE_INDEX.md").write_text(_empty_index_md(), encoding="utf-8")
    if not (base / "resources.jsonl").exists():
        (base / "resources.jsonl").write_text("", encoding="utf-8")
    return base


def import_resource(
    file_path: str | Path,
    category: ResourceCategory,
    *,
    title: str | None = None,
    root: str | Path = RESOURCE_LIBRARY_DIR,
    status: ResourceStatus = "draft",
) -> ResourceRecord:
    """Import one file into the AI Brother resource library.

    The original file is copied under ``originals/<category>/``. A Markdown
    analysis note is written under ``<category>/`` and both JSONL and Markdown
    indexes are refreshed.
    """

    category = _validate_category(category)
    status = _validate_status(status)
    base = ensure_resource_library(root)
    source = Path(file_path)
    if not source.is_file():
        raise FileNotFoundError(f"Resource file not found: {source}")

    imported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    content_hash = _file_digest(source)
    existing = _find_existing_resource(base, category, content_hash)
    if existing is not None:
        return existing

    derived_title = title or _title_from_filename(source)
    resource_id = _resource_id(imported_at, derived_title, content_hash)
    safe_name = f"{resource_id}_{_safe_filename(source.name)}"
    original_path = base / "originals" / category / safe_name
    shutil.copy2(source, original_path)

    text = extract_text(original_path)
    analysis = analyze_resource(text, category, title=derived_title, filename=source.name)
    summary_path = base / category / f"{resource_id}.md"
    record = ResourceRecord(
        id=resource_id,
        category=category,
        title=analysis["title"],
        original_filename=source.name,
        original_path=_display_path(original_path),
        summary_md_path=_display_path(summary_path),
        tags=analysis["tags"],
        key_findings=analysis["key_findings"],
        source_type=source.suffix.lower().lstrip(".") or "file",
        imported_at=imported_at,
        content_hash=content_hash,
        status=status,
        summary=analysis["summary"],
        questions=analysis["questions"],
    )
    write_summary_md(record, summary_path)
    upsert_resource_record(record, root=base)
    rebuild_resource_index_md(root=base)
    return record


def extract_text(path: str | Path) -> str:
    """Extract text from a resource file, returning an empty string on failure."""

    fp = Path(path)
    if fp.suffix.lower() in _TEXT_EXTENSIONS:
        return _read_text_file(fp)[:_MAX_ANALYSIS_CHARS]

    try:
        from nanobot.utils.document import extract_text as extract_document_text
    except ImportError:
        return ""

    extracted = extract_document_text(fp)
    if extracted is None or extracted.startswith("[error:"):
        return ""
    return extracted[:_MAX_ANALYSIS_CHARS]


def analyze_resource(
    text: str,
    category: ResourceCategory,
    *,
    title: str | None = None,
    filename: str = "",
) -> dict[str, Any]:
    """Produce a conservative first-pass analysis for an imported resource."""

    category = _validate_category(category)
    normalized = _normalize_text(text)
    inferred_title = title or _title_from_text(normalized) or _title_from_filename(filename)
    tags = _unique([*RESOURCE_CATEGORY_TAGS[category], *_keyword_tags(normalized)])
    key_findings = _key_findings(normalized, category)
    summary = _summary_from_text(normalized, key_findings)
    questions = _questions_from_text(normalized, category)
    if not normalized:
        questions = _unique(["未能抽取正文，需要人工补充摘要或检查文件格式。", *questions])

    return {
        "title": inferred_title,
        "tags": tags[:10],
        "key_findings": key_findings[:5],
        "summary": summary,
        "questions": questions[:5],
    }


def write_summary_md(record: ResourceRecord, path: str | Path | None = None) -> Path:
    """Write the human-readable Markdown summary for one resource."""

    output_path = Path(path or record.summary_md_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_summary_md(record), encoding="utf-8", newline="\n")
    return output_path


def read_resource_records(root: str | Path = RESOURCE_LIBRARY_DIR) -> list[ResourceRecord]:
    """Read all resource records from the JSONL index."""

    path = Path(root) / "resources.jsonl"
    if not path.exists():
        return []
    records: list[ResourceRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(ResourceRecord.from_json(json.loads(line)))
    return records


def write_resource_records(
    records: list[ResourceRecord],
    root: str | Path = RESOURCE_LIBRARY_DIR,
) -> Path:
    """Write the JSONL index in a stable order."""

    base = ensure_resource_library(root)
    path = base / "resources.jsonl"
    ordered = sorted(records, key=lambda item: (item.imported_at, item.id))
    payload = "\n".join(
        json.dumps(record.to_json(), ensure_ascii=False, sort_keys=True)
        for record in ordered
    )
    path.write_text(payload + ("\n" if payload else ""), encoding="utf-8", newline="\n")
    return path


def upsert_resource_record(
    record: ResourceRecord,
    root: str | Path = RESOURCE_LIBRARY_DIR,
) -> list[ResourceRecord]:
    """Insert or replace one resource record by id."""

    records = [item for item in read_resource_records(root) if item.id != record.id]
    records.append(record)
    write_resource_records(records, root=root)
    return records


def rebuild_resource_index_md(root: str | Path = RESOURCE_LIBRARY_DIR) -> Path:
    """Rebuild the human-readable Markdown resource index from JSONL."""

    base = ensure_resource_library(root)
    records = read_resource_records(base)
    content = _resource_index_md(records)
    path = base / "RESOURCE_INDEX.md"
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _find_existing_resource(
    root: Path,
    category: ResourceCategory,
    content_hash: str,
) -> ResourceRecord | None:
    if not content_hash:
        return None
    for record in read_resource_records(root):
        if record.category == category and record.content_hash == content_hash:
            return record
    return None


def _validate_category(value: str) -> ResourceCategory:
    if value not in RESOURCE_CATEGORY_LABELS:
        expected = ", ".join(RESOURCE_CATEGORY_LABELS)
        raise ValueError(f"Unknown resource category {value!r}; expected one of: {expected}")
    return value  # type: ignore[return-value]


def _validate_status(value: str) -> ResourceStatus:
    if value not in {"draft", "ready", "needs_review"}:
        raise ValueError("Resource status must be draft, ready, or needs_review")
    return value  # type: ignore[return-value]


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resource_id(imported_at: str, title: str, digest: str) -> str:
    day = imported_at[:10].replace("-", "")
    seed = f"{imported_at}|{title}|{digest}".encode("utf-8")
    suffix = hashlib.sha1(seed).hexdigest()[:8]
    return f"res_{day}_{suffix}"


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", value, flags=re.UNICODE).strip("._")
    return cleaned or "resource"


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _title_from_filename(value: str | Path) -> str:
    name = Path(value).stem if value else "未命名资源"
    return re.sub(r"[_\-]+", " ", name).strip() or "未命名资源"


def _title_from_text(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip(" #\t")
        if 4 <= len(stripped) <= 80:
            return stripped
    return ""


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _keyword_tags(text: str) -> list[str]:
    candidates = [
        "CO2",
        "MEA",
        "MDEA",
        "吸收",
        "解析",
        "再生",
        "离子液体",
        "相变吸收剂",
        "动力学",
        "传质",
        "组会",
        "PPT",
        "实验方案",
        "实验结果",
        "综述",
        "论文",
    ]
    lowered = text.lower()
    tags: list[str] = []
    for candidate in candidates:
        if candidate.lower() in lowered:
            tags.append(candidate)
    return tags


def _key_findings(text: str, category: ResourceCategory) -> list[str]:
    if not text:
        return ["正文未能抽取，暂无法自动生成关键结论。"]

    lines = _candidate_lines(text)
    priority = {
        "group_meeting_ppt": ["结论", "总结", "下一步", "问题", "结果", "progress", "conclusion"],
        "experiment_records": ["结果", "现象", "问题", "结论", "备注", "效率", "容量"],
        "read_papers": ["conclusion", "result", "finding", "takeaway", "结论", "结果", "发现", "提出"],
    }[category]
    ranked = sorted(
        lines,
        key=lambda line: (
            not any(token.lower() in line.lower() for token in priority),
            len(line),
        ),
    )
    return _unique(ranked)[:5] or ["未识别到明确结论，需要人工补充。"]


def _candidate_lines(text: str) -> list[str]:
    raw_lines = re.split(r"[\n。；;]+", text)
    lines: list[str] = []
    for line in raw_lines:
        stripped = line.strip(" -•\t")
        if 12 <= len(stripped) <= 180:
            lines.append(stripped)
    return lines[:80]


def _summary_from_text(text: str, key_findings: list[str]) -> str:
    if not text:
        return "未能从原文件中抽取可用正文。"
    intro = "；".join(key_findings[:3])
    if intro:
        return intro[:_MAX_SUMMARY_CHARS]
    return text[:_MAX_SUMMARY_CHARS]


def _questions_from_text(text: str, category: ResourceCategory) -> list[str]:
    questions = []
    if category == "group_meeting_ppt":
        questions.append("是否需要补充本次组会的提问、导师反馈和后续任务？")
    elif category == "experiment_records":
        questions.append("是否需要补充原始数据表、实验条件和异常排查记录？")
    elif category == "read_papers":
        questions.append("是否需要补充 DOI、引用格式和与本课题的关联评价？")
    if len(text) < 200:
        questions.append("正文较短，建议人工确认摘要是否充分。")
    return questions


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(RESOURCE_LIBRARY_DIR.parent.parent).as_posix()
    except ValueError:
        return path.as_posix()


def _summary_md(record: ResourceRecord) -> str:
    label = RESOURCE_CATEGORY_LABELS[record.category]
    tags = ", ".join(record.tags) if record.tags else "待补充"
    findings = "\n".join(f"- {item}" for item in record.key_findings)
    questions = "\n".join(f"- {item}" for item in record.questions) or "- 无"
    return f"""# {record.title}

## 元信息
- 资源ID：{record.id}
- 分类：{label}
- 原文件：{record.original_filename}
- 原文件路径：`{record.original_path}`
- 导入时间：{record.imported_at}
- 状态：{record.status}
- 标签：{tags}

## 最重要结论
{findings}

## 摘要
{record.summary}

## 待确认问题
{questions}
"""


def _empty_index_md() -> str:
    return _resource_index_md([])


def _resource_index_md(records: list[ResourceRecord]) -> str:
    lines = [
        "# AI Brother 资源索引",
        "",
        "此文件由资源导入流程维护，用于人工快速查看已导入资源；结构化索引见 `resources.jsonl`。",
        "",
    ]
    if not records:
        lines.append("暂无已导入资源。")
        lines.append("")
        return "\n".join(lines)

    for category, label in RESOURCE_CATEGORY_LABELS.items():
        group = [record for record in records if record.category == category]
        lines.extend([f"## {label}", ""])
        if not group:
            lines.extend(["暂无。", ""])
            continue
        lines.append("| 标题 | 标签 | 关键结论 | 摘要文件 | 导入时间 |")
        lines.append("|---|---|---|---|---|")
        for record in group:
            tags = ", ".join(record.tags[:5])
            finding = record.key_findings[0] if record.key_findings else ""
            lines.append(
                "| "
                + " | ".join(
                    [
                        _escape_table(record.title),
                        _escape_table(tags),
                        _escape_table(finding),
                        f"`{record.summary_md_path}`",
                        record.imported_at,
                    ]
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines)


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
