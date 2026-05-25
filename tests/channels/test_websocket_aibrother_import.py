"""WebSocket ``aibrother_import`` envelope handling."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.aibrother.knowledge import KnowledgeIndex
from nanobot.channels.websocket import WebSocketChannel


def _make_channel() -> WebSocketChannel:
    bus = MagicMock()
    bus.publish_inbound = AsyncMock()
    channel = WebSocketChannel(
        {"enabled": True, "allowFrom": ["*"], "websocketRequiresToken": False},
        bus,
    )
    channel._handle_message = AsyncMock()  # type: ignore[method-assign]
    return channel


def _tiny_png_data_url() -> str:
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
        b"\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx"
        b"\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb4\x00"
        b"\x00\x00\x00IEND\xaeB`\x82"
    )
    return f"data:image/png;base64,{base64.b64encode(png).decode()}"


@pytest.fixture
def channel() -> WebSocketChannel:
    return _make_channel()


@pytest.fixture
def mock_conn() -> MagicMock:
    conn = MagicMock()
    conn.send = AsyncMock()
    return conn


@pytest.mark.asyncio
async def test_aibrother_import_indexes_text_file(
    channel: WebSocketChannel,
    mock_conn: MagicMock,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "aibrother"
    (workspace / "knowledge" / "group_knowledge" / "uploads").mkdir(parents=True)
    data_url = _tiny_png_data_url()
    request_id = "req-1"

    with (
        patch("nanobot.channels.websocket.get_workspace_path", return_value=workspace),
        patch("nanobot.channels.websocket.get_media_dir", return_value=tmp_path / "media"),
    ):
        await channel._dispatch_envelope(
            mock_conn,
            "client-1",
            {
                "type": "aibrother_import",
                "request_id": request_id,
                "data_url": data_url,
                "name": "figure.png",
            },
        )

    mock_conn.send.assert_awaited()
    raw = mock_conn.send.await_args.args[0]
    event = json.loads(raw)
    assert event["event"] == "aibrother_imported"
    assert event["request_id"] == request_id
    assert event["document"]["path"].endswith(".md")
    assert (workspace / event["document"]["path"]).is_file()
    assets_dir = workspace / "knowledge" / "group_knowledge" / "uploads" / "assets"
    assert any(assets_dir.glob("*.png"))


@pytest.mark.asyncio
async def test_aibrother_import_indexes_txt_file(
    channel: WebSocketChannel,
    mock_conn: MagicMock,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "aibrother"
    (workspace / "knowledge" / "group_knowledge" / "uploads").mkdir(parents=True)
    payload = base64.b64encode("课题组实验记录".encode()).decode()
    data_url = f"data:text/plain;base64,{payload}"
    request_id = "req-txt"

    with (
        patch("nanobot.channels.websocket.get_workspace_path", return_value=workspace),
        patch("nanobot.channels.websocket.get_media_dir", return_value=tmp_path / "media"),
    ):
        await channel._dispatch_envelope(
            mock_conn,
            "client-1",
            {
                "type": "aibrother_import",
                "request_id": request_id,
                "data_url": data_url,
                "name": "notes.txt",
            },
        )

    raw = mock_conn.send.await_args.args[0]
    event = json.loads(raw)
    assert event["event"] == "aibrother_imported"
    assert event["document"]["path"].endswith(".md")
    text = (workspace / event["document"]["path"]).read_text(encoding="utf-8")
    assert "课题组实验记录" in text


@pytest.mark.asyncio
async def test_aibrother_asset_serves_uploaded_image(
    channel: WebSocketChannel,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "aibrother"
    assets = workspace / "knowledge" / "group_knowledge" / "uploads" / "assets"
    assets.mkdir(parents=True)
    png = assets / "demo.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00"
        b"\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx"
        b"\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x18\xdd\x8d\xb4\x00"
        b"\x00\x00\x00IEND\xaeB`\x82"
    )
    channel._api_tokens["test-token"] = 9999999999.0
    request = MagicMock()
    request.path = (
        "/api/aibrother/asset?"
        "path=knowledge/group_knowledge/uploads/assets/demo.png&token=test-token"
    )
    request.headers = {}

    with patch("nanobot.channels.websocket.get_workspace_path", return_value=workspace):
        import nanobot.channels.websocket as ws_mod

        ws_mod._AIBROTHER_INDEX = KnowledgeIndex(workspace)
        response = channel._handle_aibrother_asset(request)

    assert response.status_code == 200
    assert response.body.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_aibrother_asset_serves_uploaded_pdf(
    channel: WebSocketChannel,
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "aibrother"
    uploads = workspace / "knowledge" / "group_knowledge" / "uploads"
    uploads.mkdir(parents=True)
    pdf = uploads / "paper_demo.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    channel._api_tokens["test-token"] = 9999999999.0
    request = MagicMock()
    request.path = (
        "/api/aibrother/asset?"
        "path=knowledge/group_knowledge/uploads/paper_demo.pdf&token=test-token"
    )
    request.headers = {}

    with patch("nanobot.channels.websocket.get_workspace_path", return_value=workspace):
        import nanobot.channels.websocket as ws_mod

        ws_mod._AIBROTHER_INDEX = KnowledgeIndex(workspace)
        response = channel._handle_aibrother_asset(request)

    assert response.status_code == 200
    assert response.body.startswith(b"%PDF")
    assert response.headers.get("Content-Type") == "application/pdf"


@pytest.mark.asyncio
async def test_aibrother_import_rejects_missing_data_url(
    channel: WebSocketChannel,
    mock_conn: MagicMock,
) -> None:
    await channel._dispatch_envelope(
        mock_conn,
        "client-1",
        {"type": "aibrother_import", "request_id": "req-2"},
    )
    raw = mock_conn.send.await_args.args[0]
    event = json.loads(raw)
    assert event["event"] == "aibrother_import_failed"
    assert event["request_id"] == "req-2"
