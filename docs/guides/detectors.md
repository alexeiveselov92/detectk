# Detectors Guide

Detectors analyze metric values and determine if they are anomalous. This guide helps you choose the right detector for your use case.

## Quick Decision Tree

```
Is your metric stable with known thresholds?
├─ YES → Use Threshold Detector
└─ NO → Does it have patterns (hourly, daily, weekly)?
    ├─ YES → Use MAD or Z-Score with seasonal_features
    └─ NO → Use MAD or Z-Score without seasonality
```

## Available Detectors

| Detector | Package | Use Case | Requires Storage |
|----------|---------|----------|------------------|
| Threshold | `detectk-detectors` | Simple rules (value > X) | No |
| MAD | `detectk-detectors` | General purpose, robust to outliers | Yes |
| Z-Score | `detectk-detectors` | Normal distribution assumption | Yes |
| Prophet | `detectk-detectors-timeseries` | Complex seasonality, trends | Yes |
| IsolationForest | `detectk-detectors-ml` | Multivariate anomalies | Yes |

## Threshold Detector

**Best for:** Simple business rules, SLA monitoring, known limits.

### Installation

```bash
pip install detectk-detectors
```

### Basic Usage

```yaml
detector:
  type: "threshold"
  params:
    value: 1000
    operator: "greater_than"
```

### Operators

**Comparison operators:**

```yaml
# Alert if value > 1000
params:
  value: 1000
  operator: "greater_than"

# Alert if value >= 1000
params:
  value: 1000
  operator: "greater_equal"

# Alert if value < 100
params:
  value: 100
  operator: "less_than"

# Alert if value <= 100
params:
  value: 100
  operator: "less_equal"

# Alert if value == 0
params:
  value: 0
  operator: "equals"

# Alert if value != 1
params:
  value: 1
  operator: "not_equals"
```

**Range operators:**

```yaml
# Alert if value is in BAD range
params:
  min_value: 500
  max_value: 1000
  operator: "between"  # Alerts if 500 <= value <= 1000

# Alert if value is outside GOOD range
params:
  min_value: 1000
  max_value: 5000
  operator: "outside"  # Alerts if value < 1000 OR value > 5000
```

### Percentage Change

Monitor relative changes instead of absolute values:

```yaml
detector:
  type: "threshold"
  params:
    percent_change: 20  # Alert if +20% or -20% change
    baseline: "previous"  # Compare to previous value

# OR compare to average
detector:
  type: "threshold"
  params:
    percent_change: 30
    baseline: "average"
    baseline_window: "7 days"
```

### Examples

**SLA monitoring (uptime > 99.9%):**

```yaml
collector:
  params:
    query: |
      SELECT
        countIf(status_code = 200) / count() * 100 as value
      FROM http_requests
      WHERE timestamp >= now() - INTERVAL 1 MINUTE

detector:
  type: "threshold"
  params:
    value: 99.9
    operator: "less_than"  # Alert if uptime < 99.9%
```

**Revenue drop detection:**

```yaml
collector:
  params:
    query: "SELECT sum(amount) as value FROM purchases WHERE date = today()"

detector:
  type: "threshold"
  params:
    percent_change: 20
    baseline: "average"
    baseline_window: "7 days"  # Alert if revenue 20% below 7-day average
```

**Latency SLA (p95 < 500ms):**

```yaml
collector:
  params:
    query: "SELECT quantile(0.95)(duration_ms) as value FROM requests WHERE timestamp >= now() - INTERVAL 5 MINUTE"

detector:
  type: "threshold"
  params:
    value: 500
    operator: "greater_than"  # Alert if p95 latency > 500ms
```

## MAD Detector (Median Absolute Deviation)

**Best for:** General purpose anomaly detection, metrics with outliers, seasonal patterns.

**Why MAD?**
- Robust to outliers (unlike Z-Score)
- Works with non-normal distributions
- Reliable with small datasets

### Installation

```bash
pip install detectk-detectors
```

### Basic Usage

```yaml
detector:
  type: "mad"
  params:
    window_size: "30 days"  # Historical window
    n_sigma: 3.0            # Sensitivity (higher = fewer alerts)

storage:
  enabled: true  # Required for MAD
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `window_size` | string | "30 days" | Historical data window |
| `n_sigma` | float | 3.0 | Standard deviations threshold |
| `min_window_size` | int | 100 | Minimum data points required |
| `use_weighted` | bool | false | Weight recent data more |
| `weights_type` | string | "exponential" | Weight function type |
| `exp_decay_factor` | float | 0.001 | Exponential decay rate |
| `seasonal_features` | list | [] | Seasonal grouping features |
| `use_combined_seasonality` | bool | true | Group by all features together |

### Sensitivity Tuning

**n_sigma controls how strict the detector is:**

```yaml
# Aggressive - more alerts (catch everything)
params:
  n_sigma: 2.0  # ~95% confidence interval

# Balanced - default
params:
  n_sigma: 3.0  # ~99.7% confidence interval

# Conservative - fewer alerts (only clear anomalies)
params:
  n_sigma: 5.0  # ~99.9999% confidence interval
```

**Rule of thumb:**
- Start with `n_sigma: 3.0`
- Getting too many false positives? Increase to 4.0 or 5.0
- Missing real issues? Decrease to 2.5

### Seasonal Features

Account for patterns like hourly, daily, or weekly cycles:

```yaml
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0

    # Compare Monday 2PM to other Monday 2PMs
    seasonal_features:
      - name: "hour_of_day"
        expression: "toHour(now())"
      - name: "day_of_week"
        expression: "toDayOfWeek(now())"
```

**Common seasonal patterns:**

```yaml
# Hourly pattern (traffic higher during business hours)
seasonal_features:
  - name: "hour_of_day"
    expression: "toHour(now())"

# Daily pattern (weekday vs weekend)
seasonal_features:
  - name: "day_of_week"
    expression: "toDayOfWeek(now())"

# Combined (Monday 2PM vs Tuesday 3PM)
seasonal_features:
  - name: "hour_of_day"
    expression: "toHour(now())"
  - name: "day_of_week"
    expression: "toDayOfWeek(now())"

# Monthly pattern (end-of-month billing cycles)
seasonal_features:
  - name: "day_of_month"
    expression: "toDayOfMonth(now())"

# Business-specific (14-day league cycle)
seasonal_features:
  - name: "league_day"
    expression: "dateDiff('day', '2024-01-01', now()) % 14"
```

### Weighted Statistics

Give more importance to recent data:

```yaml
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    use_weighted: true
    weights_type: "exponential"
    exp_decay_factor: 0.001  # Adjust decay rate
```

**When to use:**
- Metric is changing over time (growing user base)
- Recent patterns more relevant than old data
- Concept drift in your system

### Examples

**Session monitoring with hourly patterns:**

```yaml
name: "sessions_10min"

collector:
  type: "clickhouse"
  params:
    query: "SELECT count(DISTINCT user_id) as value FROM sessions WHERE timestamp >= now() - INTERVAL 10 MINUTE"

detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    seasonal_features:
      - name: "hour_of_day"
        expression: "toHour(now())"
      - name: "day_of_week"
        expression: "toDayOfWeek(now())"

storage:
  enabled: true
  type: "clickhouse"
```

**Revenue with weekly patterns:**

```yaml
name: "daily_revenue"

collector:
  params:
    query: "SELECT sum(amount) as value FROM purchases WHERE date = today()"

detector:
  type: "mad"
  params:
    window_size: "90 days"
    n_sigma: 4.0  # Conservative for revenue
    seasonal_features:
      - name: "day_of_week"
        expression: "toDayOfWeek(now())"
    use_weighted: true  # Recent trends matter more
```

## Z-Score Detector

**Best for:** Metrics with normal distribution, stationary time series.

**Difference from MAD:**
- Assumes normal distribution (MAD doesn't)
- Less robust to outliers
- Faster computation

### Basic Usage

```yaml
detector:
  type: "zscore"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    seasonal_features:
      - name: "hour_of_day"
        expression: "toHour(now())"

storage:
  enabled: true
```

**Parameters same as MAD detector.**

**When to prefer Z-Score over MAD:**
- Data is normally distributed
- No significant outliers in history
- Need faster computation

**When to prefer MAD over Z-Score:**
- Data has outliers (common in real-world metrics)
- Unknown distribution
- More robust detection needed

## Multi-Detector A/B Testing

Test multiple detection strategies simultaneously:

```yaml
name: "sessions_ab_test"

collector:
  type: "clickhouse"
  params:
    query: "SELECT count() as value FROM sessions"

# Multiple detectors
detectors:
  # Conservative
  - type: "mad"
    params:
      window_size: "30 days"
      n_sigma: 5.0

  # Balanced
  - type: "mad"
    params:
      window_size: "30 days"
      n_sigma: 3.0

  # Aggressive
  - type: "mad"
    params:
      window_size: "7 days"
      n_sigma: 2.5

  # Alternative algorithm
  - type: "zscore"
    params:
      window_size: "30 days"
      n_sigma: 3.0

storage:
  enabled: true
  params:
    save_detections: true  # Save all detector results for comparison

alerter:
  type: "slack"
  params:
    webhook_url: "${SLACK_WEBHOOK}"
```

**Each detector gets a unique auto-generated ID** based on type + params.

**Query detector performance:**

```sql
SELECT
    detector_id,
    detector_type,
    detector_params,
    COUNT(*) as checks,
    SUM(is_anomaly) as anomalies
FROM dtk_detections
WHERE metric_name = 'sessions_ab_test'
  AND detected_at >= now() - INTERVAL 7 DAY
GROUP BY detector_id, detector_type, detector_params
ORDER BY anomalies DESC;
```

## Advanced: Prophet Detector

**Best for:** Complex seasonality (multiple patterns), trend detection, long-term forecasting.

### Installation

```bash
pip install detectk-detectors-timeseries[prophet]
```

### Usage

```yaml
detector:
  type: "prophet"
  params:
    window_size: "90 days"
    seasonality_mode: "multiplicative"
    yearly_seasonality: true
    weekly_seasonality: true
    daily_seasonality: false

storage:
  enabled: true
```

**Note:** Prophet is slower than MAD/Z-Score. Use for complex patterns only.

## Choosing the Right Detector

### Decision Matrix

| Metric Type | Recommended Detector | Parameters |
|-------------|---------------------|------------|
| Fixed threshold (SLA) | Threshold | `value`, `operator` |
| Stable metric, no patterns | MAD | `window_size: "30 days"`, `n_sigma: 3.0` |
| Hourly pattern (traffic) | MAD | Add `seasonal_features: hour_of_day` |
| Daily pattern (weekday/weekend) | MAD | Add `seasonal_features: day_of_week` |
| Both hourly + daily | MAD | Both features |
| Growing metric | MAD | `use_weighted: true` |
| Complex seasonality | Prophet | Multi-level seasonality |

### Tuning for Production

**Start conservative:**
1. Use `n_sigma: 4.0` or `5.0` initially
2. Monitor for 1-2 weeks
3. If missing real issues → decrease to 3.0
4. If too many false positives → increase back

**Iterate window size:**
1. Start with `window_size: "30 days"`
2. Too sensitive to recent changes? → Increase to 60-90 days
3. Missing recent pattern changes? → Decrease to 7-14 days

**Add seasonality gradually:**
1. Start without seasonal features
2. See false alerts at specific times? → Add hour_of_day
3. See weekday/weekend differences? → Add day_of_week

## Best Practices

### 1. Use Backtesting

Always test on historical data before deploying:

```bash
dtk backtest metric.yaml --start 2024-01-01 --end 2024-02-01
```

See [Backtesting Guide](backtesting.md) for details.

### 2. Start Simple

Begin with Threshold detector, graduate to MAD if needed:

```yaml
# Phase 1: Simple threshold
detector:
  type: "threshold"
  params: {value: 1000, operator: "less_than"}

# Phase 2: Statistical detection
detector:
  type: "mad"
  params: {window_size: "30 days", n_sigma: 3.0}

# Phase 3: Add seasonality
detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0
    seasonal_features:
      - {name: "hour_of_day", expression: "toHour(now())"}
```

### 3. Storage is Required

MAD, Z-Score, and Prophet need historical data:

```yaml
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"
```

### 4. Monitor Detector Performance

Save detection results for analysis:

```yaml
storage:
  params:
    save_detections: true
```

Query false positive rate:

```sql
SELECT
    metric_name,
    COUNT(*) as total_checks,
    SUM(is_anomaly) as anomalies_detected,
    SUM(is_anomaly) / COUNT(*) * 100 as anomaly_rate
FROM dtk_detections
WHERE detected_at >= now() - INTERVAL 30 DAY
GROUP BY metric_name;
```

## Troubleshooting

### "Storage required for detector type 'mad'"

Add storage configuration:

```yaml
storage:
  enabled: true
  type: "clickhouse"
  params:
    host: "localhost"
    port: 9000
    database: "analytics"
```

### "Insufficient data for window"

Detector needs more historical data. Either:
- Wait for data to accumulate
- Decrease `window_size`
- Decrease `min_window_size`

```yaml
detector:
  params:
    window_size: "7 days"  # Smaller window
    min_window_size: 50    # Fewer points required
```

### Too Many False Positives

**Solution 1: Increase n_sigma**
```yaml
params:
  n_sigma: 5.0  # Was 3.0
```

**Solution 2: Add seasonal features**
```yaml
params:
  seasonal_features:
    - name: "hour_of_day"
      expression: "toHour(now())"
```

**Solution 3: Increase window**
```yaml
params:
  window_size: "60 days"  # Was 30 days
```

### Missing Real Anomalies

**Solution 1: Decrease n_sigma**
```yaml
params:
  n_sigma: 2.5  # Was 3.0
```

**Solution 2: Use weighted statistics**
```yaml
params:
  use_weighted: true
```

**Solution 3: Decrease window (more reactive)**
```yaml
params:
  window_size: "14 days"  # Was 30 days
```

## Next Steps

- **[Backtesting Guide](backtesting.md)** - Test detectors on historical data
- **[Configuration Reference](configuration.md)** - Complete YAML schema
- **[Examples](../../examples/)** - Ready-to-use configurations
