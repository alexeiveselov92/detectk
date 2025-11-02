# Backtesting Guide

Backtesting lets you test your detection strategy on historical data before deploying to production. This helps you tune parameters and avoid false positives.

## Why Backtest?

**Without backtesting:**
- Deploy detector → get flooded with false alerts → tune blindly → repeat
- No confidence in detector performance
- Stakeholders lose trust in alerts

**With backtesting:**
- Test on historical data → see precision/recall → tune parameters → verify
- Know expected alert rate before deploying
- Build confidence with stakeholders

## Quick Start

### Step 1: Create Metric Config

```yaml
# sessions_monitor.yaml
name: "sessions_10min"

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
        AND timestamp < toDateTime('{{ period_finish }}') 10 MINUTE
        AND timestamp < '{{ execution_time }}'

detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    seasonal_features:
      - name: "hour_of_day"
        expression: "toHour('{{ execution_time }}')"

storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"

alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK}"
```

### Step 2: Run Backtest

```bash
dtk backtest sessions_monitor.yaml \
  --start "2024-01-01" \
  --end "2024-02-01" \
  --step "10 minutes"
```

### Step 3: Analyze Results

```
Backtesting sessions_10min
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 4464/4464 [00:45<00:00, 98 checks/s]

Backtest Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Period: 2024-01-01 to 2024-02-01 (31 days)
Step interval: 10 minutes
Total checks: 4464

Anomalies Detected: 23 (0.52%)

Performance Metrics:
  Precision: 0.87 (87% of alerts were real issues)
  Recall: 0.91 (caught 91% of known issues)
  F1 Score: 0.89
  False Positive Rate: 0.13

Detector: mad (n_sigma=3.0, window_size=30 days)

Top Anomalies (by deviation):
  2024-01-15 14:30 → value=1245 (expected: 800-1000, +24.5%)
  2024-01-22 03:00 → value=50 (expected: 600-800, -92.5%)
  2024-01-28 19:45 → value=1890 (expected: 900-1100, +71.8%)
```

## Backtest Configuration

### Command-Line Options

```bash
dtk backtest <config> [options]

Required:
  --start DATETIME       Start date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
  --end DATETIME         End date

Optional:
  --step INTERVAL        Time step (default: from config or "10 minutes")
  --output FORMAT        Output format: text|json|csv (default: text)
  --save-results PATH    Save results to file
  --no-alerts            Don't send alerts during backtest
  --verbose              Show detailed progress
```

### YAML Configuration

```yaml
# In metric config file
backtest:
  enabled: true
  data_load_start: "2024-01-01"    # Start loading data
  detection_start: "2024-02-01"    # Start detecting (after window accumulated)
  detection_end: "2024-03-01"      # End detection
  step_interval: "10 minutes"      # Simulation step
```

**Run with config:**
```bash
dtk backtest sessions_monitor.yaml  # Uses backtest config from YAML
```

## Understanding Results

### Precision

**What it means:** Of all anomalies detected, how many were real issues?

```
Precision = True Positives / (True Positives + False Positives)
```

**Example:**
- Detected 100 anomalies
- 87 were real issues, 13 were false alarms
- Precision = 87 / 100 = 0.87 (87%)

**Interpretation:**
- High precision (>80%) = Few false positives, stakeholders trust alerts
- Low precision (<50%) = Too many false alarms, need to tune detector

**How to improve:**
- Increase `n_sigma` (3.0 → 4.0 or 5.0)
- Add seasonal features (hour_of_day, day_of_week)
- Increase window_size (30 days → 60 days)

### Recall

**What it means:** Of all real issues, how many did we catch?

```
Recall = True Positives / (True Positives + False Negatives)
```

**Example:**
- There were 100 real issues in the period
- Detected 91 of them, missed 9
- Recall = 91 / 100 = 0.91 (91%)

**Interpretation:**
- High recall (>80%) = Catching most issues, good coverage
- Low recall (<50%) = Missing real problems, detector too conservative

**How to improve:**
- Decrease `n_sigma` (3.0 → 2.5)
- Decrease window_size (30 days → 14 days)
- Use weighted statistics (recent data matters more)

### F1 Score

**What it means:** Harmonic mean of precision and recall.

```
F1 = 2 * (Precision * Recall) / (Precision + Recall)
```

**Interpretation:**
- F1 > 0.85 = Excellent detector
- F1 0.70-0.85 = Good detector
- F1 < 0.70 = Needs tuning

### False Positive Rate

**What it means:** What percentage of normal periods were incorrectly flagged?

```
FPR = False Positives / (False Positives + True Negatives)
```

**Target:** < 1% for production systems

## Tuning Detectors

### Scenario 1: Too Many False Positives

**Symptoms:**
- Precision < 70%
- Lots of alerts that aren't real issues

**Solution - Make detector more conservative:**

```yaml
# Before (aggressive)
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0

# After (conservative)
detector:
  type: "mad"
  params:
    window_size: "60 days"  # Longer history
    n_sigma: 5.0            # Higher threshold
    seasonal_features:      # Add seasonality
      - name: "hour_of_day"
        expression: "toHour('{{ execution_time }}')"
```

**Run backtest again:**
```bash
dtk backtest sessions_monitor.yaml --start 2024-01-01 --end 2024-02-01
```

### Scenario 2: Missing Real Issues

**Symptoms:**
- Recall < 70%
- Known incidents not detected

**Solution - Make detector more sensitive:**

```yaml
# Before (conservative)
detector:
  type: "mad"
  params:
    window_size: "60 days"
    n_sigma: 5.0

# After (sensitive)
detector:
  type: "mad"
  params:
    window_size: "14 days"  # Shorter window (more reactive)
    n_sigma: 2.5            # Lower threshold
    use_weighted: true      # Recent data matters more
```

### Scenario 3: Weekday vs Weekend Patterns

**Symptoms:**
- False alerts every Monday morning
- False alerts every weekend

**Solution - Add day_of_week seasonality:**

```yaml
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    seasonal_features:
      - name: "day_of_week"
        expression: "toDayOfWeek('{{ execution_time }}')"
      - name: "hour_of_day"
        expression: "toHour('{{ execution_time }}')"
```

## Advanced Backtesting

### A/B Testing Detectors

Compare multiple detection strategies:

```yaml
name: "sessions_ab_test"

collector:
  type: "clickhouse"
  params:
    query: |
      SELECT
        toStartOfInterval(toDateTime('{{ period_finish }}'), INTERVAL 10 MINUTE) as period_time,
        count() as value
      FROM sessions
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')

detectors:
  # Strategy A: Conservative MAD
  - id: "conservative"
    type: "mad"
    params:
      window_size: "30 days"
      n_sigma: 5.0

  # Strategy B: Balanced MAD
  - id: "balanced"
    type: "mad"
    params:
      window_size: "30 days"
      n_sigma: 3.0

  # Strategy C: Aggressive MAD
  - id: "aggressive"
    type: "mad"
    params:
      window_size: "14 days"
      n_sigma: 2.5

  # Strategy D: Z-Score alternative
  - id: "zscore"
    type: "zscore"
    params:
      window_size: "30 days"
      n_sigma: 3.0

storage:
  enabled: true
  params:
    save_detections: true  # Save all results for comparison
```

**Run backtest:**
```bash
dtk backtest sessions_ab_test.yaml --start 2024-01-01 --end 2024-02-01 --output json --save-results results.json
```

**Compare results:**
```python
import json
import pandas as pd

with open('results.json') as f:
    data = json.load(f)

# Compare detector performance
for detector_id, metrics in data['detectors'].items():
    print(f"{detector_id}:")
    print(f"  Precision: {metrics['precision']:.2%}")
    print(f"  Recall: {metrics['recall']:.2%}")
    print(f"  F1: {metrics['f1_score']:.2%}")
    print(f"  Anomalies: {metrics['anomalies_detected']}")
    print()
```

### Save Backtest Results

```bash
# Save as JSON
dtk backtest metric.yaml \
  --start 2024-01-01 \
  --end 2024-02-01 \
  --output json \
  --save-results backtest_results.json

# Save as CSV (for Excel/analysis)
dtk backtest metric.yaml \
  --start 2024-01-01 \
  --end 2024-02-01 \
  --output csv \
  --save-results backtest_results.csv
```

**JSON output includes:**
- Summary statistics (precision, recall, F1)
- All detected anomalies with timestamps and values
- Detector configuration used
- Per-detector results (if multi-detector)

### Visualize Backtest Results

```python
import pandas as pd
import matplotlib.pyplot as plt

# Load backtest results
df = pd.read_csv('backtest_results.csv')

# Plot metric over time with anomalies highlighted
plt.figure(figsize=(15, 6))
plt.plot(df['timestamp'], df['value'], label='Metric value')
plt.scatter(
    df[df['is_anomaly']]['timestamp'],
    df[df['is_anomaly']]['value'],
    color='red',
    label='Anomalies',
    s=100,
    marker='x'
)
plt.xlabel('Time')
plt.ylabel('Value')
plt.title('Backtest Results: sessions_10min')
plt.legend()
plt.savefig('backtest_visualization.png')
```

## Best Practices

### 1. Use Realistic Time Ranges

```bash
# ✓ GOOD - representative period (includes weekdays, weekends, events)
dtk backtest metric.yaml --start "2024-01-01" --end "2024-02-01"

# ✗ BAD - too short (only 3 days, not representative)
dtk backtest metric.yaml --start "2024-01-01" --end "2024-01-03"
```

**Recommended:**
- Minimum: 2-4 weeks (captures weekly patterns)
- Ideal: 1-3 months (captures monthly patterns, holidays)

### 2. Include Known Incidents

Test on periods with known issues to verify recall:

```bash
# Backtest over period with known incident on 2024-01-15
dtk backtest metric.yaml --start "2024-01-01" --end "2024-02-01"

# Check if incident was detected
grep "2024-01-15" backtest_results.json
```

### 3. Don't Send Alerts During Backtest

```bash
# Suppress alerts (default)
dtk backtest metric.yaml --no-alerts --start 2024-01-01 --end 2024-02-01

# Or test alert formatting (careful!)
dtk backtest metric.yaml --start 2024-01-01 --end 2024-01-02  # Short period only
```

### 4. Iterate Parameters

```bash
# Test 1: Conservative
dtk backtest metric.yaml --start 2024-01-01 --end 2024-02-01 > test1_n5.txt

# Edit metric.yaml, change n_sigma to 3.0

# Test 2: Balanced
dtk backtest metric.yaml --start 2024-01-01 --end 2024-02-01 > test2_n3.txt

# Edit metric.yaml, change n_sigma to 2.5

# Test 3: Aggressive
dtk backtest metric.yaml --start 2024-01-01 --end 2024-02-01 > test3_n2.5.txt

# Compare results
diff test1_n5.txt test2_n3.txt
```

### 5. Verify Query Templates

Ensure `{{ execution_time }}` is used correctly:

```yaml
# ✓ GOOD - uses execution_time for backtesting
collector:
  params:
    query: |
      SELECT count() as value
      FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}') 10 MINUTE
        AND timestamp < '{{ execution_time }}'

# ✗ BAD - uses now(), doesn't work for backtesting
collector:
  params:
    query: |
      SELECT count() as value
      FROM events
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
```

## Troubleshooting

### "Insufficient data for window"

**Cause:** Not enough historical data accumulated before detection_start.

**Solution:**
```bash
# Ensure data_load_start is earlier than detection_start
# Rule: detection_start >= data_load_start + window_size

# If window_size = 30 days:
dtk backtest metric.yaml \
  --start "2024-01-01" \  # data_load_start
  --end "2024-03-01"      # Will start detecting on 2024-01-31 (30 days later)
```

### Backtest is very slow

**Causes:**
- Large time range
- Small step interval
- Slow database queries

**Solutions:**

```bash
# 1. Reduce time range for testing
dtk backtest metric.yaml --start 2024-01-01 --end 2024-01-07  # 1 week only

# 2. Increase step interval
dtk backtest metric.yaml --start 2024-01-01 --end 2024-02-01 --step "1 hour"  # Instead of 10 minutes

# 3. Optimize database query
# Add indexes on timestamp columns
```

### All precision/recall metrics are 0

**Cause:** No known anomalies to compare against (ground truth missing).

**Current behavior:** DetectK calculates metrics based on detected anomalies only.

**Workaround:** Manually review anomalies in output and assess false positive rate.

**Future:** Support for ground truth labels (verified anomalies).

### Query returns empty results

**Cause:** Time range in backtest is before data exists.

**Solution:**
```bash
# Check data availability first
clickhouse-client --query "SELECT min(timestamp), max(timestamp) FROM events"

# Use appropriate time range
dtk backtest metric.yaml --start "2023-06-01" --end "2023-07-01"
```

## Examples

See [examples/backtesting/](../../examples/backtesting/) for complete examples:

- `basic_backtest.yaml` - Simple backtest configuration
- `ab_testing.yaml` - Multi-detector comparison
- `seasonal_tuning.yaml` - Tuning seasonal features
- `analyze_results.py` - Python script for result analysis

## Next Steps

- **[Detectors Guide](detectors.md)** - Understand detector parameters
- **[Quick Start Guide](quickstart.md)** - Get started with first metric
- **[Configuration Reference](configuration.md)** - Complete YAML schema
