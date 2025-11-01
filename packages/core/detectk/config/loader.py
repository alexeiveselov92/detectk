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
    ) -> MetricConfig:
        """Load metric configuration from YAML file.

        Args:
            config_path: Path to YAML configuration file
            template_context: Optional context for Jinja2 template rendering
                            (e.g., {"execution_time": datetime.now()})

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
            config_dict = self._parse_yaml(raw_content, template_context or {})
        except Exception as e:
            raise ConfigurationError(
                f"Failed to parse YAML: {e}",
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
    ) -> dict[str, Any]:
        """Parse YAML with environment variable substitution and templating.

        Processing order:
        1. Environment variable substitution (${VAR_NAME})
        2. Jinja2 template rendering ({{ execution_time }})
        3. YAML parsing

        Args:
            yaml_content: Raw YAML content as string
            template_context: Context for Jinja2 rendering

        Returns:
            Parsed configuration dictionary

        Raises:
            ConfigurationError: If parsing or substitution fails
        """
        # Step 1: Environment variable substitution
        content_with_env = self._substitute_env_vars(yaml_content)

        # Step 2: Jinja2 template rendering (if context provided)
        if template_context:
            try:
                template = self.jinja_env.from_string(content_with_env)
                content_rendered = template.render(**template_context)
            except TemplateError as e:
                raise ConfigurationError(f"Jinja2 template rendering failed: {e}")
        else:
            content_rendered = content_with_env

        # Step 3: Parse YAML
        try:
            config_dict = yaml.safe_load(content_rendered)
        except yaml.YAMLError as e:
            raise ConfigurationError(f"YAML parsing failed: {e}")

        if not isinstance(config_dict, dict):
            raise ConfigurationError("Configuration must be a YAML mapping (dict)")

        return config_dict

    def _substitute_env_vars(self, content: str) -> str:
        """Substitute environment variables in format ${VAR_NAME}.

        Supports:
        - ${VAR_NAME} - required variable (raises error if not set)
        - ${VAR_NAME:-default_value} - optional with default value

        Args:
            content: String content with ${VAR_NAME} placeholders

        Returns:
            Content with substituted values

        Raises:
            ConfigurationError: If required variable is not set

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
    ) -> dict[str, Any] | list[Any] | Any:
        """Recursively process Jinja2 templates in dictionary values.

        Args:
            data: Data structure to process (dict, list, or primitive)
            template_context: Context for template rendering

        Returns:
            Processed data structure with rendered templates
        """
        if isinstance(data, dict):
            return {
                key: self._process_dict_templates(value, template_context)
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return [
                self._process_dict_templates(item, template_context)
                for item in data
            ]
        elif isinstance(data, str):
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
