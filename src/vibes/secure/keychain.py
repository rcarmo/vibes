"""Keychain entry storage: named, encrypted credentials managed from Settings."""

from __future__ import annotations

import asyncio
import hmac
import os
import secrets
import stat
from pathlib import Path

from ..config import _load_settings_file
from . import aead
from .environment_overrides import EnvironmentStore
from .shell_secrets import env_name

ENTRY_TYPES = {'token', 'password', 'basic', 'secret'}
SALT_BYTES = 16
KEY_FILE_NAME = 'keychain.key'
KEY_FILE_MODE = 0o600


class InvalidMasterPassword(ValueError):
    """The supplied password does not match the configured password."""


class MasterPasswordRequired(Exception):
    """Raised when a protected keychain is read without its master password."""


def resolve_master_password(env=None, settings=None) -> str | None:
    env = env if env is not None else os.environ
    value = env.get('VIBES_KEYCHAIN_MASTER_PASSWORD')
    if value:
        return value
    stored = (settings if settings is not None else _load_settings_file()).get('keychain_master_password')
    return str(stored) if stored else None


def resolve_key_path(env=None) -> str | None:
    value = (env if env is not None else os.environ).get('VIBES_KEYCHAIN_KEY_PATH')
    return value or None


def stores(db, env=None) -> tuple[KeychainStore, EnvironmentStore]:
    keychain = KeychainStore(db, master_password=resolve_master_password(env), key_path=resolve_key_path(env))
    return keychain, EnvironmentStore(db, keychain=keychain)


class KeychainStore:
    """Entries are encrypted at rest; the secret is only decrypted when a caller asks for it."""

    def __init__(self, db, master_password: str | None = None, key_path: str | None = None):
        self.db = db
        self.master_password = master_password or None
        self.key_path = Path(key_path) if key_path else None

    async def _salt(self) -> bytes:
        async with self.db.transaction() as connection:
            await connection.execute(
                "INSERT OR IGNORE INTO keychain_meta (name, value) VALUES ('salt', ?)",
                (os.urandom(SALT_BYTES),),
            )
            async with connection.execute(
                "SELECT value FROM keychain_meta WHERE name = 'salt'"
            ) as cursor:
                row = await cursor.fetchone()
        return bytes(row['value'])

    async def _key(self, master_password: str | None = None) -> bytes:
        if master_password is not None and (
            not self.master_password or not hmac.compare_digest(
                master_password.encode('utf-8'), self.master_password.encode('utf-8')
            )
        ):
            raise InvalidMasterPassword('Incorrect master password')
        if self.master_password:
            key = await asyncio.to_thread(aead.derive_key, self.master_password, await self._salt())
        else:
            key = await asyncio.to_thread(self._installation_key)
        # Fail before any write if configuration changed the key for an existing store.
        async with self.db.transaction() as connection:
            await connection.execute(
                "INSERT OR IGNORE INTO keychain_meta (name, value) VALUES ('key_check', ?)",
                (aead.encrypt(key, b'vibes-keychain'),),
            )
            async with connection.execute(
                "SELECT value FROM keychain_meta WHERE name = 'key_check'"
            ) as cursor:
                check = await cursor.fetchone()
        if aead.decrypt(key, bytes(check['value'])) != b'vibes-keychain':
            raise ValueError('Keychain key configuration does not match the stored key')
        return key

    def _installation_key(self) -> bytes:
        path = self.key_path
        if path is None:
            from ..config import _settings_write_path
            path = _settings_write_path().parent / KEY_FILE_NAME
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Publish a complete key atomically, never truncate a key or follow a symlink.
            temporary = path.with_name(path.name + '.' + secrets.token_hex(12))
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, KEY_FILE_MODE)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(secrets.token_bytes(32))
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass
            finally:
                temporary.unlink(missing_ok=True)
            fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or (
                os.name != 'nt' and (metadata.st_mode & 0o077 or metadata.st_uid != os.getuid())
            ):
                raise ValueError('Keychain key file must be owned by this user with mode 0600')
            key = stream.read(33)
        if len(key) != 32:
            raise ValueError('Keychain key file is not a 32-byte key')
        return key

    async def list(self) -> list[dict]:
        async with self.db._connection.execute(
            'SELECT name, type, username, user_note, agent_note, created_at, updated_at FROM keychain_entries ORDER BY name'
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                'name': row['name'],
                'type': row['type'],
                'username': row['username'],
                'user_note': row['user_note'],
                'agent_note': row['agent_note'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
            }
            for row in rows
        ]

    async def save(self, name: str, secret: str, username: str | None = None,
                   entry_type: str = 'secret', master_password: str | None = None,
                   user_note: str = '', agent_note: str = '') -> dict:
        if not isinstance(name, str) or not isinstance(secret, str):
            raise ValueError('Keychain name and secret must be strings')
        if username is not None and not isinstance(username, str):
            raise ValueError('Keychain username must be a string')
        if any(not isinstance(note, str) or len(note) > 8000 for note in (user_note, agent_note)):
            raise ValueError('Keychain notes must be strings of at most 8000 characters')
        name = name.strip()
        if not name:
            raise ValueError('Keychain entry name is required')
        if not isinstance(entry_type, str) or entry_type not in ENTRY_TYPES:
            raise ValueError(f'Unknown keychain entry type: {entry_type}')
        key = await self._key(master_password)
        blob = aead.encrypt(key, (secret or '').encode('utf-8'))
        async with self.db.transaction() as connection:
            await connection.execute(
                """
                INSERT INTO keychain_entries (name, type, username, secret_encrypted, user_note, agent_note)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    type = excluded.type,
                    username = excluded.username,
                    secret_encrypted = excluded.secret_encrypted,
                    user_note = excluded.user_note,
                    agent_note = excluded.agent_note,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, entry_type, username, blob, user_note, agent_note),
            )
        return {'name': name, 'type': entry_type, 'username': username}

    async def reveal(self, name: str, master_password: str | None = None) -> dict:
        return (await self.reveal_many([name], master_password))[name]

    async def reveal_many(self, names, master_password: str | None = None) -> dict[str, dict]:
        """Decrypt only requested entries, deriving one key for this operation.

        The key is local to this call; it is never cached on the store or across commands.
        An empty request does not read key material or decrypt any entry.
        """
        names = list(dict.fromkeys(names))
        if not names:
            return {}
        if self.master_password and not master_password:
            raise MasterPasswordRequired('Master password required')
        key = await self._key(master_password)
        entries = {}
        for name in names:
            async with self.db._connection.execute(
                'SELECT name, type, username, secret_encrypted FROM keychain_entries WHERE name = ?',
                (name,),
            ) as cursor:
                row = await cursor.fetchone()
            if not row:
                raise LookupError(f'Keychain entry not found: {name}')
            entries[name] = {
                'name': row['name'], 'type': row['type'], 'username': row['username'],
                'secret': aead.decrypt(key, bytes(row['secret_encrypted'])).decode('utf-8'),
            }
        return entries

    async def delete(self, name: str) -> bool:
        async with self.db.transaction() as connection:
            cursor = await connection.execute('DELETE FROM keychain_entries WHERE name = ?', (name,))
            return cursor.rowcount > 0

    async def variable_map(self, master_password: str | None = None) -> dict[str, str]:
        """Shell variable -> entry name, resolving collisions by byte-order sort."""
        best: dict[str, str] = {}
        for entry in await self.list():
            variable = env_name(entry['name'])
            if not variable:
                continue
            if variable not in best or entry['name'] < best[variable]:
                best[variable] = entry['name']
        return best
