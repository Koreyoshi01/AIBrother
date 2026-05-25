import tempfile
import unittest
from pathlib import Path

from nanobot.aibrother.chat_knowledge import (
    ChatKnowledgeStore,
    archive_session_turn,
    extract_latest_turn,
)
from nanobot.aibrother.knowledge import KnowledgeIndex, index_archived_chat_turn
from nanobot.session.manager import Session


class ChatKnowledgeTests(unittest.TestCase):
    def test_extract_latest_turn_skips_commands(self) -> None:
        session = Session(key="websocket:test")
        session.messages = [
            {"role": "user", "content": "/stop"},
            {"role": "assistant", "content": "已停止"},
        ]
        self.assertIsNone(extract_latest_turn(session))

    def test_extract_latest_turn_across_tool_calls(self) -> None:
        session = Session(key="websocket:test")
        session.messages = [
            {"role": "user", "content": "NaOH溶液放哪里了"},
            {
                "role": "assistant",
                "content": "我来查一下知识库。",
                "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "grep"}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "grep", "content": "found"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "call_2"}]},
            {"role": "tool", "tool_call_id": "call_2", "name": "grep", "content": "cabinet"},
            {"role": "assistant", "content": "NaOH溶液在左手边第二个柜子上。"},
        ]
        pair = extract_latest_turn(session)
        self.assertIsNotNone(pair)
        user, assistant = pair or ({}, {})
        self.assertEqual(user.get("content"), "NaOH溶液放哪里了")
        self.assertIn("柜子上", assistant.get("content", ""))

    def test_archive_turn_writes_db_md_and_search_index(self) -> None:
        root = Path(tempfile.mkdtemp())
        (root / "knowledge" / "group_knowledge").mkdir(parents=True)
        session = Session(key="websocket:chat-1")
        session.metadata["title"] = "CO2 吸收讨论"
        session.messages = [
            {
                "role": "user",
                "content": "CO2吸收实验用什么吸收剂？",
                "knowledge_imports": [{
                    "filename": "paper.pdf",
                    "path": "knowledge/group_knowledge/uploads/paper.pdf",
                }],
            },
            {"role": "assistant", "content": "常用 30 wt% MEA，性价比高。"},
        ]

        turn_id = archive_session_turn(session, workspace=root)
        self.assertIsNotNone(turn_id)

        store = ChatKnowledgeStore(root)
        try:
            hits = store.search("MEA", limit=3)
            self.assertTrue(hits)
            self.assertIn("CO2吸收实验", hits[0]["user_message"])
        finally:
            store.close()

        history = (root / "knowledge/group_knowledge/conversation_history.md").read_text(
            encoding="utf-8",
        )
        self.assertIn("CO2吸收实验用什么吸收剂", history)
        self.assertIn("paper.pdf", history)

        index = KnowledgeIndex(root)
        index_archived_chat_turn(root, turn_id or 0)
        results = index.search("MEA", limit=5)
        self.assertTrue(any("chat_archive.db" in item.path for item in results))

        turn_id_again = archive_session_turn(session, workspace=root)
        self.assertIsNone(turn_id_again)


if __name__ == "__main__":
    unittest.main()
