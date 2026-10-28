"""Storage races, password validation and Settings input boundaries."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.db import Database
from vibes.routes import settings
from vibes.secure.keychain import KeychainStore


@pytest.mark.asyncio
async def test_concurrent_first_writes_share_salt_and_installation_key(tmp_path):
    db = Database(str(tmp_path / 'race.db'))
    await db.connect()
    try:
        stores = [KeychainStore(db, key_path=str(tmp_path / 'key')) for _ in range(12)]
        with ThreadPoolExecutor(max_workers=12) as pool:
            keys = list(pool.map(lambda store: store._installation_key(), stores))
        assert len(set(keys)) == 1
        await asyncio.gather(*(store.save(f'entry_{i}', str(i)) for i, store in enumerate(stores)))
        for i, store in enumerate(stores):
            assert (await store.reveal(f'entry_{i}'))['secret'] == str(i)
        assert len(set(await asyncio.gather(*(store._salt() for store in stores)))) == 1
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_wrong_password_cannot_write_an_unreadable_entry(tmp_path):
    db = Database(str(tmp_path / 'password.db'))
    await db.connect()
    try:
        store = KeychainStore(db, master_password='right')
        with pytest.raises(ValueError):
            await store.save('entry', 'value', master_password='wrong')
        assert await store.list() == []
        await store.save('entry', 'original')
        with pytest.raises(ValueError):
            await store.save('entry', 'replacement', master_password='wrong')
        assert (await store.reveal('entry', 'right'))['secret'] == 'original'
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_changed_master_configuration_rejects_writes_without_losing_original(tmp_path):
    db = Database(str(tmp_path / 'changed.db'))
    await db.connect()
    try:
        original = KeychainStore(db, master_password='original')
        await original.save('first', 'value')
        changed = KeychainStore(db, master_password='changed')
        with pytest.raises(ValueError):
            await changed.save('second', 'unreadable')
        assert [row['name'] for row in await original.list()] == ['first']
        assert (await original.reveal('first', 'original'))['secret'] == 'value'
    finally:
        await db.close()


def test_installation_key_rejects_symlink_and_insecure_mode(tmp_path):
    if os.name == 'nt':
        pytest.skip('POSIX ownership and symlink protection')
    target = tmp_path / 'target'
    target.write_bytes(b'x' * 32)
    target.chmod(0o600)
    link = tmp_path / 'link'
    link.symlink_to(target)
    with pytest.raises(OSError):
        KeychainStore(None, key_path=str(link))._installation_key()
    target.chmod(0o644)
    with pytest.raises(ValueError):
        KeychainStore(None, key_path=str(target))._installation_key()


@pytest.mark.asyncio
async def test_environment_routes_persist_clear_validate_and_hide_keychain_config(tmp_path, monkeypatch):
    db = Database(str(tmp_path / 'environment.db'))
    await db.connect()
    monkeypatch.setattr(settings, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setenv('VIBES_KEYCHAIN_KEY_PATH', str(tmp_path / 'key'))
    monkeypatch.setenv('VIBES_KEYCHAIN_MASTER_PASSWORD', 'master')
    app = web.Application()
    settings.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        assert (await client.post('/api/settings/environment', json={'name': 'TEST_OVERRIDE', 'value': 'one'})).status == 201
        assert (await client.post('/api/settings/keychain', json={'name': 'SECRET_ENTRY', 'secret': 'secret'})).status == 201
        for name in ['BAD NAME', 'newline\n', 'SECRET_ENTRY', 'VIBES_KEYCHAIN_MASTER_PASSWORD']:
            assert (await client.post('/api/settings/environment', json={'name': name, 'value': 'bad'})).status == 400
        variables = (await (await client.get('/api/settings/environment')).json())['variables']
        indexed = {row['name']: row for row in variables}
        assert indexed['TEST_OVERRIDE']['value'] == 'one'
        assert not {'SECRET_ENTRY', 'VIBES_KEYCHAIN_MASTER_PASSWORD', 'VIBES_KEYCHAIN_KEY_PATH'} & indexed.keys()
        await db.close()
        await db.connect()
        variables = (await (await client.get('/api/settings/environment')).json())['variables']
        assert any(row['name'] == 'TEST_OVERRIDE' and row['value'] == 'one' for row in variables)
        assert (await client.post('/api/settings/environment', json={'name': 'TEST_OVERRIDE', 'value': None})).status == 200
        assert (await client.post('/api/settings/environment', json={'name': 'TEST_OVERRIDE', 'value': None})).status == 404
        for payload in [[], {'name': []}, {'name': 'x', 'type': []}, {'name': 'x', 'secret': {}}]:
            assert (await client.post('/api/settings/keychain', json=payload)).status == 400
        for payload in [[], {'name': []}, {'name': 'SECRET_ENTRY', 'master_password': []}]:
            assert (await client.post('/api/settings/keychain/reveal', json=payload)).status == 400
        denied = await client.post('/api/settings/keychain/reveal', json={
            'name': 'SECRET_ENTRY', 'master_password': 'wrong',
        })
        assert denied.status == 401
        assert (await denied.json())['code'] == 'needs_master_password'
    finally:
        await client.close()
        await db.close()
