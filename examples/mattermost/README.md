# Mattermost Alerting Examples

Examples of using DetectK with Mattermost for anomaly alerts.

## Prerequisites

1. **ClickHouse database** with your metrics data
2. **Mattermost incoming webhook**:
   - Go to Mattermost → Integrations → Incoming Webhooks
   - Create new webhook, copy URL
   - Set as environment variable: `export MATTERMOST_WEBHOOK="https://your-mattermost.com/hooks/xxx"`

3. **Environment variables**:
```bash
export CLICKHOUSE_HOST="localhost"
export MATTERMOST_WEBHOOK="https://your-mattermost.com/hooks/xxx"
```

## Examples

### 1. Simple Alert (`simple_alert.yaml`)

Basic anomaly detection with Mattermost notifications:
- Monitors sessions count every 10 minutes
- Uses MAD detector with 30-day window
- Sends alert when value is 3 sigma away from median
- 60-minute cooldown to prevent spam

**Run:**
```bash
dtk run examples/mattermost/simple_alert.yaml
```

**Customize:**
- Change `window_size` for more/less history
- Change `n_sigma` for sensitivity (lower = more alerts)
- Change `cooldown_minutes` for alert frequency

---

### 2. Seasonal Alert (`seasonal_alert.yaml`)

Anomaly detection accounting for seasonal patterns:
- Monitors hourly revenue
- Groups by hour-of-day and day-of-week
- Compares current value to historical values at same time
- Example: Monday 3pm compared to other Monday 3pm values

**Run:**
```bash
dtk run examples/mattermost/seasonal_alert.yaml
```

**When to use:**
- Metrics with daily patterns (higher during business hours)
- Metrics with weekly patterns (weekday vs weekend)
- Metrics with custom business cycles (e.g., league/season days)

**Customize:**
- Add custom seasonal features:
  ```yaml
  seasonal_features:
    - name: "is_weekend"
      expression: "toDayOfWeek(collected_at) IN (6, 7)"
    - name: "league_day"
      expression: "dateDiff('day', '2024-01-01', collected_at) % 14"
  ```

---

### 3. Multi-Detector Alert (`multi_detector_alert.yaml`)

A/B testing multiple detection strategies:
- Uses 3 detectors on same metric:
  - Conservative MAD (n_sigma=5.0) - fewer false positives
  - Aggressive MAD (n_sigma=3.0) - catch more anomalies
  - Z-Score (7-day window) - faster adaptation
- Saves all detection results for comparison
- Alert sent if ANY detector finds anomaly

**Run:**
```bash
dtk run examples/mattermost/multi_detector_alert.yaml
```

**Query detector performance:**
```sql
SELECT
    detector_id,
    detector_type,
    detector_params,
    COUNT(*) as total_checks,
    SUM(is_anomaly) as anomalies_detected,
    AVG(anomaly_score) as avg_score
FROM dtk_detections
WHERE metric_name = 'active_users_5min'
  AND detected_at >= now() - INTERVAL 7 DAY
GROUP BY detector_id, detector_type, detector_params
ORDER BY anomalies_detected DESC;
```

**Use case:**
- Test detection strategies before production
- Compare algorithm performance (MAD vs Z-Score)
- Tune parameters (n_sigma, window_size) based on data

---

## Alert Message Format

Mattermost alerts include:
- Metric name and timestamp
- Current value and direction (up/down)
- Expected bounds (if available)
- Anomaly score (sigma)
- Percent deviation
- Detector metadata (algorithm, parameters)

**Example:**
```
🚨 **ANOMALY DETECTED** `sessions_10min`

📊 **Value:** 1,500.00 (↗ up)
📈 **Expected:** [900.00 - 1,100.00]
📉 **Score:** 4.2 sigma
⚠️ **Deviation:** +36.4%

🕒 2024-11-01 23:50:00
🔍 **Detector:** mad, window: 30 days, n_sigma: 3.0
```

---

## Configuration Options

### Mattermost Alerter Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `webhook_url` | string | **required** | Mattermost incoming webhook URL |
| `cooldown_minutes` | int | 60 | Minutes to wait between alerts for same metric |
| `username` | string | "DetectK" | Bot username displayed in Mattermost |
| `icon_url` | string | None | Bot icon URL (optional) |
| `channel` | string | None | Channel override (optional, uses webhook default) |
| `timeout` | int | 10 | HTTP request timeout in seconds |

### Cooldown Behavior

Cooldown prevents alert spam:
- **First anomaly**: Alert sent immediately
- **Subsequent anomalies** (within cooldown): Skipped
- **After cooldown expires**: Alert sent again

**Example with cooldown_minutes=60:**
- 10:00 - Anomaly detected → Alert sent ✅
- 10:30 - Anomaly detected → Skipped (in cooldown) ⏭️
- 10:45 - Anomaly detected → Skipped (in cooldown) ⏭️
- 11:15 - Anomaly detected → Alert sent ✅ (cooldown expired)

**Set cooldown_minutes=0** to disable (send every anomaly - not recommended).

---

## Best Practices

1. **Start conservative** (high n_sigma) to avoid alert fatigue
2. **Use seasonal features** for metrics with daily/weekly patterns
3. **Set appropriate cooldown** based on metric frequency:
   - High-frequency metrics (every 5-10 min): 60+ minutes
   - Hourly metrics: 2-4 hours
   - Daily metrics: 24+ hours
4. **Test with backtesting** before production (see backtesting examples)
5. **Monitor detector performance** with multi-detector approach
6. **Adjust gradually** - tune one parameter at a time

---

## Troubleshooting

### No alerts sent

1. **Check if anomalies detected:**
   ```sql
   SELECT * FROM dtk_detections
   WHERE metric_name = 'your_metric'
   ORDER BY detected_at DESC
   LIMIT 10;
   ```

2. **Check detector sensitivity:**
   - Lower `n_sigma` for more alerts (e.g., 3.0 → 2.5)
   - Shorter `window_size` for faster adaptation
   - Check if using appropriate detector (seasonal features?)

3. **Check cooldown:**
   - Query `dtk_detections` for `alert_sent` column
   - Reduce `cooldown_minutes` for testing

### Too many alerts (false positives)

1. **Increase detector threshold:**
   - Higher `n_sigma` (e.g., 3.0 → 4.0 or 5.0)
   - Longer `window_size` (more historical context)

2. **Add seasonal features:**
   - Metrics with daily patterns need `hour_of_day`
   - Metrics with weekly patterns need `day_of_week`

3. **Increase cooldown:**
   - Higher `cooldown_minutes` (fewer notifications)

4. **Use MAD instead of Z-Score:**
   - MAD is more robust to outliers
   - Z-Score can be sensitive to extreme historical values

---

## See Also

- [MAD Detector Examples](../mad/) - More MAD detector configurations
- [Multi-Detector Examples](../multi_detector/) - A/B testing strategies
- [Backtesting Guide](../../docs/guides/backtesting.md) - Test before deployment
