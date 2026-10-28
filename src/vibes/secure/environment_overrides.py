"""Environment Settings: stored overrides applied to every later shell command."""

import os

from .shell_secrets import IDENTIFIER_RE

PRIVATE_VARIABLES = {'VIBES_KEYCHAIN_MASTER_PASSWORD', 'VIBES_KEYCHAIN_KEY_PATH'}


class EnvironmentStore:
    """Overrides survive reloads and restarts; clearing one restores the inherited value."""

    def __init__(self, db, base_env=None, keychain=None):
        self.db = db
        self.base_env = dict(base_env if base_env is not None else os.environ)
        self.keychain = keychain

    async def overrides(self) -> dict[str, str]:
        async with self.db._connection.execute(
            'SELECT name, value FROM environment_overrides ORDER BY name'
        ) as cursor:
            rows = await cursor.fetchall()
        return {row['name']: row['value'] for row in rows}

    async def list(self) -> list[dict]:
        """Runtime environment variables with their values, keychain variables excluded."""
        stored = await self.overrides()
        keychain_vars = set(PRIVATE_VARIABLES)
        if self.keychain is not None:
            keychain_vars.update(await self.keychain.variable_map())
        names = sorted(set(self.base_env) | set(stored))
        rows = []
        for name in names:
            if name in keychain_vars:
                continue
            value = stored.get(name, self.base_env.get(name))
            if value is None:
                continue
            rows.append({'name': name, 'value': value, 'override': name in stored})
        return rows

    async def set(self, name: str, value: str) -> dict:
        if not isinstance(name, str) or not IDENTIFIER_RE.fullmatch(name):
            raise ValueError('Environment variable name must be a shell identifier')
        if name in PRIVATE_VARIABLES or (self.keychain is not None and name in await self.keychain.variable_map()):
            raise ValueError(f'{name} is a keychain variable and cannot be overridden')
        async with self.db.transaction() as connection:
            await connection.execute(
                """
                INSERT INTO environment_overrides (name, value) VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (name, value),
            )
        return {'name': name, 'value': value, 'override': True}

    async def clear(self, name: str) -> bool:
        if not isinstance(name, str) or not IDENTIFIER_RE.fullmatch(name):
            raise ValueError('Environment variable name must be a shell identifier')
        async with self.db.transaction() as connection:
            cursor = await connection.execute('DELETE FROM environment_overrides WHERE name = ?', (name,))
            return cursor.rowcount > 0

    def effective_env(self, stored: dict | None = None, base: dict | None = None, extra: dict | None = None) -> dict:
        env = dict(base if base is not None else self.base_env)
        env.update(stored or {})
        env.update(extra or {})
        return env
