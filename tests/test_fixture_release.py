"""Check the consumer's explicit Classic-only fixture release contract."""

import json
import subprocess
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from vibes.db import init_db, close_db
from vibes.routes import sessions

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SHA = '8f76048862febf91c26f84a293a9761e5f3cca68'


def test_fixture_release_pin_and_only_classic_layout():
    fixture = ROOT / 'references/fixtures-vibes'
    actual = subprocess.check_output(['git', '-C', str(fixture), 'rev-parse', 'HEAD'], text=True).strip()
    assert actual == FIXTURE_SHA
    assert (fixture / 'ui/classic/static/dist/app.bundle.js').is_file()
    assert not (fixture / 'ui/vibes').exists()
    assert not (fixture / 'ui/tau').exists()
    assert (ROOT / 'src/vibes/static').readlink() == Path('../../references/fixtures-vibes/ui/classic/static')
    skips = json.loads((ROOT / 'tests/fixtures-vibes/skips.json').read_text())
    assert skips['fixturesVibes'] == 'v0.3.0'


@pytest.mark.asyncio
async def test_fixture_profile_session_contract(tmp_path):
    profile = json.loads((ROOT / 'tests/fixtures-vibes/profile.json').read_text())
    create = profile['session']['create']
    assert create == {'method': 'POST', 'path': '/api/sessions',
                      'body': {'title': '{name}', 'agent_id': 'web'}, 'idField': 'session.id'}
    assert profile['session']['open'] == '/?chat_jid=gi:{id}'
    await init_db(str(tmp_path / 'vibes.db'))
    try:
        app = web.Application()
        sessions.setup_routes(app)
        async with TestClient(TestServer(app)) as client:
            body = {key: value.replace('{name}', 'fixture-profile') for key, value in create['body'].items()}
            response = await client.post(create['path'], json=body)
            data = await response.json()
            assert response.status == 201
            session_id = data['session']['id']
            assert session_id and data['session']['title'] == 'fixture-profile'
            assert profile['session']['open'].replace('{id}', session_id) == f'/?chat_jid=gi:{session_id}'
    finally:
        await close_db()
