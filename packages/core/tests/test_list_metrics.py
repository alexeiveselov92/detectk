"""Tests for dtk list-metrics command."""

import tempfile
from pathlib import Path

from click.testing import CliRunner

from detectk.cli.main import cli


class TestListMetricsCommand:
    """Test suite for list-metrics CLI command."""

    def test_list_metrics_no_metrics_directory(self):
        """Test listing metrics when no metrics/ directory exists."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(cli, ["list-metrics", "--path", tmpdir])

            assert result.exit_code == 0
            assert "No 'metrics/' directory found" in result.output
            assert "dtk init-project" in result.output

    def test_list_metrics_empty_metrics_directory(self):
        """Test listing metrics in empty metrics/ directory."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create empty metrics/ directory
            (Path(tmpdir) / "metrics").mkdir()

            result = runner.invoke(cli, ["list-metrics", "--path", tmpdir])

            assert result.exit_code == 0
            assert "No metric configuration files found in metrics/" in result.output

    def test_list_metrics_single_metric(self):
        """Test listing a single metric."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create metrics/ directory
            metrics_dir = Path(tmpdir) / "metrics"
            metrics_dir.mkdir()

            # Create a simple metric config
            config_content = """name: "test_metric"
description: "Test metric for CLI"

collector:
  type: "clickhouse"
  params:
    query: "SELECT 42 as value"
    host: "${CLICKHOUSE_HOST:-localhost}"

detector:
  type: "threshold"
  params:
    threshold: 100
    operator: "greater_than"

alerter:
  type: "mattermost"
  params:
    webhook_url: "${WEBHOOK_URL:-http://localhost}"

storage:
  enabled: false
"""
            config_path = metrics_dir / "test_metric.yaml"
            config_path.write_text(config_content)

            result = runner.invoke(cli, ["list-metrics", "--path", tmpdir])

            assert result.exit_code == 0
            assert "test_metric" in result.output
            assert "[clickhouse]" in result.output
            assert "metrics/test_metric.yaml" in result.output
            assert "Total: 1 metrics found" in result.output

    def test_list_metrics_with_details(self):
        """Test listing metrics with detailed output."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_dir = Path(tmpdir) / "metrics"
            metrics_dir.mkdir()

            config_content = """name: "detailed_metric"
description: "Metric with details"

collector:
  type: "sql"
  params:
    connection_string: "sqlite:///test.db"
    query: "SELECT COUNT(*) as value FROM test"

detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0

alerter:
  type: "slack"
  params:
    webhook_url: "https://hooks.slack.com/test"

storage:
  enabled: true
  type: "sql"
  params:
    connection_string: "postgresql://localhost/metrics"
"""
            config_path = metrics_dir / "detailed.yaml"
            config_path.write_text(config_content)

            result = runner.invoke(cli, ["list-metrics", "--path", tmpdir, "--details"])

            assert result.exit_code == 0
            assert "detailed_metric" in result.output
            assert "Metric with details" in result.output
            assert "Collector: sql" in result.output
            assert "Detectors: mad" in result.output
            assert "Alerter: slack" in result.output
            assert "Storage: sql (enabled)" in result.output

    def test_list_metrics_with_validate(self):
        """Test listing metrics with validation."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_dir = Path(tmpdir) / "metrics"
            metrics_dir.mkdir()

            # Create valid metric
            valid_config = """name: "valid_metric"
collector:
  type: "clickhouse"
  params:
    query: "SELECT 1 as value"
    host: "localhost"
detector:
  type: "threshold"
  params:
    threshold: 10
alerter:
  type: "mattermost"
  params:
    webhook_url: "http://test"
"""
            (metrics_dir / "valid.yaml").write_text(valid_config)

            # Create invalid metric (missing required fields)
            invalid_config = """name: "invalid_metric"
collector:
  type: "clickhouse"
# Missing detector and alerter
"""
            (metrics_dir / "invalid.yaml").write_text(invalid_config)

            result = runner.invoke(cli, ["list-metrics", "--path", tmpdir, "--validate"])

            assert result.exit_code == 0
            assert "✅" in result.output  # Valid metric
            assert "❌" in result.output  # Invalid metric
            assert "Total: 2 metrics found" in result.output
            assert "Valid: 1/2" in result.output

    def test_list_metrics_filter_by_collector(self):
        """Test filtering metrics by collector type."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_dir = Path(tmpdir) / "metrics"
            metrics_dir.mkdir()

            # Create ClickHouse metric
            clickhouse_config = """name: "ch_metric"
collector:
  type: "clickhouse"
  params:
    query: "SELECT 1"
detector:
  type: "threshold"
  params:
    threshold: 10
alerter:
  type: "mattermost"
  params:
    webhook_url: "http://test"
"""
            (metrics_dir / "ch_metric.yaml").write_text(clickhouse_config)

            # Create SQL metric
            sql_config = """name: "sql_metric"
collector:
  type: "sql"
  params:
    connection_string: "sqlite:///test.db"
    query: "SELECT 1"
detector:
  type: "threshold"
  params:
    threshold: 10
alerter:
  type: "mattermost"
  params:
    webhook_url: "http://test"
"""
            (metrics_dir / "sql_metric.yaml").write_text(sql_config)

            # Filter by clickhouse
            result = runner.invoke(
                cli, ["list-metrics", "--path", tmpdir, "--collector", "clickhouse"]
            )

            assert result.exit_code == 0
            assert "ch_metric" in result.output
            assert "sql_metric" not in result.output
            assert "Total: 1 metrics found" in result.output
            assert "Filtered: 1 metrics excluded" in result.output

    def test_list_metrics_multiple_detectors(self):
        """Test listing metric with multiple detectors."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_dir = Path(tmpdir) / "metrics"
            metrics_dir.mkdir()

            config_content = """name: "multi_detector"
collector:
  type: "clickhouse"
  params:
    query: "SELECT 1"
detectors:
  - type: "mad"
    params:
      window_size: "30 days"
      n_sigma: 3.0
  - type: "zscore"
    params:
      window_size: "7 days"
      n_sigma: 2.5
alerter:
  type: "mattermost"
  params:
    webhook_url: "http://test"
"""
            (metrics_dir / "multi.yaml").write_text(config_content)

            result = runner.invoke(cli, ["list-metrics", "--path", tmpdir, "--details"])

            assert result.exit_code == 0
            assert "multi_detector" in result.output
            assert "mad" in result.output
            assert "zscore" in result.output

    def test_list_metrics_lenient_mode_with_missing_env_vars(self):
        """Test that list-metrics works even with missing environment variables."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_dir = Path(tmpdir) / "metrics"
            metrics_dir.mkdir()

            # Config with required environment variable
            config_content = """name: "env_var_metric"
collector:
  type: "clickhouse"
  params:
    query: "SELECT 1"
    host: "${REQUIRED_HOST}"  # No default - would fail in strict mode
detector:
  type: "threshold"
  params:
    threshold: 10
alerter:
  type: "mattermost"
  params:
    webhook_url: "${REQUIRED_WEBHOOK}"  # No default
"""
            (metrics_dir / "env_metric.yaml").write_text(config_content)

            # Should work in lenient mode (list-metrics uses lenient=True)
            result = runner.invoke(cli, ["list-metrics", "--path", tmpdir])

            assert result.exit_code == 0
            assert "env_var_metric" in result.output
            # Should successfully load despite missing REQUIRED_HOST and REQUIRED_WEBHOOK

    def test_list_metrics_skips_template_files(self):
        """Test that .template files are skipped."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_dir = Path(tmpdir) / "metrics"
            metrics_dir.mkdir()

            # Create regular metric
            regular_config = """name: "regular"
collector:
  type: "clickhouse"
  params:
    query: "SELECT 1"
detector:
  type: "threshold"
  params:
    threshold: 10
alerter:
  type: "mattermost"
  params:
    webhook_url: "http://test"
"""
            (metrics_dir / "regular.yaml").write_text(regular_config)

            # Create template file (should be skipped)
            template_config = """name: "template"
collector:
  type: "clickhouse"
  params:
    query: "SELECT 1"
"""
            (metrics_dir / "template.yaml.template").write_text(template_config)

            result = runner.invoke(cli, ["list-metrics", "--path", tmpdir])

            assert result.exit_code == 0
            assert "regular" in result.output
            assert "template" not in result.output
            assert "Total: 1 metrics found" in result.output

    def test_list_metrics_recursive_search(self):
        """Test that metrics are found recursively in subdirectories."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create nested structure within metrics/
            metrics_dir = tmpdir / "metrics"
            metrics_dir.mkdir()
            production_dir = metrics_dir / "production"
            production_dir.mkdir()

            config = """name: "nested_metric"
collector:
  type: "clickhouse"
  params:
    query: "SELECT 1"
detector:
  type: "threshold"
  params:
    threshold: 10
alerter:
  type: "mattermost"
  params:
    webhook_url: "http://test"
"""
            (production_dir / "nested.yaml").write_text(config)

            result = runner.invoke(cli, ["list-metrics", "--path", str(tmpdir)])

            assert result.exit_code == 0
            assert "nested_metric" in result.output
            assert "metrics/production/nested.yaml" in result.output
