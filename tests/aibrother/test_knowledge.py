from pathlib import Path
import unittest
from unittest.mock import patch

from nanobot.aibrother.knowledge import KnowledgeIndex, resolve_aibrother_root


class AIBrotherKnowledgeTests(unittest.TestCase):
    def test_resolve_aibrother_root_prefers_workspace(self) -> None:
        workspace = Path(__file__).resolve().parents[2] / "aibrother"

        root = resolve_aibrother_root(workspace)

        self.assertEqual(root, workspace)
        self.assertTrue((root / "knowledge").is_dir())

    def test_search_returns_source_path_and_line(self) -> None:
        root = Path(__file__).resolve().parents[2] / "aibrother"
        index = KnowledgeIndex(root)

        results = index.search("CO2 吸收 试剂", limit=3)

        self.assertTrue(results)
        top = results[0]
        self.assertTrue(top.path.endswith(".md"))
        self.assertIsInstance(top.line, int)
        self.assertGreaterEqual(top.line, 1)
        self.assertIn("knowledge/", top.path)
        self.assertTrue(top.snippet)

    def test_read_file_rejects_paths_outside_knowledge(self) -> None:
        root = Path(__file__).resolve().parents[2] / "aibrother"
        index = KnowledgeIndex(root)

        with self.assertRaises(ValueError):
            index.read_file("../config.json")

    def test_import_file_writes_markdown_and_indexes(self) -> None:
        import tempfile

        root = Path(tempfile.mkdtemp())
        (root / "knowledge" / "group_knowledge" / "uploads").mkdir(parents=True)
        index = KnowledgeIndex(root)
        source = root / "sample.txt"
        source.write_text("课题组测试文档内容", encoding="utf-8")

        document = index.import_file(source, original_name="实验记录.txt")

        self.assertIn("uploads/", document.path)
        self.assertTrue(document.path.endswith(".md"))
        md_path = root / document.path
        self.assertTrue(md_path.is_file())
        text = md_path.read_text(encoding="utf-8")
        self.assertIn("课题组测试文档内容", text)
        self.assertIn("实验记录.txt", text)
        results = index.search("课题组测试文档", limit=3)
        self.assertTrue(any(document.path in item.path for item in results))

    def test_resolve_asset_path_serves_uploaded_image(self) -> None:
        import tempfile

        root = Path(tempfile.mkdtemp())
        uploads = root / "knowledge" / "group_knowledge" / "uploads"
        assets = uploads / "assets"
        assets.mkdir(parents=True)
        png = assets / "demo.png"
        png.write_bytes(b"\x89PNG\r\n")
        index = KnowledgeIndex(root)

        resolved = index.resolve_asset_path("knowledge/group_knowledge/uploads/assets/demo.png")

        self.assertEqual(resolved, png.resolve())

    def test_import_pdf_stores_binary_and_indexes_text(self) -> None:
        import tempfile

        root = Path(tempfile.mkdtemp())
        (root / "knowledge" / "group_knowledge" / "uploads").mkdir(parents=True)
        (root / "knowledge" / "papers").mkdir(parents=True)
        index = KnowledgeIndex(root)
        source = root / "paper.pdf"
        source.write_bytes(b"%PDF-1.4 paper")

        with patch(
            "nanobot.aibrother.knowledge.extract_text",
            return_value="Generative Pre-Trained Diffusion 时间序列 forecasting results",
        ):
            document = index.import_file(source, original_name="2406.02212v1.pdf")

        self.assertTrue(document.path.endswith(".pdf"))
        self.assertTrue((root / document.path).is_file())
        summaries = (root / "knowledge" / "papers" / "summaries.md").read_text(encoding="utf-8")
        self.assertIn("2406.02212v1", summaries)
        self.assertIn(document.path, summaries)
        self.assertIn("时间序列", summaries)
        results = index.search("时间序列", limit=3)
        self.assertTrue(any(document.path in item.path for item in results))
        summary_hits = index.search("Generative Pre-Trained Diffusion", limit=5)
        self.assertTrue(any("papers/summaries.md" in item.path for item in summary_hits))

    def test_sync_paper_summaries_backfills_existing_pdf(self) -> None:
        import tempfile

        root = Path(tempfile.mkdtemp())
        uploads = root / "knowledge" / "group_knowledge" / "uploads"
        papers = root / "knowledge" / "papers"
        uploads.mkdir(parents=True)
        papers.mkdir(parents=True)
        pdf = uploads / "2506-12623v1_abcd1234.pdf"
        pdf.write_bytes(b"%PDF-1.4 cached paper")

        with patch(
            "nanobot.aibrother.knowledge.extract_text",
            return_value="CO2 capture using amine solvents kinetic study",
        ):
            index = KnowledgeIndex(root)

        summaries = (papers / "summaries.md").read_text(encoding="utf-8")
        self.assertIn("CO2 capture", summaries)
        self.assertIn("knowledge/group_knowledge/uploads/2506-12623v1_abcd1234.pdf", summaries)
        hits = index.search("CO2 capture", limit=5)
        self.assertTrue(any("papers/summaries.md" in item.path for item in hits))

    def test_read_file_marks_pdf_documents(self) -> None:
        import tempfile

        root = Path(tempfile.mkdtemp())
        uploads = root / "knowledge" / "group_knowledge" / "uploads"
        uploads.mkdir(parents=True)
        pdf = uploads / "demo_abcd1234.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        index = KnowledgeIndex(root)

        payload = index.read_file("knowledge/group_knowledge/uploads/demo_abcd1234.pdf")

        self.assertEqual(payload["media_type"], "application/pdf")
        self.assertEqual(payload["content"], "")


if __name__ == "__main__":
    unittest.main()
