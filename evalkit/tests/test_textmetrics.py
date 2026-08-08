import unittest

from evalkit.textmetrics import chrf, normalized_exact, token_f1


class ChrfTests(unittest.TestCase):
    def test_identical_is_one(self) -> None:
        self.assertEqual(chrf("ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ", "ՊՈՂՊԱՏԵ ՊՏՈՒՏԱԿ"), 1.0)

    def test_both_empty_is_one(self) -> None:
        self.assertEqual(chrf("", ""), 1.0)

    def test_one_empty_is_zero(self) -> None:
        self.assertEqual(chrf("something", ""), 0.0)

    def test_whitespace_insensitive(self) -> None:
        self.assertEqual(chrf("A B  C", "a b c"), 1.0)

    def test_partial_between_zero_and_one(self) -> None:
        score = chrf("MEILOSE GMC 3112D", "MEILOSE GMC 3110")
        self.assertTrue(0.0 < score < 1.0)

    def test_more_similar_scores_higher(self) -> None:
        near = chrf("cellulose ether meilose", "cellulose ether meilose x")
        far = chrf("cellulose ether meilose", "gypsum retarder additive")
        self.assertGreater(near, far)


class TokenAndExactTests(unittest.TestCase):
    def test_token_f1_full_overlap(self) -> None:
        self.assertEqual(token_f1("a b c", "c b a"), 1.0)

    def test_token_f1_partial(self) -> None:
        self.assertAlmostEqual(token_f1("a b c d", "a b x y"), 0.5, places=6)

    def test_token_f1_disjoint(self) -> None:
        self.assertEqual(token_f1("a b", "c d"), 0.0)

    def test_normalized_exact(self) -> None:
        self.assertTrue(normalized_exact("Hello   World", "hello world"))
        self.assertFalse(normalized_exact("hello", "world"))


if __name__ == "__main__":
    unittest.main()
