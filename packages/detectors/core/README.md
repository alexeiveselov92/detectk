# detectk-detectors

Core detectors for DetectK: threshold-based, statistical (MAD, Z-score, IQR).

## Installation

```bash
pip install detectk-detectors
```

## Detectors

### ThresholdDetector

Simple but powerful detector that compares metric values against static thresholds.

**Features:**
- Multiple comparison operators
- Absolute and percentage-based thresholds
- Range checks (between/outside)
- Auto-registration in DetectorRegistry

**Operators:**
- `greater_than`: value > threshold
- `greater_equal`: value >= threshold
- `less_than`: value < threshold
- `less_equal`: value <= threshold
- `equals`: value == threshold (with tolerance)
- `not_equals`: value != threshold (with tolerance)
- `between`: threshold <= value <= upper_threshold (anomaly if INSIDE range)
- `outside`: value < threshold OR value > upper_threshold (anomaly if OUTSIDE range)

## Usage Examples

### Simple Threshold (absolute value)

```yaml
# config.yaml
name: "sessions_10min"

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

detector:
  type: "threshold"
  params:
    threshold: 1000
    operator: "greater_than"  # Alert if > 1000

alerter:
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
```

### Percentage Change Detection

Detect anomalies based on percentage change from baseline:

```yaml
detector:
  type: "threshold"
  params:
    threshold: 10.0  # 10% increase
    operator: "greater_than"
    percent: true
    baseline: 1000  # Baseline value
```

**Example:** If sessions jump from 1000 to 1150 (15% increase), anomaly is detected.

### Range Check (outside bounds)

Alert if value falls outside expected range:

```yaml
detector:
  type: "threshold"
  params:
    threshold: 900        # Lower bound
    upper_threshold: 1100 # Upper bound
    operator: "outside"   # Anomaly if < 900 OR > 1100
```

### Range Check (inside bounds)

Alert if value is INSIDE a specific range (opposite of `outside`):

```yaml
detector:
  type: "threshold"
  params:
    threshold: 900
    upper_threshold: 1100
    operator: "between"  # Anomaly if 900 <= value <= 1100
```

**Use case:** Detect when metric is in a "bad" range (e.g., error rate between 5-10%).

### Decrease Detection

Alert on significant decreases:

```yaml
detector:
  type: "threshold"
  params:
    threshold: 800
    operator: "less_than"  # Alert if < 800
```

Or with percentage:

```yaml
detector:
  type: "threshold"
  params:
    threshold: -10.0  # 10% decrease
    operator: "less_than"
    percent: true
    baseline: 1000
```

### Equals Detection (with tolerance)

Alert when value equals specific number (useful for zero-value detection):

```yaml
detector:
  type: "threshold"
  params:
    threshold: 0
    operator: "equals"
    tolerance: 0.1  # Within ±0.1
```

### Multiple Detectors (A/B Testing)

Compare different threshold strategies:

```yaml
detectors:
  # Conservative (fewer false positives)
  - id: "threshold_high"
    type: "threshold"
    params:
      threshold: 1500
      operator: "greater_than"

  # Aggressive (catch more anomalies)
  - id: "threshold_medium"
    type: "threshold"
    params:
      threshold: 1200
      operator: "greater_than"

  # Percentage-based
  - id: "percent_20"
    type: "threshold"
    params:
      threshold: 20.0
      operator: "greater_than"
      percent: true
      baseline: 1000
```

## Configuration Parameters

### Required

- `threshold` (float): Threshold value (or lower bound for range operators)

### Optional

- `operator` (str): Comparison operator (default: `"greater_than"`)
  - Options: `"greater_than"`, `"greater_equal"`, `"less_than"`, `"less_equal"`, `"equals"`, `"not_equals"`, `"between"`, `"outside"`

- `upper_threshold` (float): Upper bound for `between`/`outside` operators (required for these operators)

- `percent` (bool): If true, threshold is percentage change from baseline (default: `false`)

- `baseline` (float): Baseline value for percentage calculation (required if `percent=true`)

- `tolerance` (float): Tolerance for `equals`/`not_equals` operators (default: `0.001`)

## Detection Result

ThresholdDetector returns `DetectionResult` with:

- `is_anomaly` (bool): Whether value violates threshold
- `score` (float): Distance from threshold (higher = more anomalous)
- `lower_bound` / `upper_bound` (float | None): Expected bounds for visualization
- `direction` (str | None): `"up"`, `"down"`, or `None`
- `percent_deviation` (float | None): Percentage deviation from threshold (if anomaly)
- `metadata` (dict): Detector configuration and comparison details

## Edge Cases

### Zero Threshold

```yaml
detector:
  type: "threshold"
  params:
    threshold: 0
    operator: "greater_than"
```

Works correctly: any positive value triggers anomaly.

### Negative Values

```yaml
detector:
  type: "threshold"
  params:
    threshold: -100
    operator: "less_than"
```

Works correctly: `-150 < -100` → anomaly.

### Zero Baseline (percentage mode)

❌ Not allowed - raises `ConfigurationError`:

```yaml
detector:
  type: "threshold"
  params:
    threshold: 10
    percent: true
    baseline: 0  # ERROR: Division by zero
```

## Testing

```bash
cd packages/detectors/core
pytest tests/ -v
```

All 23 tests passing ✅

## License

MIT
