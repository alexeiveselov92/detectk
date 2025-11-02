# Seasonal Anomaly Detection Examples

This directory contains comprehensive examples of seasonal anomaly detection in DetectK.

## What is Seasonality?

Seasonality refers to predictable patterns that repeat over time. In metric monitoring, different times may have different "normal" baselines:

- **Hour of day:** Traffic at 2 AM vs 2 PM
- **Day of week:** Weekday vs weekend patterns
- **Custom cycles:** Game leagues, promotional campaigns, billing cycles

Without seasonality, comparing current 2 AM traffic (low) to overall average (higher) would trigger false alarms.

## Two Seasonality Modes

DetectK supports two modes of seasonal grouping:

### 1. Combined Seasonality (Intersection, AND)

**`use_combined_seasonality: true`**

Compares current point only with historical points that match **ALL** seasonal features simultaneously.

**Example:**
- Current: Monday 14:00
- Historical group: Only other Monday 14:00 points
- Precise matching, smaller group

**When to use:**
- Seasonal factors are tightly coupled
- Monday 9 AM is very different from Saturday 9 AM
- Have long historical window (30+ days)
- Need precise seasonal matching

**Examples:** User sessions, revenue, game activity

### 2. Separate Seasonality (Union, OR)

**`use_combined_seasonality: false`**

Compares current point with historical points that match **ANY** of the seasonal features.

**Example:**
- Current: Monday 14:00
- Historical group: All Mondays (any hour) OR all 14:00 (any day)
- More data, less precise matching

**When to use:**
- Seasonal factors are somewhat independent
- Need more data for reliable statistics
- Short historical window available
- Metric behavior driven by single dominant factor

**Examples:** Error rates, API latency, queue lengths

## Examples in This Directory

### 1. `sessions_hourly_dow.yaml`

**Use Case:** User sessions with combined hour + day-of-week seasonality

**Features:**
- Combined mode: Monday 9 AM vs Monday 9 AM
- 30-day window for sufficient data per group
- Weighted statistics with exponential decay
- Comprehensive documentation

**Run:**
```bash
dtk run examples/seasonal/sessions_hourly_dow.yaml
```

### 2. `game_league_cycle.yaml`

**Use Case:** Game revenue with 14-day league cycle

**Features:**
- Custom `league_day` feature (0-13) using modulo arithmetic
- Captures recurring patterns that don't align with calendar
- League day 0 (start) vs day 13 (finale) have different baselines
- 84-day window (6 complete cycles)

**Run:**
```bash
dtk run examples/seasonal/game_league_cycle.yaml
```

### 3. `api_errors_separate.yaml`

**Use Case:** API error rate with separate (union) seasonality

**Features:**
- Separate mode: Hour OR day-of-week
- More data for statistics
- Shorter window possible (14 days)
- Good for metrics with independent seasonal factors

**Run:**
```bash
dtk run examples/seasonal/api_errors_separate.yaml
```

## How Seasonality Works in DetectK

### Full Pipeline

```
1. Collector: Extract seasonal features from SQL query
   ↓
2. Storage: Save with context as JSON
   ↓
3. Detector: Load historical window + current context
   ↓
4. Filter: Group by seasonal features (AND or OR)
   ↓
5. Calculate: Median + MAD only for filtered group
   ↓
6. Detect: Check if current value outside bounds
   ↓
7. Alert: Send notification if anomaly detected
```

### Configuration Example

```yaml
collector:
  type: "clickhouse"
  params:
    query: |
      SELECT
        toStartOfInterval(timestamp, INTERVAL 10 minute) AS period_time,
        count() AS value,
        toHour(period_time) AS hour_of_day,        # <- Seasonal feature
        toDayOfWeek(period_time) AS day_of_week   # <- Seasonal feature
      FROM events
      WHERE timestamp >= '{{ period_start }}'
        AND timestamp < '{{ period_finish }}'
      GROUP BY period_time
      ORDER BY period_time

    context_columns: ["hour_of_day", "day_of_week"]  # <- Extract these

detector:
  type: "mad"
  params:
    window_size: "30 days"
    seasonal_features: ["hour_of_day", "day_of_week"]  # <- Use for grouping
    use_combined_seasonality: true  # <- AND (intersection) mode
```

## Custom Seasonal Features

You can create any seasonal feature using SQL expressions:

### Examples

```sql
-- Hour of day (0-23)
toHour(period_time) AS hour_of_day

-- Day of week (1=Monday, 7=Sunday)
toDayOfWeek(period_time) AS day_of_week

-- Day of month (1-31)
toDayOfMonth(period_time) AS day_of_month

-- Week of year (1-53)
toWeek(period_time) AS week_of_year

-- Is weekend (0 or 1)
if(toDayOfWeek(period_time) IN (6, 7), 1, 0) AS is_weekend

-- Is business hours (0 or 1)
if(toHour(period_time) BETWEEN 9 AND 17, 1, 0) AS is_business_hours

-- League day (14-day cycle)
dateDiff('day', toDate('2024-01-01'), period_time) % 14 AS league_day

-- Billing cycle day (30-day cycle)
dateDiff('day', toDate('2024-01-01'), period_time) % 30 AS billing_day

-- Quarter of year (1-4)
toQuarter(period_time) AS quarter

-- Is holiday (requires holiday table)
if(period_time IN (SELECT date FROM holidays), 1, 0) AS is_holiday

-- Promotional campaign day (7-day campaign)
if(dateDiff('day', toDate('2024-03-01'), period_time) BETWEEN 0 AND 6, 1, 0) AS is_promo
```

## Choosing the Right Approach

### Decision Tree

```
Do seasonal factors change behavior independently?
├─ YES → Use Separate mode (union, OR)
│         Example: Error rate affected by hour OR day but not specific combo
│
└─ NO → Do you have 30+ days of history?
         ├─ YES → Use Combined mode (intersection, AND)
         │         Example: User sessions very different by hour+day combo
         │
         └─ NO → Use Separate mode or wait for more data
                   Combined needs enough points in each specific group
```

### Window Size Guidelines

| Mode | Seasonal Features | Minimum Window | Recommended |
|------|------------------|----------------|-------------|
| Combined | 1 feature | 7-14 days | 30 days |
| Combined | 2 features | 14-30 days | 60 days |
| Combined | 3+ features | 30-60 days | 90 days |
| Separate | Any | 7 days | 14-30 days |

**Why:** Combined mode creates smaller groups, needs more history to have enough points per group.

## Testing Your Configuration

### 1. Validate Configuration

```bash
dtk validate examples/seasonal/your_config.yaml
```

### 2. Test with Historical Data

```yaml
# In your config
schedule:
  start_time: "2024-01-01"
  end_time: "2024-03-01"
  interval: "10 minutes"

alerter:
  enabled: false  # Don't spam during testing
```

Run:
```bash
dtk run examples/seasonal/your_config.yaml
```

### 3. Check Detection Quality

After running historical test:

```sql
-- Query detection results
SELECT
    detected_at,
    value,
    is_anomaly,
    anomaly_score,
    lower_bound,
    upper_bound,
    metadata
FROM metrics.dtk_detections
WHERE metric_name = 'your_metric'
ORDER BY detected_at DESC
LIMIT 100;
```

Look for:
- ✓ Known incidents detected as anomalies
- ✗ Normal periods flagged as anomalies (false positives)
- Adjust `n_sigma` if needed (higher = fewer alerts, lower = more sensitive)

### 4. Compare Modes

Try both modes and measure:

```python
# Pseudo-code
false_positive_rate = anomalies_during_normal_periods / total_normal_periods
detection_rate = known_incidents_detected / total_known_incidents

# Choose mode with:
# - Lower false positive rate
# - Higher detection rate
# - Balance depends on your tolerance
```

## Troubleshooting

### Error: "No historical data found for seasonal group"

**Cause:** Combined mode with insufficient history

**Solutions:**
1. Increase `window_size` to get more data
2. Switch to Separate mode (`use_combined_seasonality: false`)
3. Wait to accumulate more historical data
4. Reduce number of seasonal features

### Error: "Insufficient data in seasonal group: 2 points (minimum 3 required)"

**Cause:** Specific seasonal group has too few matching points

**Solutions:**
1. Use longer `window_size`
2. Use Separate mode for more data
3. Remove less important seasonal features
4. Check if seasonal feature values are correct

### False Positives (Too Many Alerts)

**Causes:**
- `n_sigma` too low (too sensitive)
- Wrong seasonality mode
- Missing important seasonal features

**Solutions:**
1. Increase `n_sigma` (3.0 → 3.5 → 4.0)
2. Add more seasonal features (Combined mode)
3. Try opposite mode (Combined ↔ Separate)
4. Increase `cooldown_minutes`

### False Negatives (Missed Incidents)

**Causes:**
- `n_sigma` too high (not sensitive enough)
- Wrong seasonal grouping
- Too much historical noise

**Solutions:**
1. Decrease `n_sigma` (3.0 → 2.5 → 2.0)
2. Review seasonal features
3. Use weighted statistics (`use_weighted: true`)
4. Increase `exp_decay_factor` (0.1 → 0.2)

## Best Practices

1. **Start Simple:**
   - Begin with 1-2 obvious seasonal features
   - Use Combined mode if clear coupling exists
   - Add features incrementally

2. **Test Thoroughly:**
   - Run historical backtest first
   - Review detection quality
   - Adjust parameters based on results

3. **Document Assumptions:**
   - Why these seasonal features?
   - Why this mode (Combined/Separate)?
   - What patterns are you expecting?

4. **Monitor Performance:**
   - Track false positive rate
   - Track detection latency
   - Adjust as metric behavior changes

5. **Version Control:**
   - Keep configs in git
   - Document parameter changes
   - Track tuning history

## Additional Resources

- **Core Documentation:** See `ARCHITECTURE.md` for technical details
- **Detector Docs:** `packages/detectors/core/README.md`
- **MAD Algorithm:** Wikipedia - Median Absolute Deviation
- **Other Examples:** `examples/mad/` for non-seasonal examples

## Questions?

- Check documentation: `docs/`
- Review tests: `packages/detectors/core/tests/test_mad.py`
- GitHub Issues: https://github.com/alexeiveselov92/detectk/issues

---

**Note:** All examples use environment variables for sensitive data (passwords, webhooks). Set these before running:

```bash
export CLICKHOUSE_HOST="your_host"
export CLICKHOUSE_PASSWORD="your_password"
export MATTERMOST_WEBHOOK="your_webhook_url"
export SLACK_WEBHOOK="your_slack_webhook"
```
