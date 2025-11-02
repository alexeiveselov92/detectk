# Quick Start Guide

Get started with DetectK in 5 minutes.

## Installation

```bash
# Install core package
pip install detectk

# Install ClickHouse collector
pip install detectk-collectors-clickhouse

# Install basic detectors
pip install detectk-detectors

# Install Slack alerter (or use mattermost/telegram/email)
pip install detectk-alerters-slack
```

## Option 1: Initialize New Project (Recommended)

The fastest way to get started is using `dtk init-project`:

```bash
# Create new project with all templates and examples
dtk init-project my-metrics-monitoring

# Navigate to project
cd my-metrics-monitoring

# Set up credentials
cp detectk_profiles.yaml.template detectk_profiles.yaml
cp .env.template .env

# Edit with your credentials
vim detectk_profiles.yaml
vim .env

# Load environment variables
source .env

# Validate example configuration
dtk validate metrics/example_metric.yaml

# Run your first check
dtk run metrics/example_metric.yaml
```

This creates a complete project structure:
- `detectk_profiles.yaml.template` - Connection profile template
- `.env.template` - Environment variables template
- `.gitignore` - Credentials protection (gitignored files)
- `README.md` - Setup instructions
- `metrics/example_metric.yaml` - Starter metric configuration
- `examples/` - Reference examples (optional)

**Interactive mode:**
```bash
dtk init-project --interactive
```

**Minimal setup (no examples):**
```bash
dtk init-project --minimal
```

See [Connection Profiles Guide](profiles.md) for more details on credential management.

---

## Option 2: Manual Setup

If you prefer manual setup, follow these steps:

## Your First Metric Check

### Step 1: Create Configuration

Create `my_first_metric.yaml`:

```yaml
name: "user_sessions"
description: "Monitor active user sessions"

collector:
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"
    user: "default"
    password: ""
    query: |
      SELECT count(DISTINCT user_id) as value
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

detector:
  type: "threshold"
  params:
    value: 100
    operator: "less_than"

alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK_URL}"
    cooldown_minutes: 60

storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"
```

### Step 2: Set Environment Variables

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### Step 3: Run the Check

```bash
dtk run my_first_metric.yaml
```

**Expected output:**
```
✓ Collected value: 1234.0
✓ Detection complete: Not anomalous
✓ Check completed successfully
```

If value < 100, you'll get a Slack alert!

## Next Steps: Threshold Detection

Threshold detector is the simplest - alerts when value crosses a threshold.

**Common operators:**

```yaml
# Alert when value is too low
detector:
  type: "threshold"
  params:
    value: 100
    operator: "less_than"

# Alert when value is too high
detector:
  type: "threshold"
  params:
    value: 10000
    operator: "greater_than"

# Alert when value is in range (BAD range)
detector:
  type: "threshold"
  params:
    min_value: 500
    max_value: 1000
    operator: "between"  # Alert if 500 <= value <= 1000

# Alert when value is NOT in range (GOOD range)
detector:
  type: "threshold"
  params:
    min_value: 1000
    max_value: 5000
    operator: "outside"  # Alert if value < 1000 OR value > 5000
```

## Advanced: Statistical Detection (MAD)

For metrics that change over time, use statistical detectors:

```yaml
name: "sessions_with_seasonality"

collector:
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"
    query: |
      SELECT count(DISTINCT user_id) as value
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

detector:
  type: "mad"  # Median Absolute Deviation - robust to outliers
  params:
    window_size: "30 days"  # Look at last 30 days
    n_sigma: 3.0            # Alert if 3 standard deviations away

    # Account for daily patterns
    seasonal_features:
      - name: "hour_of_day"
        expression: "toHour(now())"
      - name: "day_of_week"
        expression: "toDayOfWeek(now())"

alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK_URL}"
    cooldown_minutes: 60

storage:
  enabled: true  # Required for MAD - needs historical data
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"
```

**How it works:**
1. Detector reads last 30 days of data from storage
2. Groups by hour + day of week (e.g., "Monday 2PM")
3. Calculates median and MAD for each group
4. Compares current value to expected range
5. Alerts if outside 3 standard deviations

## Connection Profiles (Recommended)

Instead of repeating connection details in every metric, use profiles:

**Create `detectk_profiles.yaml`:**

```yaml
profiles:
  prod_clickhouse:
    type: "clickhouse"
    host: "prod.clickhouse.company.com"
    port: 9000
    database: "analytics"
    user: "detectk"
    password: "${CLICKHOUSE_PASSWORD}"
```

**Use in metric config:**

```yaml
name: "sessions_with_profile"

collector:
  profile: "prod_clickhouse"  # ← Reference profile
  params:
    query: |
      SELECT
        toStartOfInterval(toDateTime('{{ period_finish }}'), INTERVAL 10 MINUTE) as period_time,
        count() as value
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

detector:
  type: "threshold"
  params:
    value: 100
    operator: "less_than"

storage:
  enabled: true
  profile: "prod_clickhouse"  # ← Reuse same profile

alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK_URL}"
```

**Benefits:**
- DRY - define connection once
- Secure - credentials in separate file (not in git)
- Flexible - change globally or override per metric

## Backtesting

Test your detector on historical data before deploying:

```bash
dtk backtest my_metric.yaml \
  --start "2024-01-01" \
  --end "2024-02-01" \
  --step "10 minutes"
```

**Output:**
```
Backtesting sessions_with_seasonality
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 4464/4464 [00:45<00:00]

Results:
  Total checks: 4464
  Anomalies detected: 23
  Precision: 0.87
  Recall: 0.91
  F1 Score: 0.89
```

See [Backtesting Guide](backtesting.md) for details.

## CLI Commands

```bash
# Run single metric
dtk run metric.yaml

# Run all metrics in directory
dtk run configs/

# Validate configuration
dtk validate metric.yaml

# Generate template
dtk init revenue_monitoring --detector mad

# List available components
dtk list-collectors
dtk list-detectors
dtk list-alerters

# Backtest
dtk backtest metric.yaml --start 2024-01-01 --end 2024-02-01

# Help
dtk --help
dtk run --help
```

## What's Next?

- **[Collectors Guide](collectors.md)** - Connect to different data sources
- **[Detectors Guide](detectors.md)** - Choose the right detection algorithm
- **[Connection Profiles](profiles.md)** - Manage credentials securely
- **[Backtesting Guide](backtesting.md)** - Test on historical data
- **[Configuration Reference](configuration.md)** - Complete YAML schema

## Common Issues

### "No module named 'detectk_collectors_clickhouse'"

Install the collector package:
```bash
pip install detectk-collectors-clickhouse
```

### "ConfigurationError: Invalid webhook_url"

Set environment variable:
```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

### "Storage required for detector type 'mad'"

MAD detector needs historical data. Add storage config:
```yaml
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"
```

### Empty query results return value=0

This is expected behavior. If you want to alert on missing data, see [Missing Data Handling](../reference/missing-data.md).

## Examples

See [examples/](../../examples/) directory for ready-to-use configurations:
- `examples/quickstart/` - Minimal working example
- `examples/threshold/` - Simple threshold checks
- `examples/seasonal/` - MAD with hourly/daily patterns
- `examples/multi-detector/` - A/B testing detectors
- `examples/profiles/` - Using connection profiles
