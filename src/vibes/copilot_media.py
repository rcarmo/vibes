"""Conversation-scoped upload materialisation for the Copilot SDK.

Only uploads scoped to the current conversation, or legacy media referenced
exclusively there, can become model input. Original filenames never become paths.
"""

import asyncio
import base64
import io
import json
from pathlib import Path
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from PIL import Image

MAX_TOTAL = 20 * 1024 * 1024
MAX_FILES = 8
IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".vtt"}
OFFICE_SUFFIXES = {".docx", ".pptx", ".xlsx"}
DOCUMENT_SUFFIXES = TEXT_SUFFIXES | OFFICE_SUFFIXES
MAX_TEXT = 200_000


def document_text(suffix, data):
    """Bounded text extraction only; never execute macros or external XML entities."""
    if suffix in TEXT_SUFFIXES:
        text = data.decode("utf-8-sig")
        if "\x00" in text:
            raise ValueError("Binary content in text input")
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (
                len(entries) > 2000
                or sum(item.file_size for item in entries) > MAX_TOTAL
            ):
                raise ValueError("Office input expands beyond limit")
            prefixes = {
                ".docx": ("word/document.xml",),
                ".pptx": ("ppt/slides/slide",),
                ".xlsx": ("xl/sharedStrings.xml", "xl/worksheets/sheet"),
            }
            chunks = []
            for item in sorted(entries, key=lambda i: i.filename):
                if not item.filename.endswith(".xml") or not item.filename.startswith(
                    prefixes[suffix]
                ):
                    continue
                content = archive.read(item)
                if b'\x00' in content or b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
                    raise ValueError("XML declarations are not supported")
                document = ET.fromstring(content)
                chunks.append(
                    item.filename
                    + "\n"
                    + "\n".join(
                        node.text
                        for node in document.iter()
                        if node.tag.rsplit("}", 1)[-1] in {"t", "v"} and node.text
                    )
                )
            text = "\n\n".join(chunks)
            if not chunks:
                raise ValueError("Office document has no supported text parts")
    if len(text) > MAX_TEXT:
        raise ValueError("Document text exceeds input limit")
    return text


async def validate_media(database, ids, session_id):
    if (
        not isinstance(ids, list)
        or len(ids) > MAX_FILES
        or any(type(i) is not int or i < 1 for i in ids)
    ):
        raise ValueError("Expected at most eight positive media IDs")
    records, total = [], 0
    for media_id in dict.fromkeys(ids):
        record = await database.get_media(media_id)
        if not record:
            raise ValueError("Attachment unavailable")
        async with database._connection.execute(
            """SELECT DISTINCT COALESCE(json_extract(i.data,'$.session_id'),'default') owner
            FROM interactions i, json_each(i.data,'$.media_ids') m WHERE m.value=?""",
            (media_id,),
        ) as cursor:
            owners = {row[0] for row in await cursor.fetchall()}
        metadata = record.get("metadata") or {}
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        upload_owner = metadata.get("session_id")
        if upload_owner is not None:
            allowed = upload_owner == session_id
        else:
            # Legacy uploads were not scoped until referenced. Never admit an
            # unreferenced legacy ID or infer ownership from a mixed-session set.
            allowed = owners == {session_id}
        if not allowed:
            raise ValueError("Attachment unavailable in this conversation")
        pair = await database.get_media_data(media_id)
        if not pair:
            raise ValueError("Attachment unavailable")
        mime, data = pair
        total += len(data)
        if len(data) > 10 * 1024 * 1024 or total > MAX_TOTAL:
            raise ValueError("Model input attachments exceed size limit")
        name = str(record["filename"])
        if len(name) > 255 or any(ord(c) < 32 for c in name):
            raise ValueError("Invalid attachment name")
        suffix = Path(name).suffix.lower()
        if mime in IMAGE_MIMES:
            await asyncio.to_thread(_verify_image, data, mime)
        elif suffix not in DOCUMENT_SUFFIXES:
            raise ValueError("Unsupported model input format")
        else:
            try:
                await asyncio.to_thread(document_text, suffix, data)
            except (zipfile.BadZipFile, ET.ParseError, KeyError, RuntimeError) as exc:
                raise ValueError("Invalid document input") from exc
        records.append((name, suffix, mime, data))
    return records


def _verify_image(data, mime):
    with Image.open(io.BytesIO(data)) as image:
        actual = {
            "PNG": "image/png",
            "JPEG": "image/jpeg",
            "GIF": "image/gif",
            "WEBP": "image/webp",
        }.get(image.format)
        if actual != mime or image.width * image.height > 40_000_000:
            raise ValueError("Invalid model input image")
        image.verify()


class ModelInputs:
    def __init__(self, records):
        self.records = records
        self.directory = None

    async def prepare(self):
        self.directory = tempfile.TemporaryDirectory(prefix="vibes-model-input-")
        attachments = []
        for index, (name, suffix, mime, data) in enumerate(self.records):
            if mime in IMAGE_MIMES:
                attachments.append(
                    {
                        "type": "blob",
                        "data": base64.b64encode(data).decode("ascii"),
                        "mimeType": mime,
                        "displayName": name,
                    }
                )
            else:
                path = Path(self.directory.name) / f"input-{index}{suffix}"
                await asyncio.to_thread(path.write_bytes, data)
                text = await asyncio.to_thread(document_text, suffix, data)
                attachments.append(
                    {
                        "type": "selection",
                        "filePath": str(path),
                        "displayName": name,
                        "text": text,
                        "selection": {"start": {"line": 0, "character": 0},
                                      "end": {"line": text.count('\n'), "character": len(text.rsplit('\n', 1)[-1])}},
                    }
                )
        return attachments

    def close(self):
        if self.directory:
            self.directory.cleanup()
            self.directory = None
