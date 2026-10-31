import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock

from vibes.db import Database
from vibes.secure import aead
from vibes.secure.keychain import KeychainStore, MasterPasswordRequired
from vibes.secure.shell_secrets import env_name, placeholder_names, referenced_names
from vibes.routes import settings


def test_aead_envelope_roundtrip_and_rejects_tampering():
    key = bytes(range(32))
    nonce = bytes.fromhex('000000000000000000000000')
    plaintext = b'Ladies and Gentlemen of the class of \'99: If you could offer me the chance to double my life...'
    # RFC 8439 encryption is supplied by cryptography; cover the storage envelope here.
    assert aead.decrypt(key, aead.encrypt(key, plaintext, nonce)) == plaintext

    blob = aead.encrypt(key, b'a keychain secret', nonce)
    assert aead.decrypt(key, blob) == b'a keychain secret'
    with pytest.raises(ValueError):
        aead.decrypt(bytes(range(32))[::-1], blob)
    with pytest.raises(ValueError):
        aead.decrypt(key, blob[:-1] + bytes([blob[-1] ^ 1]))


def test_keychain_variable_names_follow_the_documented_mapping():
    assert env_name('fixtures_lower_42') == 'fixtures_lower_42'
    assert env_name('fixtures/kcc-42') == 'FIXTURES_KCC_42'
    assert env_name('fixtures.kcc.42') == 'FIXTURES_KCC_42'
    assert env_name('42bad') is None
    assert env_name('a b!c') == 'ABC'


def test_only_variables_named_in_the_command_text_are_retrieved():
    text = "printenv | grep -i secret; echo $ALPHA ${BETA} $env:GAMMA %DELTA% 'ALPHA'; echo $alpha"
    assert referenced_names(text) == ['ALPHA', 'BETA', 'GAMMA', 'DELTA', 'alpha']
    assert 'alpha' in referenced_names(text)
    assert placeholder_names('run keychain:fixtures/kcc-1 and keychain:other:username now') == ['fixtures/kcc-1', 'other']


@pytest.mark.asyncio
async def test_keychain_entries_are_encrypted_at_rest_and_survive_reconnect(tmp_path):
    db = Database(str(tmp_path / 'keychain.db'))
    await db.connect()
    store = KeychainStore(db, key_path=str(tmp_path / 'key.key'))
    await store.save('fixtures/alpha', 'hunter2', username='rui')
    async with db._connection.execute('SELECT secret_encrypted FROM keychain_entries') as cursor:
        row = await cursor.fetchone()
    assert b'hunter2' not in bytes(row['secret_encrypted'])

    listed = await store.list()
    assert listed[0]['name'] == 'fixtures/alpha'
    assert 'secret' not in listed[0]
    assert await store.reveal('fixtures/alpha') == {
        'name': 'fixtures/alpha', 'type': 'secret', 'username': 'rui', 'secret': 'hunter2'
    }

    await db.close()
    await db.connect()
    reopened = KeychainStore(db, key_path=str(tmp_path / 'key.key'))
    assert (await reopened.reveal('fixtures/alpha'))['secret'] == 'hunter2'
    assert await reopened.delete('fixtures/alpha')
    assert not await reopened.delete('fixtures/alpha')
    await db.close()


@pytest.mark.asyncio
async def test_master_password_protects_reveal_and_derives_its_own_key(tmp_path):
    db = Database(str(tmp_path / 'protected.db'))
    await db.connect()
    store = KeychainStore(db, master_password='correct horse', key_path=str(tmp_path / 'unused.key'))
    await store.save('protected', 'value')
    with pytest.raises(MasterPasswordRequired):
        await store.reveal('protected')
    assert (await store.reveal('protected', 'correct horse'))['secret'] == 'value'
    with pytest.raises(ValueError):
        await store.reveal('protected', 'wrong horse')
    await db.close()


@pytest.mark.asyncio
async def test_colliding_entry_names_resolve_by_byte_order(tmp_path):
    db = Database(str(tmp_path / 'collide.db'))
    await db.connect()
    store = KeychainStore(db, key_path=str(tmp_path / 'key.key'))
    await store.save('fixtures/kcc-1', 'slash')
    await store.save('fixtures.kcc.1', 'dot')
    mapping = await store.variable_map()
    assert mapping['FIXTURES_KCC_1'] == 'fixtures.kcc.1'
    await db.close()


@pytest.mark.asyncio
async def test_settings_routes_cover_list_save_reveal_and_delete(tmp_path, monkeypatch):
    db = Database(str(tmp_path / 'routes.db'))
    await db.connect()
    monkeypatch.setattr(settings, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setenv('VIBES_KEYCHAIN_KEY_PATH', str(tmp_path / 'key.key'))

    app = web.Application()
    settings.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        created = await client.post('/api/settings/keychain', json={'name': 'fixtures/one', 'secret': 's3cret', 'username': 'u', 'userNote': 'private UI note', 'agentNote': 'safe hint'})
        assert created.status == 201
        saved = await created.json()
        entry = saved['entry']
        assert saved['enabled'] is True
        assert saved['entries'][0]['name'] == 'fixtures/one'
        assert saved['ok'] is True
        assert saved['entries'][0]['envVar'] == 'FIXTURES_ONE'
        assert saved['entries'][0]['updatedAt']
        assert saved['entries'][0]['userNote'] == 'private UI note'
        assert saved['entries'][0]['agentNote'] == 'safe hint'
        assert 'secret' not in saved['entries'][0]
        assert entry['name'] == 'fixtures/one' and 'secret' not in entry

        listed = (await (await client.get('/api/settings/keychain')).json())['entries']
        assert listed[0]['name'] == 'fixtures/one' and 'secret' not in listed[0]

        await db.close()
        await db.connect()
        reloaded = (await (await client.get('/api/settings/keychain')).json())['entries'][0]
        assert reloaded['userNote'] == 'private UI note' and reloaded['agentNote'] == 'safe hint'
        revealed_response = await (await client.post('/api/settings/keychain/reveal', json={'name': 'fixtures/one'})).json()
        revealed = revealed_response['entry']
        assert revealed_response['ok'] is True and revealed_response['secret'] == 's3cret'
        assert revealed['secret'] == 's3cret'
        assert revealed['username'] == 'u'

        assert (await client.post('/api/settings/keychain/reveal', json={'name': 'missing'})).status == 404
        assert (await client.post('/api/settings/keychain', json={'name': ''})).status == 400
        deleted = await client.delete('/api/settings/keychain', json={'name': 'fixtures/one'})
        assert deleted.status == 200
        assert (await deleted.json())['entries'] == []
        assert (await client.delete('/api/settings/keychain', json={'name': 'fixtures/one'})).status == 404
    finally:
        await client.close()
        await db.close()


@pytest.mark.asyncio
async def test_reveal_requires_master_password_when_the_keychain_is_protected(tmp_path, monkeypatch):
    db = Database(str(tmp_path / 'protected-routes.db'))
    await db.connect()
    monkeypatch.setattr(settings, 'get_db', AsyncMock(return_value=db))
    monkeypatch.setenv('VIBES_KEYCHAIN_KEY_PATH', str(tmp_path / 'key.key'))
    monkeypatch.setenv('VIBES_KEYCHAIN_MASTER_PASSWORD', 'fixture-master')

    app = web.Application()
    settings.setup_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        await client.post('/api/settings/keychain', json={'name': 'protected', 'secret': 'value'})
        denied = await client.post('/api/settings/keychain/reveal', json={'name': 'protected'})
        assert denied.status == 401
        challenge = await denied.json()
        assert challenge['code'] == 'needs_master_password'
        assert challenge['needs_master_password'] is True and challenge['ok'] is False
        allowed = await client.post('/api/settings/keychain/reveal', json={'name': 'protected', 'master_password': 'fixture-master'})
        assert allowed.status == 200
        assert (await allowed.json())['entry']['secret'] == 'value'
    finally:
        await client.close()
        await db.close()
