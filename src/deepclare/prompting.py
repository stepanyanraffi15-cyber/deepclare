"""Loading and rendering the prompt files.

Every prompt the system sends to a model is a file in the prompt directory. No prompt
text is assembled in Python, and nothing outside this module reads that directory.

A prompt file declares its own version, and a rendered prompt carries that version back
to the caller, so a value a model produced can record which text produced it.

Substitution is total in both directions: every placeholder in the file must be given a
value, and every value given must name a placeholder in the file. A substitution that
fails quietly yields a prompt that reads perfectly and is wrong, which is the failure a
prompt loader exists to prevent.

The prompt directory arrives as an argument. This module reads no configuration and no
environment of its own.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_HEADER_FENCE = "---"
_HEADER_KEYS = ("name", "version")
_OUTPUT_CONTRACT_HEADING = "## Output contract"

_PROMPT_NAME = re.compile(r"[a-z][a-z0-9_]*")
_PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
# Anything that looks like it was meant to be a placeholder, so a typo in the braces or
# in the name is caught when the file is parsed rather than shipped to a model.
_BRACED = re.compile(r"\{\{.*?\}\}", re.DOTALL)


class PromptError(RuntimeError):
    """A prompt file is missing, malformed, or was rendered with the wrong values."""


class Prompt(BaseModel):
    """One rendered prompt, with the identity of the text that produced it.

    `version` identifies the file, not this rendering: two calls that fill the same file
    with different values report the same version. `name` and `version` are what a value
    produced by the call records as its provenance.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    text: str


def render_prompt(
    prompts_dir: Path, name: str, values: Mapping[str, str]
) -> Prompt:
    """Load prompt `name` from `prompts_dir` and fill its placeholders from `values`.

    Raises PromptError when a placeholder has no value, when a value names no
    placeholder, or when the file itself is malformed.
    """
    prompt_file = _load_prompt_file(prompts_dir, name)
    _check_values(prompt_file, values)
    text = _PLACEHOLDER.sub(lambda match: values[match.group(1)], prompt_file.body)
    return Prompt(name=prompt_file.name, version=prompt_file.version, text=text)


class _PromptFile(BaseModel):
    """A parsed prompt file. Frozen because it is shared between calls by the cache."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    body: str
    placeholders: tuple[str, ...]


@lru_cache(maxsize=None)
def _load_prompt_file(prompts_dir: Path, name: str) -> _PromptFile:
    """Read and parse one prompt file. Cached: prompts do not change during a run."""
    if not _PROMPT_NAME.fullmatch(name):
        raise PromptError(
            f"{name!r} is not a prompt name; names are lowercase words joined by "
            "underscores, matching the file name in the prompt directory."
        )

    path = prompts_dir / f"{name}.md"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptError(f"prompt {name!r} could not be read from {path}: {exc}") from exc

    return _parse_prompt_file(name, raw)


def _parse_prompt_file(name: str, raw: str) -> _PromptFile:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != _HEADER_FENCE:
        raise PromptError(f"prompt {name!r}: the file must open with a '---' line.")
    try:
        header_end = lines.index(_HEADER_FENCE, 1)
    except ValueError:
        raise PromptError(
            f"prompt {name!r}: the header is not closed by a second '---' line."
        ) from None

    header = _parse_header(name, lines[1:header_end])
    if header["name"] != name:
        raise PromptError(
            f"prompt {name!r}: the header declares the name {header['name']!r}. "
            "The declared name and the file name must agree."
        )

    body = "\n".join(lines[header_end + 1 :]).strip()
    if not body:
        raise PromptError(f"prompt {name!r}: the body is empty.")
    if _OUTPUT_CONTRACT_HEADING not in body:
        raise PromptError(
            f"prompt {name!r}: the body has no {_OUTPUT_CONTRACT_HEADING!r} section. "
            "A prompt states the shape it expects back; the bound output schema and the "
            "prompt text reach the model together and are reviewed together."
        )

    malformed = [
        match.group(0)
        for match in _BRACED.finditer(body)
        if not _PLACEHOLDER.fullmatch(match.group(0))
    ]
    if malformed:
        raise PromptError(
            f"prompt {name!r}: malformed placeholder(s) "
            f"{', '.join(sorted(set(malformed)))}. A placeholder is {{{{lowercase_name}}}}, "
            "with no spaces inside the braces."
        )

    placeholders = tuple(
        dict.fromkeys(match.group(1) for match in _PLACEHOLDER.finditer(body))
    )
    return _PromptFile(
        name=name, version=header["version"], body=body, placeholders=placeholders
    )


def _parse_header(name: str, lines: list[str]) -> dict[str, str]:
    header: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not separator or not key:
            raise PromptError(
                f"prompt {name!r}: header line {line!r} is not 'key: value'."
            )
        if key not in _HEADER_KEYS:
            raise PromptError(
                f"prompt {name!r}: unknown header key {key!r}; the header carries "
                f"exactly {' and '.join(_HEADER_KEYS)}."
            )
        if key in header:
            raise PromptError(f"prompt {name!r}: header key {key!r} appears twice.")
        if not value:
            raise PromptError(f"prompt {name!r}: header key {key!r} has no value.")
        header[key] = value

    missing = [key for key in _HEADER_KEYS if key not in header]
    if missing:
        raise PromptError(f"prompt {name!r}: the header is missing {', '.join(missing)}.")
    return header


def _check_values(prompt_file: _PromptFile, values: Mapping[str, str]) -> None:
    missing = sorted(set(prompt_file.placeholders) - set(values))
    unknown = sorted(set(values) - set(prompt_file.placeholders))
    if missing or unknown:
        problems = []
        if missing:
            problems.append(f"no value given for {', '.join(missing)}")
        if unknown:
            problems.append(f"no such placeholder: {', '.join(unknown)}")
        takes = ", ".join(prompt_file.placeholders) or "no placeholders at all"
        raise PromptError(
            f"prompt {prompt_file.name!r} version {prompt_file.version}: "
            f"{'; '.join(problems)}. It takes {takes}."
        )

    for key in prompt_file.placeholders:
        value = values[key]
        if not isinstance(value, str):
            raise PromptError(
                f"prompt {prompt_file.name!r}: {key!r} was given a value of type "
                f"{type(value).__name__}; placeholder values are strings, rendered by "
                "the caller, who knows how the value should read to a model."
            )
        if not value.strip():
            raise PromptError(
                f"prompt {prompt_file.name!r}: {key!r} was given an empty value. Absence "
                "is stated to a model as an explicit literal — 'unknown', '(none)' — "
                "never as nothing, because a key that is absent and a key whose value is "
                "missing are different signals."
            )
