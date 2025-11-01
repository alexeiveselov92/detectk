# DetectK Quickstart

Get started with DetectK in 5 minutes!

## Prerequisites

1. **Install DetectK packages:**
```bash
# Core package
pip install -e packages/core

# ClickHouse collector
pip install -e packages/collectors/clickhouse

# Detectors
pip install -e packages/detectors/core

# Mattermost alerter
pip install -e packages/alerters/mattermost
```

2. **Set up ClickHouse** (optional):
```bash
# Using Docker
docker run -d --name clickhouse -p 9000:9000 -p 8123:8123 clickhouse/clickhouse-server
```

3. **Set up Mattermost webhook** (optional):
- Go to Mattermost → Integrations → Incoming Webhooks
- Create new webhook
- Copy URL

## Quick Test (No External Services)

Test the CLI without ClickHouse or Mattermost:

```bash
# Validate configuration
dtk validate examples/quickstart/quickstart.yaml

# This will show:
# ✅ Configuration is valid!
```

## Run with ClickHouse

If you have ClickHouse running:

```bash
# Set environment variables
export CLICKHOUSE_HOST=localhost
export MATTERMOST_WEBHOOK=https://your-mattermost.com/hooks/xxx

# Run the check
dtk run examples/quickstart/quickstart.yaml
```

**Expected output:**
```
📊 Running metric check: examples/quickstart/quickstart.yaml

======================================================================
RESULTS
======================================================================
Metric: quickstart_example
Timestamp: 2024-11-02 12:34:56
Value: 100.00

Detections:
  [f270ccf6] 🚨 ANOMALY
    Direction: up

✉️  Alert sent: Anomaly detected

✅ Check completed successfully
```

## What Happens

1. **Collector** queries ClickHouse: `SELECT 100 as value`
2. **Detector** checks: Is 100 > 50? → Yes, **anomaly!**
3. **Alerter** sends message to Mattermost

## Next Steps

### 1. Create Your Own Metric

Copy `quickstart.yaml` and modify:

```yaml
name: "my_custom_metric"

collector:
  params:
    query: |
      SELECT count(*) as value
      FROM my_events
      WHERE timestamp >= now() - INTERVAL 1 HOUR
```

### 2. Try Different Detectors

**MAD (Median Absolute Deviation)** - statistical detection:
```yaml
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
```

**Z-Score** - mean/std detection:
```yaml
detector:
  type: "zscore"
  params:
    window_size: "7 days"
    n_sigma: 3.0
```

### 3. Enable Storage

Store historical data for analysis:

```yaml
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "localhost"
    database: "detectk"
    datapoints_retention_days: 90
```

### 4. Add Seasonal Features

For metrics with daily/weekly patterns:

```yaml
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    seasonal_features:
      - name: "hour_of_day"
        expression: "toHour(collected_at)"
      - name: "day_of_week"
        expression: "toDayOfWeek(collected_at)"
```

### 5. Multiple Detectors (A/B Testing)

Compare different detection strategies:

```yaml
detectors:
  - type: "mad"
    params: {window_size: "30 days", n_sigma: 3.0}

  - type: "mad"
    params: {window_size: "30 days", n_sigma: 5.0}

  - type: "zscore"
    params: {window_size: "7 days", n_sigma: 3.0}

storage:
  params:
    save_detections: true  # Save all detector results for comparison
```

## Troubleshooting

### "Connection refused" (ClickHouse)

ClickHouse not running. Start it:
```bash
docker start clickhouse
```

Or use different host:
```bash
export CLICKHOUSE_HOST=your-clickhouse-server.com
```

### "Invalid webhook URL" (Mattermost)

Set valid webhook:
```bash
export MATTERMOST_WEBHOOK=https://your-mattermost.com/hooks/xxx
```

Or disable alerting for testing (modify config):
```yaml
# Remove alerter section - NOT ALLOWED (alerter is required)
# Instead, use dummy webhook - alert will fail but detection still works
```

### "No module named 'detectk'"

Install core package:
```bash
cd packages/core
pip install -e .
```

### "No collectors registered"

Install collector package:
```bash
cd packages/collectors/clickhouse
pip install -e .
```

## CLI Commands Reference

```bash
# Run metric check
dtk run <config.yaml>

# Run with specific execution time
dtk run <config.yaml> -t "2024-11-01 14:30:00"

# Validate configuration
dtk validate <config.yaml>

# List available components
dtk list-detectors
dtk list-collectors
dtk list-alerters

# Show help
dtk --help
dtk run --help

# Verbose logging
dtk run <config.yaml> --verbose

# Quiet mode (errors only)
dtk run <config.yaml> --quiet
```

## Example Configurations

More examples available in `examples/` directory:

- `examples/threshold/` - Simple threshold detection
- `examples/mad/` - MAD detector with seasonal features
- `examples/zscore/` - Z-score detection
- `examples/mattermost/` - Mattermost alerting examples
- `examples/multi_detector/` - A/B testing multiple detectors

## Learn More

- **Architecture**: See `ARCHITECTURE.md` for technical details
- **Development**: See `CLAUDE.md` for design decisions
- **API Reference**: See docstrings in source code
- **Examples**: Browse `examples/` directory

---

**Questions? Issues?** Report at https://github.com/alexeiveselov92/detectk/issues
