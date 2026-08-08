import unittest

from evalkit.rubric import detect_brand, score_rubric


class DetectBrandTests(unittest.TestCase):
    def test_finds_latin_brand(self) -> None:
        self.assertEqual(detect_brand("ՑԵԼՅՈՒԼՈԶԱՅԻՆ ԵԹԵՐ, MEILOSE GMC 3110"), "MEILOSE")

    def test_skips_units_and_acronyms(self) -> None:
        self.assertIsNone(detect_brand("ԺԱՊԱՎԵՆ PVC 50 MM"))

    def test_none_when_unbranded(self) -> None:
        self.assertIsNone(detect_brand("ՓԱՅՏԵ ՏԱԽՏԱԿ ԱՌԱՆՑ ԱՊՐԱՆՔԱՅԻՆ ՆՇԱՆԻ"))


class RubricWithAtomsTests(unittest.TestCase):
    def test_brand_and_trade_retained(self) -> None:
        r = score_rubric(
            "ՑԵԼՅՈՒԼՈԶԱՅԻՆ ԵԹԵՐ, MEILOSE GMC 3110, ՓՈՇԵՆՄԱՆ",
            brand="MEILOSE",
            trade_name="MEILOSE GMC 3110",
            material="ՑԵԼՅՈՒԼՈԶ",
        )
        self.assertTrue(r.brand_retained)
        self.assertTrue(r.trade_name_present)
        self.assertTrue(r.material_stated)
        self.assertTrue(r.no_hallucinated_brand)

    def test_missing_trade_name_flagged(self) -> None:
        r = score_rubric("ՑԵԼՅՈՒԼՈԶԱՅԻՆ ԵԹԵՐ", brand="MEILOSE", trade_name="MEILOSE GMC 3110")
        self.assertFalse(r.brand_retained)
        self.assertFalse(r.trade_name_present)

    def test_hallucinated_brand_detected(self) -> None:
        # output invents DERFIBER when the known brand is MEILOSE and ref never says DERFIBER
        r = score_rubric("ԵԹԵՐ DERFIBER 330", ref="ԵԹԵՐ MEILOSE", brand="MEILOSE")
        self.assertFalse(r.no_hallucinated_brand)


class RubricNoAtomsTests(unittest.TestCase):
    def test_expected_brand_detected_from_ref(self) -> None:
        r = score_rubric("ԵԹԵՐ MEILOSE GMC 3110", ref="ԵԹԵՐ MEILOSE GMC 3110")
        self.assertTrue(r.brand_retained)
        self.assertIsNone(r.trade_name_present)  # nothing asserted

    def test_material_only_when_ref_states_one(self) -> None:
        r = score_rubric("ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ", ref="ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ")
        self.assertTrue(r.material_stated)


if __name__ == "__main__":
    unittest.main()
