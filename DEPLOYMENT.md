# DetectK Production Deployment Guide

Complete guide for deploying DetectK to production environments.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Infrastructure Requirements](#infrastructure-requirements)
3. [Installation](#installation)
4. [Database Setup](#database-setup)
5. [Configuration Management](#configuration-management)
6. [Scheduling Options](#scheduling-options)
7. [Monitoring & Observability](#monitoring--observability)
8. [Security](#security)
9. [High Availability](#high-availability)
10. [Disaster Recovery](#disaster-recovery)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Source Databases                           │
│  (ClickHouse, PostgreSQL, MySQL, HTTP APIs)                     │
└─────────────┬───────────────────────────────────────────────────┘
              │ Query data
              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DetectK Service                          │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Collector   │→ │   Detector   │→ │   Alerter    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                  │                  │                 │
│         ▼                  ▼                  │                 │
│  ┌────────────────────────────┐              │                 │
│  │  Storage (ClickHouse)      │              │                 │
│  │  - dtk_datapoints          │              │                 │
│  │  - dtk_detections          │              │                 │
│  └────────────────────────────┘              │                 │
└──────────────────────────────────────────────┼─────────────────┘
                                                │
                                                ▼
                                   ┌─────────────────────────┐
                                   │  Alert Channels         │
                                   │  (Mattermost/Slack)     │
                                   └─────────────────────────┘
```

---

## Infrastructure Requirements

### Compute

**Minimum (dev/staging):**
- 1 CPU core
- 2 GB RAM
- 10 GB disk

**Recommended (production):**
- 2-4 CPU cores
- 4-8 GB RAM
- 50 GB disk (for logs, temp data)

**Scaling:**
- CPU: Light (queries + calculations)
- Memory: Moderate (pandas DataFrames for historical windows)
- Disk: Light (only config files + logs)
- Network: Moderate (database queries)

### Database

**Storage Database (metrics):**
- ClickHouse recommended
- Size depends on retention and metric count
- Example: 100 metrics × 10-min interval × 90 days = ~13M rows (~5-10 GB)

**Source Databases:**
- Read-only access sufficient
- Lightweight queries (usually <100ms)

### Network

- Access to source databases
- Access to storage database
- Access to alert webhooks (HTTPS outbound)
- Optional: VPN/bastion for security

---

## Installation

### Option 1: Virtual Environment (Recommended)

```bash
# Create dedicated user
sudo useradd -r -s /bin/bash -d /opt/detectk detectk

# Create directory
sudo mkdir -p /opt/detectk/{configs,logs,venv}
sudo chown -R detectk:detectk /opt/detectk

# Switch to detectk user
sudo -u detectk -i

# Create virtual environment
cd /opt/detectk
python3.10 -m venv venv
source venv/bin/activate

# Install DetectK
pip install --upgrade pip
pip install detectk detectk-collectors-clickhouse detectk-detectors detectk-alerters-mattermost

# Verify installation
dtk --version
```

### Option 2: Docker (Alternative)

```dockerfile
# Dockerfile
FROM python:3.10-slim

# Install dependencies
RUN pip install --no-cache-dir \
    detectk \
    detectk-collectors-clickhouse \
    detectk-detectors \
    detectk-alerters-mattermost

# Create directories
RUN mkdir -p /app/configs /app/logs
WORKDIR /app

# Copy configs
COPY configs/ /app/configs/

# Run
CMD ["dtk", "run", "configs/my_metric.yaml"]
```

Build and run:
```bash
docker build -t detectk:latest .
docker run -e CLICKHOUSE_PASSWORD=xxx -e MATTERMOST_WEBHOOK=xxx detectk:latest
```

---

## Database Setup

### ClickHouse Storage Setup

```sql
-- Create dedicated database
CREATE DATABASE IF NOT EXISTS metrics;

-- Create dedicated user
CREATE USER IF NOT EXISTS detectk
IDENTIFIED WITH sha256_password BY 'your_secure_password';

-- Grant permissions
GRANT SELECT, INSERT ON metrics.* TO detectk;

-- Optional: Grant to source database (read-only)
GRANT SELECT ON analytics.* TO detectk;
```

DetectK will auto-create tables:
- `metrics.dtk_datapoints` - Collected metric values
- `metrics.dtk_detections` - Detection results (optional)

### PostgreSQL/MySQL Source

```sql
-- Create read-only user
CREATE USER detectk WITH PASSWORD 'your_secure_password';
GRANT SELECT ON schema_name.* TO detectk;
```

---

## Configuration Management

### Directory Structure

```
/opt/detectk/
├── configs/
│   ├── production/
│   │   ├── sessions_10min.yaml
│   │   ├── revenue_hourly.yaml
│   │   └── api_errors_5min.yaml
│   ├── staging/
│   │   └── test_metrics.yaml
│   └── detectk_profiles.yaml  # Shared connection profiles
├── logs/
│   ├── sessions_10min.log
│   ├── revenue_hourly.log
│   └── detectk.log
├── venv/
└── scripts/
    ├── deploy.sh
    └── health_check.sh
```

### Connection Profiles (Recommended)

Create `/opt/detectk/configs/detectk_profiles.yaml`:

```yaml
# Production ClickHouse
clickhouse_prod:
  type: "clickhouse"
  host: "clickhouse-prod.example.com"
  port: 9000
  user: "detectk"
  password: "${CLICKHOUSE_PASSWORD}"
  database: "analytics"

# Metrics storage
clickhouse_metrics:
  type: "clickhouse"
  host: "clickhouse-metrics.example.com"
  port: 9000
  user: "detectk"
  password: "${METRICS_DB_PASSWORD}"
  database: "metrics"

# Mattermost alerts
mattermost_ops:
  type: "mattermost"
  webhook_url: "${MATTERMOST_WEBHOOK}"
  channel: "#ops-alerts"
  username: "DetectK Monitor"
```

Reference in configs:

```yaml
collector:
  profile: "clickhouse_prod"
  params:
    query: |
      ...

storage:
  enabled: true
  profile: "clickhouse_metrics"

alerter:
  profile: "mattermost_ops"
```

### Environment Variables

Create `/opt/detectk/.env`:

```bash
# Database credentials
export CLICKHOUSE_PASSWORD="your_secure_password"
export METRICS_DB_PASSWORD="your_secure_password"

# Alert webhooks
export MATTERMOST_WEBHOOK="https://mattermost.example.com/hooks/xxx"
export SLACK_WEBHOOK="https://hooks.slack.com/services/xxx"

# Optional: Sentry for error tracking
export SENTRY_DSN="https://xxx@sentry.io/xxx"
```

Load before running:
```bash
source /opt/detectk/.env
```

---

## Scheduling Options

### Option 1: Systemd Timers (Recommended for Production)

**Advantages:**
- Native Linux service management
- Automatic restarts on failure
- Easy logging with journald
- Service dependencies

**Setup for each metric:**

Create `/etc/systemd/system/detectk-sessions.service`:

```ini
[Unit]
Description=DetectK Sessions Monitor
After=network.target

[Service]
Type=oneshot
User=detectk
Group=detectk
WorkingDirectory=/opt/detectk
EnvironmentFile=/opt/detectk/.env

ExecStart=/opt/detectk/venv/bin/dtk run /opt/detectk/configs/production/sessions_10min.yaml

# Logging
StandardOutput=append:/opt/detectk/logs/sessions_10min.log
StandardError=append:/opt/detectk/logs/sessions_10min.log

# Restart on failure
Restart=on-failure
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/detectk-sessions.timer`:

```ini
[Unit]
Description=Run DetectK Sessions Monitor every 10 minutes
Requires=detectk-sessions.service

[Timer]
OnBootSec=1min
OnUnitActiveSec=10min
AccuracySec=1s

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable detectk-sessions.timer
sudo systemctl start detectk-sessions.timer

# Check status
sudo systemctl status detectk-sessions.timer
sudo systemctl list-timers detectk-*

# View logs
sudo journalctl -u detectk-sessions.service -f
```

**Create multiple timers:**

```bash
# Script to generate systemd files
for metric in sessions_10min revenue_hourly api_errors_5min; do
    cat > /etc/systemd/system/detectk-${metric}.service <<EOF
[Unit]
Description=DetectK ${metric}
After=network.target

[Service]
Type=oneshot
User=detectk
WorkingDirectory=/opt/detectk
EnvironmentFile=/opt/detectk/.env
ExecStart=/opt/detectk/venv/bin/dtk run /opt/detectk/configs/production/${metric}.yaml
StandardOutput=append:/opt/detectk/logs/${metric}.log
StandardError=append:/opt/detectk/logs/${metric}.log
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

    # Extract interval from config (or set manually)
    interval="10min"  # Adjust per metric

    cat > /etc/systemd/system/detectk-${metric}.timer <<EOF
[Unit]
Description=Run DetectK ${metric}
Requires=detectk-${metric}.service

[Timer]
OnBootSec=1min
OnUnitActiveSec=${interval}

[Install]
WantedBy=timers.target
EOF

    sudo systemctl enable detectk-${metric}.timer
    sudo systemctl start detectk-${metric}.timer
done
```

### Option 2: Cron (Simple, Widely Supported)

```bash
# Edit crontab
crontab -e -u detectk

# Add entries (one per metric)
*/10 * * * * cd /opt/detectk && source .env && venv/bin/dtk run configs/production/sessions_10min.yaml >> logs/sessions_10min.log 2>&1
0 * * * * cd /opt/detectk && source .env && venv/bin/dtk run configs/production/revenue_hourly.yaml >> logs/revenue_hourly.log 2>&1
```

**Advantages:**
- Simple, universally available
- Easy to understand

**Disadvantages:**
- No service management
- No automatic restarts
- Manual log rotation

### Option 3: Kubernetes CronJob (Cloud-Native)

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: detectk-sessions
  namespace: monitoring
spec:
  schedule: "*/10 * * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: detectk
            image: your-registry.com/detectk:latest
            command: ["dtk", "run", "/configs/sessions_10min.yaml"]
            env:
            - name: CLICKHOUSE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: detectk-secrets
                  key: clickhouse-password
            - name: MATTERMOST_WEBHOOK
              valueFrom:
                secretKeyRef:
                  name: detectk-secrets
                  key: mattermost-webhook
            volumeMounts:
            - name: configs
              mountPath: /configs
              readOnly: true
          restartPolicy: OnFailure
          volumes:
          - name: configs
            configMap:
              name: detectk-configs
```

---

## Monitoring & Observability

### Health Checks

Create `/opt/detectk/scripts/health_check.sh`:

```bash
#!/bin/bash

# Check if DetectK can run
if ! /opt/detectk/venv/bin/dtk --version > /dev/null 2>&1; then
    echo "ERROR: DetectK binary not working"
    exit 1
fi

# Check database connectivity
if ! /opt/detectk/venv/bin/dtk validate /opt/detectk/configs/production/*.yaml; then
    echo "ERROR: Config validation failed"
    exit 1
fi

echo "OK: DetectK healthy"
exit 0
```

### Metrics to Monitor

1. **Execution Success Rate:**
   - Track failed runs vs successful
   - Alert if failure rate > 5%

2. **Execution Duration:**
   - Track how long each run takes
   - Alert if duration > 2× normal

3. **Alert Volume:**
   - Track alerts sent per day
   - Alert if sudden spike (configuration issue?)

4. **Database Latency:**
   - Track query times
   - Alert if queries slow (database issue?)

### Logging Strategy

**Log Rotation:**

Create `/etc/logrotate.d/detectk`:

```
/opt/detectk/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 detectk detectk
}
```

**Structured Logging:**

DetectK logs include:
- Timestamp
- Log level
- Metric name
- Operation (collect/detect/alert)
- Result (success/failure)
- Error details (if failed)

Example log entry:
```
2025-11-02 14:30:00 INFO [sessions_10min] Collection successful: 1 datapoints
2025-11-02 14:30:01 INFO [sessions_10min] Detection: no anomaly (score=1.2)
2025-11-02 14:30:01 INFO [sessions_10min] Check completed successfully
```

### Centralized Logging (Optional)

**Option 1: ELK Stack**

```bash
# Install filebeat
sudo apt-get install filebeat

# Configure filebeat to ship logs
cat > /etc/filebeat/filebeat.yml <<EOF
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /opt/detectk/logs/*.log
  fields:
    service: detectk

output.elasticsearch:
  hosts: ["elasticsearch.example.com:9200"]
EOF

sudo systemctl start filebeat
```

**Option 2: Promtail + Loki**

```yaml
# promtail-config.yaml
clients:
  - url: http://loki.example.com:3100/loki/api/v1/push

scrape_configs:
  - job_name: detectk
    static_configs:
      - targets:
          - localhost
        labels:
          job: detectk
          __path__: /opt/detectk/logs/*.log
```

---

## Security

### Credentials Management

**Never hardcode credentials in configs!**

✅ Good:
```yaml
collector:
  params:
    password: "${CLICKHOUSE_PASSWORD}"
```

❌ Bad:
```yaml
collector:
  params:
    password: "my_password_123"  # NEVER DO THIS!
```

### Secrets Management Options

**Option 1: Environment Variables (Simple)**
```bash
export CLICKHOUSE_PASSWORD="$(vault kv get -field=password secret/detectk/clickhouse)"
```

**Option 2: HashiCorp Vault (Enterprise)**
```bash
# Fetch secrets on startup
vault kv get -field=password secret/detectk/clickhouse > /tmp/ch_pass
export CLICKHOUSE_PASSWORD=$(cat /tmp/ch_pass)
rm /tmp/ch_pass
```

**Option 3: AWS Secrets Manager**
```bash
export CLICKHOUSE_PASSWORD=$(aws secretsmanager get-secret-value \
    --secret-id detectk/clickhouse-password \
    --query SecretString \
    --output text)
```

### Network Security

1. **Firewall Rules:**
   ```bash
   # Allow only necessary outbound connections
   - Source databases (port 9000 for ClickHouse, 5432 for PostgreSQL, etc.)
   - Metrics database
   - Alert webhooks (HTTPS/443)
   ```

2. **TLS/SSL:**
   ```yaml
   collector:
     params:
       secure: true  # Use TLS
       verify: true  # Verify certificates
   ```

3. **Read-Only Database User:**
   - DetectK only needs SELECT on source databases
   - Only needs INSERT on metrics database

### File Permissions

```bash
# Secure config directory
sudo chown -R detectk:detectk /opt/detectk/configs
sudo chmod 750 /opt/detectk/configs
sudo chmod 640 /opt/detectk/configs/*.yaml

# Secure .env file
sudo chmod 600 /opt/detectk/.env
```

---

## High Availability

### Redundancy Strategies

**Single Instance (Simple):**
- One server running all metrics
- Systemd restarts on failure
- Good for: Small deployments (<10 metrics)

**Active-Passive (HA):**
- Two servers, one active
- Heartbeat/keepalived for failover
- Good for: Medium deployments (10-50 metrics)

**Active-Active (Scaled):**
- Multiple servers, metrics distributed
- Load balancer / Kubernetes
- Good for: Large deployments (50+ metrics)

### Kubernetes Deployment (Active-Active)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: detectk
  namespace: monitoring
spec:
  replicas: 3
  selector:
    matchLabels:
      app: detectk
  template:
    metadata:
      labels:
        app: detectk
    spec:
      containers:
      - name: detectk
        image: your-registry.com/detectk:latest
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        env:
        - name: CLICKHOUSE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: detectk-secrets
              key: clickhouse-password
```

### Database HA

**ClickHouse Cluster:**
- Use ClickHouse cluster for storage
- DetectK supports failover via connection string

```yaml
storage:
  params:
    # Multiple hosts, automatic failover
    host: "ch1.example.com,ch2.example.com,ch3.example.com"
```

---

## Disaster Recovery

### Backup Strategy

**What to Backup:**
1. Configurations (`/opt/detectk/configs/`)
2. Environment variables (encrypted)
3. *(Optional)* Metrics database

**Configuration Backup:**
```bash
# Daily backup to S3
0 2 * * * tar -czf /tmp/detectk-configs-$(date +\%Y\%m\%d).tar.gz /opt/detectk/configs && \
          aws s3 cp /tmp/detectk-configs-*.tar.gz s3://backups/detectk/ && \
          rm /tmp/detectk-configs-*.tar.gz
```

**Database Backup (Optional):**
```bash
# ClickHouse backup
clickhouse-backup create detectk-metrics-$(date +%Y%m%d)
clickhouse-backup upload detectk-metrics-$(date +%Y%m%d)
```

### Recovery Procedure

**Scenario 1: Server Failure**

1. Provision new server
2. Install DetectK (see Installation)
3. Restore configs from backup
4. Set environment variables
5. Enable systemd timers
6. Verify health checks

**Scenario 2: Database Loss**

- Metrics database can be rebuilt by re-running historical loads
- Source databases are unaffected (read-only)

**Scenario 3: Configuration Corruption**

```bash
# Restore from Git
cd /opt/detectk/configs
git reset --hard origin/main
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] Infrastructure provisioned
- [ ] Databases set up with correct permissions
- [ ] Network connectivity verified
- [ ] Secrets management configured
- [ ] Monitoring/logging set up

### Deployment

- [ ] DetectK installed
- [ ] Configs deployed
- [ ] Configs validated (`dtk validate`)
- [ ] Environment variables set
- [ ] Historical data loaded
- [ ] Scheduling configured
- [ ] Services started

### Post-Deployment

- [ ] Health checks passing
- [ ] Test alert sent successfully
- [ ] Logs being collected
- [ ] Metrics being recorded
- [ ] Documentation updated
- [ ] Team notified

### Ongoing Maintenance

- [ ] Weekly: Review alerts for false positives
- [ ] Monthly: Review detector parameters
- [ ] Quarterly: Review retention policies
- [ ] Yearly: Review architecture and scaling

---

## Performance Optimization

### Query Optimization

- Use indexes on timestamp columns
- Limit time ranges in queries
- Use materialized views for complex aggregations

### Detector Optimization

- Use appropriate window sizes (don't overload)
- Use weighted statistics (faster than full window)
- Consider separate mode for larger sample sizes

### Storage Optimization

- Use proper retention periods
- Partition tables by month
- Use ReplacingMergeTree for deduplication

---

## Support & Escalation

### Troubleshooting Steps

1. Check logs: `tail -f /opt/detectk/logs/*.log`
2. Validate config: `dtk validate config.yaml`
3. Test database connectivity
4. Check systemd status: `systemctl status detectk-*`
5. Review recent changes

### Contact

- **Documentation:** See README.md, ARCHITECTURE.md
- **Examples:** See examples/ directory
- **Issues:** https://github.com/alexeiveselov92/detectk/issues

---

**Production deployment complete!** Your DetectK installation is now running reliably in production. 🚀
