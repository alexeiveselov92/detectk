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
from detectk.cli.init_project import (
    copy_examples,
    create_project_structure,
    init_git_repo,
)
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


@cli.command("list-metrics")
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    default=".",
    help="Directory to search for metric configs (default: current directory)",
)
@click.option(
    "--details",
    is_flag=True,
    help="Show detailed information about each metric",
)
@click.option(
    "--validate",
    is_flag=True,
    help="Validate each metric configuration",
)
@click.option(
    "--collector",
    "-c",
    help="Filter by collector type (e.g., clickhouse, sql, http)",
)
def list_metrics(path: Path, details: bool, validate: bool, collector: str | None) -> None:
    """List all metric configurations in the project.

    Scans directories for .yaml files and displays configured metrics.

    \b
    Examples:
        # List all metrics in current directory
        dtk list-metrics

        # List metrics in specific directory
        dtk list-metrics --path configs/

        # Show detailed information
        dtk list-metrics --details

        # Validate all metrics
        dtk list-metrics --validate

        # Filter by collector type
        dtk list-metrics --collector clickhouse
    """
    click.echo("📊 DetectK Metrics:")
    click.echo()

    # Strict structure: all metrics must be in "metrics/" directory
    # (like dbt's "models/" directory)
    metrics_dir = path / "metrics"

    if not metrics_dir.exists():
        click.echo("  ❌ No 'metrics/' directory found")
        click.echo(f"  Expected location: {metrics_dir}")
        click.echo()
        click.echo("  💡 Initialize a DetectK project with:")
        click.echo("     dtk init-project")
        return

    # Find all .yaml files recursively in metrics/ directory
    yaml_files = []
    yaml_files.extend(metrics_dir.glob("**/*.yaml"))
    yaml_files.extend(metrics_dir.glob("**/*.yml"))

    if not yaml_files:
        click.echo("  No metric configuration files found in metrics/")
        click.echo(f"  Directory: {metrics_dir}")
        click.echo()
        click.echo("  💡 Create a metric config:")
        click.echo("     dtk init metrics/my_metric.yaml")
        return

    # Load and display metrics
    config_loader = ConfigLoader()
    metrics_found = 0
    metrics_valid = 0
    metrics_filtered = 0

    for yaml_file in sorted(yaml_files):
        # Skip template files
        if yaml_file.name.endswith(".template"):
            continue

        try:
            # Try to load config (lenient mode - allow missing env vars)
            config = config_loader.load_file(str(yaml_file), lenient=True)

            # Filter by collector if specified
            if collector and config.collector.type != collector:
                metrics_filtered += 1
                continue

            metrics_found += 1

            # Display metric
            # Show path relative to metrics/ directory (not project root)
            rel_path = yaml_file.relative_to(metrics_dir)

            if details:
                click.echo("─" * 70)
                click.echo(f"📌 {config.name}")
                click.echo(f"   File: metrics/{rel_path}")
                if config.description:
                    click.echo(f"   Description: {config.description}")
                click.echo(f"   Collector: {config.collector.type}")

                # Detectors
                detectors = config.get_detectors()
                detector_info = ", ".join(
                    f"{d.type}(id={d.id[:8] if d.id else 'auto'})" for d in detectors
                )
                click.echo(f"   Detectors: {detector_info}")

                # Alerter
                alerter_info = config.alerter.type if config.alerter else "none"
                click.echo(f"   Alerter: {alerter_info}")

                # Storage
                storage_info = (
                    f"{config.storage.type} (enabled)"
                    if config.storage and config.storage.enabled
                    else "disabled"
                )
                click.echo(f"   Storage: {storage_info}")

                if validate:
                    click.echo("   Status: ✅ Valid")
                    metrics_valid += 1

                click.echo()
            else:
                # Simple format
                collector_info = f"[{config.collector.type}]"
                file_path = f"metrics/{rel_path}"
                status = "✅" if validate else ""

                if validate:
                    metrics_valid += 1

                click.echo(f"  {status} {config.name:30s} {collector_info:15s} {file_path}")

        except ConfigurationError as e:
            # Configuration error - show in output
            rel_path = yaml_file.relative_to(metrics_dir)

            if details:
                click.echo("─" * 70)
                click.echo(f"📌 {yaml_file.name}")
                click.echo(f"   File: metrics/{rel_path}")
                click.echo(f"   Status: ❌ Invalid - {e}")
                click.echo()
            else:
                file_path = f"metrics/{rel_path}"
                click.echo(f"  ❌ {yaml_file.stem:30s} {'[error]':15s} {file_path}")

            metrics_found += 1
            continue

        except Exception as e:
            # Unexpected error - skip this file
            logger.debug(f"Skipping {yaml_file}: {e}")
            continue

    # Summary
    click.echo()
    click.echo("─" * 70)
    click.echo(f"Total: {metrics_found} metrics found")

    if collector:
        click.echo(f"Filtered: {metrics_filtered} metrics excluded (collector != {collector})")

    if validate:
        click.echo(f"Valid: {metrics_valid}/{metrics_found}")


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


@cli.command("init-project")
@click.argument("directory", type=click.Path(path_type=Path), default=".")
@click.option(
    "--database",
    "-d",
    type=click.Choice(["clickhouse", "postgres", "mysql", "sqlite"]),
    default="clickhouse",
    help="Primary database type",
)
@click.option(
    "--minimal",
    is_flag=True,
    help="Create minimal structure (no examples)",
)
@click.option(
    "--no-git",
    is_flag=True,
    help="Skip git repository initialization",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Interactive mode (ask questions)",
)
def init_project(
    directory: Path,
    database: str,
    minimal: bool,
    no_git: bool,
    interactive: bool,
) -> None:
    """Initialize a new DetectK project with complete structure.

    Creates a ready-to-use project directory with:
    - Connection profile templates
    - Environment variable templates
    - .gitignore for credentials
    - README with setup instructions
    - Example metric configuration
    - Optional: Reference examples from library

    DIRECTORY: Project directory (default: current directory)

    \b
    Examples:
        # Initialize in current directory
        dtk init-project

        # Create new project directory
        dtk init-project my-metrics-monitoring

        # Interactive mode
        dtk init-project --interactive

        # Minimal (no examples)
        dtk init-project my-project --minimal

        # PostgreSQL instead of ClickHouse
        dtk init-project my-project -d postgres
    """
    # Interactive mode
    if interactive:
        click.echo()
        click.echo("╔════════════════════════════════════════════════════════╗")
        click.echo("║         DetectK Project Initialization                 ║")
        click.echo("╚════════════════════════════════════════════════════════╝")
        click.echo()

        # Ask project name if directory is current
        if directory == Path("."):
            project_name = click.prompt(
                "Project name",
                default="my-detectk-project",
                type=str,
            )
            directory = Path(project_name)

        # Ask database type
        database = click.prompt(
            "Primary database",
            type=click.Choice(["clickhouse", "postgres", "mysql", "sqlite"]),
            default=database,
        )

        # Ask about examples
        include_examples = click.confirm(
            "Include example configurations?",
            default=True,
        )
        minimal = not include_examples

        # Ask about git
        init_git = click.confirm("Initialize git repository?", default=True)
        no_git = not init_git

        click.echo()

    # Resolve directory
    project_dir = directory.resolve()

    # Check if directory exists and is not empty
    if project_dir.exists() and any(project_dir.iterdir()):
        if not click.confirm(
            f"Directory '{project_dir}' is not empty. Continue?",
            default=False,
        ):
            click.echo("Aborted.")
            sys.exit(0)

    try:
        # Create project structure
        click.echo(f"Creating project structure in: {project_dir}")
        click.echo()

        created_files = create_project_structure(
            project_dir,
            include_examples=not minimal,
            minimal=minimal,
        )

        # Report created files
        click.echo("✓ Created project structure:")
        click.echo(f"  • detectk_profiles.yaml.template")
        click.echo(f"  • .env.template")
        click.echo(f"  • .gitignore")
        click.echo(f"  • README.md")
        click.echo(f"  • metrics/example_metric.yaml")

        # Copy examples if requested
        if not minimal:
            # Try to find examples in package
            try:
                import detectk

                package_root = Path(detectk.__file__).parent.parent.parent.parent
                examples_source = package_root / "examples"

                if examples_source.exists():
                    copied = copy_examples(project_dir, examples_source)
                    if copied > 0:
                        click.echo(f"✓ Copied {copied} example configuration(s)")
                else:
                    click.echo("⚠ Example configurations not found (install from source)")
            except Exception as e:
                click.echo(f"⚠ Could not copy examples: {e}")

        # Initialize git repository
        if not no_git:
            if init_git_repo(project_dir):
                click.echo("✓ Initialized git repository")
            else:
                click.echo("⚠ Could not initialize git repository (git not found?)")

        # Display next steps
        click.echo()
        click.echo("=" * 70)
        click.echo("NEXT STEPS")
        click.echo("=" * 70)
        click.echo()

        # Navigation step if directory was created
        if project_dir != Path(".").resolve():
            click.echo(f"1. cd {project_dir.name}")
            click.echo()

        click.echo("2. Set up credentials:")
        click.echo("   cp detectk_profiles.yaml.template detectk_profiles.yaml")
        click.echo("   cp .env.template .env")
        click.echo()

        click.echo("3. Edit with your credentials:")
        click.echo("   vim detectk_profiles.yaml")
        click.echo("   vim .env")
        click.echo()

        click.echo("4. Load environment variables:")
        click.echo("   source .env")
        click.echo()

        click.echo("5. Validate configuration:")
        click.echo("   dtk validate metrics/example_metric.yaml")
        click.echo()

        click.echo("6. Run your first check:")
        click.echo("   dtk run metrics/example_metric.yaml")
        click.echo()

        click.echo("📚 Documentation: https://github.com/alexeiveselov92/detectk")
        click.echo()

    except Exception as e:
        click.echo(f"❌ Error creating project: {e}", err=True)
        logger.exception("Project initialization failed")
        sys.exit(1)


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
