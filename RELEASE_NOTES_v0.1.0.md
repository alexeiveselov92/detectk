# DetectK v0.1.0 - First Public Release 🎉

**Release Date:** November 2, 2025  
**PyPI:** https://pypi.org/project/detectk/

---

## Overview

DetectK v0.1.0 is the first public release of a flexible, production-ready Python library for monitoring database metrics, detecting anomalies using various algorithms, and sending alerts through multiple channels.

---

## What's New in 0.1.0

### Core Features

- **Time Series Data Collection:** Efficient bulk data collection with checkpoint system for resumable loads
- **Multiple Data Sources:** ClickHouse, PostgreSQL, MySQL, SQLite, HTTP/REST APIs
- **Advanced Detection:** MAD, Z-Score, Threshold, and Missing Data detectors
- **Seasonality Support:** Combined (AND) and Separate (OR) modes for seasonal grouping
- **Multi-Detector Architecture:** Run multiple detection strategies per metric simultaneously
- **Tag System:** Group and filter metrics by tags for flexible scheduling
- **Multiple Alert Channels:** Mattermost and Slack integrations
- **Orchestrator Integration:** Works seamlessly with Airflow and Prefect

### CLI Tool

9 commands available:
- `dtk run` - Execute metric check
- `dtk run-tagged` - Run metrics filtered by tags
- `dtk validate` - Validate configuration
- `dtk list-collectors/detectors/alerters` - List available components
- `dtk list-metrics` - List all configured metrics
- `dtk init` - Generate template config
- `dtk init-project` - Initialize project structure

### Published Packages

7 packages published to PyPI:
1. `detectk` - Core library
2. `detectk-detectors` - Detection algorithms
3. `detectk-collectors-clickhouse` - ClickHouse connector
4. `detectk-collectors-sql` - Generic SQL connector
5. `detectk-collectors-http` - HTTP/REST API connector
6. `detectk-alerters-mattermost` - Mattermost alerter
7. `detectk-alerters-slack` - Slack alerter

---

## Installation

```bash
# Quick start (ClickHouse + MAD + Mattermost)
pip install detectk detectk-collectors-clickhouse detectk-detectors detectk-alerters-mattermost

# Full installation
pip install detectk detectk-detectors \
    detectk-collectors-clickhouse detectk-collectors-sql detectk-collectors-http \
    detectk-alerters-mattermost detectk-alerters-slack
```

---

## Documentation

- [README.md](README.md) - Project overview
- [QUICKSTART.md](QUICKSTART.md) - 5-minute tutorial
- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment guide
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Problem solving
- [ORCHESTRATORS.md](ORCHESTRATORS.md) - Airflow/Prefect integration
- [examples/](examples/) - 37 working configurations

---

## Testing

- 257 unit tests (all passing)
- Test coverage: ~85%
- Tested on Python 3.10, 3.11, 3.12

---

## Example Usage

```yaml
# revenue_hourly.yaml
name: "revenue_hourly"
description: "Monitor hourly revenue"

tags: ["critical", "revenue", "hourly"]

collector:
  type: "clickhouse"
  params:
    host: "${CLICKHOUSE_HOST}"
    query: |
      SELECT
        toStartOfHour(timestamp) AS period_time,
        sum(amount_usd) AS value
      FROM orders
      WHERE timestamp >= toDateTime('{{ period_start }}')
        AND timestamp < toDateTime('{{ period_finish }}')
      GROUP BY period_time
      ORDER BY period_time

    timestamp_column: "period_time"
    value_column: "value"

detector:
  type: "mad"
  params:
    window_size: "30 days"
    n_sigma: 3.0

alerter:
  enabled: true
  type: "mattermost"
  params:
    webhook_url: "${MATTERMOST_WEBHOOK}"
    cooldown_minutes: 60

schedule:
  interval: "1 hour"
```

Run it:
```bash
dtk validate revenue_hourly.yaml
dtk run revenue_hourly.yaml
```

---

## Key Architectural Decisions

1. **Orchestrator-Agnostic:** Works with cron, systemd, Airflow, Prefect, or any scheduler
2. **Configuration-Driven:** Analysts configure YAML files, not Python code
3. **Modular Design:** Install only what you need
4. **Time Series First:** Efficient bulk data collection
5. **Tag-Based Filtering:** Flexible metric grouping for different schedules
6. **Seasonality Support:** Compare apples to apples (Monday 9 AM vs Monday 9 AM)

---

## Migration from Previous Versions

This is the first public release. No migration needed.

---

## Known Limitations

1. No integration tests with real databases yet (unit tests only)
2. No standalone scheduler (use cron/systemd/Airflow/Prefect)
3. ML-based detectors (Prophet, IQR) not included
4. Telegram and Email alerters not included

All planned for v2.0.

---

## Breaking Changes

None (first release).

---

## Roadmap (V2.0)

Planned features:
- Standalone scheduler (`dtk standalone start/stop`)
- Prophet detector (ML-based forecasting)
- IQR detector (Interquartile Range)
- Telegram and Email alerters
- Integration tests with real databases
- Performance benchmarks

---

## Credits

- **Author:** Alexey Veselov (alexeiveselov92)
- **Repository:** https://github.com/alexeiveselov92/detectk
- **License:** MIT

---

## Support

- **Issues:** https://github.com/alexeiveselov92/detectk/issues
- **Documentation:** https://github.com/alexeiveselov92/detectk
- **PyPI:** https://pypi.org/project/detectk/

---

## Statistics

- **Development Time:** ~3 weeks
- **Git Commits:** 49
- **Lines of Code:** ~15,000
- **Tests:** 257
- **Documentation:** 10 guides
- **Examples:** 37 configurations
- **Packages:** 7

---

**Thank you for using DetectK!** 🎉
