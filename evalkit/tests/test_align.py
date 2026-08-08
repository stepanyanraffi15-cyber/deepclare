import unittest

from evalkit.align import align
from evalkit.parse import Good


def good(desc: str, hs: str, qty: float = 100.0) -> Good:
    return Good(
        numeric=None,
        description=desc,
        hs_code=hs,
        origin="DE",
        unit="166",
        quantity=qty,
        net_weight=qty,
        gross_weight=qty + 5,
        invoiced_cost=qty * 2,
        package_count=4.0,
    )


class AlignTests(unittest.TestCase):
    def test_reordered_lines_still_match(self) -> None:
        gold = [good("RELAY ABB", "8536100000"), good("STEEL SCREW", "7318150000")]
        mine = [gold[1], gold[0]]  # reversed
        a = align(mine, gold)
        self.assertEqual(len(a.pairs), 2)
        self.assertEqual(a.f1(), 1.0)

    def test_missing_line_lowers_recall(self) -> None:
        gold = [good("RELAY", "8536100000"), good("SCREW", "7318150000"), good("PIPE", "7304110000")]
        mine = [good("RELAY", "8536100000"), good("SCREW", "7318150000")]
        a = align(mine, gold)
        self.assertEqual(len(a.pairs), 2)
        self.assertEqual(a.precision(), 1.0)
        self.assertAlmostEqual(a.recall(), 2 / 3, places=6)
        self.assertEqual(len(a.unmatched_gold), 1)

    def test_invented_line_lowers_precision(self) -> None:
        gold = [good("RELAY", "8536100000")]
        mine = [good("RELAY", "8536100000"), good("MYSTERY", "9999999999")]
        a = align(mine, gold)
        self.assertEqual(len(a.pairs), 1)
        self.assertAlmostEqual(a.precision(), 0.5, places=6)
        self.assertEqual(a.recall(), 1.0)
        self.assertEqual(len(a.unmatched_mine), 1)


if __name__ == "__main__":
    unittest.main()
