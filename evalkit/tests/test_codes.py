import unittest

from evalkit.codes import score_code


class CodeTests(unittest.TestCase):
    def test_exact(self) -> None:
        s = score_code("39123985000", "39123985000")
        self.assertTrue(s.exact)
        self.assertEqual(s.prefix_len, 11)
        self.assertTrue(s.at(2) and s.at(6) and s.at(10))

    def test_diverges_at_national_tail(self) -> None:
        # same to 6 digits (chapter/heading/subheading), differ after
        s = score_code("39123985000", "39123990000")
        self.assertFalse(s.exact)
        self.assertEqual(s.prefix_len, 6)
        self.assertTrue(s.at(6))
        self.assertFalse(s.at(8))

    def test_wrong_chapter(self) -> None:
        s = score_code("39123985000", "84713000000")
        self.assertFalse(s.exact)
        self.assertEqual(s.prefix_len, 0)
        self.assertFalse(s.at(2))

    def test_ignores_non_digits(self) -> None:
        s = score_code("3912 39 850 00", "39123985000")
        self.assertTrue(s.exact)

    def test_empty_is_not_exact(self) -> None:
        self.assertFalse(score_code("", "").exact)


if __name__ == "__main__":
    unittest.main()
