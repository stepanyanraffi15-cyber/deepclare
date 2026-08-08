"""Chapter legal notes — the General Interpretative Rules context for classification.

These notes are what legally separates two commodity codes that look equally plausible,
and they are the input the final code pick reasons over. The nomenclature artifact ships
`notes.json` as an empty dict, which means the classifier has been reading the literal
"(none)" on every run and choosing without legal context, silently and with no error.

Source is the UK Trade Tariff public API. The basis for using it: chapter notes are
legal text of the Harmonized System, which is harmonized internationally to six digits,
so they apply to this tree as much as to any other HS-derived nomenclature. It is the
same reasoning that makes official English heading titles valid here.

Measured on the current tree: 94 of 96 chapters carry a note, totalling roughly 338,000
characters. The two without are genuinely noteless, not a fetch failure.

Caveat worth carrying: where the EAEU publishes its own supplementary notes, these do
not capture them. An authority-published EAEU note set would be the more faithful source
and should replace this if one is obtained.
"""
import json, re, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

ART = "data/reference/nomenclature_exim"
chapters = sorted({json.loads(l)["code"] for l in open(f"{ART}/entries.jsonl", encoding="utf-8")
                   if len(json.loads(l)["code"]) == 2})
print(f"chapters to fetch: {len(chapters)}")

def clean(s):
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s or "")   # markdown links -> text
    s = re.sub("<[^>]+>", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()

def one(ch):
    url = f"https://www.trade-tariff.service.gov.uk/api/v2/chapters/{ch}"
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                d = json.load(r)
            return ch, clean(d["data"]["attributes"].get("chapter_note", ""))
        except Exception as e:
            if attempt == 3: return ch, f"__ERR__{e}"
            time.sleep(1.0 * 2**attempt)

notes, errs = {}, []
with ThreadPoolExecutor(6) as p:
    for ch, note in p.map(one, chapters):
        if note.startswith("__ERR__"): errs.append((ch, note[7:]))
        elif note: notes[ch] = note

json.dump(notes, open(f"{ART}/notes.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, sort_keys=True)
total = sum(len(v) for v in notes.values())
print(f"chapters with a note : {len(notes)}/{len(chapters)}")
print(f"chapters with none   : {len(chapters)-len(notes)-len(errs)}")
print(f"fetch errors         : {len(errs)} {errs[:3]}")
print(f"total legal text     : {total:,} characters")
