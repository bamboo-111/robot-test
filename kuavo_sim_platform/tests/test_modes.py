import unittest
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim.modes import CtrlMode, resolve_mode


class ResolveModeTest(unittest.TestCase):
    def test_resolves_names_ints_and_enum(self):
        self.assertEqual(resolve_mode("BaseOnly"), 2)
        self.assertEqual(resolve_mode("2"), 2)
        self.assertEqual(resolve_mode(2), 2)
        self.assertEqual(resolve_mode(CtrlMode.BaseOnly), 2)

    def test_rejects_unknown_name(self):
        with self.assertRaisesRegex(ValueError, "unknown mode"):
            resolve_mode("Drive")

    def test_rejects_out_of_range_int(self):
        with self.assertRaisesRegex(ValueError, "out of range"):
            resolve_mode(9)


if __name__ == "__main__":
    unittest.main()
