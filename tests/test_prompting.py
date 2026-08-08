"""The prompt loader, mostly through its refusals.

A prompt that renders wrong reads perfectly, which is the whole reason this loader
exists. So the cases that matter are the ones it must refuse.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deepclare.prompting import PromptError, render_prompt

VALID = """\
---
name: sample
version: 3
---

Read the {{subject}} on page {{page}}.

## Output contract

One record.
"""


def write(directory: Path, name: str, text: str) -> Path:
    path = directory / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_valid_prompt_renders_and_carries_its_identity(tmp_path: Path) -> None:
    write(tmp_path, "sample", VALID)
    prompt = render_prompt(tmp_path, "sample", {"subject": "invoice", "page": "2"})
    assert prompt.name == "sample"
    assert prompt.version == "3"
    assert "Read the invoice on page 2." in prompt.text
    assert "{{" not in prompt.text


def test_the_version_identifies_the_file_not_the_rendering(tmp_path: Path) -> None:
    write(tmp_path, "sample", VALID)
    first = render_prompt(tmp_path, "sample", {"subject": "a", "page": "1"})
    second = render_prompt(tmp_path, "sample", {"subject": "b", "page": "2"})
    assert first.version == second.version
    assert first.text != second.text


def test_a_prompt_with_no_placeholders_renders_from_an_empty_mapping(
    tmp_path: Path,
) -> None:
    write(
        tmp_path,
        "plain",
        "---\nname: plain\nversion: 1\n---\n\nSay yes.\n\n## Output contract\n\nA word.\n",
    )
    assert render_prompt(tmp_path, "plain", {}).text.startswith("Say yes.")


def test_single_braces_are_ordinary_text(tmp_path: Path) -> None:
    """A JSON example in a prompt body must survive untouched."""
    body = (
        "---\nname: jsonish\nversion: 1\n---\n\n"
        'Answer like {"a": 1}.\n\n## Output contract\n\nJSON.\n'
    )
    write(tmp_path, "jsonish", body)
    assert '{"a": 1}' in render_prompt(tmp_path, "jsonish", {}).text


# --- substitution is total in both directions -----------------------------------


def test_a_placeholder_with_no_value_is_refused_and_named(tmp_path: Path) -> None:
    write(tmp_path, "sample", VALID)
    with pytest.raises(PromptError, match="page"):
        render_prompt(tmp_path, "sample", {"subject": "invoice"})


def test_a_value_naming_no_placeholder_is_refused_and_named(tmp_path: Path) -> None:
    write(tmp_path, "sample", VALID)
    with pytest.raises(PromptError, match="tenant"):
        render_prompt(
            tmp_path, "sample", {"subject": "a", "page": "1", "tenant": "acme"}
        )


@pytest.mark.parametrize("empty", ["", "   ", "\n"])
def test_an_empty_value_is_refused(tmp_path: Path, empty: str) -> None:
    """Absence is stated to a model as a literal, never rendered as nothing."""
    write(tmp_path, "sample", VALID)
    with pytest.raises(PromptError, match="empty value"):
        render_prompt(tmp_path, "sample", {"subject": "a", "page": empty})


def test_a_non_string_value_is_refused_rather_than_coerced(tmp_path: Path) -> None:
    write(tmp_path, "sample", VALID)
    with pytest.raises(PromptError, match="int"):
        render_prompt(tmp_path, "sample", {"subject": "a", "page": 2})  # type: ignore[dict-item]


# --- the file itself --------------------------------------------------------------


def test_a_missing_file_is_refused_and_names_the_path(tmp_path: Path) -> None:
    with pytest.raises(PromptError, match="absent"):
        render_prompt(tmp_path, "absent", {})


@pytest.mark.parametrize("name", ["Sample", "sample-file", "1sample", "", "sample.md"])
def test_a_name_that_is_not_a_prompt_name_is_refused(tmp_path: Path, name: str) -> None:
    with pytest.raises(PromptError):
        render_prompt(tmp_path, name, {})


def test_a_file_with_no_header_fence_is_refused(tmp_path: Path) -> None:
    write(tmp_path, "bare", "Just body text.\n\n## Output contract\n\nA word.\n")
    with pytest.raises(PromptError, match="must open"):
        render_prompt(tmp_path, "bare", {})


def test_an_unclosed_header_is_refused(tmp_path: Path) -> None:
    write(tmp_path, "open", "---\nname: open\nversion: 1\n\nBody.\n")
    with pytest.raises(PromptError, match="not closed"):
        render_prompt(tmp_path, "open", {})


def test_a_header_name_that_disagrees_with_the_file_name_is_refused(
    tmp_path: Path,
) -> None:
    """A copied file must not quietly answer to the wrong name."""
    write(tmp_path, "copied", VALID)
    with pytest.raises(PromptError, match="sample"):
        render_prompt(tmp_path, "copied", {})


@pytest.mark.parametrize(
    ("header", "message"),
    [
        ("name: x\nversion: 1\ntier: cheap", "unknown header key"),
        ("name: x\nversion: 1\nversion: 2", "appears twice"),
        ("name: x\nversion:", "has no value"),
        ("name: x", "missing version"),
        ("version: 1", "missing name"),
        ("name x\nversion: 1", "not 'key: value'"),
    ],
)
def test_a_malformed_header_is_refused(
    tmp_path: Path, header: str, message: str
) -> None:
    write(tmp_path, "x", f"---\n{header}\n---\n\nBody.\n\n## Output contract\n\nA word.\n")
    with pytest.raises(PromptError, match=message):
        render_prompt(tmp_path, "x", {})


def test_an_empty_body_is_refused(tmp_path: Path) -> None:
    write(tmp_path, "hollow", "---\nname: hollow\nversion: 1\n---\n\n")
    with pytest.raises(PromptError, match="body is empty"):
        render_prompt(tmp_path, "hollow", {})


def test_a_body_with_no_output_contract_is_refused(tmp_path: Path) -> None:
    """The schema and the prompt reach the model together and are reviewed together."""
    write(tmp_path, "loose", "---\nname: loose\nversion: 1\n---\n\nRead it.\n")
    with pytest.raises(PromptError, match="Output contract"):
        render_prompt(tmp_path, "loose", {})


@pytest.mark.parametrize(
    "broken", ["{{ subject }}", "{{Subject}}", "{{sub ject}}", "{{}}", "{{sub-ject}}"]
)
def test_a_malformed_placeholder_is_refused_at_load(tmp_path: Path, broken: str) -> None:
    """A typo inside the braces is caught here rather than shipped to a model."""
    write(
        tmp_path,
        "typo",
        f"---\nname: typo\nversion: 1\n---\n\nRead {broken}.\n\n"
        "## Output contract\n\nA word.\n",
    )
    with pytest.raises(PromptError, match="malformed placeholder"):
        render_prompt(tmp_path, "typo", {"subject": "a"})


def test_a_placeholder_repeated_in_the_body_takes_one_value(tmp_path: Path) -> None:
    write(
        tmp_path,
        "twice",
        "---\nname: twice\nversion: 1\n---\n\n{{word}} and {{word}}.\n\n"
        "## Output contract\n\nA word.\n",
    )
    assert "yes and yes." in render_prompt(tmp_path, "twice", {"word": "yes"}).text


def test_a_substituted_value_is_not_scanned_for_placeholders(tmp_path: Path) -> None:
    """Substitution happens once; a value is data, never more template."""
    write(
        tmp_path,
        "once",
        "---\nname: once\nversion: 1\n---\n\n{{word}}\n\n## Output contract\n\nA word.\n",
    )
    rendered = render_prompt(tmp_path, "once", {"word": "{{word}}"})
    assert rendered.text.startswith("{{word}}")


# --- the shipped prompts ----------------------------------------------------------


def test_every_shipped_prompt_file_loads() -> None:
    """The loader's own rules, applied to the directory the repository ships."""
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    names = sorted(
        path.stem for path in prompts_dir.glob("*.md") if path.stem.islower()
    )
    assert names, "no prompt files found"
    for name in names:
        placeholders = {
            "read_invoice": {"page_count": "2"},
            "read_consignment_note": {"page_count": "1"},
            "classify_page_type": {"page_count": "2", "page_manifest": "[]"},
            "adapter_check_text": {"word": "bonjour"},
            "adapter_check_vision": {"width": "64", "height": "32"},
        }[name]
        assert render_prompt(prompts_dir, name, placeholders).name == name
