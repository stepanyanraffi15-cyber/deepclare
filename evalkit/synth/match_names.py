"""Cross-lingual name matching — attach a real English invoice name to each good.

Some seeds (big multi-line invoices) carry unbranded goods whose declaration text is
Armenian-only, so no product name can be extracted from the declaration. The real
English names live on the invoice (an xlsx table, or a scanned PDF), but the invoice
and declaration don't line up 1:1 — the broker consolidates and rephrases (e.g. a
218-line invoice → 135 declaration goods). So we match by MEANING with an LLM: for
each Armenian declaration good, pick the English invoice name of the same product.

Dev-only (imports langchain_google_genai + reads a private invoice). Run once; cache
the resulting {good_index: english_name} map and generate from it.
"""

from __future__ import annotations

import json
import os

from pydantic import BaseModel

from .seed import Seed

_SYSTEM = """You align Armenian customs-declaration goods to the English product names printed on \
the invoice they were declared from.

You are given DECLARATION GOODS (each an id + an Armenian description) and INVOICE NAMES (English \
product names printed on the invoice). For each declaration good, choose the ONE invoice name that \
denotes the SAME physical product — matching across languages by what the product IS.

Return, per good id, its `name` copied VERBATIM from the invoice-name list, or null if none clearly \
matches. One invoice name may serve several goods (invoices are more granular than declarations). \
Never invent a name."""


class _Match(BaseModel):
    id: str
    name: str | None = None


class _Matches(BaseModel):
    matches: list[_Match] = []


def read_xlsx_items(path: str) -> list[dict]:
    """Read an invoice xlsx's line-item table → [{code, en, hy}]. Skips the header preamble."""
    import openpyxl

    ws = openpyxl.load_workbook(path, data_only=True).active
    items: list[dict] = []
    started = False
    for row in ws.iter_rows(values_only=True):
        if not started:
            if any(str(c).strip().upper() == "DESCRIPTION" for c in row if c):
                started = True
            continue
        if not row or row[0] is None:
            if items:
                break
            continue
        try:
            int(row[0])
        except (TypeError, ValueError):
            continue
        if row[2]:
            items.append({"code": row[1], "en": str(row[2]).strip(), "hy": str(row[3] or "").strip()})
    return items


def gemini_model(model: str | None = None):
    from langchain_google_genai import ChatGoogleGenerativeAI

    name = model or os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    return ChatGoogleGenerativeAI(model=name, google_api_key=os.environ["GOOGLE_API_KEY"], temperature=0)


def match_names(seed: Seed, candidate_names: list[str], model, batch: int = 25) -> dict[int, str]:
    """Map each pool good's index → its best English invoice name (LLM, batched)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    names = sorted({n for n in candidate_names if n})
    structured = model.with_structured_output(_Matches)
    out: dict[int, str] = {}
    valid = set(names)
    for start in range(0, len(seed.pool), batch):
        chunk = seed.pool[start : start + batch]
        goods = [{"id": str(start + i), "armenian": g.armenian_desc} for i, g in enumerate(chunk)]
        human = (
            "DECLARATION GOODS (JSON):\n" + json.dumps(goods, ensure_ascii=False)
            + "\n\nINVOICE NAMES (JSON):\n" + json.dumps(names, ensure_ascii=False)
        )
        result = structured.invoke([SystemMessage(content=_SYSTEM), HumanMessage(content=human)])
        for m in result.matches:
            if m.name and m.name in valid and m.id.isdigit():
                out[int(m.id)] = m.name
    return out
