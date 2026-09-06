import pytest


@pytest.mark.asyncio
async def test_search_thread_and_media_filters(db):
    image = await db.create_media('image.png', 'image/png', b'png')
    text = await db.create_media('file.txt', 'text/plain', b'text')
    root = await db.create_interaction({'type': 'user', 'content': 'needle root'})
    reply = await db.create_interaction({'type': 'user', 'content': 'needle image', 'thread_id': root, 'media_ids': [image]})
    other = await db.create_interaction({'type': 'user', 'content': 'needle text', 'media_ids': [text]})
    assert {x['id'] for x in await db.search('needle', thread_id=root)} == {root, reply}
    assert {x['id'] for x in await db.search('needle', has_attachments=True)} == {reply, other}
    assert {x['id'] for x in await db.search('needle', has_images=True)} == {reply}
    assert await db.search('needle', thread_id=other, has_images=True) == []
