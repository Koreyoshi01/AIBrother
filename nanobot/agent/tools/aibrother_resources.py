"""AI Brother resource import and search tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aibrother.resources import (
    RESOURCE_CATEGORY_LABELS,
    RESOURCE_LIBRARY_DIR,
    ResourceRecord,
    import_resource,
    read_resource_records,
)
from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import IntegerSchema, StringSchema, tool_parameters_schema


_CATEGORY_VALUES = list(RESOURCE_CATEGORY_LABELS)
_STATUS_VALUES = ["draft", "ready", "needs_review"]


def _is_under(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory.resolve())
        return True
    except ValueError:
        return False


class _AIBrotherResourceTool(Tool):
    def __init__(
        self,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
    ) -> None:
        self._workspace = Path(workspace).resolve() if workspace else None
        self._allowed_dir = Path(allowed_dir).resolve() if allowed_dir else None

    @classmethod
    def create(cls, ctx: Any) -> Tool:
        exec_config = getattr(ctx.config, "exec", None)
        restrict = (
            getattr(ctx.config, "restrict_to_workspace", False)
            or getattr(exec_config, "sandbox", False)
        )
        workspace = Path(ctx.workspace)
        return cls(
            workspace=workspace,
            allowed_dir=workspace if restrict else None,
        )

    def _resolve(self, path: str) -> Path:
        target = Path(path).expanduser()
        if not target.is_absolute() and self._workspace:
            target = self._workspace / target
        resolved = target.resolve()
        if self._allowed_dir and not _is_under(resolved, self._allowed_dir):
            raise PermissionError(
                f"Path {path} is outside allowed directory {self._allowed_dir}"
            )
        return resolved


def _resource_root_for_workspace(workspace: Path | None) -> Path:
    if workspace is None:
        return RESOURCE_LIBRARY_DIR

    workspace = workspace.resolve()
    if (
        (workspace / "knowledge").exists()
        or (workspace / "SOUL.md").exists()
        or (workspace / "skills" / "ask_senior").exists()
    ):
        return workspace / "knowledge" / "resources"

    package_workspace = workspace / "aibrother"
    if (package_workspace / "knowledge").exists():
        return package_workspace / "knowledge" / "resources"

    return RESOURCE_LIBRARY_DIR


def _record_payload(record: ResourceRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "category": record.category,
        "category_label": RESOURCE_CATEGORY_LABELS[record.category],
        "title": record.title,
        "status": record.status,
        "tags": record.tags,
        "key_findings": record.key_findings,
        "summary": record.summary,
        "summary_md_path": record.summary_md_path,
        "original_path": record.original_path,
        "original_filename": record.original_filename,
        "imported_at": record.imported_at,
    }


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _match_record(record: ResourceRecord, query: str | None) -> tuple[bool, int, str]:
    if not query or not query.strip():
        return True, 0, record.summary[:240]

    haystack_parts = [
        record.title,
        record.original_filename,
        " ".join(record.tags),
        " ".join(record.key_findings),
        record.summary,
    ]
    haystack = "\n".join(haystack_parts)
    lowered = haystack.lower()
    terms = [term for term in query.lower().split() if term]
    if not terms:
        terms = [query.lower().strip()]

    if not all(term in lowered for term in terms):
        return False, 0, ""

    score = 0
    title_lowered = record.title.lower()
    for term in terms:
        if term in title_lowered:
            score += 5
        if any(term in tag.lower() for tag in record.tags):
            score += 3
        if any(term in finding.lower() for finding in record.key_findings):
            score += 2
        if term in record.summary.lower():
            score += 1

    snippet_source = record.summary or "；".join(record.key_findings)
    snippet = snippet_source[:240]
    return True, score, snippet


@tool_parameters(
    tool_parameters_schema(
        path=StringSchema("Workspace-relative or absolute file path to import."),
        category=StringSchema(
            "Resource category: group meeting PPT, experiment records, or read papers.",
            enum=_CATEGORY_VALUES,
        ),
        title=StringSchema("Optional resource title.", nullable=True),
        status=StringSchema(
            "Review status for the imported resource.",
            enum=_STATUS_VALUES,
            nullable=True,
        ),
        required=["path", "category"],
    )
)
class AIBrotherImportResourceTool(_AIBrotherResourceTool):
    """Import a user-provided file into the AI Brother resource library."""

    _scopes = {"core"}

    @property
    def name(self) -> str:
        return "aibrother_import_resource"

    @property
    def description(self) -> str:
        return (
            "Import one file into AI Brother's resource library. "
            "Use this when the user uploads or points to group meeting PPTs, "
            "experiment records, or already-read papers. The tool copies the "
            "original, extracts a first-pass summary, tags/key findings, and "
            "updates the resource index."
        )

    async def execute(
        self,
        path: str | None = None,
        category: str | None = None,
        title: str | None = None,
        status: str | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            if not path:
                return "Error: path is required."
            if not category:
                return "Error: category is required."

            source = self._resolve(path)
            root = _resource_root_for_workspace(self._workspace)
            record = import_resource(
                source,
                category=category,  # type: ignore[arg-type]
                title=title or None,
                root=root,
                status=(status or "draft"),  # type: ignore[arg-type]
            )
            return _json(
                {
                    "ok": True,
                    "resource_root": root.as_posix(),
                    "resource": _record_payload(record),
                }
            )
        except Exception as exc:
            return f"Error importing AI Brother resource: {exc}"


@tool_parameters(
    tool_parameters_schema(
        query=StringSchema("Search query. Leave empty to list recent resources.", nullable=True),
        category=StringSchema("Optional category filter.", enum=_CATEGORY_VALUES, nullable=True),
        limit=IntegerSchema(
            5,
            description="Maximum number of resources to return.",
            minimum=1,
            maximum=20,
        ),
    )
)
class AIBrotherSearchResourcesTool(_AIBrotherResourceTool):
    """Search imported AI Brother resources."""

    _scopes = {"core"}

    @property
    def name(self) -> str:
        return "aibrother_search_resources"

    @property
    def description(self) -> str:
        return (
            "Search AI Brother's imported resource index by title, tags, key "
            "findings, and summary. Use this before broader filesystem or web "
            "searches for experiments, papers, reports, and diary/resource recall."
        )

    @property
    def read_only(self) -> bool:
        return True

    async def execute(
        self,
        query: str | None = None,
        category: str | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            root = _resource_root_for_workspace(self._workspace)
            records = read_resource_records(root)
            if category:
                records = [
                    record
                    for record in records
                    if record.category == category
                ]

            matches: list[tuple[int, ResourceRecord, str]] = []
            for record in records:
                matched, score, snippet = _match_record(record, query)
                if matched:
                    matches.append((score, record, snippet))

            cap = limit or 5
            matches.sort(key=lambda item: (item[0], item[1].imported_at), reverse=True)
            payload = [
                {
                    **_record_payload(record),
                    "match_score": score,
                    "snippet": snippet,
                }
                for score, record, snippet in matches[:cap]
            ]
            return _json(
                {
                    "ok": True,
                    "resource_root": root.as_posix(),
                    "count": len(payload),
                    "resources": payload,
                }
            )
        except Exception as exc:
            return f"Error searching AI Brother resources: {exc}"
