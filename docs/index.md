# DetectK Documentation

**DetectK** - A flexible, production-ready Python library for monitoring metrics from databases, detecting anomalies using various algorithms, and sending alerts through multiple channels.

## Quick Links

- [Quick Start Guide](quickstart.md)
- [Configuration Reference](guides/configuration.md)
- [Detectors Guide](guides/detectors.md)
- [Collectors Guide](guides/collectors.md)
- [Alerters Guide](guides/alerters.md)
- [API Reference](reference/core.md)
- [Architecture](architecture.md)

## What is DetectK?

DetectK is designed for data analysts and engineers who need to:

- ✅ Monitor database metrics in real-time
- ✅ Detect anomalies using various algorithms
- ✅ Send alerts when anomalies are detected
- ✅ Backtest detection strategies on historical data
- ✅ A/B test different detection parameters

## Key Features

### Configuration-Driven

Analysts work with YAML configs, not Python code:

```yaml
name: "sessions_10min"

collector:
  type: "clickhouse"
  params:
    query: "SELECT count() as value FROM sessions"

detector:
  type: "threshold"
  params:
    threshold: 1000
    operator: "greater_than"

alerter:
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
```

### Multiple Detectors

Compare different detection strategies on the same metric:

```yaml
detectors:
  - type: "threshold"
    params: {threshold: 1000}

  - type: "mad"
    params: {window_size: "30 days", n_sigma: 3.0}

  - type: "zscore"
    params: {window_size: "7 days"}
```

### Modular Architecture

Install only what you need:

```bash
# Core + ClickHouse + Threshold detector
pip install detectk detectk-clickhouse detectk-detectors

# Add ML-based detectors
pip install detectk-detectors-ml

# Add Slack alerter
pip install detectk-alerters-slack
```

### Orchestrator-Agnostic

Works standalone or with workflow engines:

- Standalone (APScheduler)
- Prefect
- Airflow
- Any scheduler (cron, etc.)

## Installation

```bash
# Basic installation
pip install detectk detectk-clickhouse detectk-detectors

# With ML detectors
pip install detectk-detectors-ml

# All components
pip install detectk[all]
```

## Quick Example

```bash
# Run single check
dtk run configs/sessions.yaml

# Backtest on historical data
dtk backtest configs/sessions.yaml \
  --start "2024-01-01" \
  --end "2024-02-01"

# Validate configuration
dtk validate configs/sessions.yaml
```

## Architecture Overview

```
┌─────────────┐
│  Collector  │ → Query database for current value
└──────┬──────┘
       ↓
┌─────────────┐
│   Storage   │ → Save to dtk_datapoints table
└──────┬──────┘
       ↓
┌─────────────┐
│  Detector   │ → Analyze historical window, detect anomalies
└──────┬──────┘
       ↓
┌─────────────┐
│   Alerter   │ → Send alert if conditions met
└─────────────┘
```

## Guides

- **[Quick Start](quickstart.md)** - Get started in 5 minutes
- **[Configuration](guides/configuration.md)** - Complete configuration reference
- **[Collectors](guides/collectors.md)** - Data source connectors
- **[Detectors](guides/detectors.md)** - Anomaly detection algorithms
- **[Alerters](guides/alerters.md)** - Notification channels
- **[Backtesting](guides/backtesting.md)** - Test on historical data

## API Reference

- **[Core API](reference/core.md)** - Base classes and models
- **[Collectors API](reference/collectors.md)** - Collector implementations
- **[Detectors API](reference/detectors.md)** - Detector implementations
- **[Alerters API](reference/alerters.md)** - Alerter implementations

## Examples

See [examples/](../examples/) directory for ready-to-use configurations.

## Community

- **GitHub:** https://github.com/alexeiveselov92/detectk
- **Issues:** https://github.com/alexeiveselov92/detectk/issues
- **Discussions:** https://github.com/alexeiveselov92/detectk/discussions

## License

MIT
