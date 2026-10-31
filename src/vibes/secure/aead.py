"""Authenticated keychain encryption using cryptography's RFC 8439 implementation."""

import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

FORMAT = b'K1'
NONCE_BYTES = 12
TAG_BYTES = 16


def encrypt(key: bytes, plaintext: bytes, nonce: bytes | None = None) -> bytes:
    nonce = os.urandom(NONCE_BYTES) if nonce is None else nonce
    return FORMAT + nonce + ChaCha20Poly1305(key).encrypt(nonce, plaintext, FORMAT)


def decrypt(key: bytes, blob: bytes) -> bytes:
    if len(blob) < len(FORMAT) + NONCE_BYTES + TAG_BYTES or not blob.startswith(FORMAT):
        raise ValueError('Invalid encrypted keychain value')
    try:
        return ChaCha20Poly1305(key).decrypt(blob[2:14], blob[14:], FORMAT)
    except InvalidTag as exc:
        raise ValueError('Keychain authentication failed') from exc


def derive_key(password: str, salt: bytes) -> bytes:
    if not password or len(salt) < 16:
        raise ValueError('A master password and a 16-byte salt are required')
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=16384, r=8, p=1, dklen=32)
