"""Reverse seeding from the history DB (the LLM translation step needs no test — pure I/O here)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from synth.history import load_history_seed

_RECORDS = [
    {"record_key": "abc123", "description": "ՊԼԱՍՏԻԿ ԽՈՂՈՎԱԿ", "code": "39172300000",
     "measure_unit_code": "166", "net_weight": "100", "gross_weight": "105",
     "brand": "VERSEL", "part_number": "None", "importer_name": "«Ռեալ» ՍՊԸ", "sender_name": "None"},
    {"record_key": "def456", "description": "ԱՊԱԿԵ ՇԻՇ", "code": "70109000000",
     "measure_unit_code": "166", "net_weight": "50", "brand": "None", "importer_name": "«Այլ» ՍՊԸ"},
    {"record_key": "nohs", "description": "X", "code": "None"},  # no HS → skipped
]


class HistorySeedTests(unittest.TestCase):
    def _seed(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as fh:
            for r in _RECORDS:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            path = fh.name
        return load_history_seed(Path(path))

    def test_skips_records_without_hs(self) -> None:
        self.assertEqual(len(self._seed().pool), 2)

    def test_branded_good_carries_trade_name(self) -> None:
        seed = self._seed()
        self.assertEqual(seed.pool[0].trade_name, "VERSEL")
        self.assertEqual(seed.pool[0].hs_code, "39172300000")
        self.assertEqual(seed.pool[0].quantity, 100.0)

    def test_unbranded_good_has_no_trade_name(self) -> None:
        self.assertIsNone(self._seed().pool[1].trade_name)

    def test_real_party_names_become_forbidden(self) -> None:
        self.assertIn("«Ռեալ» ՍՊԸ", self._seed().forbidden_terms)


if __name__ == "__main__":
    unittest.main()
