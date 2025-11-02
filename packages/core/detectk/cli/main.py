"""DetectK CLI main entry point.

This module provides the main CLI interface using Click framework.
"""

import logging
import sys
from pathlib import Path
from typing import Any

import click

from detectk import __version__
from detectk.backtest import BacktestRunner
from detectk.check import MetricCheck
from detectk.config.loader import ConfigLoader
from detectk.exceptions import ConfigurationError, DetectKError
from detectk.registry import AlerterRegistry, CollectorRegistry, DetectorRegistry

# Import packages to trigger auto-registration
try:
    import detectk_clickhouse  # noqa: F401
except ImportError:
    pass

try:
    import detectk_detectors  # noqa: F401
except ImportError:
    pass

try:
    import detectk_alerters_mattermost  # noqa: F401
except ImportError:
    pass

try:
    import detectk_alerters_slack  # noqa: F401
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version=__version__, prog_name="dtk")
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging (DEBUG level)",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress all output except errors",
)
def cli(verbose: bool, quiet: bool) -> None:
    """DetectK - Flexible anomaly detection and alerting for metrics.

    Monitor database metrics, detect anomalies using various algorithms,
    and send alerts through multiple channels.

    \b
    Examples:
        dtk run configs/sessions.yaml
        dtk validate configs/revenue.yaml
        dtk list-detectors
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif quiet:
        logging.getLogger().setLevel(logging.ERROR)


@cli.command()
@click.argument("config_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--execution-time",
    "-t",
    type=str,
    help="Override execution time (ISO format: YYYY-MM-DD HH:MM:SS)",
)
def run(config_path: Path, execution_time: str | None) -> None:
    """Run metric check from configuration file.

    CONFIG_PATH: Path to YAML configuration file

    \b
    Examples:
        # Run with current time
        dtk run configs/sessions.yaml

        # Run with specific execution time
        dtk run configs/sessions.yaml -t "2024-11-01 14:30:00"
    """
    try:
        click.echo(f"📊 Running metric check: {config_path}")

        # Parse execution time if provided
        exec_time = None
        if execution_time:
            from datetime import datetime

            exec_time = datetime.fromisoformat(execution_time)
            click.echo(f"⏰ Execution time: {exec_time}")

        # Run check
        checker = MetricCheck()
        result = checker.execute(str(config_path), execution_time=exec_time)

        # Display results
        click.echo()
        click.echo("=" * 70)
        click.echo("RESULTS")
        click.echo("=" * 70)
        click.echo(f"Metric: {result.metric_name}")
        click.echo(f"Timestamp: {result.timestamp}")
        click.echo(f"Value: {result.value:,.2f}")
        click.echo()

        if result.detections:
            click.echo("Detections:")
            for detection in result.detections:
                status = "🚨 ANOMALY" if detection.is_anomaly else "✅ NORMAL"
                click.echo(f"  [{detection.metadata.get('detector_id', 'unknown')}] {status}")
                if detection.is_anomaly:
                    if detection.score is not None:
                        click.echo(f"    Score: {detection.score:.2f} sigma")
                    if detection.direction:
                        click.echo(f"    Direction: {detection.direction}")
                    if detection.percent_deviation is not None:
                        click.echo(f"    Deviation: {detection.percent_deviation:+.1f}%")
        else:
            click.echo("No detections configured")

        click.echo()
        if result.alert_sent:
            click.echo(f"✉️  Alert sent: {result.alert_reason}")
        elif result.detections and any(d.is_anomaly for d in result.detections):
            click.echo("⏭️  Alert skipped (cooldown or other condition)")
        else:
            click.echo("📧 No alert sent (no anomaly detected)")

        if result.errors:
            click.echo()
            click.echo("⚠️  Errors:")
            for error in result.errors:
                click.echo(f"  - {error}", err=True)
            sys.exit(1)

        click.echo()
        click.echo("✅ Check completed successfully")

    except ConfigurationError as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        sys.exit(1)
    except DetectKError as e:
        click.echo(f"❌ Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error")
        click.echo(f"❌ Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("config_path", type=click.Path(exists=True, path_type=Path))
def validate(config_path: Path) -> None:
    """Validate configuration file without running check.

    CONFIG_PATH: Path to YAML configuration file

    \b
    Example:
        dtk validate configs/sessions.yaml
    """
    try:
        click.echo(f"🔍 Validating configuration: {config_path}")

        # Load and validate config
        loader = ConfigLoader()
        config = loader.load_file(str(config_path))

        click.echo()
        click.echo("=" * 70)
        click.echo("CONFIGURATION SUMMARY")
        click.echo("=" * 70)
        click.echo(f"Metric: {config.name}")
        if config.description:
            click.echo(f"Description: {config.description}")

        click.echo()
        click.echo(f"Collector: {config.collector.type}")
        click.echo(f"Storage: {config.storage.type if config.storage and config.storage.enabled else 'disabled'}")

        click.echo()
        detectors = config.get_detectors()
        click.echo(f"Detectors: {len(detectors)}")
        for detector in detectors:
            detector_id = detector.id or "auto-generated"
            click.echo(f"  - {detector.type} (ID: {detector_id})")

        if config.alerter:
            click.echo()
            click.echo(f"Alerter: {config.alerter.type}")

        click.echo()
        click.echo("✅ Configuration is valid!")

    except ConfigurationError as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error during validation")
        click.echo(f"❌ Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command("list-collectors")
def list_collectors() -> None:
    """List available data collectors.

    \b
    Example:
        dtk list-collectors
    """
    click.echo("📡 Available Collectors:")
    click.echo()

    collectors = CollectorRegistry.list_all()
    if not collectors:
        click.echo("  No collectors registered")
        return

    for name in sorted(collectors):
        collector_class = CollectorRegistry.get(name)
        docstring = collector_class.__doc__ or "No description"
        # First line of docstring
        description = docstring.strip().split("\n")[0]
        click.echo(f"  • {name:15s} - {description}")


@cli.command("list-detectors")
def list_detectors() -> None:
    """List available anomaly detectors.

    \b
    Example:
        dtk list-detectors
    """
    click.echo("🔍 Available Detectors:")
    click.echo()

    detectors = DetectorRegistry.list_all()
    if not detectors:
        click.echo("  No detectors registered")
        return

    for name in sorted(detectors):
        detector_class = DetectorRegistry.get(name)
        docstring = detector_class.__doc__ or "No description"
        # First line of docstring
        description = docstring.strip().split("\n")[0]
        click.echo(f"  • {name:15s} - {description}")


@cli.command("list-alerters")
def list_alerters() -> None:
    """List available alerters.

    \b
    Example:
        dtk list-alerters
    """
    click.echo("📢 Available Alerters:")
    click.echo()

    alerters = AlerterRegistry.list_all()
    if not alerters:
        click.echo("  No alerters registered")
        return

    for name in sorted(alerters):
        alerter_class = AlerterRegistry.get(name)
        docstring = alerter_class.__doc__ or "No description"
        # First line of docstring
        description = docstring.strip().split("\n")[0]
        click.echo(f"  • {name:15s} - {description}")


@cli.command()
@click.argument("output_path", type=click.Path(path_type=Path), default="metric_config.yaml")
@click.option(
    "--detector",
    "-d",
    type=click.Choice(["threshold", "mad", "zscore"]),
    default="threshold",
    help="Detector type to use in template",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite existing file",
)
def init(output_path: Path, detector: str, overwrite: bool) -> None:
    """Generate template configuration file.

    OUTPUT_PATH: Path where to create config file (default: metric_config.yaml)

    \b
    Examples:
        # Create template with threshold detector
        dtk init

        # Create template with MAD detector
        dtk init my_config.yaml -d mad

        # Overwrite existing file
        dtk init my_config.yaml --overwrite
    """
    # Check if file exists
    if output_path.exists() and not overwrite:
        click.echo(f"❌ File already exists: {output_path}", err=True)
        click.echo("   Use --overwrite to replace it", err=True)
        sys.exit(1)

    # Template configurations for different detectors
    templates = {
        "threshold": """# DetectK Configuration - Threshold Detector
# Simple threshold-based anomaly detection

name: "my_metric"
description: "Describe your metric here"

# Data Collection
collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST:-localhost}"
    port: 9000
    database: "your_database"
    query: |
      SELECT
        count(*) as value,
        now() as timestamp
      FROM your_table
      WHERE timestamp >= now() - INTERVAL 1 HOUR

# Anomaly Detection
detector:
  type: "threshold"
  params:
    operator: "greater_than"  # greater_than, less_than, between, outside, etc.
    threshold: 1000           # Adjust based on your metric

# Alert Delivery
alerter:
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
    cooldown_minutes: 60  # Wait 1 hour between alerts

# Historical Data Storage (optional)
storage:
  enabled: false  # Set to true to enable historical data storage
  # type: "clickhouse"
  # params:
  #   host: "${CLICKHOUSE_HOST:-localhost}"
  #   database: "detectk"
  #   datapoints_retention_days: 90
""",
        "mad": """# DetectK Configuration - MAD Detector
# Statistical anomaly detection using Median Absolute Deviation
# Robust to outliers, good for "dirty" data

name: "my_metric"
description: "Describe your metric here"

# Data Collection
collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST:-localhost}"
    port: 9000
    database: "your_database"
    query: |
      SELECT
        count(*) as value,
        now() as timestamp
      FROM your_table
      WHERE timestamp >= now() - INTERVAL 10 MINUTE

# Anomaly Detection
detector:
  type: "mad"
  params:
    window_size: "30 days"   # Historical window for comparison
    n_sigma: 3.0             # Alert if value > median + 3*MAD_sigma
    use_weighted: true       # Weight recent data more (exponential decay)
    exp_decay_factor: 0.1    # Higher = more weight to recent data

# Alert Delivery
alerter:
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
    cooldown_minutes: 60

# Historical Data Storage (required for MAD detector)
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST:-localhost}"
    database: "detectk"
    datapoints_retention_days: 90
    save_detections: false  # Save space - only store raw values
""",
        "zscore": """# DetectK Configuration - Z-Score Detector
# Statistical anomaly detection using mean and standard deviation
# Faster than MAD, less robust to outliers

name: "my_metric"
description: "Describe your metric here"

# Data Collection
collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST:-localhost}"
    port: 9000
    database: "your_database"
    query: |
      SELECT
        sum(amount) as value,
        now() as timestamp
      FROM transactions
      WHERE timestamp >= now() - INTERVAL 1 HOUR

# Anomaly Detection
detector:
  type: "zscore"
  params:
    window_size: "7 days"    # Historical window for comparison
    n_sigma: 3.0             # Alert if value > mean + 3*std
    use_weighted: true       # Weight recent data more
    exp_decay_factor: 0.1

# Alert Delivery
alerter:
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
    cooldown_minutes: 120  # Wait 2 hours for revenue alerts

# Historical Data Storage (required for Z-score detector)
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST:-localhost}"
    database: "detectk"
    datapoints_retention_days: 90
    save_detections: false
""",
    }

    # Get template content
    template_content = templates[detector]

    # Write to file
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(template_content)

        click.echo(f"✅ Created configuration file: {output_path}")
        click.echo()
        click.echo(f"Detector type: {detector}")
        click.echo()
        click.echo("Next steps:")
        click.echo("1. Edit the configuration file:")
        click.echo(f"   - Update collector query for your data")
        click.echo(f"   - Adjust detector parameters")
        click.echo(f"   - Set CLICKHOUSE_HOST and MATTERMOST_WEBHOOK environment variables")
        click.echo()
        click.echo("2. Validate configuration:")
        click.echo(f"   dtk validate {output_path}")
        click.echo()
        click.echo("3. Run metric check:")
        click.echo(f"   dtk run {output_path}")

    except Exception as e:
        click.echo(f"❌ Error creating file: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("config_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Save results to CSV file (optional)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed progress",
)
def backtest(config_path: Path, output: Path | None, verbose: bool) -> None:
    """Run backtesting on historical data.

    CONFIG_PATH: Path to metric configuration file with backtest enabled

    Backtesting simulates running the metric check at multiple points in time
    to test detector performance on historical data before production deployment.

    Configuration requirements:
    - backtest.enabled: true
    - backtest.data_load_start: "2024-01-01"  # Start loading data
    - backtest.detection_start: "2024-02-01"  # Start detecting (after window)
    - backtest.detection_end: "2024-03-01"    # End detecting
    - backtest.step_interval: "10 minutes"    # Time between checks

    \b
    Examples:
        # Run backtest
        dtk backtest examples/backtest/sessions.yaml

        # Save results to CSV
        dtk backtest examples/backtest/sessions.yaml -o results.csv

        # Verbose output
        dtk backtest examples/backtest/sessions.yaml -v
    """
    if verbose:
        logging.getLogger("detectk").setLevel(logging.DEBUG)

    try:
        click.echo(f"📊 Running backtest: {config_path}")
        click.echo()

        # Run backtest
        runner = BacktestRunner()
        result = runner.run(config_path)

        # Display summary
        click.echo()
        click.echo("✅ Backtest completed!")
        click.echo()
        click.echo(f"📈 Results for: {result.metric_name}")
        click.echo(f"   Duration: {result.duration_seconds:.2f}s")
        click.echo(f"   Total checks: {result.total_checks}")
        click.echo(f"   Anomalies detected: {result.anomalies_detected}")
        click.echo(f"   Alerts sent: {result.alerts_sent}")

        if result.total_checks > 0:
            anomaly_rate = (result.anomalies_detected / result.total_checks) * 100
            alert_rate = (result.alerts_sent / result.total_checks) * 100
            click.echo(f"   Anomaly rate: {anomaly_rate:.1f}%")
            click.echo(f"   Alert rate: {alert_rate:.1f}%")

        # Save results if requested
        if output:
            runner.save_results(result, output)
            click.echo()
            click.echo(f"💾 Results saved to: {output}")

        # Show sample of anomalies
        if result.summary is not None and not result.summary.empty:
            anomalies = result.summary[result.summary["is_anomaly"] == True]  # noqa: E712
            if len(anomalies) > 0:
                click.echo()
                click.echo("🔍 Sample anomalies (first 5):")
                click.echo()
                sample = anomalies.head(5)[
                    ["timestamp", "value", "score", "direction", "alert_sent"]
                ]
                for _, row in sample.iterrows():
                    alert_icon = "✓" if row["alert_sent"] else " "
                    click.echo(
                        f"  [{alert_icon}] {row['timestamp']}: "
                        f"value={row['value']:.2f}, "
                        f"score={row['score']:.2f}, "
                        f"direction={row['direction']}"
                    )

                if len(anomalies) > 5:
                    click.echo(f"  ... and {len(anomalies) - 5} more anomalies")

    except ConfigurationError as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        if verbose and e.__cause__:
            click.echo(f"   Cause: {e.__cause__}", err=True)
        sys.exit(1)
    except DetectKError as e:
        click.echo(f"❌ Error: {e}", err=True)
        if verbose and e.__cause__:
            click.echo(f"   Cause: {e.__cause__}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {e}", err=True)
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
