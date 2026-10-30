"""Secure, human-readable gift card codes.

Codes look like ``GK-7F3K-9QXA``: a fixed prefix and eight random characters
from an alphabet without look-alikes (no 0/O, 1/I/L), which gives roughly 40 bits
of entropy, so codes cannot be guessed.
"""

import re
import secrets

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
"""Characters used in codes, chosen to be easy to read aloud and type."""

PREFIX = "GK"
_GROUP_SIZE = 4
_GROUPS = 2
_PATTERN = re.compile(rf"^{PREFIX}(-[{ALPHABET}]{{{_GROUP_SIZE}}}){{{_GROUPS}}}$")


def new_code() -> str:
    """Return a new random gift card code, e.g. ``GK-7F3K-9QXA``."""
    groups = ("".join(secrets.choice(ALPHABET) for _ in range(_GROUP_SIZE)) for _ in range(_GROUPS))
    return "-".join((PREFIX, *groups))


def is_valid(code: str) -> bool:
    """Return whether ``code`` has the format produced by :func:`new_code`."""
    return _PATTERN.fullmatch(code) is not None
