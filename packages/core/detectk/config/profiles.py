"""Connection profiles management for DetectK.

Profiles provide a centralized way to manage database connections and
avoid duplicating credentials across metric configurations.

Architecture:
- Profile files: detectk_profiles.yaml (local) or ~/.detectk/profiles.yaml (global)
- Priority: local > global > env vars > collector defaults
- Security: profiles.yaml in .gitignore, use env vars for secrets
"""

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from detectk.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class ProfileLoader:
    """Loads and manages connection profiles.

    Profiles are loaded from:
    1. ./detectk_profiles.yaml (local - highest priority)
    2. ~/.detectk/profiles.yaml (global)

    Example profiles.yaml:
        profiles:
          clickhouse_analytics:
            type: "clickhouse"
            host: "${CLICKHOUSE_HOST:-localhost}"
            port: 9000
            database: "analytics"
            user: "${CLICKHOUSE_USER:-default}"
            password: "${CLICKHOUSE_PASSWORD}"

          postgres_production:
            type: "postgres"
            connection_string: "${POSTGRES_DSN}"

    Usage in metric config:
        collector:
          profile: "clickhouse_analytics"  # Reference to profile
          params:
            query: "SELECT count() FROM sessions"

    Security:
    - Add detectk_profiles.yaml to .gitignore
    - Use env vars for secrets (${CLICKHOUSE_PASSWORD})
    - Provide detectk_profiles.yaml.template in repository
    """

    def __init__(self) -> None:
        """Initialize profile loader."""
        self._profiles: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def load(self) -> None:
        """Load profiles from all available locations.

        Loads from (in priority order):
        1. ./detectk_profiles.yaml (local)
        2. ~/.detectk/profiles.yaml (global)

        Later files don't override earlier ones - only add missing profiles.
        """
        if self._loaded:
            return  # Already loaded

        # 1. Try local profiles file (highest priority)
        local_path = Path.cwd() / "detectk_profiles.yaml"
        if local_path.exists():
            logger.debug(f"Loading local profiles: {local_path}")
            self._load_file(local_path)

        # 2. Try global profiles file (~/.detectk/profiles.yaml)
        global_path = Path.home() / ".detectk" / "profiles.yaml"
        if global_path.exists():
            logger.debug(f"Loading global profiles: {global_path}")
            self._load_file(global_path)

        self._loaded = True

        if self._profiles:
            logger.info(f"Loaded {len(self._profiles)} profile(s): {', '.join(self._profiles.keys())}")
        else:
            logger.debug("No profiles loaded")

    def _load_file(self, file_path: Path) -> None:
        """Load profiles from a YAML file.

        Args:
            file_path: Path to profiles YAML file

        Raises:
            ConfigurationError: If file is invalid
        """
        try:
            with open(file_path, "r") as f:
                content = yaml.safe_load(f)

            if not content or "profiles" not in content:
                logger.warning(f"No 'profiles' key found in {file_path}")
                return

            profiles = content["profiles"]
            if not isinstance(profiles, dict):
                raise ConfigurationError(
                    f"Invalid profiles file {file_path}: 'profiles' must be a dict",
                    config_path=str(file_path),
                )

            # Add profiles (don't override existing ones from higher priority files)
            for name, config in profiles.items():
                if name not in self._profiles:
                    self._profiles[name] = config
                    logger.debug(f"Loaded profile: {name}")
                else:
                    logger.debug(f"Skipping profile {name} (already loaded from higher priority source)")

        except yaml.YAMLError as e:
            raise ConfigurationError(
                f"Invalid YAML in profiles file {file_path}: {e}",
                config_path=str(file_path),
            ) from e
        except Exception as e:
            raise ConfigurationError(
                f"Error loading profiles file {file_path}: {e}",
                config_path=str(file_path),
            ) from e

    def get_profile(self, name: str) -> dict[str, Any]:
        """Get profile by name.

        Args:
            name: Profile name

        Returns:
            Profile configuration dict

        Raises:
            ConfigurationError: If profile not found
        """
        if not self._loaded:
            self.load()

        if name not in self._profiles:
            available = ", ".join(self._profiles.keys()) if self._profiles else "none"
            raise ConfigurationError(
                f"Profile '{name}' not found. Available profiles: {available}",
                config_path=f"collector.profile",
            )

        return self._profiles[name].copy()

    def has_profile(self, name: str) -> bool:
        """Check if profile exists.

        Args:
            name: Profile name

        Returns:
            True if profile exists
        """
        if not self._loaded:
            self.load()

        return name in self._profiles

    def list_profiles(self) -> list[str]:
        """List all available profile names.

        Returns:
            List of profile names
        """
        if not self._loaded:
            self.load()

        return list(self._profiles.keys())


def merge_profile_params(
    profile_params: dict[str, Any],
    explicit_params: dict[str, Any],
    env_defaults: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Merge parameters from profile, explicit config, and env defaults.

    Priority (highest to lowest):
    1. Explicit params from config
    2. Profile params
    3. Environment variable defaults
    4. Collector defaults (handled by collector itself)

    Args:
        profile_params: Parameters from profile
        explicit_params: Parameters explicitly set in config
        env_defaults: Optional mapping of param names to env var names

    Returns:
        Merged parameters dict

    Example:
        profile_params = {"host": "localhost", "port": 9000}
        explicit_params = {"port": 9001, "query": "SELECT ..."}
        env_defaults = {"host": "CLICKHOUSE_HOST"}

        Result (if CLICKHOUSE_HOST not set):
        {"host": "localhost", "port": 9001, "query": "SELECT ..."}

        Result (if CLICKHOUSE_HOST="prod-host"):
        {"host": "localhost", "port": 9001, "query": "SELECT ..."}
        # Note: explicit/profile have higher priority than env
    """
    # Start with env defaults (if provided)
    merged = {}
    if env_defaults:
        for param_name, env_var in env_defaults.items():
            env_value = os.environ.get(env_var)
            if env_value:
                merged[param_name] = env_value

    # Apply profile params (override env defaults)
    merged.update(profile_params)

    # Apply explicit params (highest priority - override everything)
    merged.update(explicit_params)

    return merged


# Global profile loader instance (singleton pattern)
_profile_loader: ProfileLoader | None = None


def get_profile_loader() -> ProfileLoader:
    """Get global ProfileLoader instance (singleton).

    Returns:
        ProfileLoader instance
    """
    global _profile_loader
    if _profile_loader is None:
        _profile_loader = ProfileLoader()
    return _profile_loader
