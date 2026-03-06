"""Tests for workspace manager routes."""

import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) in sys.path:
    sys.path.remove(str(SRC_PATH))
sys.path.insert(0, str(SRC_PATH))

for module_name in list(sys.modules.keys()):
    if module_name == "vibes" or module_name.startswith("vibes."):
        sys.modules.pop(module_name, None)

workspace_mod = importlib.import_module("vibes.routes.workspace")


@pytest.fixture
def workspace_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest_asyncio.fixture
async def workspace_test_client(temp_db_path, workspace_dir):
    from vibes.db import close_db, init_db

    workspace_mod._workspace_visible = False
    workspace_mod._workspace_show_hidden = False
    workspace_mod._workspace_last_signature = None
    workspace_mod._workspace_pending_updates = {}
    workspace_mod._workspace_throttle_task = None

    app = web.Application()
    workspace_mod.setup_routes(app)

    await init_db(temp_db_path)
    try:
        async with TestClient(TestServer(app)) as client:
            yield client
    finally:
        await workspace_mod.shutdown_workspace_manager()
        workspace_mod._workspace_last_signature = None
        await close_db()


def _child_names(node):
    return [child["name"] for child in node.get("children", [])]


class TestWorkspaceTreeRoutes:
    @pytest.mark.asyncio
    async def test_tree_depth_and_hidden_filter(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "visible.txt").write_text("ok", encoding="utf-8")
        (workspace_dir / ".hidden.txt").write_text("hidden", encoding="utf-8")
        (workspace_dir / "folder").mkdir()
        (workspace_dir / "folder" / "nested.txt").write_text("nested", encoding="utf-8")

        resp = await client.get("/workspace/tree?depth=1")
        assert resp.status == 200
        data = await resp.json()
        root = data["root"]
        names = _child_names(root)
        assert "visible.txt" in names
        assert ".hidden.txt" not in names
        folder_node = next(node for node in root["children"] if node["name"] == "folder")
        # At depth=1, subdirectories have no children key (not yet loaded)
        assert "children" not in folder_node

        resp = await client.get("/workspace/tree?depth=2&show_hidden=1")
        assert resp.status == 200
        data = await resp.json()
        root = data["root"]
        names = _child_names(root)
        assert ".hidden.txt" in names
        folder_node = next(node for node in root["children"] if node["name"] == "folder")
        assert any(child["name"] == "nested.txt" for child in folder_node["children"])

    @pytest.mark.asyncio
    async def test_tree_not_found_and_forbidden(self, workspace_test_client):
        client = workspace_test_client

        resp = await client.get("/workspace/tree?path=missing")
        assert resp.status == 404

        resp = await client.get("/workspace/tree?path=../outside")
        assert resp.status == 403


class TestWorkspaceFileRoutes:
    @pytest.mark.asyncio
    async def test_file_text_and_truncation(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "note.txt").write_text("hello workspace", encoding="utf-8")
        (workspace_dir / "big.txt").write_text("a" * 400, encoding="utf-8")
        (workspace_dir / "dir").mkdir()

        resp = await client.get("/workspace/file")
        assert resp.status == 400

        resp = await client.get("/workspace/file?path=note.txt")
        assert resp.status == 200
        data = await resp.json()
        assert data["kind"] == "text"
        assert data["text"] == "hello workspace"
        assert data["truncated"] is False

        resp = await client.get("/workspace/file?path=big.txt&max=256")
        assert resp.status == 200
        data = await resp.json()
        assert data["kind"] == "text"
        assert data["truncated"] is True
        assert len(data["text"]) == 256

        resp = await client.get("/workspace/file?path=dir")
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_file_image_binary_and_not_found(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "image.png").write_bytes(b"not-really-an-image")
        (workspace_dir / "blob.bin").write_bytes(b"\x00" * 300)

        resp = await client.get("/workspace/file?path=image.png")
        assert resp.status == 200
        data = await resp.json()
        assert data["kind"] == "image"
        assert data["url"].endswith("/workspace/raw?path=image.png")

        resp = await client.get("/workspace/file?path=blob.bin&max=1")
        assert resp.status == 200
        data = await resp.json()
        assert data["kind"] == "binary"
        assert data["truncated"] is True

        resp = await client.get("/workspace/file?path=nope.bin")
        assert resp.status == 404


class TestWorkspaceRawAndAttachRoutes:
    @pytest.mark.asyncio
    async def test_raw_route_success_and_errors(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "doc.txt").write_text("raw text", encoding="utf-8")
        (workspace_dir / "folder").mkdir()

        resp = await client.get("/workspace/raw")
        assert resp.status == 400

        resp = await client.get("/workspace/raw?path=folder")
        assert resp.status == 404

        resp = await client.get("/workspace/raw?path=missing.txt")
        assert resp.status == 404

        resp = await client.get("/workspace/raw?path=doc.txt")
        assert resp.status == 200
        assert await resp.read() == b"raw text"

    @pytest.mark.asyncio
    async def test_attach_route_validation_and_media_creation(self, workspace_test_client, workspace_dir):
        from vibes.db import get_db

        client = workspace_test_client
        (workspace_dir / "upload.txt").write_text("upload me", encoding="utf-8")

        resp = await client.post(
            "/workspace/attach",
            data="{",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

        resp = await client.post("/workspace/attach", json={})
        assert resp.status == 400

        resp = await client.post("/workspace/attach", json={"path": "missing.txt"})
        assert resp.status == 404

        resp = await client.post("/workspace/attach", json={"path": "upload.txt"})
        assert resp.status == 200
        body = await resp.json()
        media_id = body["media_id"]
        assert isinstance(media_id, int)

        db = await get_db()
        media = await db.get_media(media_id)
        media_blob = await db.get_media_data(media_id)
        assert media is not None
        assert media["filename"] == "upload.txt"
        assert media["metadata"]["workspace_path"] == "upload.txt"
        assert media_blob is not None
        assert media_blob[1] == b"upload me"


class TestWorkspaceVisibilityRoute:
    @pytest.mark.asyncio
    async def test_visibility_broadcast_and_change_detection(self, workspace_test_client, workspace_dir, monkeypatch):
        client = workspace_test_client
        (workspace_dir / ".hidden.txt").write_text("secret", encoding="utf-8")
        (workspace_dir / "visible.txt").write_text("visible", encoding="utf-8")

        broadcast_mock = AsyncMock()
        monkeypatch.setattr(workspace_mod, "broadcast_event", broadcast_mock)
        monkeypatch.setattr(workspace_mod, "awatch", None)
        monkeypatch.setattr(workspace_mod, "_workspace_poll_interval_s", 3600.0)

        resp = await client.post(
            "/workspace/visibility",
            data="{",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

        resp = await client.post("/workspace/visibility", json={"visible": True, "show_hidden": True})
        assert resp.status == 200
        body = await resp.json()
        assert body == {"ok": True, "visible": True, "show_hidden": True}
        assert broadcast_mock.await_count == 1
        event_name, payload = broadcast_mock.await_args_list[0].args
        assert event_name == "workspace_update"
        root_children = _child_names(payload["updates"][0]["root"])
        assert ".hidden.txt" in root_children
        assert "visible.txt" in root_children

        await workspace_mod._broadcast_workspace_tree_if_changed()
        assert broadcast_mock.await_count == 1

        (workspace_dir / "new.txt").write_text("new", encoding="utf-8")
        await workspace_mod._broadcast_workspace_tree_if_changed()
        assert broadcast_mock.await_count == 2

        resp = await client.post("/workspace/visibility", json={"visible": False, "show_hidden": False})
        assert resp.status == 200
        assert workspace_mod._workspace_poll_task is None

    @pytest.mark.asyncio
    async def test_watcher_emits_parent_paths_with_truncation_field(self, workspace_test_client, workspace_dir, monkeypatch):
        client = workspace_test_client
        (workspace_dir / "pkg").mkdir()
        (workspace_dir / "pkg" / "sub").mkdir()
        (workspace_dir / "pkg" / "mod.py").write_text("print(1)", encoding="utf-8")
        (workspace_dir / "pkg" / "sub" / "deep.py").write_text("print(2)", encoding="utf-8")
        (workspace_dir / ".hidden").mkdir()
        (workspace_dir / ".hidden" / "secret.py").write_text("print(3)", encoding="utf-8")

        async def fake_awatch(*_args, stop_event=None, **_kwargs):
            yielded = False
            while not (stop_event and stop_event.is_set()):
                if not yielded:
                    yielded = True
                    yield {
                        (1, str(workspace_dir / "pkg" / "mod.py")),
                        (1, str(workspace_dir / "pkg" / "sub" / "deep.py")),
                        (1, str(workspace_dir / ".hidden" / "secret.py")),
                    }
                await asyncio.sleep(0.01)

        broadcast_mock = AsyncMock()
        monkeypatch.setattr(workspace_mod, "broadcast_event", broadcast_mock)
        monkeypatch.setattr(workspace_mod, "awatch", fake_awatch)
        monkeypatch.setattr(workspace_mod, "_workspace_update_throttle_s", 0.0)

        resp = await client.post("/workspace/visibility", json={"visible": True, "show_hidden": False})
        assert resp.status == 200

        for _ in range(100):
            if broadcast_mock.await_count >= 2:
                break
            await asyncio.sleep(0.01)
        assert broadcast_mock.await_count >= 2
        event_name, payload = broadcast_mock.await_args_list[1].args
        assert event_name == "workspace_update"
        assert payload["updates"][0]["path"] == "pkg"
        assert "truncated" in payload["updates"][0]
        assert payload["updates"][0]["root"]["path"] == "pkg"

        resp = await client.post("/workspace/visibility", json={"visible": False, "show_hidden": False})
        assert resp.status == 200


class TestUpdateWorkspaceFile:
    @pytest.mark.asyncio
    async def test_update_creates_and_overwrites(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        # Create a new file
        resp = await client.put("/workspace/file", json={"path": "new.txt", "content": "hello"})
        assert resp.status == 200
        data = await resp.json()
        assert data["path"] == "new.txt"
        assert data["size"] == 5
        assert (workspace_dir / "new.txt").read_text(encoding="utf-8") == "hello"

        # Overwrite the file
        resp = await client.put("/workspace/file", json={"path": "new.txt", "content": "goodbye"})
        assert resp.status == 200
        assert (workspace_dir / "new.txt").read_text(encoding="utf-8") == "goodbye"

    @pytest.mark.asyncio
    async def test_update_creates_parent_dirs(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        resp = await client.put("/workspace/file", json={"path": "sub/dir/file.txt", "content": "nested"})
        assert resp.status == 200
        assert (workspace_dir / "sub" / "dir" / "file.txt").read_text(encoding="utf-8") == "nested"

    @pytest.mark.asyncio
    async def test_update_rejects_missing_fields(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.put("/workspace/file", json={})
        assert resp.status == 400

        resp = await client.put("/workspace/file", json={"path": "x.txt"})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_update_rejects_directory_path(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "mydir").mkdir()
        resp = await client.put("/workspace/file", json={"path": "mydir", "content": "nope"})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_update_rejects_path_traversal(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.put("/workspace/file", json={"path": "../escape.txt", "content": "nope"})
        assert resp.status == 403

    @pytest.mark.asyncio
    async def test_update_rejects_invalid_json(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.put("/workspace/file", data="not json", headers={"Content-Type": "application/json"})
        assert resp.status == 400


class TestUploadWorkspaceFile:
    @pytest.mark.asyncio
    async def test_upload_creates_file(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        import aiohttp
        data = aiohttp.FormData()
        data.add_field("file", b"hello upload", filename="uploaded.txt", content_type="text/plain")
        resp = await client.post("/workspace/upload", data=data)
        assert resp.status == 200
        result = await resp.json()
        assert result["path"] == "uploaded.txt"
        assert (workspace_dir / "uploaded.txt").read_bytes() == b"hello upload"

    @pytest.mark.asyncio
    async def test_upload_to_subdir(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "subdir").mkdir()
        import aiohttp
        data = aiohttp.FormData()
        data.add_field("file", b"nested file", filename="test.txt", content_type="text/plain")
        resp = await client.post("/workspace/upload?path=subdir", data=data)
        assert resp.status == 200
        result = await resp.json()
        assert result["path"] == "subdir/test.txt"
        assert (workspace_dir / "subdir" / "test.txt").read_bytes() == b"nested file"

    @pytest.mark.asyncio
    async def test_upload_missing_file_field(self, workspace_test_client):
        client = workspace_test_client
        import aiohttp
        data = aiohttp.FormData()
        data.add_field("other", b"not a file", filename="x.txt")
        resp = await client.post("/workspace/upload", data=data)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_upload_sanitizes_path_traversal(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        import aiohttp
        data = aiohttp.FormData()
        data.add_field("file", b"escape", filename="../escape.txt", content_type="text/plain")
        resp = await client.post("/workspace/upload", data=data)
        assert resp.status == 200
        result = await resp.json()
        # Filename is sanitized: "../escape.txt" -> "escape.txt"
        assert result["path"] == "escape.txt"
        assert (workspace_dir / "escape.txt").read_bytes() == b"escape"
        assert not (workspace_dir.parent / "escape.txt").exists()

    @pytest.mark.asyncio
    async def test_upload_invalid_filename(self, workspace_test_client):
        """Upload with filename of '.' or '..' returns 400."""
        client = workspace_test_client
        import aiohttp
        data = aiohttp.FormData()
        data.add_field("file", b"bad", filename="..", content_type="text/plain")
        resp = await client.post("/workspace/upload", data=data)
        assert resp.status == 400
        result = await resp.json()
        assert "Invalid filename" in result["error"]

    @pytest.mark.asyncio
    async def test_upload_too_large(self, workspace_test_client, workspace_dir):
        """Upload exceeding MAX_FILE_WRITE_BYTES returns 413."""
        client = workspace_test_client
        import aiohttp
        original = workspace_mod.MAX_FILE_WRITE_BYTES
        workspace_mod.MAX_FILE_WRITE_BYTES = 16
        try:
            data = aiohttp.FormData()
            data.add_field("file", b"x" * 32, filename="big.bin", content_type="application/octet-stream")
            resp = await client.post("/workspace/upload", data=data)
            assert resp.status == 413
            result = await resp.json()
            assert "too large" in result["error"].lower()
            assert not (workspace_dir / "big.bin").exists()
        finally:
            workspace_mod.MAX_FILE_WRITE_BYTES = original

    @pytest.mark.asyncio
    async def test_put_file_content_too_large(self, workspace_test_client):
        """PUT /workspace/file with content exceeding limit returns 413."""
        client = workspace_test_client
        original = workspace_mod.MAX_FILE_WRITE_BYTES
        workspace_mod.MAX_FILE_WRITE_BYTES = 16
        try:
            resp = await client.put(
                "/workspace/file",
                json={"path": "large.txt", "content": "x" * 32},
            )
            assert resp.status == 413
            result = await resp.json()
            assert "too large" in result["error"].lower()
        finally:
            workspace_mod.MAX_FILE_WRITE_BYTES = original

    @pytest.mark.asyncio
    async def test_upload_to_nonexistent_subdir(self, workspace_test_client, workspace_dir):
        """Upload to a path that doesn't exist yet creates the parent directory."""
        client = workspace_test_client
        import aiohttp
        # Create a/b so that a/b/c is treated as a non-dir, falling back to parent a/b
        (workspace_dir / "a" / "b").mkdir(parents=True)
        data = aiohttp.FormData()
        data.add_field("file", b"deep", filename="deep.txt", content_type="text/plain")
        resp = await client.post("/workspace/upload?path=a/b/c", data=data)
        assert resp.status == 200
        # c is not a dir so file lands in parent dir a/b
        assert (workspace_dir / "a" / "b" / "deep.txt").read_bytes() == b"deep"
