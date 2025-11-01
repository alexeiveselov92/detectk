# DetectK

> A flexible, production-ready Python library for monitoring metrics from databases, detecting anomalies using various algorithms, and sending alerts through multiple channels.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

**DetectK** (Detection Kit) is designed for data analysts and engineers who need to monitor database metrics and receive alerts when anomalies are detected. It provides a configuration-driven approach where you work with YAML configs instead of writing Python code.

### Key Features

- **Configuration-Driven**: Define metrics, detectors, and alerts in YAML files
- **Modular Architecture**: Install only the components you need
- **Orchestrator-Agnostic**: Works standalone or with Prefect, Airflow, or any workflow engine
- **Flexible Time Intervals**: No hardcoded assumptions - works with any interval from seconds to months
- **Multiple Databases**: ClickHouse, PostgreSQL, MySQL, SQLite, and more
- **Advanced Detection**: Threshold, statistical (MAD, Z-score, IQR), seasonal patterns, and ML-based detectors
- **Multiple Alert Channels**: Mattermost, Slack, Telegram, Email
- **Backtesting**: Test metrics on historical data before deploying to production
- **Production-Ready**: Proper error handling, structured logging, retries, and observability

---

## Quick Start

### Installation

```bash
# Core library with basic detectors
pip install detectk detectk-detectors

# Add ClickHouse collector
pip install detectk-collectors-clickhouse

# Add Mattermost alerter
pip install detectk-alerters-mattermost
```

### Create a Metric Configuration

Create `configs/sessions_10min.yaml`:

```yaml
name: "sessions_10min"
description: "Monitor user sessions every 10 minutes"

# Data collection
collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST}"
    database: "analytics"
    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL 10 MINUTE) as timestamp,
        count(DISTINCT user_id) as value
      FROM sessions
      WHERE timestamp >= now() - INTERVAL 10 MINUTE
        AND timestamp < now()

# Anomaly detection
detector:
  type: "mad"  # Median Absolute Deviation (robust)
  params:
    window_size: "30 days"
    n_sigma: 3.0
    seasonal_features:
      - name: "hour_of_day"
        expression: "toHour(timestamp)"
      - name: "day_of_week"
        expression: "toDayOfWeek(timestamp)"

# Alert delivery
alerter:
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
    channel: "#ops-alerts"
  conditions:
    consecutive_anomalies: 3
    direction: "both"
    cooldown_minutes: 60
```

### Run Metric Check

```bash
# Run once
dtk run configs/sessions_10min.yaml

# Run all metrics in directory
dtk run configs/

# Run with backtesting
dtk backtest configs/sessions_10min.yaml \
  --start 2024-01-01 \
  --end 2024-02-01 \
  --step "10 minutes"
```

---

## Architecture

DetectK uses a three-stage pipeline:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Collector   │────▶│  Detector    │────▶│ AlertAnalyzer +  │
│              │     │              │     │ Alerter          │
│ Query source │     │ Find         │     │ Decide & send    │
│ database     │     │ anomalies    │     │ alerts           │
└──────────────┘     └──────────────┘     └──────────────────┘
       │                     │                      │
       ▼                     ▼                      ▼
  ┌─────────────────────────────────────────────────────┐
  │              Optional Storage                       │
  │  - metrics_history (for historical windows)         │
  │  - detection_results (for dashboards/analysis)      │
  └─────────────────────────────────────────────────────┘
```

**Stage 1: Collection**
- Query source database for current value (1 row - lightweight)
- Optionally save to `metrics_history` table

**Stage 2: Detection**
- Read historical window from storage (e.g., 30 days)
- Apply detection algorithm with seasonal features
- Return anomaly status and bounds

**Stage 3: Alert Decision**
- Check alert conditions (consecutive anomalies, direction, cooldown)
- Send alert if conditions met

---

## Available Components

### Collectors (Data Sources)

| Package | Databases | Status |
|---------|-----------|--------|
| `detectk-collectors-clickhouse` | ClickHouse | 🚧 In Development |
| `detectk-collectors-sql` | PostgreSQL, MySQL, SQLite | 📋 Planned |
| `detectk-collectors-http` | REST APIs | 📋 Planned |

### Detectors (Anomaly Detection)

| Package | Algorithms | Status |
|---------|------------|--------|
| `detectk-detectors` | Threshold, Z-score, MAD, IQR | 🚧 In Development |
| `detectk-detectors-timeseries` | Prophet, SARIMA, Exponential Smoothing | 📋 Planned |
| `detectk-detectors-ml` | Isolation Forest, Autoencoder, LSTM | 📋 Planned |

### Alerters (Notification Channels)

| Package | Channels | Status |
|---------|----------|--------|
| `detectk-alerters-mattermost` | Mattermost | 🚧 In Development |
| `detectk-alerters-slack` | Slack | 📋 Planned |
| `detectk-alerters-telegram` | Telegram | 📋 Planned |
| `detectk-alerters-email` | Email (SMTP) | 📋 Planned |

### Orchestrators

| Package | Integration | Status |
|---------|-------------|--------|
| `detectk-standalone` | APScheduler (built-in) | 📋 Planned |
| `detectk-prefect` | Prefect 2.x | 📋 Planned |
| `detectk-airflow` | Apache Airflow | 📋 Planned |

---

## Use Cases

### Simple Threshold Monitoring

Monitor if metric falls below/above a threshold:

```yaml
detector:
  type: "threshold"
  params:
    operator: "less_than"
    threshold: 1000
```

### Statistical Anomaly Detection

Detect anomalies using robust statistics (MAD):

```yaml
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    use_weighted: true
    weights_type: "exponential"
```

### Seasonal Pattern Detection

Account for time-of-day and day-of-week patterns:

```yaml
detector:
  type: "mad"
  params:
    seasonal_features:
      - name: "hour_of_day"
        expression: "toHour(timestamp)"
      - name: "day_of_week"
        expression: "toDayOfWeek(timestamp)"
    use_combined_seasonality: true
```

### Backtesting

Test detector on historical data:

```yaml
backtest:
  enabled: true
  data_load_start: "2024-01-01"
  detection_start: "2024-02-01"  # After 30-day window
  step_interval: "10 minutes"
```

---

## Project Status

**Current Status:** 🚧 Active Development - Phase 1

We are currently implementing the core foundation:
- Base classes and interfaces
- Registry pattern for component discovery
- Configuration parsing and validation
- ClickHouse collector and storage
- MAD detector
- Mattermost alerter

**Next Steps:**
- Complete Phase 1 (core foundation)
- Add more detectors (Z-score, IQR)
- Add more collectors (PostgreSQL, MySQL)
- CLI tools
- Documentation and examples

See [TODO.md](TODO.md) for detailed roadmap (internal).

---

## Documentation

- **Quick Start** (this README)
- **Architecture Guide** - Design decisions and extension points (internal)
- **Configuration Reference** - Complete YAML schema documentation (coming soon)
- **API Documentation** - Auto-generated from docstrings (coming soon)
- **Examples** - Working examples for common use cases (coming soon)

---

## Contributing

This project is currently in active development. Contributions are welcome once we reach MVP status.

---

## License

MIT License - See [LICENSE](LICENSE) for details.

---

## Credits

Developed with lessons learned from production monitoring systems and inspired by:
- **dbt** - Configuration-first approach
- **Prefect/Airflow** - Orchestrator patterns
- **scikit-learn** - Clean API design
- **Facebook Prophet** - Time series analysis

---

## Contact

- **Repository**: https://github.com/alexeiveselov92/detectk
- **Issues**: https://github.com/alexeiveselov92/detectk/issues

---

**Built with by data engineers, for data analysts.**
