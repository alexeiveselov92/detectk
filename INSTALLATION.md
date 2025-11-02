# DetectK Installation Guide

Complete guide for installing DetectK in various environments.

---

## Quick Start

### Minimal Installation

Install core library only:
```bash
pip install detectk
```

### Recommended Installation

For ClickHouse monitoring with basic detectors and Mattermost alerts:
```bash
pip install detectk \
    detectk-detectors \
    detectk-collectors-clickhouse \
    detectk-alerters-mattermost
```

### Full Installation

All collectors, detectors, and alerters:
```bash
pip install detectk \
    detectk-detectors \
    detectk-collectors-clickhouse \
    detectk-collectors-sql \
    detectk-collectors-http \
    detectk-alerters-mattermost \
    detectk-alerters-slack
```

---

## Requirements

### Python Version
- **Python 3.10+** required
- Tested on Python 3.10, 3.11, 3.12

### System Requirements
- Linux, macOS, or Windows (with WSL recommended)
- 512 MB RAM minimum (2 GB recommended for production)
- Network access to monitored databases

---

## Installation Methods

### 1. PyPI (Recommended)

Install from Python Package Index:

```bash
# Latest stable version
pip install detectk

# Specific version
pip install detectk==0.1.1

# Upgrade to latest
pip install --upgrade detectk
```

### 2. Virtual Environment (Recommended for Development)

Create isolated environment:

```bash
# Create venv
python3 -m venv detectk-env

# Activate (Linux/macOS)
source detectk-env/bin/activate

# Activate (Windows)
detectk-env\Scripts\activate

# Install
pip install detectk detectk-detectors detectk-collectors-clickhouse

# Verify
dtk --version
```

### 3. Docker

Use official Docker image (coming soon):

```bash
docker pull detectk/detectk:latest

docker run -v $(pwd)/configs:/configs detectk/detectk \
    dtk run /configs/my_metric.yaml
```

### 4. From Source (Development)

Clone and install from GitHub:

```bash
# Clone repository
git clone https://github.com/alexeiveselov92/detectk.git
cd detectk

# Install in development mode
pip install -e packages/core
pip install -e packages/detectors/core
pip install -e packages/collectors/clickhouse
pip install -e packages/alerters/mattermost

# Run tests
pytest packages/core/tests
```

---

## Package Overview

DetectK is modular - install only what you need:

### Core Package

**`detectk`** - Core library (required)
- Base classes and interfaces
- Configuration system
- CLI tool (`dtk` command)
- Orchestrator (MetricCheck)
- Registry system

```bash
pip install detectk
```

### Detector Packages

**`detectk-detectors`** - Basic detection algorithms
- Threshold detector
- MAD (Median Absolute Deviation)
- Z-Score detector
- Missing data detector

```bash
pip install detectk-detectors
```

### Collector Packages

**`detectk-collectors-clickhouse`** - ClickHouse connector
- Time series bulk collection
- Connection pooling
- Efficient batch operations

```bash
pip install detectk-collectors-clickhouse
```

**`detectk-collectors-sql`** - Generic SQL databases
- PostgreSQL
- MySQL
- SQLite
- SQLAlchemy-based

```bash
pip install detectk-collectors-sql
```

**`detectk-collectors-http`** - HTTP/REST APIs
- Prometheus integration
- Generic JSON APIs
- Custom endpoint support

```bash
pip install detectk-collectors-http
```

### Alerter Packages

**`detectk-alerters-mattermost`** - Mattermost webhooks
- Rich emoji formatting
- Cooldown support
- Custom templates

```bash
pip install detectk-alerters-mattermost
```

**`detectk-alerters-slack`** - Slack Block Kit
- Rich formatting
- Color-coded alerts
- Cooldown support

```bash
pip install detectk-alerters-slack
```

---

## Database-Specific Installations

### For ClickHouse Users

```bash
pip install detectk \
    detectk-detectors \
    detectk-collectors-clickhouse \
    detectk-alerters-mattermost
```

**Additional dependencies:**
- `clickhouse-driver` (installed automatically)

### For PostgreSQL Users

```bash
pip install detectk \
    detectk-detectors \
    detectk-collectors-sql \
    detectk-alerters-slack

# Install PostgreSQL driver
pip install psycopg2-binary
```

### For MySQL Users

```bash
pip install detectk \
    detectk-detectors \
    detectk-collectors-sql \
    detectk-alerters-mattermost

# Install MySQL driver
pip install mysqlclient
# OR
pip install pymysql
```

### For SQLite Users

```bash
pip install detectk \
    detectk-detectors \
    detectk-collectors-sql

# SQLite driver included with Python
```

---

## Verification

After installation, verify everything works:

### Check Installation

```bash
# Check version
dtk --version
# Output: dtk, version 0.1.1

# List available components
dtk list-collectors
dtk list-detectors
dtk list-alerters
```

### Test Configuration

```bash
# Generate template config
dtk init test_metric.yaml

# Validate it
dtk validate test_metric.yaml
```

### Quick Test Run

Create a simple test config `test.yaml`:

```yaml
name: "test_metric"
description: "Test installation"

collector:
  type: "clickhouse"
  params:
    host: "localhost"
    database: "default"
    query: |
      SELECT
        toStartOfInterval(now(), INTERVAL 10 MINUTE) AS period_time,
        100 AS value

    timestamp_column: "period_time"
    value_column: "value"

detector:
  type: "threshold"
  params:
    operator: "greater_than"
    threshold: 50

alerter:
  enabled: false

schedule:
  interval: "10 minutes"
```

Run it:
```bash
dtk validate test.yaml
dtk run test.yaml
```

---

## Common Installation Issues

### Issue: `dtk: command not found`

**Cause:** Package scripts not in PATH

**Solution:**
```bash
# Find where pip installed scripts
python3 -m pip show detectk | grep Location

# Add to PATH (Linux/macOS)
export PATH="$HOME/.local/bin:$PATH"

# Or use python module syntax
python3 -m detectk.cli.main --version
```

### Issue: `ImportError: No module named 'detectk'`

**Cause:** Wrong Python environment

**Solution:**
```bash
# Check which python
which python3
python3 --version

# Install in correct environment
python3 -m pip install detectk
```

### Issue: `ModuleNotFoundError: No module named 'clickhouse_driver'`

**Cause:** Missing database driver

**Solution:**
```bash
# ClickHouse driver is auto-installed with collector
pip install detectk-collectors-clickhouse

# Or install driver manually
pip install clickhouse-driver
```

### Issue: Permission errors on Linux

**Cause:** System-wide installation without sudo

**Solution:**
```bash
# Install for current user only (recommended)
pip install --user detectk

# OR use virtual environment (better)
python3 -m venv myenv
source myenv/bin/activate
pip install detectk
```

### Issue: `SSLCertVerificationError` when connecting to database

**Cause:** SSL certificate issues

**Solution:**
```yaml
# In your config, disable SSL verification (not recommended for production)
collector:
  params:
    secure: false
    verify: false
```

---

## Production Deployment

### System Package Installation

For production servers, create requirements file:

```bash
# requirements.txt
detectk==0.1.1
detectk-detectors==0.1.1
detectk-collectors-clickhouse==0.1.1
detectk-collectors-sql==0.1.1
detectk-alerters-mattermost==0.1.1
psycopg2-binary==2.9.9  # If using PostgreSQL
```

Install:
```bash
pip install -r requirements.txt
```

### Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

# Install DetectK
RUN pip install --no-cache-dir \
    detectk==0.1.1 \
    detectk-detectors==0.1.1 \
    detectk-collectors-clickhouse==0.1.1 \
    detectk-alerters-mattermost==0.1.1

# Copy configs
COPY configs/ /app/configs/

WORKDIR /app

# Run metric
CMD ["dtk", "run", "/app/configs/my_metric.yaml"]
```

Build and run:
```bash
docker build -t my-detectk .
docker run -e CLICKHOUSE_HOST=mydb.com my-detectk
```

### Kubernetes Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete Kubernetes setup.

---

## Upgrading DetectK

### Upgrade to Latest Version

```bash
pip install --upgrade detectk
pip install --upgrade detectk-detectors
pip install --upgrade detectk-collectors-clickhouse
# ... etc for all packages
```

### Check What's Installed

```bash
pip list | grep detectk
```

Output:
```
detectk                      0.1.1
detectk-alerters-mattermost  0.1.1
detectk-collectors-clickhouse 0.1.1
detectk-detectors            0.1.1
```

### Upgrade Specific Package

```bash
pip install --upgrade detectk-detectors
```

---

## Uninstallation

Remove DetectK and all packages:

```bash
pip uninstall -y detectk \
    detectk-detectors \
    detectk-collectors-clickhouse \
    detectk-collectors-sql \
    detectk-collectors-http \
    detectk-alerters-mattermost \
    detectk-alerters-slack
```

---

## Next Steps

After installation:

1. **Quick Start:** Follow [QUICKSTART.md](QUICKSTART.md) for 5-minute tutorial
2. **Configuration:** See [CONFIGURATION.md](docs/guides/configuration.md) for config reference
3. **Examples:** Browse `examples/` directory for working configs
4. **Deployment:** See [DEPLOYMENT.md](DEPLOYMENT.md) for production setup

---

## Support

- **Documentation:** https://github.com/alexeiveselov92/detectk
- **Issues:** https://github.com/alexeiveselov92/detectk/issues
- **PyPI:** https://pypi.org/project/detectk/

---

**Ready to monitor your metrics!** 🎉
