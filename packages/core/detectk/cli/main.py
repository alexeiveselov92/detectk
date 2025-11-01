"""DetectK CLI main entry point.

This module provides the main CLI interface using Click framework.
"""

import logging
import sys
from pathlib import Path
from typing import Any

import click

from detectk import __version__
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


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
