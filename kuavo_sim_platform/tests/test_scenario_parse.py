import unittest
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim.scenario import validate_scenario


class ScenarioValidationTest(unittest.TestCase):
    def test_accepts_probe_shape(self):
        scenario = validate_scenario(
            {
                "name": "base_probe",
                "steps": [
                    {"action": "wait_ready", "timeout": 30},
                    {"action": "set_mode", "mode": "BaseOnly"},
                    {"action": "move_for", "duration": 1.0, "x": 0.05},
                    {"action": "stop_base"},
                    {"action": "set_mode", "mode": "NoControl"},
                ],
            }
        )
        self.assertEqual(scenario["steps"][2]["duration"], 1.0)

    def test_rejects_unknown_action(self):
        with self.assertRaisesRegex(ValueError, "unknown action"):
            validate_scenario({"steps": [{"action": "dance"}]})

    def test_rejects_move_without_duration(self):
        with self.assertRaisesRegex(ValueError, "missing duration"):
            validate_scenario({"steps": [{"action": "move_for"}]})

    def test_rejects_set_mode_without_mode(self):
        with self.assertRaisesRegex(ValueError, "missing mode"):
            validate_scenario({"steps": [{"action": "set_mode"}]})


if __name__ == "__main__":
    unittest.main()
