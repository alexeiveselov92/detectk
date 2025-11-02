# Tags Examples

This directory demonstrates how to use tags for organizing and filtering metrics in DetectK.

## What are Tags?

Tags are labels you can attach to metrics to:
- **Group related metrics** (e.g., all revenue metrics, all API metrics)
- **Filter by priority** (e.g., only run critical metrics)
- **Separate environments** (e.g., production vs experimental)
- **Schedule different intervals** (e.g., hourly vs daily metrics)

Tags are especially useful when using orchestrators like Prefect or Airflow, or when running metrics in batches with `dtk run-tagged`.

---

## Configuration Example

Add tags to your metric configuration:

```yaml
name: "revenue_hourly"
description: "Monitor hourly revenue"

# Tags for filtering and grouping
tags:
  - "critical"      # High priority metrics
  - "revenue"       # Revenue-related metrics
  - "hourly"        # Hourly check interval
  - "business"      # Business KPIs

collector:
  type: "clickhouse"
  # ...
```

---

## CLI Commands

### List Metrics with Tags

```bash
# Show all metrics with their tags
dtk list-metrics --details

# Filter by single tag
dtk list-metrics --tags critical

# Filter by multiple tags (OR logic - match ANY)
dtk list-metrics --tags revenue --tags api

# Filter by multiple tags (AND logic - match ALL)
dtk list-metrics --tags critical --tags hourly --match-all-tags
```

### Run Metrics by Tags

```bash
# Run all critical metrics
dtk run-tagged --tags critical

# Run revenue OR api metrics
dtk run-tagged --tags revenue --tags api

# Run metrics with BOTH 'hourly' AND 'critical' tags
dtk run-tagged --tags hourly --tags critical --match-all

# Run all except experimental metrics
dtk run-tagged --exclude-tags experimental

# Dry run (see what would execute without running)
dtk run-tagged --tags critical --dry-run

# Run in parallel (experimental)
dtk run-tagged --tags critical --parallel
```

---

## Common Tagging Strategies

### 1. By Priority

```yaml
tags: ["critical"]  # P0 - must run always
tags: ["important"] # P1 - run in production
tags: ["optional"]  # P2 - run when resources available
tags: ["experimental"]  # P3 - testing only
```

**Use case:** Run only critical metrics during incidents.

```bash
# Emergency mode - only critical metrics
dtk run-tagged --tags critical
```

### 2. By Interval

```yaml
tags: ["realtime"]   # 1-10 minute intervals
tags: ["hourly"]     # 1 hour intervals
tags: ["daily"]      # 1 day intervals
tags: ["weekly"]     # 1 week intervals
```

**Use case:** Schedule different intervals in Airflow/Prefect.

```python
# Airflow DAG
from airflow import DAG
from airflow.operators.bash import BashOperator

# Hourly DAG
with DAG("detectk_hourly", schedule_interval="@hourly") as dag:
    BashOperator(
        task_id="run_hourly_metrics",
        bash_command="dtk run-tagged --tags hourly"
    )

# Daily DAG
with DAG("detectk_daily", schedule_interval="@daily") as dag:
    BashOperator(
        task_id="run_daily_metrics",
        bash_command="dtk run-tagged --tags daily"
    )
```

### 3. By Domain

```yaml
tags: ["revenue", "business"]    # Finance metrics
tags: ["api", "infrastructure"]  # Platform metrics
tags: ["sessions", "product"]    # Product metrics
tags: ["errors", "monitoring"]   # Observability
```

**Use case:** Different teams own different metric groups.

```bash
# Finance team runs their metrics
dtk run-tagged --tags revenue --tags business

# Platform team runs their metrics
dtk run-tagged --tags api --tags infrastructure
```

### 4. By Environment

```yaml
tags: ["production"]     # Deployed to prod
tags: ["staging"]        # Staging only
tags: ["experimental"]   # Under development
```

**Use case:** Separate production from experimental metrics.

```bash
# Production scheduler (cron)
*/10 * * * * dtk run-tagged --tags production --exclude-tags experimental

# Development environment
dtk run-tagged --tags staging --tags experimental
```

### 5. Combined Strategy (Recommended)

Use multiple tag dimensions:

```yaml
# Critical revenue metric, runs hourly, owned by finance
tags: ["critical", "revenue", "hourly", "business"]

# Experimental API metric, runs every 5 min, owned by platform
tags: ["experimental", "api", "realtime", "infrastructure"]

# Important product metric, runs every 10 min
tags: ["important", "sessions", "realtime", "product"]
```

**Use case:** Flexible filtering for different scenarios.

```bash
# Run all critical metrics regardless of domain
dtk run-tagged --tags critical

# Run all hourly business metrics
dtk run-tagged --tags hourly --tags business --match-all

# Run realtime metrics except experimental ones
dtk run-tagged --tags realtime --exclude-tags experimental
```

---

## Examples in This Directory

| File | Tags | Description |
|------|------|-------------|
| `revenue_hourly.yaml` | `critical`, `revenue`, `hourly`, `business` | Critical revenue monitoring |
| `api_errors_5min.yaml` | `critical`, `api`, `errors`, `realtime` | API error rate monitoring |
| `sessions_10min.yaml` | `sessions`, `realtime`, `product` | User sessions monitoring |
| `experimental_metric.yaml` | `experimental`, `conversion`, `testing` | Under development |

---

## Orchestrator Integration Examples

### Prefect

```python
from prefect import flow, task
from detectk.check import MetricCheck
from detectk.config import ConfigLoader
from pathlib import Path

@task
def run_metric(config_path: str):
    """Run single metric check."""
    checker = MetricCheck()
    return checker.execute(config_path)

@flow
def run_tagged_metrics(tags: list[str], match_all: bool = False):
    """Run all metrics matching tags."""
    loader = ConfigLoader()
    configs_dir = Path("configs")

    # Find matching configs
    matched = []
    for yaml_file in configs_dir.rglob("*.yaml"):
        try:
            config = loader.load(str(yaml_file))
            metric_tags = set(config.tags) if config.tags else set()
            required_tags = set(tags)

            if match_all:
                if required_tags.issubset(metric_tags):
                    matched.append(yaml_file)
            else:
                if required_tags & metric_tags:
                    matched.append(yaml_file)
        except Exception:
            continue

    # Run in parallel
    results = run_metric.map(matched)
    return results

# Schedule flows
from prefect.deployments import Deployment
from prefect.server.schemas.schedules import CronSchedule

# Hourly critical metrics
Deployment.build_from_flow(
    flow=run_tagged_metrics,
    name="detectk-hourly-critical",
    parameters={"tags": ["hourly", "critical"], "match_all": True},
    schedule=CronSchedule(cron="0 * * * *"),  # Every hour
)

# Every 5 minutes - realtime metrics
Deployment.build_from_flow(
    flow=run_tagged_metrics,
    name="detectk-realtime",
    parameters={"tags": ["realtime"]},
    schedule=CronSchedule(cron="*/5 * * * *"),  # Every 5 minutes
)
```

### Airflow

```python
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    "owner": "data-team",
    "depends_on_past": False,
    "start_date": datetime(2024, 11, 1),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# Critical metrics - every 10 minutes
with DAG(
    "detectk_critical_realtime",
    default_args=default_args,
    schedule_interval="*/10 * * * *",
    catchup=False,
) as dag:
    run_critical = BashOperator(
        task_id="run_critical_realtime",
        bash_command="dtk run-tagged --tags critical --tags realtime --match-all",
    )

# Business metrics - hourly
with DAG(
    "detectk_business_hourly",
    default_args=default_args,
    schedule_interval="@hourly",
    catchup=False,
) as dag:
    run_business = BashOperator(
        task_id="run_business_hourly",
        bash_command="dtk run-tagged --tags hourly --tags business --match-all",
    )

# Daily aggregates
with DAG(
    "detectk_daily",
    default_args=default_args,
    schedule_interval="@daily",
    catchup=False,
) as dag:
    run_daily = BashOperator(
        task_id="run_daily_metrics",
        bash_command="dtk run-tagged --tags daily --exclude-tags experimental",
    )
```

---

## Best Practices

1. **Use consistent tag names:**
   - Choose a standard vocabulary (critical/important/optional)
   - Document tag meanings in your project README

2. **Multiple dimensions:**
   - Combine priority + domain + interval tags
   - Example: `["critical", "revenue", "hourly"]`

3. **Avoid too many tags:**
   - 3-5 tags per metric is optimal
   - More tags = harder to filter effectively

4. **Document tag strategy:**
   - Create a tags.md file explaining your tagging scheme
   - Share with team members

5. **Test filters before production:**
   - Use `--dry-run` to verify what metrics match
   - Ensure critical metrics aren't accidentally excluded

6. **Review tags regularly:**
   - Metrics change priority over time
   - Remove obsolete tags

---

## Testing Your Tags

```bash
# See what critical metrics would run
dtk run-tagged --tags critical --dry-run

# List all metrics with specific tag
dtk list-metrics --tags experimental

# Verify tag coverage
dtk list-metrics --details | grep "Tags:"

# Count metrics by tag (bash)
for tag in critical important hourly daily; do
    count=$(dtk list-metrics --tags $tag 2>/dev/null | grep -c "✓")
    echo "$tag: $count metrics"
done
```

---

## Next Steps

- Create your own tagging scheme based on your needs
- Integrate with your orchestrator (Prefect/Airflow)
- Set up different schedules for different tag groups
- Monitor tag usage and adjust as needed

**See also:**
- [DEPLOYMENT.md](../../DEPLOYMENT.md) - Production deployment guide
- [examples/](../) - More configuration examples
