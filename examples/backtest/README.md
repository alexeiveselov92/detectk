# Backtesting Examples

Test your anomaly detection configurations on historical data before deploying to production.

## What is Backtesting?

Backtesting simulates running your metric check at multiple points in time using historical data. This allows you to:

✅ **Evaluate detector performance** - See how many anomalies would have been detected
✅ **Tune parameters** - Test different `n_sigma`, `window_size` values
✅ **Estimate alert frequency** - Understand cooldown impact
✅ **Validate before production** - Catch issues before deployment

## Quick Start

### 1. Prepare Configuration

Add `backtest` section to your metric config:

```yaml
backtest:
  enabled: true
  data_load_start: "2024-01-01"    # Start loading historical data
  detection_start: "2024-02-01"    # Start detecting (after window accumulated)
  detection_end: "2024-03-01"      # End detection
  step_interval: "10 minutes"      # Time between simulated checks
```

**Important:** Your collector query must use `{{ execution_time }}` template variable:

```yaml
collector:
  params:
    query: |
      SELECT count() as value
      FROM sessions
      WHERE timestamp >= toDateTime('{{ execution_time }}') - INTERVAL 10 MINUTE
        AND timestamp < toDateTime('{{ execution_time }}')
```

### 2. Run Backtest

```bash
# Basic run
dtk backtest examples/backtest/sessions_backtest.yaml

# Save results to CSV
dtk backtest examples/backtest/sessions_backtest.yaml -o results.csv

# Verbose output
dtk backtest examples/backtest/sessions_backtest.yaml -v
```

### 3. Analyze Results

Backtest output shows:
- Total checks performed
- Anomalies detected
- Alerts sent (after cooldown)
- Anomaly rate and alert rate
- Sample of detected anomalies

If saved to CSV, you get all detection results for detailed analysis.

## Configuration Parameters

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `enabled` | Enable backtesting mode | `true` |
| `data_load_start` | When to start loading data | `"2024-01-01"` |
| `detection_start` | When to start detecting | `"2024-02-01"` |
| `detection_end` | When to stop detecting | `"2024-03-01"` |
| `step_interval` | Time between checks | `"10 minutes"` |

### Date Formats

Supports flexible date formats:
- `"2024-01-01"` - Date only (00:00:00 assumed)
- `"2024-01-01 14:30:00"` - Full datetime
- `"2024-01-01T14:30:00"` - ISO format

### Step Intervals

Supported interval formats:
- `"10 minutes"` or `"10 minute"`
- `"1 hour"` or `"1 hours"`
- `"1 day"` or `"1 days"`
- `"1 week"` or `"1 weeks"`

## How It Works

### 1. Timeline

```
data_load_start     detection_start          detection_end
       |                    |                      |
       v                    v                      v
|------+--------------------+----------------------|
       [  accumulate window  ]  [  detect period   ]
```

**Why two start dates?**

- `data_load_start`: Collectors start here, allowing detector's historical window to accumulate
- `detection_start`: Detection starts here, after sufficient data collected
- Example: MAD with 30-day window needs 30 days between starts

### 2. Execution Flow

For each time step from `detection_start` to `detection_end`:

1. **Collect** - Query data at `execution_time`
2. **Detect** - Run anomaly detection using historical window
3. **Alert** - Send alert if anomaly (respects cooldown)
4. **Store** - Save detection results (if storage enabled)
5. **Repeat** - Move to next time step

### 3. Same Code Path

**Critical:** Backtesting uses the SAME `MetricCheck.execute()` as production!
- No separate backtest-specific logic
- What you test is what you deploy
- Just iterates through time instead of running once

## Examples

### Example 1: Basic MAD Backtest

```yaml
name: "sessions_backtest"

collector:
  type: "clickhouse"
  params:
    query: |
      SELECT count() as value
      FROM sessions
      WHERE timestamp >= toDateTime('{{ execution_time }}') - INTERVAL 10 MINUTE
        AND timestamp < toDateTime('{{ execution_time }}')

detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0

backtest:
  enabled: true
  data_load_start: "2024-01-01"
  detection_start: "2024-02-01"  # 30 days later
  detection_end: "2024-03-01"
  step_interval: "10 minutes"
```

**Result:** ~4,320 checks (30 days * 144 checks/day)

### Example 2: Parameter Tuning

Test multiple n_sigma values:

```bash
# Conservative (fewer alerts)
dtk backtest config_nsigma_5.yaml -o results_nsigma_5.csv

# Moderate
dtk backtest config_nsigma_3.yaml -o results_nsigma_3.csv

# Aggressive (more alerts)
dtk backtest config_nsigma_2.yaml -o results_nsigma_2.csv
```

Compare CSV files to find optimal threshold.

### Example 3: Quick Test (Small Window)

For quick validation, use shorter period:

```yaml
backtest:
  enabled: true
  data_load_start: "2024-03-01"
  detection_start: "2024-03-08"  # 7 days later
  detection_end: "2024-03-09"    # Just 1 day of testing
  step_interval: "10 minutes"
```

**Result:** ~144 checks (1 day)
**Use case:** Quick sanity check before full backtest

## Analyzing Results

### CSV Output Columns

| Column | Description |
|--------|-------------|
| `timestamp` | Time of check |
| `value` | Metric value collected |
| `is_anomaly` | Boolean - anomaly detected? |
| `score` | Anomaly score (sigma) |
| `lower_bound` | Expected minimum |
| `upper_bound` | Expected maximum |
| `direction` | "up" or "down" |
| `percent_deviation` | % deviation from expected |
| `alert_sent` | Boolean - alert sent? (after cooldown) |

### Analysis with pandas

```python
import pandas as pd

df = pd.read_csv("results.csv")

# Anomaly rate
anomaly_rate = (df["is_anomaly"].sum() / len(df)) * 100
print(f"Anomaly rate: {anomaly_rate:.2f}%")

# Alert rate (after cooldown)
alert_rate = (df["alert_sent"].sum() / len(df)) * 100
print(f"Alert rate: {alert_rate:.2f}%")

# Distribution of anomaly scores
print(df[df["is_anomaly"]]["score"].describe())

# Anomalies by hour of day
df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
hourly_anomalies = df[df["is_anomaly"]].groupby("hour").size()
print(hourly_anomalies)
```

## Best Practices

### 1. Choose Appropriate Period

- **Too short** (<7 days): May not capture patterns
- **Too long** (>90 days): Slow, expensive
- **Recommended:** 30-60 days for most use cases

### 2. Match Production Interval

Use same `step_interval` as production scheduler:
- Production runs every 10 min → `step_interval: "10 minutes"`
- Production runs hourly → `step_interval: "1 hour"`

### 3. Accumulate Sufficient Window

Ensure gap between `data_load_start` and `detection_start` matches detector's window:
- MAD with 30-day window → 30-day gap
- Z-Score with 7-day window → 7-day gap
- Threshold detector → No gap needed (no historical window)

### 4. Disable Alerts in Backtest

To prevent spam during testing, use dummy alerter or disable webhooks:

```yaml
alerter:
  type: "mattermost"
  params:
    webhook_url: "https://httpbin.org/post"  # Dummy endpoint
    cooldown_minutes: 9999999  # Effectively disable
```

Or comment out alerter temporarily.

### 5. Enable Storage

Always enable storage during backtest for analysis:

```yaml
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "localhost"
    database: "detectk"
```

Query results later:
```sql
SELECT * FROM dtk_detections
WHERE metric_name = 'your_metric'
ORDER BY detected_at DESC;
```

## Performance

### Execution Time

Depends on:
- Number of checks (period length / step interval)
- Detector complexity (MAD/Z-Score slower than Threshold)
- Database query performance
- Window size

**Rough estimates:**
- 1,000 checks: ~30-60 seconds
- 10,000 checks: ~5-10 minutes
- 100,000 checks: ~30-60 minutes

### Memory Usage

Minimal - each check is independent, no accumulated state.

### Database Load

Backtesting generates many queries. Recommendations:
- Run on replica database (not production)
- Use off-peak hours
- Consider smaller `step_interval` for testing (e.g., "1 hour" instead of "10 minutes")

## Troubleshooting

### "Backtesting not enabled"

```yaml
# Add this to your config
backtest:
  enabled: true
  # ... other parameters
```

### "data_load_start must be before detection_start"

Ensure correct date order:
```yaml
backtest:
  data_load_start: "2024-01-01"    # Earlier
  detection_start: "2024-02-01"    # Later
  detection_end: "2024-03-01"      # Latest
```

### "Invalid interval format"

Use format: `"<number> <unit>"`
- ✅ Correct: `"10 minutes"`, `"1 hour"`, `"1 day"`
- ❌ Wrong: `"10min"`, `"1h"`, `"every hour"`

### Query doesn't use execution_time

Your collector query must use `{{ execution_time }}` template:

```yaml
collector:
  params:
    query: |
      SELECT count() as value
      FROM events
      WHERE timestamp >= toDateTime('{{ execution_time }}') - INTERVAL 10 MINUTE
        AND timestamp < toDateTime('{{ execution_time }}')
      # ↑ execution_time injected by BacktestRunner
```

### Too slow / too many checks

Reduce check frequency:
```yaml
# Instead of every 10 minutes (4,320 checks/month)
step_interval: "10 minutes"

# Try every hour (720 checks/month)
step_interval: "1 hour"
```

Or reduce testing period:
```yaml
# Instead of 30 days
detection_end: "2024-03-01"

# Try 7 days
detection_end: "2024-02-08"
```

## See Also

- [MAD Detector Examples](../mad/) - Statistical detection configurations
- [Multi-Detector Examples](../multi_detector/) - A/B testing multiple algorithms
- [Mattermost Alerting](../mattermost/) - Alert configuration
- [DetectK Documentation](https://github.com/alexeiveselov92/detectk)
