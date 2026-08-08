"""End-to-end: seed -> recombine -> render, cross-checked with the verifier.

Uses a tiny inline declaration as the seed so the test needs no private data.
"""

from __future__ import annotations

import random
import unittest

from evalkit import parse_declaration, score_case
from synth.guardrails import consistency, leak_scan
from synth.recombine import make_case
from synth.render_xml import render_atoms, render_xml
from synth.seed import Seed, load_seed
from synth.stamps import signature_svg, stamp_svg

_SEED_XML = """
<ESADout_CU><ESADout_CUGoodsShipment>
  <ESADout_CUConsignor><OrganizationName>REAL SECRET TRADING LLC</OrganizationName></ESADout_CUConsignor>
  <ESADout_CUGoods>
    <GoodsNumeric>1</GoodsNumeric>
    <GoodsDescription>ՑԵԼՅՈՒԼՈԶԱՅԻՆ ԵԹԵՐ, MEILOSE GMC 3110, ՓՈՇԵՆՄԱՆ</GoodsDescription>
    <GoodsTNVEDCode>39123985000</GoodsTNVEDCode>
    <OriginCountryCode>CN</OriginCountryCode>
    <NetWeightQuantity>3000</NetWeightQuantity><GrossWeightQuantity>3100</GrossWeightQuantity>
    <InvoicedCost>12510</InvoicedCost><GoodsQuantity>3000</GoodsQuantity>
    <MeasureUnitQualifierCode>166</MeasureUnitQualifierCode>
    <ESADGoodsPackaging><PakageQuantity>120</PakageQuantity></ESADGoodsPackaging>
  </ESADout_CUGoods>
  <ESADout_CUGoods>
    <GoodsNumeric>2</GoodsNumeric>
    <GoodsDescription>ՑԵԼՅՈՒԼՈԶԱՅԻՆ ՄԱՆՐԱԹԵԼ, DERFIBER 330</GoodsDescription>
    <GoodsTNVEDCode>39129090000</GoodsTNVEDCode>
    <OriginCountryCode>DE</OriginCountryCode>
    <NetWeightQuantity>5050</NetWeightQuantity><GrossWeightQuantity>5175</GrossWeightQuantity>
    <InvoicedCost>12221</InvoicedCost><GoodsQuantity>5050</GoodsQuantity>
    <MeasureUnitQualifierCode>166</MeasureUnitQualifierCode>
    <ESADGoodsPackaging><PakageQuantity>202</PakageQuantity></ESADGoodsPackaging>
  </ESADout_CUGoods>
  <ESADout_CUGoods>
    <GoodsNumeric>3</GoodsNumeric>
    <GoodsDescription>ԲԻՈՑԻԴԱՅԻՆ ՊԱՀՊԱՆԻՉ, ACTICIDE LA 1209</GoodsDescription>
    <GoodsTNVEDCode>38089480000</GoodsTNVEDCode>
    <OriginCountryCode>GB</OriginCountryCode>
    <NetWeightQuantity>100</NetWeightQuantity><GrossWeightQuantity>105</GrossWeightQuantity>
    <InvoicedCost>683</InvoicedCost><GoodsQuantity>100</GoodsQuantity>
    <MeasureUnitQualifierCode>166</MeasureUnitQualifierCode>
    <ESADGoodsPackaging><PakageQuantity>4</PakageQuantity></ESADGoodsPackaging>
  </ESADout_CUGoods>
</ESADout_CUGoodsShipment></ESADout_CU>
"""


class SeedTests(unittest.TestCase):
    def test_pool_extracts_trade_names_and_forbidden(self) -> None:
        seed = load_seed_from_string(_SEED_XML)
        self.assertEqual(len(seed.pool), 3)
        self.assertEqual(seed.pool[0].trade_name, "MEILOSE GMC 3110")
        self.assertEqual(seed.pool[0].brand, "MEILOSE")
        self.assertIn("REAL SECRET TRADING LLC", seed.forbidden_terms)


class RecombineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.seed = load_seed_from_string(_SEED_XML)

    def test_deterministic_in_seed(self) -> None:
        a = make_case(self.seed, 7)
        b = make_case(self.seed, 7)
        self.assertEqual(render_xml(a), render_xml(b))

    def test_case_is_consistent(self) -> None:
        case = make_case(self.seed, 3)
        self.assertEqual(consistency(case), [])

    def test_no_real_party_leaks(self) -> None:
        case = make_case(self.seed, 5)
        self.assertEqual(leak_scan(render_xml(case), self.seed.forbidden_terms), [])

    def test_partition_yields_valid_families(self) -> None:
        from synth.recombine import partition

        families = partition(self.seed, 2)
        self.assertTrue(families)
        self.assertTrue(all(len(f.pool) >= 2 for f in families))
        self.assertLessEqual(sum(len(f.pool) for f in families), len(self.seed.pool))

    def test_apply_name_map_sets_invoice_name(self) -> None:
        from synth.enrich import apply_name_map

        mapped = apply_name_map(self.seed, {"0": "photo frame 15*21"})
        self.assertEqual(mapped.pool[0].source_name, "photo frame 15*21")
        # a branded good keeps its brand as the Model column; unmapped goods are untouched
        self.assertEqual(mapped.pool[0].trade_name, self.seed.pool[0].trade_name)
        self.assertEqual(mapped.pool[1].source_name, self.seed.pool[1].source_name)


class RenderAndVerifyTests(unittest.TestCase):
    def test_ground_truth_scores_perfect_against_itself(self) -> None:
        seed = load_seed_from_string(_SEED_XML)
        case = make_case(seed, 2)
        xml = render_xml(case)
        decl = parse_declaration(xml)
        result = score_case(decl, decl, name=case.case_id)
        self.assertTrue(result.passed)
        self.assertEqual(result.line_f1, 1.0)
        self.assertEqual(result.code_exact_rate, 1.0)

    def test_atoms_align_to_goods(self) -> None:
        import json

        seed = load_seed_from_string(_SEED_XML)
        case = make_case(seed, 4)
        atoms = json.loads(render_atoms(case))
        self.assertEqual(len(atoms["goods"]), len(case.goods))
        self.assertIn("trade_name", atoms["goods"][0])


class StampTests(unittest.TestCase):
    def test_svgs_are_wellformed(self) -> None:
        rng = random.Random(1)
        self.assertIn("<svg", stamp_svg("NOVA CHEM", rng))
        self.assertIn("<path", signature_svg(rng))


def load_seed_from_string(xml: str) -> Seed:
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as fh:
        fh.write(xml)
        path = fh.name
    return load_seed(Path(path))


if __name__ == "__main__":
    unittest.main()
