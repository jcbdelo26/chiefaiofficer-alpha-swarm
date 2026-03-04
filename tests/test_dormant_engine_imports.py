#!/usr/bin/env python3
"""
Dormant engine import-level smoke tests -- prevent code rot.

These tests validate that dormant engine files:
1. Import cleanly (no broken transitive dependencies)
2. Have a STATUS header in the first 15 lines
3. Export their primary class/callable
4. Reference their feature flag in the docstring/header

This does NOT activate any engine logic -- purely structural validation.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

# (module_path, primary_class_name, status_keyword, feature_flag_name)
DORMANT_ENGINES = [
    ("core.ab_test_engine", "ABTestEngine", "DORMANT", "AB_TEST_ENGINE_ENABLED"),
    ("core.self_annealing_engine", "SelfAnnealingPipeline", "DORMANT", "SELF_ANNEALING_ENGINE_ENABLED"),
    ("core.self_learning_icp", "ICPMemory", "DORMANT", "SELF_LEARNING_ICP_ENABLED"),
    ("execution.rl_engine", "RLEngine", "DORMANT", "RL_ENGINE_ENABLED"),
    ("core.feedback_loop", "FeedbackLoop", "PARTIALLY ACTIVE", "FEEDBACK_LOOP_POLICY_ENABLED"),
]


@pytest.mark.parametrize(
    "module_path,class_name,status_keyword,flag_name",
    DORMANT_ENGINES,
    ids=[e[0].split(".")[-1] for e in DORMANT_ENGINES],
)
class TestDormantEngineContract:
    """Structural contract tests for dormant engine files."""

    def test_imports_cleanly(self, module_path, class_name, status_keyword, flag_name):
        """Engine must import without errors (catches broken dependencies)."""
        mod = importlib.import_module(module_path)
        assert mod is not None

    def test_primary_class_exists(self, module_path, class_name, status_keyword, flag_name):
        """Engine must export its primary class."""
        mod = importlib.import_module(module_path)
        assert hasattr(mod, class_name), (
            f"{module_path} missing primary class '{class_name}'"
        )

    def test_status_header_present(self, module_path, class_name, status_keyword, flag_name):
        """Engine file must have a STATUS: header in the first 15 lines."""
        mod = importlib.import_module(module_path)
        source_file = Path(mod.__file__)
        header_lines = source_file.read_text(encoding="utf-8").splitlines()[:15]
        header_text = "\n".join(header_lines).upper()
        assert "STATUS:" in header_text, (
            f"{module_path} missing STATUS header in first 15 lines"
        )
        assert status_keyword.upper() in header_text, (
            f"{module_path} STATUS header should contain '{status_keyword}'"
        )

    def test_feature_flag_documented(self, module_path, class_name, status_keyword, flag_name):
        """Engine file must reference its feature flag in the header/docstring."""
        mod = importlib.import_module(module_path)
        source_file = Path(mod.__file__)
        # Check first 30 lines (covers docstring)
        header_lines = source_file.read_text(encoding="utf-8").splitlines()[:30]
        header_text = "\n".join(header_lines)
        assert flag_name in header_text, (
            f"{module_path} should reference '{flag_name}' in header/docstring"
        )
