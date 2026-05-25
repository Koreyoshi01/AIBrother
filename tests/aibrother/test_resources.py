import asyncio
from pathlib import Path

from aibrother import (
    ensure_resource_library,
    import_resource,
    read_resource_records,
    rebuild_resource_index_md,
)
from aibrother.resources import RESOURCE_CATEGORY_LABELS
from nanobot.agent.tools.aibrother_resources import (
    AIBrotherImportResourceTool,
    AIBrotherSearchResourcesTool,
)


def test_ensure_resource_library_creates_expected_layout(tmp_path: Path) -> None:
    root = ensure_resource_library(tmp_path)

    assert (root / "RESOURCE_INDEX.md").is_file()
    assert (root / "resources.jsonl").is_file()
    for category in RESOURCE_CATEGORY_LABELS:
        assert (root / category).is_dir()
        assert (root / "originals" / category).is_dir()


def test_import_resource_writes_summary_and_indexes(tmp_path: Path) -> None:
    source = tmp_path / "co2_notes.md"
    source.write_text(
        "\n".join(
            [
                "# MEA CO2 absorption notes",
                "实验结果：30 wt% MEA 在 30°C 时吸收效率最高，达到 92%。",
                "结论：气体流量过大会降低吸收效率，需要降低到 0.5-0.8 L/min。",
                "下一步：补充循环吸收解析实验。",
            ]
        ),
        encoding="utf-8",
    )
    library = tmp_path / "library"

    record = import_resource(
        source,
        "experiment_records",
        title="MEA CO2 absorption notes",
        root=library,
        status="ready",
    )

    records = read_resource_records(library)
    summary_path = library / "experiment_records" / f"{record.id}.md"
    index_text = (library / "RESOURCE_INDEX.md").read_text(encoding="utf-8")
    jsonl_text = (library / "resources.jsonl").read_text(encoding="utf-8")

    assert [item.id for item in records] == [record.id]
    assert record.category == "experiment_records"
    assert record.status == "ready"
    assert record.content_hash
    assert "CO2" in record.tags
    assert any("吸收效率" in item for item in record.key_findings)
    assert summary_path.is_file()
    assert "最重要结论" in summary_path.read_text(encoding="utf-8")
    assert "MEA CO2 absorption notes" in index_text
    assert record.id in jsonl_text

    duplicate = import_resource(
        source,
        "experiment_records",
        title="Duplicate title should not create a new row",
        root=library,
        status="ready",
    )
    assert duplicate.id == record.id
    assert len(read_resource_records(library)) == 1


def test_rebuild_resource_index_from_jsonl(tmp_path: Path) -> None:
    source = tmp_path / "paper.txt"
    source.write_text(
        "Conclusion: Ionic liquids can reduce solvent loss, but high viscosity limits mass transfer.",
        encoding="utf-8",
    )
    library = tmp_path / "library"
    record = import_resource(source, "read_papers", root=library)

    (library / "RESOURCE_INDEX.md").write_text("stale", encoding="utf-8")
    rebuild_resource_index_md(library)

    index_text = (library / "RESOURCE_INDEX.md").read_text(encoding="utf-8")
    assert "已读文章" in index_text
    assert record.id in index_text or record.title in index_text


def test_aibrother_resource_tools_import_and_search(tmp_path: Path) -> None:
    workspace = tmp_path / "aibrother"
    source = workspace / "uploads" / "paper_note.md"
    source.parent.mkdir(parents=True)
    (workspace / "knowledge").mkdir()
    source.write_text(
        "Conclusion: MEA regeneration energy is high, and blended amines reduce solvent loss.",
        encoding="utf-8",
    )

    import_tool = AIBrotherImportResourceTool(workspace=workspace)
    import_result = asyncio.run(
        import_tool.execute(
            path="uploads/paper_note.md",
            category="read_papers",
            title="MEA regeneration note",
            status="ready",
        )
    )
    assert '"ok": true' in import_result
    assert "MEA regeneration note" in import_result

    search_tool = AIBrotherSearchResourcesTool(workspace=workspace)
    search_result = asyncio.run(
        search_tool.execute(query="regeneration", category="read_papers", limit=3)
    )
    assert '"count": 1' in search_result
    assert "MEA regeneration note" in search_result
