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
        assert data["lossless"] is True
        assert data["editable"] is True

        resp = await client.get("/workspace/file?path=big.txt&max=256")
        assert resp.status == 200
        data = await resp.json()
        assert data["kind"] == "text"
        assert data["truncated"] is True
        assert len(data["text"]) == 256
        assert data["editable"] is False

        (workspace_dir / "lossy.txt").write_bytes(b"hello\xffworld")
        resp = await client.get("/workspace/file?path=lossy.txt")
        data = await resp.json()
        assert data["lossless"] is False
        assert data["editable"] is False

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
    async def test_upload_conflict_returns_409(self, workspace_test_client, workspace_dir):
        """Upload to existing file without overwrite flag returns 409."""
        client = workspace_test_client
        (workspace_dir / "exists.txt").write_text("original", encoding="utf-8")
        import aiohttp
        data = aiohttp.FormData()
        data.add_field("file", b"new content", filename="exists.txt", content_type="text/plain")
        resp = await client.post("/workspace/upload", data=data)
        assert resp.status == 409
        result = await resp.json()
        assert result["code"] == "file_exists"
        assert (workspace_dir / "exists.txt").read_text() == "original"

    @pytest.mark.asyncio
    async def test_upload_overwrite_succeeds(self, workspace_test_client, workspace_dir):
        """Upload with overwrite=1 replaces existing file."""
        client = workspace_test_client
        (workspace_dir / "exists.txt").write_text("original", encoding="utf-8")
        import aiohttp
        data = aiohttp.FormData()
        data.add_field("file", b"replaced", filename="exists.txt", content_type="text/plain")
        resp = await client.post("/workspace/upload?overwrite=1", data=data)
        assert resp.status == 200
        assert (workspace_dir / "exists.txt").read_bytes() == b"replaced"

    @pytest.mark.asyncio
    async def test_upload_new_file_no_conflict(self, workspace_test_client, workspace_dir):
        """Upload a new file (no existing) succeeds without overwrite flag."""
        client = workspace_test_client
        import aiohttp
        data = aiohttp.FormData()
        data.add_field("file", b"brand new", filename="fresh.txt", content_type="text/plain")
        resp = await client.post("/workspace/upload", data=data)
        assert resp.status == 200
        assert (workspace_dir / "fresh.txt").read_bytes() == b"brand new"

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


class TestDeleteWorkspaceFile:
    @pytest.mark.asyncio
    async def test_delete_existing_file(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        target = workspace_dir / "deleteme.txt"
        target.write_text("goodbye", encoding="utf-8")
        assert target.exists()

        resp = await client.delete("/workspace/file?path=deleteme.txt")
        assert resp.status == 200
        data = await resp.json()
        assert data["deleted"] is True
        assert data["name"] == "deleteme.txt"
        assert not target.exists()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.delete("/workspace/file?path=no_such_file.txt")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_delete_directory_rejected(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "mydir").mkdir(exist_ok=True)
        resp = await client.delete("/workspace/file?path=mydir")
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_delete_missing_path(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.delete("/workspace/file?path=")
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_delete_path_traversal(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.delete("/workspace/file?path=../escape.txt")
        assert resp.status == 403


class TestCreateWorkspaceFile:
    @pytest.mark.asyncio
    async def test_create_file(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        resp = await client.post("/workspace/create", json={"path": ".", "name": "hello.md", "content": "# Hi"})
        assert resp.status == 200
        data = await resp.json()
        assert data["name"] == "hello.md"
        assert (workspace_dir / "hello.md").read_text() == "# Hi"

    @pytest.mark.asyncio
    async def test_create_conflict(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "exists.txt").write_text("old")
        resp = await client.post("/workspace/create", json={"path": ".", "name": "exists.txt", "content": ""})
        assert resp.status == 409

    @pytest.mark.asyncio
    async def test_create_invalid_name(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.post("/workspace/create", json={"path": ".", "name": "..", "content": ""})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_create_slash_in_name(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.post("/workspace/create", json={"path": ".", "name": "a/b.txt", "content": ""})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_create_in_subdir(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "sub").mkdir()
        resp = await client.post("/workspace/create", json={"path": "sub", "name": "file.txt", "content": "x"})
        assert resp.status == 200
        assert (workspace_dir / "sub" / "file.txt").read_text() == "x"


class TestRenameWorkspaceFile:
    @pytest.mark.asyncio
    async def test_rename_file(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "old.txt").write_text("data")
        resp = await client.post("/workspace/rename", json={"path": "old.txt", "name": "new.txt"})
        assert resp.status == 200
        data = await resp.json()
        assert data["name"] == "new.txt"
        assert data["old_path"] == "old.txt"
        assert not (workspace_dir / "old.txt").exists()
        assert (workspace_dir / "new.txt").read_text() == "data"

    @pytest.mark.asyncio
    async def test_rename_conflict(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "a.txt").write_text("a")
        (workspace_dir / "b.txt").write_text("b")
        resp = await client.post("/workspace/rename", json={"path": "a.txt", "name": "b.txt"})
        assert resp.status == 409

    @pytest.mark.asyncio
    async def test_rename_not_found(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.post("/workspace/rename", json={"path": "nope.txt", "name": "new.txt"})
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_rename_same_name(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "same.txt").write_text("x")
        resp = await client.post("/workspace/rename", json={"path": "same.txt", "name": "same.txt"})
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_rename_root_rejected(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.post("/workspace/rename", json={"path": ".", "name": "nope"})
        assert resp.status == 400


class TestMoveWorkspaceEntry:
    @pytest.mark.asyncio
    async def test_move_file(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "src.txt").write_text("data")
        (workspace_dir / "dest").mkdir()
        resp = await client.post("/workspace/move", json={"path": "src.txt", "target": "dest"})
        assert resp.status == 200
        data = await resp.json()
        assert data["path"] == "dest/src.txt"
        assert data["old_path"] == "src.txt"
        assert not (workspace_dir / "src.txt").exists()
        assert (workspace_dir / "dest" / "src.txt").read_text() == "data"

    @pytest.mark.asyncio
    async def test_move_conflict(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "dup.txt").write_text("a")
        (workspace_dir / "dest").mkdir()
        (workspace_dir / "dest" / "dup.txt").write_text("b")
        resp = await client.post("/workspace/move", json={"path": "dup.txt", "target": "dest"})
        assert resp.status == 409

    @pytest.mark.asyncio
    async def test_move_into_self(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        d = workspace_dir / "folder"
        d.mkdir()
        (d / "sub").mkdir()
        resp = await client.post("/workspace/move", json={"path": "folder", "target": "folder/sub"})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_move_root_rejected(self, workspace_test_client, workspace_dir):
        client = workspace_test_client
        (workspace_dir / "dest").mkdir()
        resp = await client.post("/workspace/move", json={"path": ".", "target": "dest"})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_move_not_found(self, workspace_test_client):
        client = workspace_test_client
        resp = await client.post("/workspace/move", json={"path": "ghost.txt", "target": "."})
        assert resp.status == 404

@pytest.mark.asyncio
async def test_conditional_save_rejects_external_change(workspace_test_client, workspace_dir):
    target = workspace_dir / 'revision.txt'
    target.write_text('original', encoding='utf-8')
    response = await workspace_test_client.get('/workspace/file?path=revision.txt')
    revision = (await response.json())['revision']
    target.write_text('external update', encoding='utf-8')
    response = await workspace_test_client.put('/workspace/file', json={
        'path': 'revision.txt', 'content': 'stale draft', 'expected_revision': revision,
    })
    assert response.status == 409
    assert target.read_text() == 'external update'
    response = await workspace_test_client.get('/workspace/file?path=revision.txt')
    revision = (await response.json())['revision']
    response = await workspace_test_client.put('/workspace/file', json={
        'path': 'revision.txt', 'content': 'fresh draft', 'expected_revision': revision,
    })
    assert response.status == 200
    assert (await response.json())['revision'] != revision
    assert target.read_text() == 'fresh draft'

@pytest.mark.asyncio
async def test_editor_mode_rejects_incomplete_or_lossy_snapshots(workspace_test_client, workspace_dir):
    (workspace_dir / 'oversized.txt').write_bytes(b'a' * 500001)
    response = await workspace_test_client.get('/workspace/file?path=oversized.txt&max=5000000&mode=edit')
    assert response.status == 413
    (workspace_dir / 'invalid.txt').write_bytes(b'invalid\xffutf8')
    response = await workspace_test_client.get('/workspace/file?path=invalid.txt&mode=edit')
    assert response.status == 415
    (workspace_dir / 'complete.txt').write_text('complete UTF-8 café', encoding='utf-8')
    response = await workspace_test_client.get('/workspace/file?path=complete.txt&mode=edit')
    assert response.status == 200
    assert (await response.json())['editable'] is True

@pytest.mark.asyncio
async def test_editor_save_rejects_incomplete_source(workspace_test_client, workspace_dir):
    for name, content, status in [('large.txt', b'a' * 500001, 413), ('lossy.txt', b'bad\xfftext', 415)]:
        target = workspace_dir / name
        target.write_bytes(content)
        revision = f'{target.stat().st_mtime_ns}:{target.stat().st_size}'
        response = await workspace_test_client.put('/workspace/file', json={
            'path': name, 'content': 'partial preview', 'expected_revision': revision, 'editor_snapshot': True,
        })
        assert response.status == status
        assert target.read_bytes() == content
    response = await workspace_test_client.put('/workspace/file', json={
        'path': 'large.txt', 'content': 'partial preview', 'editor_snapshot': True,
    })
    assert response.status == 400

@pytest.mark.asyncio
async def test_revision_detects_same_size_metadata_preserving_change(workspace_test_client, workspace_dir):
    import os
    target = workspace_dir / 'same-size.txt'
    target.write_text('before', encoding='utf-8')
    stat = target.stat()
    response = await workspace_test_client.get('/workspace/file?path=same-size.txt')
    revision = (await response.json())['revision']
    target.write_text('after!', encoding='utf-8')
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    response = await workspace_test_client.put('/workspace/file', json={
        'path': 'same-size.txt', 'content': 'stale', 'expected_revision': revision,
    })
    assert response.status == 409
    assert target.read_text() == 'after!'

@pytest.mark.asyncio
async def test_save_copy_never_overwrites_existing_file(workspace_test_client, workspace_dir):
    target = workspace_dir / 'copy.txt'
    target.write_text('unrelated', encoding='utf-8')
    response = await workspace_test_client.put('/workspace/file', json={
        'path': 'copy.txt', 'content': 'draft', 'create_only': True,
    })
    assert response.status == 409
    assert target.read_text() == 'unrelated'
    response = await workspace_test_client.put('/workspace/file', json={
        'path': 'new-copy.txt', 'content': 'draft', 'create_only': True,
    })
    assert response.status == 200
    assert (workspace_dir / 'new-copy.txt').read_text() == 'draft'

@pytest.mark.asyncio
async def test_workspace_subscriptions_do_not_stop_other_browser(workspace_test_client):
    from vibes.routes import workspace
    client = workspace_test_client
    await client.post('/workspace/visibility', json={'visible': True, 'subscription_id': 'browser-a'})
    await client.post('/workspace/visibility', json={'visible': True, 'subscription_id': 'browser-b', 'show_hidden': True})
    await client.post('/workspace/visibility', json={'visible': False, 'subscription_id': 'browser-a'})
    assert workspace._workspace_visible is True
    assert workspace._workspace_subscriptions == {'browser-b': True}
    await client.post('/workspace/visibility', json={'visible': False, 'subscription_id': 'browser-b'})
    assert workspace._workspace_visible is False

@pytest.mark.asyncio
async def test_disconnect_releases_only_its_workspace_subscription(workspace_test_client):
    from vibes.routes import workspace
    await workspace_test_client.post('/workspace/visibility', json={'visible': True, 'subscription_id': 'a'})
    await workspace_test_client.post('/workspace/visibility', json={'visible': True, 'subscription_id': 'b'})
    await workspace.release_workspace_subscription('a')
    assert workspace._workspace_visible is True
    assert 'a' not in workspace._workspace_subscriptions
    await workspace.release_workspace_subscription('b')
    assert workspace._workspace_visible is False

@pytest.mark.asyncio
async def test_file_view_http_confines_path_and_requires_owned_ack(workspace_test_client, workspace_dir, monkeypatch):
    from vibes.routes import workspace
    from vibes import agent_attachments as owner
    monkeypatch.setattr(owner, 'active', {'mode': 'acp', 'session_id': 'default', 'turn_id': 'file-view'})
    headers = {'Authorization': 'Bearer ' + owner.acp_token('default')}
    (workspace_dir / 'view.txt').write_text('view me', encoding='utf-8')
    events = []
    async def publish(kind, data):
        events.append(data)
    monkeypatch.setattr(workspace, 'broadcast_event', publish)
    client = workspace_test_client
    response = await client.post('/internal/agent-tools/open-file', headers=headers, json={'path': '../outside.txt'})
    assert response.status == 403
    response = await client.post('/internal/agent-tools/open-file', headers=headers, json={'path': 'missing.txt'})
    assert response.status == 400
    request = asyncio.create_task(client.post('/internal/agent-tools/open-file', headers=headers, json={'path': 'view.txt'}))
    for _ in range(100):
        if events:
            break
        await asyncio.sleep(0.001)
    request_id = events[0]['request_id']
    response = await client.post(f'/workspace/view-requests/{request_id}/ack', json={'session_id': 'wrong', 'status': 'opened'})
    assert response.status == 404
    response = await client.post(f'/workspace/view-requests/{request_id}/ack', json={'session_id': 'default', 'status': 'opened'})
    assert response.status == 200
    response = await request
    assert (await response.json())['status'] == 'opened'
    assert not workspace._file_views.pending

@pytest.mark.asyncio
async def test_raw_active_documents_are_download_only(workspace_test_client, workspace_dir):
    for name, content in [('active.html', '<script>document.cookie</script>'), ('active.svg', '<svg onload="alert(1)"/>')]:
        (workspace_dir / name).write_text(content)
        response = await workspace_test_client.get('/workspace/raw?path=' + name)
        assert response.status == 200
        assert response.headers['Content-Disposition'] == 'attachment'
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
        assert "sandbox" in response.headers['Content-Security-Policy']

@pytest.mark.asyncio
async def test_preview_revision_uses_bounded_snapshot_not_full_file_hash(workspace_test_client, workspace_dir, monkeypatch):
    from vibes.routes import workspace
    import hashlib
    def forbidden_hash(path):
        raise AssertionError('Preview must not hash the whole file')
    monkeypatch.setattr(workspace, '_file_revision', forbidden_hash)
    (workspace_dir / 'large-preview.txt').write_bytes(b'a' * 1000)
    response = await workspace_test_client.get('/workspace/file?path=large-preview.txt&max=256')
    data = await response.json()
    assert data['truncated'] is True and data['revision'] is None
    (workspace_dir / 'small-preview.txt').write_text('complete snapshot', encoding='utf-8')
    response = await workspace_test_client.get('/workspace/file?path=small-preview.txt&mode=edit')
    data = await response.json()
    assert data['revision'] == hashlib.sha256(data['text'].encode('utf-8')).hexdigest()
