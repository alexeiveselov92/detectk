# DetectK Configuration Examples

This directory contains ready-to-use configuration examples for DetectK.

## Directory Structure

```
examples/
├── threshold/          # Threshold detector examples
├── multi_detector/     # Multi-detector configurations (A/B testing)
├── mad/               # MAD detector examples (coming soon)
├── statistical/       # Statistical detectors (coming soon)
└── complete/          # Complete end-to-end examples (coming soon)
```

## Quick Start

1. Copy an example configuration
2. Set environment variables (see config comments)
3. Run the check:

```bash
dtk run examples/threshold/threshold_simple.yaml
```

## Threshold Detector Examples

### Simple Threshold (`threshold/threshold_simple.yaml`)

Basic threshold detection - alert when value exceeds a static threshold.

**Use case:** Alert when sessions > 1000

```yaml
detector:
  type: "threshold"
  params:
    threshold: 1000
    operator: "greater_than"
```

### Percentage-Based (`threshold/threshold_percentage.yaml`)

Detect anomalies based on percentage change from baseline.

**Use case:** Alert on 20%+ increase from expected baseline

```yaml
detector:
  type: "threshold"
  params:
    threshold: 20.0  # 20% increase
    operator: "greater_than"
    percent: true
    baseline: 1000
```

### Range Check (`threshold/threshold_range.yaml`)

Alert when value falls OUTSIDE expected range.

**Use case:** Sessions should be between 900-1100, alert otherwise

```yaml
detector:
  type: "threshold"
  params:
    threshold: 900
    upper_threshold: 1100
    operator: "outside"
```

## Multi-Detector Examples

### A/B Testing (`multi_detector/ab_testing.yaml`)

Compare multiple detection strategies on the same metric.

**Use case:** Test different threshold levels before committing to one

```yaml
detectors:
  - id: "threshold_high"
    type: "threshold"
    params:
      threshold: 1500

  - id: "threshold_medium"
    type: "threshold"
    params:
      threshold: 1200

  - id: "percent_20"
    type: "threshold"
    params:
      threshold: 20.0
      percent: true
      baseline: 1000
```

Query detector performance:

```sql
SELECT
    detector_id,
    COUNT(*) as total_checks,
    SUM(is_anomaly) as anomalies_detected
FROM dtk_detections
WHERE metric_name = 'your_metric'
GROUP BY detector_id;
```

## Environment Variables

Most examples use environment variables for sensitive data:

```bash
# ClickHouse connection
export CLICKHOUSE_HOST="localhost"

# Mattermost webhook
export MATTERMOST_WEBHOOK="https://mattermost.example.com/hooks/xxx"
```

## Running Examples

### Single execution

```bash
dtk run examples/threshold/threshold_simple.yaml
```

### Backtesting

```bash
dtk backtest examples/threshold/threshold_simple.yaml \
  --start "2024-01-01" \
  --end "2024-02-01" \
  --step "10 minutes"
```

### Validation only

```bash
dtk validate examples/threshold/threshold_simple.yaml
```

## Customizing Examples

1. Copy example to your configs directory
2. Update collector query for your database
3. Adjust detector parameters
4. Configure alerter (Mattermost, Slack, etc.)
5. Test with `dtk validate` before deploying

## Contributing Examples

When adding new examples:
1. Use environment variables for sensitive data
2. Add comments explaining use case
3. Include example output/results
4. Update this README
5. Test before committing

## See Also

- [Configuration Guide](../docs/guides/configuration.md)
- [Detector Reference](../docs/reference/detectors.md)
- [Collector Reference](../docs/reference/collectors.md)
