from pathlib import Path
import unittest

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


if __name__ == "__main__":
    unittest.main()
