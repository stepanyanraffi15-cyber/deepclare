# Public website (web/)

The public marketing site for DeepClare: dark "AI-SaaS" landing plus the policy pages
(privacy, terms, cancellation/refund). Armenian-language only; any added language must
mirror the full content.

No pricing and no lead-capture form — both existed in the copied-in version and were
deliberately removed (2026-08-09): no `/pricing` route, no `pricing.py`, no `POST
/leads`, no `leads/` package, no footer payment-logo chips. The legal pages (terms,
privacy, refund) still describe a paid-subscription/card-payment flow left over from
before that removal — they were not rewritten, since that's real legal text and out of
scope for a code change. Treat them as stale until someone deliberately revisits them.

This directory is its own deployable unit, separate from `src/deepclare/` (the
declaration pipeline) and from `src/deepclare/service/` (the pipeline's own service
edge). It has its own `pyproject.toml`, its own `Dockerfile`, and its own settings
object (`deepclare_web/config.py`). It carries no import from `src/deepclare` and no
import from `src/deepclare` should ever point back into it.

Origin: copied in from a prior implementation of this same site
(`mootq-ai/services/web/deepclare_web`) per the scoped exception to constraint #1 in the
root `CLAUDE.md`, then adapted to this repo's env-var and `.gitignore` conventions.
Everything below describes what was copied in, not a design done fresh in this repo —
verify before trusting a claim about "the real extension" or "the bank."

- All operator-editable values (legal name, ՀՎՀՀ, address, contacts, Chrome Web Store
  URL) come from `WEB_*` env vars via `SiteConfig.from_env()` — see the root
  `.env.example` for the full list. They default to placeholders; set the real
  registered values before this site is shown to anyone outside development.

## Design system (no build step, vanilla CSS/JS)
- One FIXED dark canvas behind every page (`.bg-canvas` in `base.html`: aurora orbs +
  grid + a scroll-driven "journey" — a blueprint truck that drives to a customs house as
  the page scrolls). Content sits in rounded glass `.module` cards that reveal on scroll
  (`static/site.js`).
- Light surfaces are intentional ONLY for: the extension-panel replica, the paper
  document cards, and legal pages (`.module-light`).
- `static/site.js` = reveal-on-scroll + parallax + journey progress (`--sy`, `--jp` CSS
  vars). Respects `prefers-reduced-motion`. Never put `overflow` rules on `html/body` —
  it breaks the sticky header.
- Static assets are cache-busted via `?v={{ static_v }}` (content hash computed in
  `app.py` over styles.css/demo.js/site.js) — add new mutable assets there too.

## The interactive extension replica (landing, #try)
- A clickable imitation of the real side panel (`extension/sidepanel/`): file zone
  (accepts real files and two draggable sample documents), run options, a 4-stage
  progress stepper, editable goods lines, XML/CSV downloads built from the edited
  fields, a ⋮ menu with history/account/feedback overlays. All local —
  `static/demo.js`, no network calls, no real processing.
- Its field labels and flow were copied from a snapshot of `extension/sidepanel/` at
  copy time — check them against the current extension before trusting they still
  match; they were not written against this repo's extension code.
- `?autoplay=1` on the URL auto-feeds the sample docs (useful for screenshot checks).

## Running and verifying
- Install: `cd web && python -m venv .venv && .venv/bin/pip install -e .[dev]`
- Run: `.venv/bin/python -m deepclare_web.main` → http://localhost:8090
  (or `PORT=... .venv/bin/python -m deepclare_web.main`)
- Tests: `.venv/bin/python -m pytest` (FastAPI `TestClient`, no network).
- No deploy path exists for this yet in this repo — `Dockerfile` builds the image but
  nothing wires it to a target.
