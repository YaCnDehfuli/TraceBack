"""Staleness (R12, guide 8.5): a memory goes stale when the code it was proven against changes.

At promote time the store records `provenAgainst`: a fingerprint of each file the fix touched, as it
is in the repository at that moment (the code the fix was verified on). Later, at read time, the
current files are fingerprinted again; any difference means "Stale: code changed since this was
proven". Staleness is a warning, not a revocation: a stale memory is still offered, and its fix must
still pass verification.

Repositories live under TRACEBACK_CODE_ROOT (default: fixture_app/ in this checkout), one folder per
repositoryId. A repository that isn't present locally can't be checked, so it's never called stale.
Line endings are normalised, so a CRLF checkout and an LF checkout fingerprint the same.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "fixture_app"


def code_root() -> Path:
    return Path(os.getenv("TRACEBACK_CODE_ROOT") or DEFAULT_ROOT)


def _repo(repository_id: str) -> Path | None:
    repo = code_root() / repository_id
    return repo if repository_id and repo.is_dir() else None


def fingerprint(repository_id: str, path: str) -> str | None:
    """sha256 of the file's text with normalised line endings; None if the repo or file is absent."""
    repo = _repo(repository_id)
    if repo is None:
        return None
    f = (repo / path).resolve()
    if repo.resolve() not in f.parents or not f.is_file():  # never read outside the repository
        return None
    text = f.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(text).hexdigest()


def proven_against(repository_id: str, paths: list[str]) -> list[dict]:
    """Fingerprints to store at promote time (only files that exist locally)."""
    out = []
    for p in dict.fromkeys(paths):
        fp = fingerprint(repository_id, p)
        if fp is not None:
            out.append({"path": p, "sha256": fp})
    return out


def changed_files(repository_id: str, proven: list[dict]) -> list[str]:
    """Paths whose current fingerprint differs from the stored one (a deleted file counts as changed).
    Empty when nothing changed or the repository can't be checked here."""
    if not proven or _repo(repository_id) is None:
        return []
    return [a["path"] for a in proven if fingerprint(repository_id, a["path"]) != a["sha256"]]
