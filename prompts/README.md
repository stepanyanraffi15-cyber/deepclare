# Prompts

Every prompt this system sends to a model is one file in this directory. No prompt text is
built in Python, not even a one-line instruction. `deepclare.prompting` is the only code
that reads this directory, and it is told where the directory is — the path is
configuration (`PROMPTS_DIR`), never a constant in the loader.

## File format

One Markdown file per prompt, named `<prompt_name>.md`, where the name is lowercase words
joined by underscores. The file is a header block followed by the body:

```
---
name: read_invoice
version: 1
---

Body text, sent to the model as written, with {{named_placeholders}}.

## Output contract

What the model must return.
```

**Header.** Opens on the first line with `---` and closes with the next `---`. It holds
exactly two keys:

| Key | Meaning |
|---|---|
| `name` | Must equal the file name without its extension. The mismatch is a loading error, so a copied file cannot quietly answer to the wrong name. |
| `version` | The version of this text. |

**Body.** Everything after the closing `---`, sent to the model verbatim after
substitution. It must contain a section headed `## Output contract` stating what the model
must return. The loader refuses a file without one: the bound output schema and the prompt
text reach the model together as a single artifact, and a prompt whose stated contract has
drifted away from the schema it is called with is how the two silently contradict each
other.

**Placeholders.** `{{lowercase_name}}`, substituted with a value the caller supplies. No
loops, no conditionals, no expressions, no defaults, no filters — a placeholder is a name
and nothing else. Anything else between double braces is a loading error, so a typo is
caught at load rather than shipped to a model. Single braces are ordinary text, which
leaves JSON examples in a prompt body alone.

## Rendering rules

`render_prompt(prompts_dir, name, values)` returns the rendered text together with the
prompt's name and version, which is what a value produced by the call records as its
provenance.

Substitution is total in both directions and every failure raises:

- a placeholder with no value raises, naming it;
- a value that names no placeholder raises, naming it;
- an empty or whitespace-only value raises. Absence is stated to a model as an explicit
  literal — `unknown`, `(none)` — never rendered as nothing, because a key that is absent
  and a key whose value is missing are different signals and downstream logic depends on
  the difference;
- a non-string value raises. How a value should read to a model is the caller's decision,
  never a coercion here.

Files are read once per process. Prompts do not change during a run.

## Versioning

Bump `version` on any change to the text of a prompt, however small, and treat a version
as immutable once a run has recorded it. A run pins the prompt version behind every value
a model produced, and that pin is worth having only if a version identifies exactly one
piece of text. Two texts that ever shared a version make every result produced under it
unattributable.

## Writing a prompt

- State the output contract explicitly, even though the call also binds a typed schema.
- Never ask for a value the caller already knows. It invites a mislabel and there is
  nothing to gain: the caller overwrites it anyway.
- Prefer withholding to forbidding. A value that is not in the payload cannot be misused,
  and a rule backed by omission cannot be broken.
- Say what absence looks like, and say that absence is never a guess.
- Where a failure survives rewording, change what the model is asked to produce rather
  than how it is asked.
