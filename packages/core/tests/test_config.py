"""Tests for configuration loading and parsing."""

import os
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from detectk.config import (
    MetricConfig,
    CollectorConfig,
    DetectorConfig,
    AlerterConfig,
    StorageConfig,
    ScheduleConfig,
    ConfigLoader,
)
from detectk.exceptions import ConfigurationError


# ============================================================================
# Configuration Model Tests
# ============================================================================


def test_collector_config_valid() -> None:
    """Test valid collector configuration."""
    config = CollectorConfig(
        type="clickhouse",
        params={
            "host": "localhost",
            "database": "analytics",
            "query": "SELECT count() as value FROM events",
        },
    )

    assert config.type == "clickhouse"
    assert config.params["host"] == "localhost"


def test_collector_config_empty_type() -> None:
    """Test collector config with empty type raises error."""
    with pytest.raises(ValueError) as exc_info:
        CollectorConfig(type="", params={})

    assert "cannot be empty" in str(exc_info.value).lower()


def test_detector_config_valid() -> None:
    """Test valid detector configuration."""
    config = DetectorConfig(
        type="mad",
        params={
            "window_size": "30 days",
            "n_sigma": 3.0,
        },
    )

    assert config.type == "mad"
    assert config.params["window_size"] == "30 days"


def test_alerter_config_valid() -> None:
    """Test valid alerter configuration."""
    config = AlerterConfig(
        type="mattermost",
        params={"webhook_url": "https://example.com/hooks/xxx"},
        conditions={
            "consecutive_anomalies": 3,
            "direction": "both",
        },
    )

    assert config.type == "mattermost"
    assert config.conditions["consecutive_anomalies"] == 3


def test_storage_config_defaults() -> None:
    """Test storage configuration defaults."""
    config = StorageConfig()

    assert config.enabled is True
    assert config.type is None
    assert config.retention_days == 90


def test_storage_config_custom() -> None:
    """Test storage configuration with custom values."""
    config = StorageConfig(
        enabled=True,
        type="clickhouse",
        params={"connection_string": "clickhouse://localhost"},
        retention_days=30,
    )

    assert config.enabled is True
    assert config.type == "clickhouse"
    assert config.retention_days == 30


def test_schedule_config_continuous() -> None:
    """Test schedule configuration for continuous monitoring."""
    config = ScheduleConfig(interval="10 minutes")

    assert config.interval == "10 minutes"
    assert config.start_time is None
    assert config.end_time is None


def test_schedule_config_historical() -> None:
    """Test schedule configuration for historical data loading."""
    config = ScheduleConfig(
        start_time="2024-01-01",
        end_time="2024-03-01",
        interval="10 minutes",
        batch_load_days=30,
    )

    assert config.start_time == "2024-01-01"
    assert config.end_time == "2024-03-01"
    assert config.batch_load_days == 30


def test_metric_config_minimal() -> None:
    """Test minimal valid metric configuration."""
    config = MetricConfig(
        name="test_metric",
        collector=CollectorConfig(type="clickhouse", params={}),
        detector=DetectorConfig(type="mad", params={}),
        alerter=AlerterConfig(type="mattermost", params={}),
    )

    assert config.name == "test_metric"
    assert config.description is None
    assert config.storage.enabled is True  # Default


def test_metric_config_full() -> None:
    """Test complete metric configuration."""
    config = MetricConfig(
        name="sessions_10min",
        description="Monitor user sessions",
        collector=CollectorConfig(
            type="clickhouse",
            params={"host": "localhost", "query": "SELECT count() as value"},
        ),
        detector=DetectorConfig(
            type="mad",
            params={"window_size": "30 days", "n_sigma": 3.0},
        ),
        alerter=AlerterConfig(
            type="mattermost",
            params={"webhook_url": "https://example.com"},
            conditions={"consecutive_anomalies": 3},
        ),
        storage=StorageConfig(
            enabled=True,
            type="clickhouse",
            retention_days=90,
        ),
        metadata={"team": "analytics", "priority": "high"},
    )

    assert config.name == "sessions_10min"
    assert config.description == "Monitor user sessions"
    assert config.metadata["team"] == "analytics"


def test_metric_config_invalid_name() -> None:
    """Test metric config with invalid name raises error."""
    with pytest.raises(ValueError) as exc_info:
        MetricConfig(
            name="invalid name with spaces",
            collector=CollectorConfig(type="clickhouse", params={}),
            detector=DetectorConfig(type="mad", params={}),
            alerter=AlerterConfig(type="mattermost", params={}),
        )

    assert "invalid characters" in str(exc_info.value).lower()


def test_metric_config_with_schedule() -> None:
    """Test metric config with schedule configuration."""
    config = MetricConfig(
        name="test",
        collector=CollectorConfig(type="clickhouse", params={}),
        detector=DetectorConfig(type="mad", params={}),
        alerter=AlerterConfig(type="mattermost", params={}),
        schedule=ScheduleConfig(interval="10 minutes"),
    )

    assert config.schedule is not None
    assert config.schedule.interval == "10 minutes"


# ============================================================================
# ConfigLoader Tests
# ============================================================================


def test_config_loader_initialization() -> None:
    """Test ConfigLoader initializes successfully."""
    loader = ConfigLoader()

    assert loader.jinja_env is not None
    assert "datetime_format" in loader.jinja_env.filters


def test_config_loader_env_var_substitution() -> None:
    """Test environment variable substitution."""
    loader = ConfigLoader()

    # Set test environment variable
    os.environ["TEST_HOST"] = "test.example.com"
    os.environ["TEST_PORT"] = "9000"

    yaml_content = """
    name: "test_metric"
    collector:
      type: "clickhouse"
      params:
        host: "${TEST_HOST}"
        port: ${TEST_PORT}
    detector:
      type: "mad"
      params:
        window_size: "30 days"
    alerter:
      type: "mattermost"
      params:
        webhook_url: "https://example.com"
    """

    config_dict = loader._parse_yaml(yaml_content, {})

    assert config_dict["collector"]["params"]["host"] == "test.example.com"
    assert config_dict["collector"]["params"]["port"] == 9000

    # Cleanup
    del os.environ["TEST_HOST"]
    del os.environ["TEST_PORT"]


def test_config_loader_env_var_with_default() -> None:
    """Test environment variable substitution with default value."""
    loader = ConfigLoader()

    # Ensure variable is NOT set
    if "NONEXISTENT_VAR" in os.environ:
        del os.environ["NONEXISTENT_VAR"]

    yaml_content = """
    name: "test"
    collector:
      type: "clickhouse"
      params:
        host: "${NONEXISTENT_VAR:-localhost}"
    detector:
      type: "mad"
      params: {}
    alerter:
      type: "mattermost"
      params: {}
    """

    config_dict = loader._parse_yaml(yaml_content, {})

    assert config_dict["collector"]["params"]["host"] == "localhost"


def test_config_loader_env_var_missing_required() -> None:
    """Test missing required environment variable raises error."""
    loader = ConfigLoader()

    # Ensure variable is NOT set
    if "REQUIRED_VAR" in os.environ:
        del os.environ["REQUIRED_VAR"]

    yaml_content = """
    name: "test"
    collector:
      type: "clickhouse"
      params:
        host: "${REQUIRED_VAR}"
    """

    with pytest.raises(ConfigurationError) as exc_info:
        loader._parse_yaml(yaml_content, {})

    assert "REQUIRED_VAR" in str(exc_info.value)
    assert "not set" in str(exc_info.value).lower()


def test_config_loader_jinja2_template() -> None:
    """Test that queries are NOT rendered (preserved for collector)."""
    loader = ConfigLoader()

    yaml_content = """
    name: "test_metric"
    collector:
      type: "clickhouse"
      params:
        query: |
          SELECT count() as value
          FROM events
          WHERE timestamp >= '{{ execution_time }}'
    detector:
      type: "mad"
      params: {}
    alerter:
      type: "mattermost"
      params: {}
    """

    execution_time = datetime(2024, 1, 15, 10, 0, 0)
    template_context = {"execution_time": execution_time}

    config_dict = loader._parse_yaml(yaml_content, template_context)

    query = config_dict["collector"]["params"]["query"]
    # CRITICAL: Query must NOT be rendered - preserved for collector
    assert "{{ execution_time }}" in query
    assert "2024-01-15 10:00:00" not in query


def test_config_loader_jinja2_datetime_filter() -> None:
    """Test that queries with filters are also NOT rendered."""
    loader = ConfigLoader()

    yaml_content = """
    name: "test"
    collector:
      type: "clickhouse"
      params:
        query: "WHERE date = '{{ execution_time | datetime_format('%Y-%m-%d') }}'"
    detector:
      type: "mad"
      params: {}
    alerter:
      type: "mattermost"
      params: {}
    """

    execution_time = datetime(2024, 1, 15, 10, 30, 45)
    config_dict = loader._parse_yaml(yaml_content, {"execution_time": execution_time})

    query = config_dict["collector"]["params"]["query"]
    # Query must NOT be rendered - preserved for collector
    assert "{{ execution_time" in query
    assert "2024-01-15" not in query


def test_config_loader_load_dict() -> None:
    """Test loading configuration from dictionary."""
    loader = ConfigLoader()

    config_dict = {
        "name": "test_metric",
        "description": "Test description",
        "collector": {
            "type": "clickhouse",
            "params": {"host": "localhost"},
        },
        "detector": {
            "type": "mad",
            "params": {"window_size": "30 days"},
        },
        "alerter": {
            "type": "mattermost",
            "params": {"webhook_url": "https://example.com"},
        },
    }

    config = loader.load_dict(config_dict)

    assert isinstance(config, MetricConfig)
    assert config.name == "test_metric"
    assert config.collector.type == "clickhouse"


def test_config_loader_load_dict_with_templates() -> None:
    """Test loading dictionary with template rendering."""
    loader = ConfigLoader()

    config_dict = {
        "name": "test",
        "collector": {
            "type": "clickhouse",
            "params": {
                "query": "WHERE timestamp >= '{{ execution_time }}'",
            },
        },
        "detector": {"type": "mad", "params": {}},
        "alerter": {"type": "mattermost", "params": {}},
    }

    execution_time = datetime(2024, 1, 15, 10, 0, 0)
    config = loader.load_dict(config_dict, template_context={"execution_time": execution_time})

    query = config.collector.params["query"]
    # Query must NOT be rendered - preserved for collector
    assert "{{ execution_time }}" in query
    assert "2024-01-15" not in query


def test_config_loader_load_file() -> None:
    """Test loading configuration from YAML file."""
    loader = ConfigLoader()

    # Create temporary YAML file
    yaml_content = """
name: "sessions_10min"
description: "Monitor user sessions"

collector:
  type: "clickhouse"
  params:
    host: "localhost"
    database: "analytics"
    query: "SELECT count() as value FROM sessions"

detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0

alerter:
  type: "mattermost"
  params:
    webhook_url: "https://mattermost.example.com/hooks/xxx"
  conditions:
    consecutive_anomalies: 3
    direction: "both"
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        config = loader.load_file(temp_path)

        assert isinstance(config, MetricConfig)
        assert config.name == "sessions_10min"
        assert config.collector.type == "clickhouse"
        assert config.detector.params["window_size"] == "30 days"
        assert config.alerter.conditions["consecutive_anomalies"] == 3
    finally:
        os.unlink(temp_path)


def test_config_loader_file_not_found() -> None:
    """Test loading non-existent file raises error."""
    loader = ConfigLoader()

    with pytest.raises(ConfigurationError) as exc_info:
        loader.load_file("/nonexistent/path/config.yaml")

    assert "not found" in str(exc_info.value).lower()


def test_config_loader_invalid_yaml() -> None:
    """Test loading invalid YAML raises error."""
    loader = ConfigLoader()

    invalid_yaml = """
    name: "test"
    collector:
      type: "clickhouse"
      params:
        host: localhost
        invalid: yaml: content: here
    """

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(invalid_yaml)
        temp_path = f.name

    try:
        with pytest.raises(ConfigurationError) as exc_info:
            loader.load_file(temp_path)

        assert "parsing failed" in str(exc_info.value).lower()
    finally:
        os.unlink(temp_path)


def test_config_loader_validation_error() -> None:
    """Test configuration validation error."""
    loader = ConfigLoader()

    # Missing required fields
    yaml_content = """
name: "test"
collector:
  type: "clickhouse"
  params: {}
# Missing detector and alerter
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        with pytest.raises(ConfigurationError) as exc_info:
            loader.load_file(temp_path)

        assert "validation failed" in str(exc_info.value).lower()
    finally:
        os.unlink(temp_path)
