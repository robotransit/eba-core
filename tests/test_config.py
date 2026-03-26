# tests/test_config.py
"""Tests for ECKConfig and effective_policy()."""

from __future__ import annotations

import unittest
from types import MappingProxyType

from eck.config import ECKConfig, PolicyMode


class TestEffectivePolicy(unittest.TestCase):
    """effective_policy() returns correct immutable mapping per policy mode."""

    def test_normal_returns_empty_mappingproxy(self) -> None:
        config = ECKConfig(policy_mode=PolicyMode.NORMAL)
        effective = config.effective_policy()
        self.assertIsInstance(effective, MappingProxyType)
        self.assertEqual(dict(effective), {})

    def test_guided_returns_expected_keys_and_values(self) -> None:
        config = ECKConfig(policy_mode=PolicyMode.GUIDED)
        effective = config.effective_policy()
        self.assertIsInstance(effective, MappingProxyType)
        self.assertEqual(set(effective.keys()), {
            "max_subtasks",
            "critic_strictness",
            "prediction_bias_delta",
        })
        self.assertEqual(effective["max_subtasks"], config._guided_max_subtasks)
        self.assertEqual(effective["critic_strictness"], config._guided_critic_strictness)
        self.assertEqual(effective["prediction_bias_delta"], config._guided_prediction_bias_delta)

    def test_enforced_returns_expected_keys_and_values(self) -> None:
        """ENFORCED mode returns max_subtasks=1 and critic_strictness=1.0."""
        config = ECKConfig(policy_mode=PolicyMode.ENFORCED)
        effective = config.effective_policy()
        self.assertIsInstance(effective, MappingProxyType)
        self.assertEqual(set(effective.keys()), {
            "max_subtasks",
            "critic_strictness",
        })
        self.assertEqual(effective["max_subtasks"], 1)
        self.assertEqual(effective["critic_strictness"], 1.0)

    def test_halt_returns_halt_true(self) -> None:
        config = ECKConfig(policy_mode=PolicyMode.HALT)
        effective = config.effective_policy()
        self.assertIsInstance(effective, MappingProxyType)
        self.assertEqual(dict(effective), {"halt": True})

    def test_is_immutable(self) -> None:
        config = ECKConfig(policy_mode=PolicyMode.GUIDED)
        effective = config.effective_policy()
        with self.assertRaises(TypeError):
            effective["new_key"] = "value"

    def test_unknown_policy_mode_raises(self) -> None:
        """effective_policy() raises ValueError for unknown policy modes."""
        config = ECKConfig(policy_mode=PolicyMode.NORMAL)
        # Patch policy_mode to an invalid value to exercise the raise
        import dataclasses
        bad_config = dataclasses.replace(config)
        object.__setattr__(bad_config, "policy_mode", "INVALID")
        with self.assertRaises((ValueError, AttributeError)):
            bad_config.effective_policy()


if __name__ == "__main__":
    unittest.main()
