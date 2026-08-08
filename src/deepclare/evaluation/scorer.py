"""Binding the vendored scorer.

`evalkit` is a finished, stdlib-only package that lives beside this repository's own
source rather than inside it, and it is deliberately not installed: it carries no
dependencies, it is copied rather than released, and installing it would leave build
artifacts inside a directory this build does not own.

So it is bound onto the import path once, from a directory the caller names. The default
is derived from the corpus directory the caller already gave — the corpus lives inside
the scorer's own tree — rather than from a path written into this file.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

PACKAGE = "evalkit"


class ScorerUnavailableError(RuntimeError):
    """The scorer could not be located or imported. Fatal: there is nothing to score with."""


def scorer_root(corpus_dir: Path, explicit: Path | None = None) -> Path:
    """The directory to put on the import path so that `import evalkit` finds the scorer.

    With `explicit`, that directory, checked. Otherwise the nearest ancestor of the
    corpus that contains an importable `evalkit` package.
    """
    if explicit is not None:
        root = Path(explicit).resolve()
        if not _holds_package(root):
            raise ScorerUnavailableError(
                f"{root} does not contain an importable {PACKAGE!r} package "
                f"(expected {root / PACKAGE / '__init__.py'})."
            )
        return root

    corpus = Path(corpus_dir).resolve()
    for candidate in (corpus, *corpus.parents):
        if _holds_package(candidate):
            return candidate
    raise ScorerUnavailableError(
        f"no {PACKAGE!r} package found in {corpus} or any directory above it. "
        f"Name it explicitly with --scorer."
    )


def bind_scorer(root: Path) -> ModuleType:
    """Import the scorer from `root`, putting it on the path if it is not there yet."""
    entry = str(Path(root).resolve())
    if entry not in sys.path:
        sys.path.insert(0, entry)
    try:
        module = importlib.import_module(PACKAGE)
    except ImportError as exc:
        raise ScorerUnavailableError(
            f"{PACKAGE} could not be imported from {entry}: {exc}"
        ) from exc

    required = ("parse_declaration", "align", "score_case", "DEFAULT")
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        raise ScorerUnavailableError(
            f"the {PACKAGE} imported from {getattr(module, '__file__', entry)} does not "
            f"expose {', '.join(missing)}. A namespace package of the same name is "
            f"shadowing the scorer."
        )
    return module


def _holds_package(directory: Path) -> bool:
    return (directory / PACKAGE / "__init__.py").is_file()
