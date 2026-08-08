import unittest

from evalkit.parse import Declaration, Good
from evalkit.score import score_case


def good(desc: str, hs: str, net: float) -> Good:
    return Good(
        numeric=None,
        description=desc,
        hs_code=hs,
        origin="DE",
        unit="166",
        quantity=net,
        net_weight=net,
        gross_weight=net + 10,
        invoiced_cost=net * 3,
        package_count=8.0,
    )


def decl(goods: list[Good]) -> Declaration:
    return Declaration(
        goods=tuple(goods),
        total_goods=len(goods),
        total_packages=sum(g.package_count or 0 for g in goods),
        total_cost=sum(g.invoiced_cost or 0 for g in goods),
        currency="USD",
    )


class ScoreCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gold = decl([good("ՌԵԼԵ ABB", "8536100000", 100), good("ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ", "7318150000", 200)])

    def test_identical_passes_perfectly(self) -> None:
        case = score_case(self.gold, self.gold, "identical")
        self.assertTrue(case.passed)
        self.assertEqual(case.line_f1, 1.0)
        self.assertEqual(case.numeric_exact_rate, 1.0)
        self.assertEqual(case.code_exact_rate, 1.0)
        self.assertEqual(case.desc_chrf, 1.0)
        self.assertTrue(all(case.totals_ok.values()))

    def test_perturbed_line_fails_but_still_aligns(self) -> None:
        mine = decl([
            good("ՌԵԼԵ ABB", "8536100000", 100),  # perfect
            good("ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ", "7318159000", 260),  # code tail + weight wrong
        ])
        case = score_case(mine, self.gold, "perturbed")
        self.assertFalse(case.passed)
        self.assertEqual(case.line_f1, 1.0)  # still matched (desc identical)
        self.assertEqual(case.code_exact_rate, 0.5)
        self.assertEqual(case.code_level_rate[6], 1.0)  # both agree to 6 digits
        self.assertEqual(case.numeric_by_field["net_weight"], 0.5)
        self.assertEqual(case.line_pass_rate, 0.5)

    def test_atoms_drive_rubric_exactly(self) -> None:
        mine = decl([good("ՌԵԼԵ", "8536100000", 100), good("ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ", "7318150000", 200)])
        atoms = [{"brand": "ABB", "trade_name": "RELAY ABB"}, {}]
        case = score_case(mine, self.gold, "atoms", atoms=atoms)
        # line 1 dropped the ABB brand the ground truth required
        self.assertEqual(case.rubric_rate["brand_retained"], 0.0)


class GroundingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gold = decl([good("ՌԵԼԵ ABB", "8536100000", 100), good("ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ", "7318150000", 200)])
        # line 2 misses only the net weight (None where gold has 200)
        mine_line2 = Good(
            numeric=None, description="ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ", hs_code="7318150000", origin="DE",
            unit="166", quantity=200, net_weight=None, gross_weight=210, invoiced_cost=600,
            package_count=8.0,
        )
        self.mine = decl([good("ՌԵԼԵ ABB", "8536100000", 100), mine_line2])

    def test_strict_counts_the_miss(self) -> None:
        s = score_case(self.mine, self.gold, "strict")
        self.assertFalse(s.lines[1].passed)
        self.assertEqual(s.excused_external, 0)

    def test_source_excuses_value_absent_from_scan(self) -> None:
        # scan text mentions 100 and gross 210 but never the net weight 200
        s = score_case(self.mine, self.gold, "lenient", source_text="relay abb 100 kg; screw gross 210")
        self.assertIn("net_weight", s.lines[1].excused)
        self.assertTrue(s.lines[1].passed)
        self.assertGreaterEqual(s.excused_external, 1)

    def test_source_with_the_value_stays_a_miss(self) -> None:
        # the scan DID carry 200, so missing it is genuinely our failure
        s = score_case(self.mine, self.gold, "grounded", source_text="screw net 200 gross 210")
        self.assertNotIn("net_weight", s.lines[1].excused)
        self.assertFalse(s.lines[1].passed)


if __name__ == "__main__":
    unittest.main()
