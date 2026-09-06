import pytest


@pytest.mark.asyncio
async def test_only_old_marked_unreferenced_uploads_removed(db):
    async def media(marked=True, old=True):
        key = await db.create_media('file.txt', 'text/plain', b'contents', metadata={'source': 'composer-upload'} if marked else None)
        if old:
            await db._connection.execute("UPDATE media SET created_at=datetime('now','-8 days') WHERE id=?", (key,))
            await db._connection.commit()
        return key
    abandoned = await media()
    referenced = await media()
    text_reference = await media()
    legacy = await media(marked=False)
    recent = await media(old=False)
    await db.create_interaction({'type': 'user', 'content': 'file', 'media_ids': [referenced]})
    await db.create_interaction({'type': 'user', 'content': f'attachment:{text_reference}'})
    assert await db.cleanup_abandoned_uploads() == 1
    assert await db.get_media(abandoned) is None
    for key in [referenced, text_reference, legacy, recent]:
        assert await db.get_media(key) is not None
    assert await db.cleanup_abandoned_uploads() == 0
    with pytest.raises(ValueError):
        await db.cleanup_abandoned_uploads(age_days=0)
