"""Dynamic Feature Flag Architecture.

Provides runtime feature flag evaluation with zero external dependencies:
- Dynamic hot-reloading on config file modifications (via mtime tracking)
- Deterministic percentage-based rollouts (SHA-256 hashing)
- User whitelist / targeting
- Environment variable overrides (e.g., FLAG_MAINTENANCE_LOCK=1)
- Clean functional and decorator interfaces
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class FeatureFlagManager:
    """Manages loading, hot-reloading, and evaluating dynamic feature flags."""

    def __init__(self, config_path: str | Path = "config.json"):
        self.config_path = Path(config_path)
        self._flags: Dict[str, Dict[str, Any]] = {}
        self._last_mtime: float = 0.0
        self.reload(force=True)

    def reload(self, force: bool = False) -> bool:
        """Reload flags from config_path if file has changed or if forced.

        Returns True if a reload occurred, False otherwise.
        """
        if not self.config_path.exists():
            if force:
                self._flags = {}
                self._last_mtime = 0.0
            return False

        try:
            current_mtime = self.config_path.stat().st_mtime
            if force or current_mtime > self._last_mtime:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._flags = data.get("flags", {})
                self._last_mtime = current_mtime
                return True
        except (json.JSONDecodeError, OSError) as err:
            # Maintain last known good state if file is being written concurrently
            print(f"[FeatureFlagManager] Warning: failed to reload config: {err}")
        return False

    def _get_env_override(self, flag_name: str) -> Optional[bool]:
        """Check environment variables for flag override (e.g. FLAG_MY_FEATURE=true)."""
        env_key = f"FLAG_{flag_name.upper()}"
        val = os.getenv(env_key)
        if val is None:
            return None
        val_lower = val.strip().lower()
        if val_lower in ("1", "true", "yes", "on", "enabled"):
            return True
        if val_lower in ("0", "false", "no", "off", "disabled"):
            return False
        return None

    def _evaluate_percentage(self, flag_name: str, entity_id: str, percentage: int) -> bool:
        """Deterministically calculate whether an entity falls within a rollout bucket."""
        if percentage <= 0:
            return False
        if percentage >= 100:
            return True

        # Hash flag_name + entity_id to ensure independent distributions across flags
        seed = f"{flag_name}:{entity_id}".encode("utf-8")
        digest = hashlib.sha256(seed).hexdigest()
        bucket = int(digest[:8], 16) % 100
        return bucket < percentage

    def is_enabled(
        self,
        flag_name: str,
        context: Optional[Dict[str, Any]] = None,
        default: bool = False,
    ) -> bool:
        """Dynamically evaluate whether a feature flag is enabled.

        Evaluation precedence:
        1. Environment variable override (FLAG_<FLAG_NAME>=true|false)
        2. Config presence and top-level 'enabled' boolean (must be true)
        3. User targeting / whitelist (if 'allowed_users' is configured)
        4. Percentage rollout (if 'rollout_percentage' is configured)
        """
        # Step 1: Hot-reload if config file changed on disk
        self.reload(force=False)

        # Step 2: Environment variable override takes highest precedence
        env_override = self._get_env_override(flag_name)
        if env_override is not None:
            return env_override

        # Step 3: Flag lookup
        flag_data = self._flags.get(flag_name)
        if flag_data is None:
            return default

        # Base master switch check
        if not flag_data.get("enabled", False):
            return False

        ctx = context or {}
        user_id = ctx.get("user_id") or ctx.get("user")

        # Step 4: Whitelist / Targeted users check
        allowed_users: Optional[List[str]] = flag_data.get("allowed_users")
        if allowed_users is not None:
            if user_id is not None and user_id in allowed_users:
                return True
            # If allowed_users is specified without a rollout percentage, must match whitelist
            if "rollout_percentage" not in flag_data:
                return False

        # Step 5: Percentage rollout check
        rollout_percentage = flag_data.get("rollout_percentage")
        if rollout_percentage is not None:
            target_id = user_id or ctx.get("entity_id") or ctx.get("device_id")
            if target_id is None:
                # If no entity identifier provided, fail closed for percentage rollouts
                return False
            return self._evaluate_percentage(flag_name, str(target_id), int(rollout_percentage))

        return True

    def get_flag_metadata(self, flag_name: str) -> Optional[Dict[str, Any]]:
        """Return the raw metadata dictionary for a given flag."""
        self.reload(force=False)
        return self._flags.get(flag_name)

    def get_all_flags(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
        """Return evaluation state of all configured flags."""
        self.reload(force=False)
        return {name: self.is_enabled(name, context=context) for name in self._flags}


# Global default instance configured with root config.json
default_manager = FeatureFlagManager()


def is_enabled(
    flag_name: str,
    context: Optional[Dict[str, Any]] = None,
    default: bool = False,
) -> bool:
    """Convenience helper to evaluate against the default FeatureFlagManager."""
    return default_manager.is_enabled(flag_name, context=context, default=default)


def require_flag(
    flag_name: str,
    fallback: Optional[Callable[..., Any]] = None,
    manager: Optional[FeatureFlagManager] = None,
):
    """Decorator to conditionally execute a function if a feature flag is enabled.

    If disabled and fallback is provided, fallback(*args, **kwargs) is executed.
    Otherwise, returns None when disabled.
    """
    mgr = manager or default_manager

    def decorator(func: Callable[..., Any]):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract context if explicitly passed in kwargs, else empty
            context = kwargs.get("flag_context")
            if mgr.is_enabled(flag_name, context=context):
                return func(*args, **kwargs)
            if fallback:
                return fallback(*args, **kwargs)
            return None

        return wrapper

    return decorator
