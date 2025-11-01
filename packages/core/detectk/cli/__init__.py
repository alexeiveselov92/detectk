"""DetectK CLI - Command line interface for metric monitoring.

The `dtk` command provides a simple interface for running metric checks,
validating configurations, and exploring available components.

Commands:
    dtk run <config>         - Run metric check from configuration file
    dtk validate <config>    - Validate configuration without running
    dtk list-collectors      - Show available data collectors
    dtk list-detectors       - Show available anomaly detectors
    dtk list-alerters        - Show available alerters
    dtk init                 - Generate template configuration (future)
    dtk backtest <config>    - Run backtesting (future)

Examples:
    # Run a single metric check
    dtk run configs/sessions.yaml

    # Validate configuration
    dtk validate configs/sessions.yaml

    # List available components
    dtk list-detectors
"""

__version__ = "0.1.0"

from detectk.cli.main import cli

__all__ = ["cli"]
