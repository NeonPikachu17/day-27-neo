"""Runnable verification suite for Dynamic Feature Flag Architecture.

Zero external dependencies — uses Python stdlib assertions.
Run with: python test_feature_flags.py
"""

import json
import os
import tempfile
import time
from pathlib import Path

from feature_flags import FeatureFlagManager, is_enabled, require_flag


def run_checks():
    print("[*] Running dynamic feature flag test suite...")

    # --- 1. Basic Boolean & Default Evaluation ---
    temp_dir = tempfile.TemporaryDirectory()
    temp_config_path = Path(temp_dir.name) / "test_config.json"

    initial_config = {
        "flags": {
            "boolean_active": {"enabled": True},
            "boolean_inactive": {"enabled": False},
            "beta_users": {
                "enabled": True,
                "allowed_users": ["alice", "trainer_tsubaki"],
            },
            "gradual_rollout": {
                "enabled": True,
                "rollout_percentage": 50,
            },
        }
    }

    with open(temp_config_path, "w", encoding="utf-8") as f:
        json.dump(initial_config, f)

    mgr = FeatureFlagManager(config_path=temp_config_path)

    assert mgr.is_enabled("boolean_active") is True, "Active boolean flag must be True"
    assert mgr.is_enabled("boolean_inactive") is False, "Inactive boolean flag must be False"
    assert mgr.is_enabled("non_existent_flag", default=True) is True, "Missing flag should return default True"
    assert mgr.is_enabled("non_existent_flag", default=False) is False, "Missing flag should return default False"
    print("  [PASS] Boolean evaluation and defaults passed.")

    # --- 2. Whitelist / Targeted Users ---
    assert mgr.is_enabled("beta_users", context={"user_id": "alice"}) is True, "Whitelisted user must have access"
    assert mgr.is_enabled("beta_users", context={"user_id": "trainer_tsubaki"}) is True, "Whitelisted user must have access"
    assert mgr.is_enabled("beta_users", context={"user_id": "bob"}) is False, "Non-whitelisted user must be denied"
    assert mgr.is_enabled("beta_users", context={}) is False, "Anonymous context must be denied targeted flag"
    print("  [PASS] User whitelist targeting passed.")

    # --- 3. Deterministic Percentage Rollouts ---
    # Consistent across repeated calls for the same user
    user_eval_1 = mgr.is_enabled("gradual_rollout", context={"user_id": "runner_001"})
    user_eval_2 = mgr.is_enabled("gradual_rollout", context={"user_id": "runner_001"})
    assert user_eval_1 == user_eval_2, "Rollout evaluation must be deterministic"

    # Rollout distribution across sample users (50% rollout should balance)
    sample_size = 100
    enabled_count = sum(
        1 for i in range(sample_size)
        if mgr.is_enabled("gradual_rollout", context={"user_id": f"sample_user_{i}"})
    )
    # With 100 samples and 50%, enabled count should be reasonably balanced (35 to 65)
    assert 35 <= enabled_count <= 65, f"50% rollout was skewed: {enabled_count}/{sample_size}"
    print(f"  [PASS] Deterministic percentage rollout passed ({enabled_count}/{sample_size} enabled).")

    # --- 4. Dynamic Hot-Reload on File Change ---
    # Sleep slightly to ensure mtime changes on filesystems with 1s resolution
    time.sleep(0.05)
    initial_config["flags"]["boolean_inactive"]["enabled"] = True
    initial_config["flags"]["new_dynamic_flag"] = {"enabled": True}

    with open(temp_config_path, "w", encoding="utf-8") as f:
        json.dump(initial_config, f)

    # Force stat change check without re-instantiating FeatureFlagManager
    assert mgr.is_enabled("boolean_inactive") is True, "Hot-reload should reflect modified flag without restart"
    assert mgr.is_enabled("new_dynamic_flag") is True, "Hot-reload should recognize newly appended flag"
    print("  [PASS] Dynamic file hot-reloading passed.")

    # --- 5. Environment Variable Overrides ---
    os.environ["FLAG_BOOLEAN_ACTIVE"] = "0"
    assert mgr.is_enabled("boolean_active") is False, "Env var override to false must take precedence"

    os.environ["FLAG_MAINTENANCE_OVERRIDE"] = "true"
    assert mgr.is_enabled("maintenance_override") is True, "Env var override to true must take precedence"

    del os.environ["FLAG_BOOLEAN_ACTIVE"]
    del os.environ["FLAG_MAINTENANCE_OVERRIDE"]
    assert mgr.is_enabled("boolean_active") is True, "Clearing env var should restore config state"
    print("  [PASS] Environment variable overrides passed.")

    # --- 6. Decorator Interface ---
    @require_flag("boolean_active", fallback=lambda: "fallback_result", manager=mgr)
    def premium_feature():
        return "premium_result"

    @require_flag("missing_feature", fallback=lambda: "fallback_result", manager=mgr)
    def disabled_feature():
        return "premium_result"

    assert premium_feature() == "premium_result", "Enabled flag decorator should execute wrapped function"
    assert disabled_feature() == "fallback_result", "Disabled flag decorator should execute fallback"
    print("  [PASS] Decorator and fallback mechanism passed.")

    temp_dir.cleanup()
    print("\n[ALL CHECKS PASSED] Dynamic Feature Flag Architecture is verified and healthy.\n")


if __name__ == "__main__":
    run_checks()
