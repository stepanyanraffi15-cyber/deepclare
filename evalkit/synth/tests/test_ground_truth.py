"""The real-renderer ground truth is portal-shaped (skipped where the agent is absent).

This path imports `mootq_agent`, so it only runs when the agent is on the path
(i.e. generating in the main repo). The committed corpus already carries the
real XML, so the competition repo never needs this.
"""

from __future__ import annotations

import unittest

try:
    import mootq_agent  # noqa: F401

    HAVE_AGENT = True
except ImportError:
    HAVE_AGENT = False

from synth.recombine import make_case
from synth.tests.test_synth import _SEED_XML, load_seed_from_string


@unittest.skipUnless(HAVE_AGENT, "mootq_agent not on path")
class GroundTruthTests(unittest.TestCase):
    def test_render_is_portal_shaped_and_parses(self) -> None:
        from evalkit import parse_declaration

        from synth.to_declaration_input import render_ground_truth

        case = make_case(load_seed_from_string(_SEED_XML), 3)
        xml = render_ground_truth(case)
        # the shape the portal's type check requires
        self.assertTrue(xml.startswith("<?xml"))
        self.assertIn("ESADout_CU:ESADout_CU", xml)
        self.assertIn("schemaLocation", xml)
        # the verifier still reads it, and trade names survive verbatim
        parsed = parse_declaration(xml)
        self.assertEqual(len(parsed.goods), len(case.goods))
        for g in case.goods:
            if g.trade_name:
                self.assertIn(g.trade_name, xml)


if __name__ == "__main__":
    unittest.main()
