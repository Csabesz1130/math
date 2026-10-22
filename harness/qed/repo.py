"""Locate the manuscript collection this harness works on."""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "QED_REPO"


class RepoNotFound(RuntimeError):
    pass


def find_repo(start: str | os.PathLike[str] | None = None) -> Path:
    """Return the collection root: the directory holding CONTENTS.md and lean/.

    Resolution order: the explicit ``start`` argument, the ``QED_REPO``
    environment variable, the current directory and its parents, then the
    parents of this package.
    """

    candidates: list[Path] = []
    if start is not None:
        candidates.append(Path(start))
    if os.environ.get(ENV_VAR):
        candidates.append(Path(os.environ[ENV_VAR]))
    cwd = Path.cwd().resolve()
    candidates.extend([cwd, *cwd.parents])
    candidates.extend(Path(__file__).resolve().parents)
    for candidate in candidates:
        if _is_repo(candidate):
            return candidate.resolve()
    raise RepoNotFound(
        "could not find the manuscript collection (a directory with CONTENTS.md and lean/); "
        f"pass --repo or set {ENV_VAR}"
    )


def _is_repo(path: Path) -> bool:
    return (path / "CONTENTS.md").is_file() and (path / "lean").is_dir()
