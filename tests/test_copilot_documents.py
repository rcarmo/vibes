"""Synthetic document extraction limits and cancelled output ownership."""

import asyncio
import io
import zipfile
from unittest.mock import AsyncMock

import pytest
from vibes.copilot_media import document_text, MAX_TEXT, validate_media


def office(path, xml):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(path, xml)
    return data.getvalue()


@pytest.mark.parametrize(
    "suffix,path",
    [
        (".docx", "word/document.xml"),
        (".pptx", "ppt/slides/slide1.xml"),
        (".xlsx", "xl/sharedStrings.xml"),
    ],
)
def test_office_text_without_external_resources(suffix, path):
    assert "Synthetic words" in document_text(
        suffix, office(path, "<doc><t>Synthetic words</t></doc>")
    )


@pytest.mark.parametrize(
    "content",
    [
        '<!DOCTYPE doc [<!ENTITY x "secret">]><doc><t>&x;</t></doc>',
        "<doc><t>" + "x" * (MAX_TEXT + 1) + "</t></doc>",
    ],
    ids=['xml-entity', 'text-limit'],
)
def test_office_xml_and_text_limits(content):
    with pytest.raises(ValueError):
        document_text(".docx", office("word/document.xml", content))


@pytest.mark.asyncio
async def test_pdf_and_bad_zip_fail_before_admission(db):
    for name, data in [("file.pdf", b"%PDF-1.7"), ("file.docx", b"not a zip")]:
        media = await db.create_media(
            name,
            "application/octet-stream",
            data,
            metadata={"source": "composer-upload", "session_id": "default"},
        )
        with pytest.raises(ValueError):
            await validate_media(db, [media], "default")


@pytest.mark.asyncio
async def test_cancel_during_attachment_read_prevents_delivery(monkeypatch):
    from vibes import agent_attachments as mod

    context = {
        "mode": "copilot-ffi",
        "session_id": "default",
        "turn_id": "test",
        "receipts": {},
    }
    monkeypatch.setattr(mod, "active", context)
    entered, release = asyncio.Event(), asyncio.Event()

    async def read(*args, **kwargs):
        entered.set()
        await release.wait()
        return "x.txt", "text/plain", b"x", None, {"kind": "file"}

    monkeypatch.setattr(mod.asyncio, "to_thread", read)
    database = AsyncMock()
    monkeypatch.setattr(mod, "get_db", AsyncMock(return_value=database))
    task = asyncio.create_task(
        mod.publish_file(
            {"path": "x.txt", "request_id": "test"},
            "copilot-ffi",
            "default",
            expected=context,
        )
    )
    await entered.wait()
    context["cancelled"] = True
    release.set()
    with pytest.raises(PermissionError):
        await task
    database.create_media.assert_not_awaited()
