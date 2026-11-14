"""Read-only view of a case's practice app for the agent's file tools, with path checks.

It contains the app (fixture_app/<repo>) plus the case's overlay, exactly what the runner tests.
It never contains trusted_tests/, cases/*/labels.json, reference fixes, or anything outside the app.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from contracts.models import CaseManifest

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".git"}
SKIP_SUFFIXES = {".pyc"}
MAX_READ_CHARS = 12_000


class PathRefused(ValueError):
    pass


class Workspace:
    def __init__(self, manifest: CaseManifest, repo_root: Path = ROOT):
        self.manifest = manifest
        self.files: dict[str, Path] = {}
        layers = [repo_root / manifest.fixture_path, repo_root / "cases" / manifest.case_id / "overlay"]
        for layer in layers:  # the overlay wins
            if not layer.is_dir():
                continue
            for p in sorted(layer.rglob("*")):
                rel = p.relative_to(layer)
                if p.is_file() and not (set(rel.parts) & SKIP_PARTS) and p.suffix not in SKIP_SUFFIXES:
                    if rel.as_posix() == "README.md":
                        continue
                    self.files[rel.as_posix()] = p

    def _key(self, path: str) -> str:
        raw = (path or "").strip().replace("\\", "/")
        pure = PurePosixPath(raw)
        if not raw or pure.is_absolute() or ".." in pure.parts or ":" in raw:
            raise PathRefused(f"path not allowed: {path!r}")
        key = pure.as_posix().removeprefix("./")
        if key not in self.files:
            raise PathRefused(f"no such file in the app: {path!r}")
        return key

    def list_files(self) -> list[str]:
        return sorted(self.files)

    def original(self, path: str) -> str:
        return self.files[self._key(path)].read_text(encoding="utf-8")

    def read(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        lines = self.original(path).splitlines()
        lo = max(1, start_line or 1)
        hi = min(len(lines), end_line or len(lines))
        out = "\n".join(f"{i:4d}  {lines[i - 1]}" for i in range(lo, hi + 1))
        return out[:MAX_READ_CHARS]

    def search(self, query: str, limit: int = 30) -> list[str]:
        q = (query or "").strip().lower()
        if not q:
            return []
        hits: list[str] = []
        for key, p in sorted(self.files.items()):
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if q in line.lower():
                    hits.append(f"{key}:{n}: {line.strip()[:160]}")
                    if len(hits) >= limit:
                        return hits
        return hits
