# reference_data

Small, hand-curated lookup tables. They are **data, not code**: a table whose content
lives as a Python constant cannot be corrected without a release, and dossier 11 §4 lists
exactly that ("reference data trapped in code") as a defect of the design this product
replaces.

They are tracked in git, unlike `data/`. Each is a few kilobytes, each was curated by
hand, and none of them is reproducible by re-running an acquisition step.

| File | Dossier 11 | What it is |
|---|---|---|
| `units.json` | D10.1 | Free-text and nomenclature unit strings → OKEI code + Armenian name |
| `product_kind_units.json` | D10.2 | Product-kind → OKEI, tier 3 of the unit ladder |
| `packing_codes.json` | D10.3 | Packing free text → UN/ECE Recommendation 21 code |
| `package_counting_units.json` | D10.6 | Quantity-unit words that count packages, not items |
| `brand_stoplist.json` | D10.7 | Latin tokens that are never brands |
| `package_nouns.json` | D10.9 | Packing code → Armenian package noun, for box 31 |
| `border_offices.json` | D10.4 | Dispatch country → land border crossing office |
| `countries.json` | D7 / D10.8 | ISO-2 code → Armenian customs name, plus printed aliases |
| `size_units.json` | §6.8 | Latin size-unit tokens → Armenian, for the box 31 size segment |
| `container_keywords.json` | §5.6 | Words in a consignment note that mean a container |

Two conventions hold across every file:

* **Aliases are matched uppercased.** Every alias here is stored uppercase, and the
  matcher uppercases the text it is given. Nothing depends on the case of a document.
* **Order can be part of the data.** In `packing_codes.json` the entries are matched
  first-hit in the order written, and the big-bag row must stay above the bag row or
  `BIG BAGS` matches as bags.

## What did not transfer, and what stands in for it

* **The portal's own 32-unit measure classifier (D6) is not here.** Nothing emitted may
  fall outside it. What stands in is `units.json`: the thirteen units this product can
  ever resolve, every one of them a unit the predecessor filed and the portal accepted.
  Membership of that set is checked before a unit is filed. That is a subset guarantee by
  construction, not a check against the real 32-row table, and the real table is what
  should replace it.
* **The country table is corpus-derived, not portal-derived.** `countries.json` carries
  only the code/name pairs that appear in the 71 accepted-shape declarations in
  `evalkit/corpus`. Codes needed for routing but never seen with an Armenian name carry
  `"name_hy": null` — the code still resolves for border-office lookup, and the code+name
  pair is simply never written, which is the all-or-nothing rule of dossier 03 §4.5
  working as intended rather than a gap being papered over.
