# DetectK

> A flexible, production-ready Python library for monitoring metrics from databases, detecting anomalies using various algorithms, and sending alerts through multiple channels.

[![PyPI version](https://badge.fury.io/py/detectk.svg)](https://pypi.org/project/detectk/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-257%20passing-brightgreen.svg)](https://github.com/alexeiveselov92/detectk)

---

## Overview

**DetectK** (Detection Kit) is designed for data analysts and engineers who need to monitor database metrics and receive alerts when anomalies are detected. It provides a configuration-driven approach where you work with YAML configs instead of writing Python code.

### Key Features

- **Configuration-Driven**: Define metrics, detectors, and alerts in YAML files
- **Time Series First**: Analyst writes ONE query with variables - system handles everything
- **Modular Architecture**: Install only the components you need
- **Orchestrator-Agnostic**: Works standalone or with Prefect, Airflow, or any workflow engine
- **Flexible Time Intervals**: No hardcoded assumptions - works with any interval from seconds to months
- **Multiple Databases**: ClickHouse, PostgreSQL, MySQL, SQLite, and more
- **Advanced Detection**: Threshold, statistical (MAD, Z-score), seasonal patterns, and ML-based detectors
- **Multiple Alert Channels**: Mattermost, Slack, Telegram, Email
- **Bulk Loading**: Efficiently load historical data for detector training
- **Checkpoint System**: Resume interrupted loads automatically
- **Production-Ready**: Proper error handling, structured logging, and observability

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

# Data collection - returns TIME SERIES (multiple rows)
collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST}"
    database: "analytics"
    # IMPORTANT: Query returns multiple rows with timestamps!
    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
        count(DISTINCT user_id) AS value,
        toHour(period_time) AS hour_of_day  -- optional context
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
      GROUP BY period_time
      ORDER BY period_time
    # Column mapping (flexible naming)
    timestamp_column: "period_time"
    value_column: "value"
    context_columns: ["hour_of_day"]

# Storage for historical window (required for detection)
storage:
  enabled: true
  type: "clickhouse"
  params:
    connection_string: "${METRICS_DB_URL}"

# Anomaly detection
detector:
  type: "mad"  # Median Absolute Deviation (robust)
  params:
    window_size: "30 days"
    n_sigma: 3.0

# Alert delivery
alerter:
  enabled: true  # Set to false for historical loads
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
    channel: "#ops-alerts"

# Scheduling
schedule:
  interval: "10 minutes"  # Continuous monitoring
```

### Run Metric Check

```bash
# Run once (typically called by cron/Prefect every 10 min)
dtk run configs/sessions_10min.yaml

# Run all metrics in directory
dtk run configs/

# Validate configuration
dtk validate configs/sessions_10min.yaml
```

### Load Historical Data

For initial setup or detector training, load historical data:

```yaml
# configs/sessions_10min_historical.yaml
name: "sessions_10min"

# ... same collector, detector config ...

schedule:
  start_time: "2024-01-01"   # Load from here
  end_time: "2024-11-01"     # Load until here
  interval: "10 minutes"
  batch_load_days: 30        # Load in 30-day batches

alerter:
  enabled: false  # NO alerts during historical load
```

Then run:
```bash
dtk load-history configs/sessions_10min_historical.yaml
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
  │              dtk_datapoints & dtk_detections        │
  │  - Time series data storage (ReplacingMergeTree)    │
  │  - Checkpoint system for resumable loads            │
  └─────────────────────────────────────────────────────┘
```

**Stage 1: Collection**
- Query source database for TIME SERIES (multiple rows with timestamps)
- Bulk insert to `dtk_datapoints` table (efficient batch operation)
- Works for any time range: 10 minutes → 1 point, or 30 days → 4,464 points

**Stage 2: Detection**
- Read historical window from storage (e.g., 30 days of data)
- Apply detection algorithm with optional seasonal features
- Return anomaly status and bounds

**Stage 3: Alert Decision**
- Check if alerting is enabled (`alerter.enabled`)
- Send alert if anomaly detected

**Key Insight: No Separate "Backtesting"**

Historical data loading = production monitoring with `alerter.enabled = false`

Same code, same pipeline, just different config flag!

---

## Time Series Architecture (CRITICAL!)

DetectK uses a time series architecture where analyst writes ONE query:

### Query Pattern

```sql
SELECT
    toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
    count() AS value
FROM events
WHERE timestamp >= toDateTime('{{ period_start }}')  -- ← Variables!
  AND timestamp < toDateTime('{{ period_finish }}')  -- ← Variables!
GROUP BY period_time
ORDER BY period_time
```

### How It Works

1. **Analyst writes query ONCE** with `{{ period_start }}`, `{{ period_finish }}` variables
2. **Collector stores query as template** (not rendered at config load time)
3. **Collector renders query on EACH call** with different time ranges:
   - Real-time: `collect_bulk(now-10min, now)` → 1 point
   - Bulk load: `collect_bulk(2024-01-01, 2024-01-31)` → 4,464 points
4. **Same query works for everything!**

### Flexible Column Naming

Analyst can name columns however they want:

```yaml
collector:
  params:
    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS ts,
        count() AS metric_val
      FROM my_table
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
      GROUP BY ts
      ORDER BY ts
    timestamp_column: "ts"         # Tell DetectK which column is timestamp
    value_column: "metric_val"     # Tell DetectK which column is value
```

---

## Available Components

### Collectors (Data Sources)

| Package | Databases | Status |
|---------|-----------|--------|
| `detectk-collectors-clickhouse` | ClickHouse | ✅ Complete |
| `detectk-collectors-sql` | PostgreSQL, MySQL, SQLite | ✅ Complete |
| `detectk-collectors-http` | REST APIs | 📋 Planned |

### Detectors (Anomaly Detection)

| Package | Algorithms | Status |
|---------|------------|--------|
| `detectk-detectors` | Threshold, Z-score, MAD | ✅ Complete |
| `detectk-detectors-timeseries` | Prophet, SARIMA | 📋 Planned |
| `detectk-detectors-ml` | Isolation Forest, Autoencoder | 📋 Planned |

### Alerters (Notification Channels)

| Package | Channels | Status |
|---------|----------|--------|
| `detectk-alerters-mattermost` | Mattermost | ✅ Complete |
| `detectk-alerters-slack` | Slack | ✅ Complete |
| `detectk-alerters-telegram` | Telegram | 📋 Planned |
| `detectk-alerters-email` | Email (SMTP) | 📋 Planned |

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

Account for time-of-day and day-of-week patterns via context columns:

```yaml
collector:
  params:
    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
        count() AS value,
        toHour(period_time) AS hour_of_day,
        toDayOfWeek(period_time) AS day_of_week
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
      GROUP BY period_time
      ORDER BY period_time
    context_columns: ["hour_of_day", "day_of_week"]

detector:
  type: "mad"
  params:
    window_size: "30 days"
    # Detector can use context for seasonal adjustment
```

---

## Project Status

**Current Status:** ✅ Phase 3 Complete - Time Series Architecture Refactored!

**Implemented (Ready to Use):**
- ✅ Core foundation (base classes, registry, configuration)
- ✅ Time series architecture with `collect_bulk()`
- ✅ ClickHouse collector and storage (with ReplacingMergeTree)
- ✅ Generic SQL collector (PostgreSQL, MySQL, SQLite)
- ✅ Multi-detector architecture with auto-generated IDs
- ✅ Detectors: Threshold, MAD, Z-Score, Missing Data
- ✅ Alerters: Mattermost, Slack
- ✅ Checkpoint system for resumable loads
- ✅ CLI tool (`dtk` command)
- ✅ 112+ tests passing
- ✅ Comprehensive documentation and examples

**CLI Commands Available:**
```bash
dtk init [path]          # Generate template configuration
dtk run <config>         # Run metric check
dtk validate <config>    # Validate configuration
dtk list-collectors      # Show available collectors
dtk list-detectors       # Show available detectors
dtk list-alerters        # Show available alerters
dtk list-metrics [dir]   # List all metrics in directory
dtk init-project [dir]   # Initialize project structure
```

**Quick Start:**
```bash
# Initialize project
dtk init-project my-metrics --minimal

cd my-metrics/

# Generate metric template
dtk init metrics/sessions.yaml -d mad

# Edit configuration
nano metrics/sessions.yaml

# Validate
dtk validate metrics/sessions.yaml

# Run
dtk run metrics/sessions.yaml
```

**Next Steps (Phase 4):**
- `dtk load-history` command for bulk loading
- Prophet time-series detector
- IQR detector
- Telegram and Email alerters
- Documentation site

See [TODO.md](TODO.md) for detailed roadmap (internal).

---

## Documentation

### User Guides
- **[INSTALLATION.md](INSTALLATION.md)** - Complete installation guide
- **[QUICKSTART.md](QUICKSTART.md)** - 5-minute tutorial
- **[CONFIGURATION.md](CONFIGURATION.md)** - Complete configuration reference
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment guide
- **[ORCHESTRATORS.md](ORCHESTRATORS.md)** - Prefect and Airflow integration
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[examples/](examples/)** - 37+ working configurations

### Developer Documentation
- **[DECISIONS.md](DECISIONS.md)** - Architectural decisions with rationale
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development standards and guidelines
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture (internal)
- **[TODO.md](TODO.md)** - Development roadmap (internal)

---

## Contributing

This project is in active development. See [CONTRIBUTING.md](CONTRIBUTING.md) for development standards.

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

**Built by data engineers, for data analysts.**
