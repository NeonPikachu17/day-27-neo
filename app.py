"""Dynamic Feature Flag Demonstration Application.

Showcases runtime feature evaluation, user targeting, deterministic percentage
rollouts, hot-reload, and environment variable overrides without server restart.
"""

import json
import os
import time
from pathlib import Path
from feature_flags import default_manager, is_enabled, require_flag


@require_flag(
    "exclusive_replay_lounge",
    fallback=lambda *args, **kwargs: "[ACCESS DENIED] Replay lounge is restricted to authorized personnel.",
)
def access_replay_lounge(user_id: str, flag_context: dict = None):
    return f"[ACCESS GRANTED] Welcome to the VIP Replay Lounge, {user_id}!"


def print_separator(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def run_demo():
    print_separator("DYNAMIC FEATURE FLAG ENGINE - RELEASE v1.0")
    print(f"Config File: {default_manager.config_path.resolve()}")

    # 1. Inspect all raw flag configurations
    print_separator("1. CURRENT FEATURE FLAGS IN CONFIG")
    for flag_name in ["gait_biomechanics_v2", "live_turf_weather_sim", "exclusive_replay_lounge", "maintenance_lock"]:
        meta = default_manager.get_flag_metadata(flag_name) or {}
        print(f" - {flag_name:25} | Enabled: {str(meta.get('enabled')):5} | {meta.get('description', '')}")

    # 2. Evaluation across different contexts
    print_separator("2. CONTEXT-AWARE FLAG EVALUATION")
    test_users = ["trainer_tsubaki", "guest_runner_42", "sakura_laurel", "anonymous"]

    for user in test_users:
        ctx = {"user_id": user}
        gait_v2 = is_enabled("gait_biomechanics_v2", context=ctx)
        weather_sim = is_enabled("live_turf_weather_sim", context=ctx)
        vip_lounge = is_enabled("exclusive_replay_lounge", context=ctx)

        print(f"User: {user:18} | Gait V2: {'ON' if gait_v2 else 'OFF'} | Turf Sim (50%): {'ON' if weather_sim else 'OFF'} | VIP Lounge: {'ON' if vip_lounge else 'OFF'}")

    # 3. Decorator Usage
    print_separator("3. DECORATOR-GATED FUNCTION CALLS")
    for user in ["trainer_tsubaki", "guest_runner_42"]:
        result = access_replay_lounge(user, flag_context={"user_id": user})
        print(f"Calling access_replay_lounge({user!r}):\n   --> {result}")

    # 4. Live Hot-Reload Demonstration
    print_separator("4. DYNAMIC HOT-RELOAD DEMONSTRATION")
    config_file = Path("config.json")
    with open(config_file, "r", encoding="utf-8") as f:
        original_content = f.read()
        config_data = json.loads(original_content)

    try:
        print("[Demo] Current 'maintenance_lock' state:", is_enabled("maintenance_lock"))
        print("[Demo] Modifying config.json on disk to set 'maintenance_lock' -> True...")
        time.sleep(0.1)

        config_data["flags"]["maintenance_lock"]["enabled"] = True
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        # Immediate evaluation without restarting or re-instantiating!
        updated_state = is_enabled("maintenance_lock")
        print(f"[Demo] Evaluated 'maintenance_lock' immediately after disk write: {updated_state}")
        print("[Demo] Hot-reload successfully picked up on-disk change!")

    finally:
        # Restore original config
        print("[Demo] Restoring original config.json content...")
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(original_content)
        time.sleep(0.05)
        print("[Demo] Restored 'maintenance_lock' state:", is_enabled("maintenance_lock"))

    # 5. Environment Variable Override Demonstration
    print_separator("5. ENVIRONMENT VARIABLE KILL-SWITCH / OVERRIDE")
    print("[Demo] Setting environment variable FLAG_MAINTENANCE_LOCK=1...")
    os.environ["FLAG_MAINTENANCE_LOCK"] = "1"
    print(f"[Demo] Evaluated 'maintenance_lock' with ENV override: {is_enabled('maintenance_lock')}")

    print("[Demo] Clearing environment variable...")
    del os.environ["FLAG_MAINTENANCE_LOCK"]
    print(f"[Demo] Evaluated 'maintenance_lock' after clearing ENV: {is_enabled('maintenance_lock')}")

    print_separator("DEMONSTRATION COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    run_demo()
