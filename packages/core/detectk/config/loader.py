"""Configuration loader with YAML parsing and template support.

This module provides functionality for loading metric configurations from
YAML files with environment variable substitution and Jinja2 templating.
"""

import os
import re
from pathlib import Path
from typing import Any
from datetime import datetime

import yaml
from jinja2 import Environment, Template, TemplateError, StrictUndefined

from detectk.config.models import MetricConfig
from detectk.config.profiles import get_profile_loader, merge_profile_params
from detectk.exceptions import ConfigurationError


class ConfigLoader:
    """Loads and parses metric configuration files.

    Supports:
    - YAML parsing
    - Environment variable substitution (${VAR_NAME})
    - Jinja2 template rendering for queries
    - Validation with Pydantic models

    Example:
        >>> loader = ConfigLoader()
        >>> config = loader.load_file("configs/sessions_10min.yaml")
        >>> print(config.name)
        "sessions_10min"

        >>> # Load with execution time context for templates
        >>> config = loader.load_file(
        ...     "configs/sessions.yaml",
        ...     template_context={"execution_time": datetime.now()}
        ... )
    """

    def __init__(self) -> None:
        """Initialize configuration loader."""
        # Create Jinja2 environment with strict undefined variables
        self.jinja_env = Environment(undefined=StrictUndefined)

        # Add custom filters for time formatting
        self.jinja_env.filters["datetime_format"] = self._datetime_format_filter

    @staticmethod
    def _datetime_format_filter(value: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Jinja2 filter for formatting datetime objects.

        Args:
            value: Datetime object to format
            fmt: Format string (strftime format)

        Returns:
            Formatted datetime string
        """
        return value.strftime(fmt)

    def load_file(
        self,
        config_path: str | Path,
        template_context: dict[str, Any] | None = None,
        lenient: bool = False,
    ) -> MetricConfig:
        """Load metric configuration from YAML file.

        Args:
            config_path: Path to YAML configuration file
            template_context: Optional context for Jinja2 template rendering
                            (e.g., {"execution_time": datetime.now()})
            lenient: If True, allows missing environment variables by using
                    placeholder values. Useful for listing/validating configs
                    without setting all environment variables. Default: False.

        Returns:
            Validated MetricConfig object

        Raises:
            ConfigurationError: If file not found, parsing fails, or validation fails

        Example:
            ```python
            loader = ConfigLoader()

            # Simple load
            config = loader.load_file("configs/sessions.yaml")

            # With template context for backtesting
            config = loader.load_file(
                "configs/sessions.yaml",
                template_context={
                    "execution_time": datetime(2024, 1, 15, 10, 0, 0)
                }
            )

            # Lenient mode for listing metrics without env vars
            config = loader.load_file("configs/sessions.yaml", lenient=True)
            ```
        """
        config_path = Path(config_path)

        # Check file exists
        if not config_path.exists():
            raise ConfigurationError(
                f"Configuration file not found: {config_path}",
                config_path=str(config_path),
            )

        # Read raw YAML content
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw_content = f.read()
        except Exception as e:
            raise ConfigurationError(
                f"Failed to read configuration file: {e}",
                config_path=str(config_path),
            )

        # Parse with environment variable substitution and templating
        try:
            config_dict = self._parse_yaml(raw_content, template_context or {}, lenient=lenient)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to parse YAML: {e}",
                config_path=str(config_path),
            )

        # Process profiles (if collector uses profile reference)
        try:
            config_dict = self._process_profiles(config_dict)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to process profiles: {e}",
                config_path=str(config_path),
            )

        # Validate with Pydantic
        try:
            return MetricConfig(**config_dict)
        except Exception as e:
            raise ConfigurationError(
                f"Configuration validation failed: {e}",
                config_path=str(config_path),
            )

    def load_dict(
        self,
        config_dict: dict[str, Any],
        template_context: dict[str, Any] | None = None,
    ) -> MetricConfig:
        """Load metric configuration from dictionary.

        Useful for programmatic configuration or testing.

        Args:
            config_dict: Configuration as dictionary
            template_context: Optional context for template rendering

        Returns:
            Validated MetricConfig object

        Raises:
            ConfigurationError: If validation fails
        """
        # Process templates in dictionary values
        if template_context:
            config_dict = self._process_dict_templates(config_dict, template_context)

        # Validate with Pydantic
        try:
            return MetricConfig(**config_dict)
        except Exception as e:
            raise ConfigurationError(f"Configuration validation failed: {e}")

    def _parse_yaml(
        self,
        yaml_content: str,
        template_context: dict[str, Any],
        lenient: bool = False,
    ) -> dict[str, Any]:
        """Parse YAML with environment variable substitution and templating.

        IMPORTANT: collector.params.query is NOT rendered here!
        It will be rendered by collector on each collect_bulk() call.

        Processing order:
        1. Environment variable substitution (${VAR_NAME})
        2. YAML parsing (NO rendering - preserves {{ period_start }} in queries)
        3. Selective Jinja2 rendering via _process_dict_templates()

        Args:
            yaml_content: Raw YAML content as string
            template_context: Context for Jinja2 rendering
            lenient: If True, use placeholders for missing env vars

        Returns:
            Parsed configuration dictionary

        Raises:
            ConfigurationError: If parsing or substitution fails
        """
        # Step 1: Environment variable substitution (only ${VAR_NAME}, not {{ }})
        content_with_env = self._substitute_env_vars(yaml_content, lenient=lenient)

        # Step 2: Parse YAML WITHOUT rendering Jinja2 templates
        # This preserves {{ period_start }}, {{ period_finish }} in queries
        try:
            config_dict = yaml.safe_load(content_with_env)
        except yaml.YAMLError as e:
            raise ConfigurationError(f"YAML parsing failed: {e}")

        if not isinstance(config_dict, dict):
            raise ConfigurationError("Configuration must be a YAML mapping (dict)")

        # Step 3: Selectively render Jinja2 templates (skips collector.params.query)
        if template_context:
            config_dict = self._process_dict_templates(config_dict, template_context)

        return config_dict

    def _substitute_env_vars(self, content: str, lenient: bool = False) -> str:
        """Substitute environment variables in format ${VAR_NAME}.

        Supports:
        - ${VAR_NAME} - required variable (raises error if not set)
        - ${VAR_NAME:-default_value} - optional with default value

        Args:
            content: String content with ${VAR_NAME} placeholders
            lenient: If True, use placeholder for missing vars instead of raising error

        Returns:
            Content with substituted values

        Raises:
            ConfigurationError: If required variable is not set (unless lenient=True)

        Example:
            Input: "host: ${CLICKHOUSE_HOST:-localhost}"
            Output: "host: localhost" (if CLICKHOUSE_HOST not set)
        """

        def replace_var(match: re.Match) -> str:
            """Replace single environment variable."""
            full_match = match.group(1)  # e.g., "CLICKHOUSE_HOST:-localhost"

            # Check for default value syntax
            if ":-" in full_match:
                var_name, default_value = full_match.split(":-", 1)
                var_name = var_name.strip()
                default_value = default_value.strip()
            else:
                var_name = full_match.strip()
                default_value = None

            # Get environment variable
            value = os.environ.get(var_name)

            if value is None:
                if default_value is not None:
                    return default_value
                elif lenient:
                    # Lenient mode: use placeholder value
                    return f"<{var_name}>"
                else:
                    raise ConfigurationError(
                        f"Required environment variable not set: {var_name}",
                        field=f"${{{var_name}}}",
                    )

            return value

        # Pattern: ${VAR_NAME} or ${VAR_NAME:-default}
        pattern = r"\$\{([^}]+)\}"

        try:
            return re.sub(pattern, replace_var, content)
        except ConfigurationError:
            raise
        except Exception as e:
            raise ConfigurationError(f"Environment variable substitution failed: {e}")

    def _process_dict_templates(
        self,
        data: dict[str, Any] | list[Any] | Any,
        template_context: dict[str, Any],
        path: str = "",
    ) -> dict[str, Any] | list[Any] | Any:
        """Recursively process Jinja2 templates in dictionary values.

        IMPORTANT: Skips rendering collector.params.query field!
        This is critical - collector queries must be rendered by the collector
        itself on each collect_bulk() call with dynamic period_start/period_finish.

        Args:
            data: Data structure to process (dict, list, or primitive)
            template_context: Context for template rendering
            path: Current path in dict (for detecting collector.params.query)

        Returns:
            Processed data structure with rendered templates
        """
        if isinstance(data, dict):
            return {
                key: self._process_dict_templates(
                    value,
                    template_context,
                    path=f"{path}.{key}" if path else key
                )
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return [
                self._process_dict_templates(item, template_context, path=f"{path}[{i}]")
                for i, item in enumerate(data)
            ]
        elif isinstance(data, str):
            # Skip rendering collector.params.query - collector will render it
            if path == "collector.params.query":
                return data  # Leave {{ period_start }}, {{ period_finish }} intact

            # Render string as Jinja2 template if it contains template syntax
            if "{{" in data or "{%" in data:
                try:
                    template = self.jinja_env.from_string(data)
                    return template.render(**template_context)
                except TemplateError as e:
                    raise ConfigurationError(f"Template rendering failed: {e}")
            return data
        else:
            return data

    def _process_profiles(self, config_dict: dict[str, Any]) -> dict[str, Any]:
        """Process profile references in collector configuration.

        If collector.profile is specified, merges profile params with explicit params.

        Priority (highest to lowest):
        1. Explicit params in config
        2. Profile params
        3. Environment variable defaults (handled by collector)

        Args:
            config_dict: Parsed configuration dictionary

        Returns:
            Configuration dict with profile params merged into collector.params

        Raises:
            ConfigurationError: If profile not found
        """
        if "collector" not in config_dict:
            return config_dict

        collector_config = config_dict["collector"]

        # Check if profile is specified
        profile_name = collector_config.get("profile")
        if not profile_name:
            return config_dict  # No profile, nothing to process

        # Load profile
        profile_loader = get_profile_loader()
        profile_params = profile_loader.get_profile(profile_name)

        # Extract type from profile if not specified in config
        if "type" not in collector_config or not collector_config["type"]:
            if "type" not in profile_params:
                raise ConfigurationError(
                    f"Profile '{profile_name}' must specify 'type' field",
                    config_path="collector.profile",
                )
            collector_config["type"] = profile_params["type"]

        # Get explicit params from config
        explicit_params = collector_config.get("params", {})

        # Merge: profile params + explicit params (explicit wins)
        # Remove 'type' from profile_params before merging (it's not a connection param)
        profile_connection_params = {k: v for k, v in profile_params.items() if k != "type"}

        merged_params = merge_profile_params(
            profile_params=profile_connection_params,
            explicit_params=explicit_params,
        )

        # Update collector config with merged params
        collector_config["params"] = merged_params

        return config_dict
