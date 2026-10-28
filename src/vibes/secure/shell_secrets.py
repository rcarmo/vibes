"""Keychain variable-name mapping, command-text reference scanning and placeholder substitution.

Rules are taken from the shared shell-environment contract: matching is textual and case-sensitive,
quoting and the shell's own expansion rules do not matter, and only what the command text names is
retrieved.
"""

import re

IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
# $env:NAME, ${NAME}, $NAME and %NAME%.
REFERENCE_RE = re.compile(
    r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}'
    r'|\$env:([A-Za-z_][A-Za-z0-9_]*)'
    r'|\$([A-Za-z_][A-Za-z0-9_]*)'
    r'|%([A-Za-z_][A-Za-z0-9_]*)%'
)
# keychain:<name> runs over [A-Za-z0-9._/:-] and ends at the first other character.
PLACEHOLDER_RE = re.compile(r'keychain:[A-Za-z0-9._/:-]+')

KNOWN_FIELDS = {'username', 'user', 'secret', 'password', 'token'}


def env_name(name: str) -> str | None:
    """Piclaw mapping: identifiers are unchanged, other names are mapped and upper-cased."""
    if IDENTIFIER_RE.fullmatch(name):
        return name
    mapped = re.sub(r'[/.-]+', '_', name)
    mapped = re.sub(r'[^A-Za-z0-9_]', '', mapped).upper()
    if not mapped or mapped[0].isdigit():
        return None
    return mapped


def referenced_names(text: str) -> list[str]:
    """Variable names the command text names literally, in first-seen order."""
    seen: list[str] = []
    for match in REFERENCE_RE.finditer(text):
        name = next(group for group in match.groups() if group)
        if name not in seen:
            seen.append(name)
    return seen


def placeholder_names(text: str) -> list[str]:
    """Entry names named by keychain:<name> placeholders, in first-seen order."""
    seen: list[str] = []
    for match in PLACEHOLDER_RE.finditer(text):
        name = match.group(0)[len('keychain:'):].partition(':')[0]
        if name and name not in seen:
            seen.append(name)
    return seen


def resolve_placeholders(text: str, entry_lookup) -> str:
    """Replace keychain:<name> placeholders; an unresolvable placeholder raises ValueError.

    `entry_lookup(name)` returns the decrypted entry or None for a missing entry. The command must
    not run when a placeholder cannot be resolved, so this raises before execution.
    """
    def replace(match):
        body = match.group(0)[len('keychain:'):]
        name, _, field = body.partition(':')
        if field and field not in KNOWN_FIELDS:
            raise ValueError(f'Unknown keychain placeholder field in {match.group(0)}')
        entry = entry_lookup(name)
        if entry is None:
            raise ValueError(f'Keychain entry not found: {name}')
        if not field:
            return entry['secret']
        if field in {'username', 'user'}:
            username = entry.get('username')
            if not username:
                raise ValueError(f'Keychain entry {name} has no username')
            return username
        return entry['secret']

    return PLACEHOLDER_RE.sub(replace, text)
