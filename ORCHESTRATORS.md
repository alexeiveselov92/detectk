# Orchestrator Integration Guide

DetectK is designed to work seamlessly with workflow orchestrators like Prefect, Airflow, and others. This guide shows how to integrate DetectK into your orchestration platform.

---

## Table of Contents

1. [Overview](#overview)
2. [Prefect Integration](#prefect-integration)
3. [Airflow Integration](#airflow-integration)
4. [Standalone Scheduler](#standalone-scheduler-coming-soon)
5. [Best Practices](#best-practices)

---

## Overview

DetectK follows the **Unix philosophy**: do one thing well. The `dtk run` command executes a single metric check and exits. This design makes it easy to integrate with any scheduler or orchestrator.

### Integration Options

| Method | When to Use | Complexity |
|--------|-------------|------------|
| **Cron** | Simple deployments, single server | ⭐ Easy |
| **Systemd Timers** | Linux production, system integration | ⭐⭐ Medium |
| **Airflow** | Complex DAGs, many metrics, team already uses Airflow | ⭐⭐⭐ Medium |
| **Prefect** | Modern workflows, dynamic scheduling, Python-first | ⭐⭐⭐ Medium |
| **Kubernetes CronJob** | Cloud-native, K8s infrastructure | ⭐⭐⭐ Medium |
| **Custom Python** | Full control, custom logic | ⭐⭐⭐⭐ Advanced |

---

## Prefect Integration

Prefect is a modern workflow orchestration platform with excellent Python integration.

### Installation

```bash
pip install prefect
pip install detectk detectk-collectors-clickhouse detectk-detectors detectk-alerters-mattermost
```

### Basic Integration

#### Option 1: Shell Command (Simple)

```python
from prefect import flow, task
from prefect.tasks import task_input_hash
from datetime import timedelta
import subprocess

@task(cache_key_fn=task_input_hash, cache_expiration=timedelta(minutes=5))
def run_metric_check(config_path: str) -> dict:
    """Run DetectK metric check via CLI."""
    result = subprocess.run(
        ["dtk", "run", config_path],
        capture_output=True,
        text=True,
        check=False,
    )

    return {
        "config": config_path,
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }

@flow(name="DetectK Metrics Check")
def detectk_metrics_flow(config_paths: list[str]):
    """Run multiple metric checks in parallel."""
    results = run_metric_check.map(config_paths)
    return results

# Run
if __name__ == "__main__":
    configs = [
        "configs/revenue_hourly.yaml",
        "configs/api_errors_5min.yaml",
        "configs/sessions_10min.yaml",
    ]
    detectk_metrics_flow(config_paths=configs)
```

#### Option 2: Python API (Advanced)

```python
from prefect import flow, task
from detectk.check import MetricCheck
from pathlib import Path

@task(retries=2, retry_delay_seconds=60)
def run_metric(config_path: str) -> dict:
    """Run metric check using DetectK Python API."""
    checker = MetricCheck()

    try:
        result = checker.execute(config_path)
        return {
            "metric_name": result.metric_name,
            "timestamp": str(result.timestamp),
            "value": result.value,
            "is_anomaly": any(d.is_anomaly for d in result.detections),
            "alert_sent": result.alert_sent,
            "errors": result.errors,
        }
    except Exception as e:
        raise Exception(f"Metric check failed: {e}")

@flow(name="DetectK Python API")
def detectk_python_flow(config_paths: list[str]):
    """Run metrics using Python API."""
    results = run_metric.map(config_paths)
    return results
```

### Tag-Based Filtering

```python
from prefect import flow, task
from detectk.config import ConfigLoader
from pathlib import Path

@task
def find_configs_by_tags(
    configs_dir: str,
    tags: list[str],
    match_all: bool = False,
) -> list[str]:
    """Find all configs matching tags."""
    loader = ConfigLoader()
    matched = []

    for yaml_file in Path(configs_dir).rglob("*.yaml"):
        try:
            config = loader.load(str(yaml_file))
            metric_tags = set(config.tags) if config.tags else set()
            required_tags = set(tags)

            if match_all:
                # ALL tags must match
                if required_tags.issubset(metric_tags):
                    matched.append(str(yaml_file))
            else:
                # ANY tag must match
                if required_tags & metric_tags:
                    matched.append(str(yaml_file))
        except Exception:
            continue

    return matched

@task
def run_metric(config_path: str) -> dict:
    """Run single metric check."""
    import subprocess
    result = subprocess.run(
        ["dtk", "run", config_path],
        capture_output=True,
        check=False,
    )
    return {"config": config_path, "success": result.returncode == 0}

@flow(name="DetectK Tagged Metrics")
def run_tagged_metrics(tags: list[str], match_all: bool = False):
    """Run all metrics matching tags."""
    # Find matching configs
    configs = find_configs_by_tags(
        configs_dir="configs",
        tags=tags,
        match_all=match_all,
    )

    # Run in parallel
    results = run_metric.map(configs)
    return results
```

### Scheduling with Prefect

```python
from prefect.deployments import Deployment
from prefect.server.schemas.schedules import CronSchedule

# Deploy hourly critical metrics
Deployment.build_from_flow(
    flow=run_tagged_metrics,
    name="detectk-hourly-critical",
    parameters={"tags": ["hourly", "critical"], "match_all": True},
    schedule=CronSchedule(cron="0 * * * *"),  # Every hour
    work_pool_name="default",
)

# Deploy realtime metrics (every 5 minutes)
Deployment.build_from_flow(
    flow=run_tagged_metrics,
    name="detectk-realtime",
    parameters={"tags": ["realtime"]},
    schedule=CronSchedule(cron="*/5 * * * *"),
    work_pool_name="default",
)

# Deploy daily aggregates
Deployment.build_from_flow(
    flow=run_tagged_metrics,
    name="detectk-daily",
    parameters={"tags": ["daily"]},
    schedule=CronSchedule(cron="0 0 * * *"),  # Daily at midnight
    work_pool_name="default",
)
```

### Deploy to Prefect Cloud/Server

```bash
# Start Prefect server (local development)
prefect server start

# Or connect to Prefect Cloud
prefect cloud login

# Deploy flows
python prefect_flows.py

# View in UI
prefect server start  # Opens http://localhost:4200
```

---

## Airflow Integration

Apache Airflow is a widely-used workflow orchestration platform.

### Installation

```bash
pip install apache-airflow
pip install detectk detectk-collectors-clickhouse detectk-detectors detectk-alerters-mattermost
```

### Basic Integration

#### Option 1: BashOperator (Simple)

```python
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    "owner": "data-team",
    "depends_on_past": False,
    "start_date": datetime(2024, 11, 1),
    "email_on_failure": True,
    "email": ["alerts@example.com"],
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

# DAG for hourly metrics
with DAG(
    "detectk_hourly_metrics",
    default_args=default_args,
    schedule_interval="@hourly",
    catchup=False,
    tags=["detectk", "monitoring"],
) as dag:

    # Run single metric
    revenue_check = BashOperator(
        task_id="revenue_hourly",
        bash_command="dtk run /opt/detectk/configs/revenue_hourly.yaml",
    )

    sessions_check = BashOperator(
        task_id="sessions_hourly",
        bash_command="dtk run /opt/detectk/configs/sessions_10min.yaml",
    )

    # Run in parallel (no dependencies)
    [revenue_check, sessions_check]
```

#### Option 2: PythonOperator (Advanced)

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from detectk.check import MetricCheck
from datetime import datetime, timedelta

def run_metric_check(config_path: str, **context):
    """Run DetectK metric check."""
    checker = MetricCheck()
    result = checker.execute(config_path)

    # Push result to XCom for downstream tasks
    context["ti"].xcom_push(key="result", value={
        "metric_name": result.metric_name,
        "value": result.value,
        "is_anomaly": any(d.is_anomaly for d in result.detections),
        "alert_sent": result.alert_sent,
    })

    # Fail task if errors occurred
    if result.errors:
        raise Exception(f"Metric check failed: {result.errors}")

    return result.metric_name

with DAG(
    "detectk_python_api",
    default_args=default_args,
    schedule_interval="@hourly",
    catchup=False,
) as dag:

    revenue_task = PythonOperator(
        task_id="revenue_check",
        python_callable=run_metric_check,
        op_args=["configs/revenue_hourly.yaml"],
    )
```

### Tag-Based DAGs

```python
from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    "owner": "data-team",
    "start_date": datetime(2024, 11, 1),
    "retries": 1,
}

# Critical metrics - every 10 minutes
with DAG(
    "detectk_critical_realtime",
    default_args=default_args,
    schedule_interval="*/10 * * * *",
    catchup=False,
    tags=["detectk", "critical"],
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
    tags=["detectk", "business"],
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
    tags=["detectk", "daily"],
) as dag:
    run_daily = BashOperator(
        task_id="run_daily_metrics",
        bash_command="dtk run-tagged --tags daily --exclude-tags experimental",
    )
```

### Dynamic DAG Generation

```python
from airflow import DAG
from airflow.operators.bash import BashOperator
from detectk.config import ConfigLoader
from datetime import datetime, timedelta
from pathlib import Path

# Load all metric configs
loader = ConfigLoader()
configs_dir = Path("/opt/detectk/configs")

# Group configs by interval
configs_by_interval = {}
for yaml_file in configs_dir.rglob("*.yaml"):
    try:
        config = loader.load(str(yaml_file))
        if config.schedule and config.schedule.interval:
            interval = config.schedule.interval
            if interval not in configs_by_interval:
                configs_by_interval[interval] = []
            configs_by_interval[interval].append(str(yaml_file))
    except Exception:
        continue

# Create DAG for each interval
for interval, configs in configs_by_interval.items():
    # Convert interval to cron expression
    # (simplified - real implementation would parse interval properly)
    schedule_map = {
        "10 minutes": "*/10 * * * *",
        "1 hour": "@hourly",
        "1 day": "@daily",
    }
    schedule = schedule_map.get(interval, "@hourly")

    dag_id = f"detectk_{interval.replace(' ', '_')}"

    with DAG(
        dag_id,
        default_args={"owner": "data-team", "start_date": datetime(2024, 11, 1)},
        schedule_interval=schedule,
        catchup=False,
        tags=["detectk", "auto-generated"],
    ) as dag:
        for config_path in configs:
            task_id = Path(config_path).stem
            BashOperator(
                task_id=task_id,
                bash_command=f"dtk run {config_path}",
                dag=dag,
            )

    # Register DAG
    globals()[dag_id] = dag
```

---

## Standalone Scheduler (Coming Soon)

DetectK will include a built-in standalone scheduler in a future release (V2.0).

**Planned features:**
```bash
# Start daemon
dtk standalone start --config-dir configs/

# Stop daemon
dtk standalone stop

# Status
dtk standalone status

# Reload configs without restart
dtk standalone reload
```

**For now, use:**
- Cron (simple deployments)
- Systemd timers (Linux production)
- Airflow/Prefect (complex workflows)

---

## Best Practices

### 1. Use Tags for Scheduling

Group metrics by interval and priority:

```yaml
# configs/revenue_hourly.yaml
tags: ["hourly", "critical", "revenue"]

# configs/api_errors_5min.yaml
tags: ["realtime", "critical", "api"]

# configs/daily_aggregates.yaml
tags: ["daily", "analytics"]
```

Schedule different tag groups:
```python
# Airflow
DAG("detectk_hourly", schedule="@hourly"):
    BashOperator(bash_command="dtk run-tagged --tags hourly")

DAG("detectk_realtime", schedule="*/5 * * * *"):
    BashOperator(bash_command="dtk run-tagged --tags realtime")
```

### 2. Error Handling

Always handle errors gracefully:

```python
# Prefect
@task(retries=2, retry_delay_seconds=60)
def run_metric(config: str):
    result = subprocess.run(["dtk", "run", config], capture_output=True)
    if result.returncode != 0:
        raise Exception(f"Metric check failed: {result.stderr}")
    return result.stdout

# Airflow
BashOperator(
    task_id="revenue",
    bash_command="dtk run configs/revenue.yaml",
    retries=2,
    retry_delay=timedelta(minutes=5),
    email_on_failure=True,
)
```

### 3. Monitoring

Track orchestrator metrics:

```python
# Prefect - track results
@flow
def detectk_metrics():
    results = run_metric.map(configs)

    # Log summary
    success_count = sum(1 for r in results if r["success"])
    logger.info(f"Completed: {success_count}/{len(results)} successful")

    return results
```

### 4. Parallel Execution

Run independent metrics in parallel:

```python
# Prefect - automatic parallelism
@flow
def run_all_metrics(configs: list[str]):
    # Runs in parallel by default
    results = run_metric.map(configs)
    return results

# Airflow - explicit parallelism
with DAG(...) as dag:
    task1 = BashOperator(task_id="revenue", ...)
    task2 = BashOperator(task_id="sessions", ...)
    task3 = BashOperator(task_id="api_errors", ...)

    # Run in parallel (no dependencies)
    [task1, task2, task3]
```

### 5. Configuration Management

Store configs in version control:

```
detectk-project/
├── configs/
│   ├── critical/
│   │   ├── revenue_hourly.yaml
│   │   └── api_errors_5min.yaml
│   ├── analytics/
│   │   └── daily_aggregates.yaml
│   └── experimental/
│       └── new_metric.yaml
├── flows/  # Prefect flows
│   ├── hourly_flow.py
│   └── daily_flow.py
├── dags/   # Airflow DAGs
│   ├── detectk_hourly.py
│   └── detectk_daily.py
└── .env    # Environment variables
```

---

## Migration Guide

### From Cron to Airflow

**Before (cron):**
```cron
*/10 * * * * dtk run /opt/detectk/configs/revenue.yaml
0 * * * * dtk run /opt/detectk/configs/sessions.yaml
```

**After (Airflow):**
```python
with DAG("detectk_metrics", schedule_interval=None) as dag:
    BashOperator(
        task_id="revenue",
        bash_command="dtk run /opt/detectk/configs/revenue.yaml",
        schedule_interval="*/10 * * * *",
    )

    BashOperator(
        task_id="sessions",
        bash_command="dtk run /opt/detectk/configs/sessions.yaml",
        schedule_interval="@hourly",
    )
```

### From Systemd to Prefect

**Before (systemd):**
```ini
[Unit]
Description=DetectK Revenue Monitor

[Service]
ExecStart=/opt/detectk/venv/bin/dtk run /opt/detectk/configs/revenue.yaml

[Timer]
OnUnitActiveSec=1h
```

**After (Prefect):**
```python
@flow
def revenue_check():
    run_metric("configs/revenue.yaml")

Deployment.build_from_flow(
    flow=revenue_check,
    name="revenue-hourly",
    schedule=CronSchedule(cron="0 * * * *"),
)
```

---

## Troubleshooting

### Issue: Metrics not running

**Check:**
1. Verify orchestrator is running
2. Check DAG/Flow is enabled
3. Review execution logs
4. Test manually: `dtk run config.yaml`

### Issue: Parallel execution causes DB connection issues

**Solution:** Limit concurrency

```python
# Prefect
@task(task_run_name="run-{config}", retries=2)
def run_metric(config):
    # Connection pooling handled by DetectK
    pass

# Airflow
dag = DAG(
    ...,
    max_active_runs=1,
    concurrency=5,  # Max 5 parallel tasks
)
```

### Issue: Configs not found

**Solution:** Use absolute paths

```python
# ❌ Wrong
BashOperator(bash_command="dtk run configs/revenue.yaml")

# ✅ Correct
BashOperator(bash_command="dtk run /opt/detectk/configs/revenue.yaml")
```

---

## Examples

Full working examples available in:
- `examples/tags/` - Tag-based filtering examples
- `examples/tags/README.md` - Prefect and Airflow integration code

---

## Next Steps

1. Choose your orchestrator (Prefect, Airflow, or Cron)
2. Add tags to your metric configs
3. Create flows/DAGs based on examples above
4. Test with `--dry-run` first
5. Deploy to production
6. Monitor execution logs

**See also:**
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment guide
- [examples/tags/README.md](examples/tags/README.md) - Tag usage guide
- [QUICKSTART.md](QUICKSTART.md) - Getting started
