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

### 4. Custom Message Template (`custom_template.yaml`)

Customize alert messages using Jinja2 templates:
- Different language (Russian example)
- Include dashboard links
- Custom formatting
- Access all detection data

**Run:**
```bash
dtk run examples/mattermost/custom_template.yaml
```

**Template example:**
```yaml
alerter:
  params:
    message_template: |
      **АНОМАЛИЯ ОБНАРУЖЕНА: {{ metric_name }}**

      Текущее значение: {{ value | round(2) }}
      Ожидаемый диапазон: {{ lower_bound | round(2) }} - {{ upper_bound | round(2) }}

      Время: {{ timestamp.strftime('%d.%m.%Y %H:%M:%S') }}

      [Открыть дашборд](https://grafana.example.com/d/sessions)
```

---

### 5. Rich Format Template (`rich_format.yaml`)

Visually rich alerts with emojis and icons:
- Eye-catching format with emojis
- Visual hierarchy
- Good for Mattermost/Slack
- **Note:** Not accessible, doesn't work in plain text

**Example output:**
```
🚨 **ANOMALY DETECTED** `sessions_10min`

📊 **Value:** 1,500.00 (↗ up)
📈 **Expected range:** 900.00 - 1100.00
📉 **Score:** 4.2 sigma

🕒 **Time:** 2024-11-02 14:30:00
```

**When to use:**
- You prioritize visual appeal over accessibility
- Alerts only go to Mattermost/Slack (not email/SMS)
- Team prefers colorful notifications

---

### 6. Minimal Template (`minimal_template.yaml`)

Brief one-line alerts for high-frequency metrics:
- Compact format
- Essential info only
- Good for frequent checks (latency, API metrics)

**Example output:**
```
**api_latency_minimal**: 150.5ms (expected: 80-120ms, up) @ 14:30:45
```

---

### 7. Conditional Template (`conditional_template.yaml`)

Different format based on severity or detector type:
- Severity-based icons (🔴 critical, 🟠 high, 🟡 moderate)
- Conditional @channel mentions
- Different format for different detectors
- Dynamic dashboard links

**Run:**
```bash
dtk run examples/mattermost/conditional_template.yaml
```

**Use case:** Severity indicators (emojis used meaningfully)

---

## Alert Message Format

### Default Format (No Custom Template)

**Philosophy:** Simple, professional, universal.
- ✅ No emojis - works everywhere (Mattermost, Slack, email, SMS, logs)
- ✅ Accessible to screen readers
- ✅ Professional appearance for corporate environments
- ✅ Plain text with minimal Markdown

**Default alert includes:**
- Metric name and timestamp
- Current value
- Expected range (if available from detector)
- Anomaly score (statistical significance)
- Direction (up/down)
- Percent deviation
- Detector metadata (for debugging)

**Example:**
```
**ANOMALY DETECTED: sessions_10min**

Value: 1500.00
Expected range: 900.00 - 1100.00
Anomaly score: 4.20 sigma
Direction: up
Deviation: +36.4%

Time: 2024-11-02 14:30:00
Detector: type=mad, window=30 days, threshold=3.0 sigma
```

**Want emojis?** See `rich_format.yaml` example for visually rich formatting.

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

## Custom Message Templates

### Why Customize?

The default format is intentionally simple and universal (no emojis, plain text).
Customize alerts for your team's specific needs:

- **Different language** (Russian, German, Spanish, etc.)
- **Team preferences** (minimal vs detailed, with/without emojis)
- **Dashboard links** (Grafana, Kibana, custom tools)
- **Severity-based formatting** (critical, high, moderate)
- **Context-specific info** (on-call mentions, runbooks)
- **Visual richness** (emojis, colors) if accessibility isn't a concern

### Available Template Variables

All DetectionResult fields accessible in template:

| Variable | Type | Description | Example |
|----------|------|-------------|---------|
| `metric_name` | string | Metric name | `"sessions_hourly"` |
| `timestamp` | datetime | Detection time | `datetime(2024, 11, 2, 14, 30)` |
| `value` | float | Current value | `1500.0` |
| `is_anomaly` | bool | Anomaly status | `True` |
| `score` | float \| None | Anomaly score (sigma) | `4.2` |
| `lower_bound` | float \| None | Expected min | `900.0` |
| `upper_bound` | float \| None | Expected max | `1100.0` |
| `direction` | str \| None | Direction | `"up"` / `"down"` / `None` |
| `percent_deviation` | float \| None | % deviation | `36.4` |
| `metadata` | dict | Detector info & custom | `{"detector": "mad", ...}` |

### Jinja2 Filters

Use built-in Jinja2 filters:

```yaml
{{ value | round(2) }}                    # Round to 2 decimals: 1234.56
{{ timestamp.strftime('%d.%m.%Y') }}      # Format date: 02.11.2024
{{ percent_deviation | abs | round(1) }}  # Absolute, rounded: 36.4
```

### Template Examples

**Russian language (no emojis):**
```yaml
message_template: |
  **АНОМАЛИЯ ОБНАРУЖЕНА: {{ metric_name }}**
  Текущее значение: {{ value | round(2) }}
  Ожидаемый диапазон: {{ lower_bound | round(2) }} - {{ upper_bound | round(2) }}
  Время: {{ timestamp.strftime('%d.%m.%Y %H:%M') }}
```

**Minimal one-liner:**
```yaml
message_template: |
  **{{ metric_name }}**: {{ value | round(1) }} ({{ direction }}) @ {{ timestamp.strftime('%H:%M') }}
```

**With dashboard links:**
```yaml
message_template: |
  **ANOMALY: {{ metric_name }}**

  Value: {{ value | round(2) }}
  Expected: {{ lower_bound | round(2) }} - {{ upper_bound | round(2) }}

  [Grafana Dashboard](https://grafana.example.com/d/{{ metric_name }})
  [View Logs](https://kibana.example.com/?q={{ metric_name }})
```

**Rich format with emojis:**
```yaml
message_template: |
  🚨 **ANOMALY DETECTED** `{{ metric_name }}`

  📊 Value: {{ value | round(2) }} ({% if direction == 'up' %}↗{% else %}↘{% endif %} {{ direction }})
  📈 Expected: {{ lower_bound | round(2) }} - {{ upper_bound | round(2) }}
  🕒 Time: {{ timestamp.strftime('%H:%M:%S') }}
```

**Severity-based (meaningful emoji use):**
```yaml
message_template: |
  {% if score >= 5.0 %}
  🔴 **CRITICAL** `{{ metric_name }}` @channel
  {% elif score >= 4.0 %}
  🟠 **HIGH** `{{ metric_name }}`
  {% else %}
  🟡 **MODERATE** `{{ metric_name }}`
  {% endif %}

  {{ value | round(2) }} ({{ score | round(1) }} sigma)
```

**Conditional detector info:**
```yaml
message_template: |
  🚨 **ANOMALY** `{{ metric_name }}`

  Value: {{ value | round(2) }}

  {% if metadata.detector == 'threshold' %}
  Threshold: {{ metadata.threshold }}
  {% elif metadata.detector == 'mad' %}
  Window: {{ metadata.window_size }}, n_sigma: {{ metadata.n_sigma }}
  {% endif %}
```

### Testing Templates

1. Create config with custom template
2. Validate: `dtk validate my_config.yaml`
3. If validation passes, template syntax is correct
4. Test with real data: `dtk run my_config.yaml`

### Template Errors

If template has errors:
- Validation will fail with error message
- Runtime errors fall back to default format
- Check logs for template rendering errors

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
