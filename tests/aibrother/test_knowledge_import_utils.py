"""Tests for knowledge import metadata helpers."""

from __future__ import annotations

from nanobot.aibrother.knowledge_import_utils import (
    normalize_knowledge_imports,
    replay_breadcrumbs,
    runtime_lines,
    session_extra,
)


class _Msg:
    metadata = {
        "knowledge_imports": [{
            "filename": "2506.12623v1.pdf",
            "path": "knowledge/group_knowledge/uploads/2506-12623v1_cb344e93.pdf",
            "title": "2506 12623v1",
        }],
    }


def test_session_extra_returns_knowledge_imports_only_when_present() -> None:
    imports = [{"filename": "a.pdf", "path": "knowledge/x/a.pdf"}]
    assert session_extra({"knowledge_imports": imports}) == {"knowledge_imports": imports}
    assert session_extra({}) == {}


def test_normalize_knowledge_imports_rejects_unsafe_paths() -> None:
    assert normalize_knowledge_imports([
        {"filename": "bad.pdf", "path": "../secrets.pdf"},
        {"filename": "good.pdf", "path": "knowledge/group_knowledge/uploads/good.pdf"},
    ]) == [{"filename": "good.pdf", "path": "knowledge/group_knowledge/uploads/good.pdf"}]


def test_runtime_lines_include_read_file_guidance() -> None:
    lines = runtime_lines(_Msg())
    assert len(lines) == 1
    assert "2506.12623v1.pdf" in lines[0]
    assert "read_file" in lines[0]


def test_replay_breadcrumbs_for_session_history() -> None:
    lines = replay_breadcrumbs([{
        "filename": "2506.12623v1.pdf",
        "path": "knowledge/group_knowledge/uploads/2506-12623v1_cb344e93.pdf",
    }])
    assert lines == [
        "[Knowledge Import: 2506.12623v1.pdf → "
        "knowledge/group_knowledge/uploads/2506-12623v1_cb344e93.pdf; tool=read_file]"
    ]
