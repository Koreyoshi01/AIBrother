"""Knowledge import helpers shared by the agent loop and WebUI surfaces."""

from __future__ import annotations

from typing import Any, Mapping


def _clip_string(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return text[:limit]


def normalize_knowledge_imports(raw: Any) -> list[dict[str, Any]]:
    """Sanitize structured knowledge imports sent by the WebUI."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        filename = _clip_string(item.get("filename"), 260)
        path = _clip_string(item.get("path"), 512)
        if not filename or not path or ".." in path or not path.startswith("knowledge/"):
            continue
        if path in seen:
            continue
        seen.add(path)
        row: dict[str, Any] = {"filename": filename, "path": path}
        title = _clip_string(item.get("title"), 260)
        if title and title != filename:
            row["title"] = title
        size_bytes = item.get("size_bytes")
        if isinstance(size_bytes, (int, float)) and size_bytes >= 0:
            row["size_bytes"] = int(size_bytes)
        mime_type = _clip_string(item.get("mime_type"), 128)
        if mime_type:
            row["mime_type"] = mime_type
        out.append(row)
    return out


def session_extra(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return persisted session kwargs for knowledge imports attached to a turn."""
    imports = metadata.get("knowledge_imports") if isinstance(metadata, Mapping) else None
    return (
        {"knowledge_imports": imports}
        if isinstance(imports, list) and imports
        else {}
    )


def _display_label(item: Mapping[str, Any]) -> str:
    filename = str(item.get("filename") or "").strip()
    title = str(item.get("title") or "").strip()
    if title and title != filename:
        return f"{filename}（{title}）"
    return filename


def _runtime_line(item: Mapping[str, Any]) -> str:
    label = _display_label(item)
    path = str(item.get("path") or "").strip()
    return (
        f"Knowledge Import Attachment: {label} → {path}. "
        "Use read_file on this path when answering the user's question."
    )


def _replay_breadcrumb(item: Mapping[str, Any]) -> str:
    label = _display_label(item)
    path = str(item.get("path") or "").strip()
    return f"[Knowledge Import: {label} → {path}; tool=read_file]"


def runtime_lines(message: Any, *, skip: bool = False) -> list[str]:
    """Return model-visible knowledge import annotations for the current turn."""
    if skip:
        return []
    metadata = message.metadata if isinstance(getattr(message, "metadata", None), Mapping) else None
    structured = metadata.get("knowledge_imports") if isinstance(metadata, Mapping) else None
    if not isinstance(structured, list):
        return []
    lines: list[str] = []
    for item in structured[:8]:
        if isinstance(item, Mapping) and item.get("path"):
            lines.append(_runtime_line(item))
    return lines


def replay_breadcrumbs(imports: list[Any]) -> list[str]:
    """Return LLM replay breadcrumbs for persisted knowledge imports."""
    lines: list[str] = []
    for item in imports[:8]:
        if isinstance(item, Mapping) and item.get("path"):
            lines.append(_replay_breadcrumb(item))
    return lines
