# DetectK v0.1.1 - Query Fixes & Documentation

**Release Date:** November 3, 2025
**PyPI:** https://pypi.org/project/detectk/0.1.1/
**GitHub:** https://github.com/alexeiveselov92/detectk

---

## Overview

DetectK v0.1.1 is a **bugfix release** that corrects SQL query examples in documentation and adds comprehensive user guides. This release ensures all examples work correctly with the time-series architecture.

**Upgrade Recommendation:** ✅ Recommended for all users
**Breaking Changes:** ❌ None - fully backward compatible

---

## What's Fixed in 0.1.1

### Critical Bugfix: SQL Query Examples

**Problem:** Many documentation examples showed SQL queries WITHOUT required time filters (`{{ period_start }}` and `{{ period_finish }}`), which would fail validation.

**Fixed:**
- ✅ Corrected 65+ queries across all documentation
- ✅ All examples now include proper time filters
- ✅ Database-specific syntax for ClickHouse, PostgreSQL, MySQL, SQLite
- ✅ All queries validated and tested

**Files Updated:**
- README.md
- QUICKSTART.md
- DEPLOYMENT.md
- TROUBLESHOOTING.md
- ORCHESTRATORS.md
- docs/guides/*.md
- examples/**/*.yaml (all 37+ configs)
- Package READMEs

**Before (Broken):**
```yaml
query: |
  SELECT count() as value FROM sessions
  WHERE timestamp >= now() - INTERVAL 10 MINUTE
```

**After (Fixed):**
```yaml
query: |
  SELECT
    toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
    count() AS value
  FROM sessions
  WHERE timestamp >= toDateTime('{{ period_start }}')
    AND timestamp < toDateTime('{{ period_finish }}')
  GROUP BY period_time
  ORDER BY period_time
```

---

## What's New in 0.1.1

### Comprehensive User Documentation

**NEW:** INSTALLATION.md (~400 lines)
- Complete installation guide for all scenarios
- PyPI, Docker, Kubernetes installation
- Database-specific setup (ClickHouse, PostgreSQL, MySQL, SQLite)
- Troubleshooting common issues
- Upgrade and uninstall procedures
- Verification steps

**NEW:** CONFIGURATION.md (~900 lines)
- Complete reference for all configuration options
- Every collector, detector, alerter parameter documented
- Environment variables and Jinja2 templates
- Connection profiles guide
- Multiple detectors configuration (A/B testing)
- Complete working examples

**Updated:** README.md
- Organized documentation section
- Links to all 7 user guides
- Links to 4 developer guides
- Clear navigation for users

---

## Installation

### Upgrade from v0.1.0

```bash
# Upgrade all packages
pip install --upgrade detectk \
    detectk-detectors \
    detectk-collectors-clickhouse \
    detectk-collectors-sql \
    detectk-alerters-mattermost \
    detectk-alerters-slack
```

### Fresh Installation

```bash
# Minimal (ClickHouse + MAD + Mattermost)
pip install detectk \
    detectk-detectors \
    detectk-collectors-clickhouse \
    detectk-alerters-mattermost

# Full installation
pip install detectk \
    detectk-detectors \
    detectk-collectors-clickhouse \
    detectk-collectors-sql \
    detectk-collectors-http \
    detectk-alerters-mattermost \
    detectk-alerters-slack
```

---

## Documentation (All Guides)

### User Guides (7)
1. **[INSTALLATION.md](INSTALLATION.md)** - Complete installation guide
2. **[QUICKSTART.md](QUICKSTART.md)** - 5-minute tutorial
3. **[CONFIGURATION.md](CONFIGURATION.md)** - Complete configuration reference
4. **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment guide
5. **[ORCHESTRATORS.md](ORCHESTRATORS.md)** - Prefect & Airflow integration
6. **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
7. **[examples/](examples/)** - 37+ working configurations

### Developer Guides (4)
1. **[DECISIONS.md](DECISIONS.md)** - Architectural decisions with rationale
2. **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture
3. **[CONTRIBUTING.md](CONTRIBUTING.md)** - Development standards
4. **[TODO.md](TODO.md)** - Development roadmap

**Total:** ~3,000 lines of user documentation + ~2,000 lines of developer docs

---

## What's Unchanged (Still Included)

All features from v0.1.0:

### Core Features
- ✅ Time series data collection (bulk operations)
- ✅ Multi-detector architecture with auto-generated IDs
- ✅ Tag system for metric grouping and filtering
- ✅ Checkpoint system for resumable loads
- ✅ Connection profiles for credential management
- ✅ CLI tool with 9 commands

### Packages (7)
1. **detectk** - Core library
2. **detectk-detectors** - MAD, Z-Score, Threshold, Missing Data
3. **detectk-collectors-clickhouse** - ClickHouse connector
4. **detectk-collectors-sql** - PostgreSQL, MySQL, SQLite
5. **detectk-collectors-http** - HTTP/REST API connector
6. **detectk-alerters-mattermost** - Mattermost webhooks
7. **detectk-alerters-slack** - Slack Block Kit

### Testing
- ✅ 257 unit tests (all passing)
- ✅ ~85% code coverage
- ✅ Tested on Python 3.10, 3.11, 3.12

---

## Migration from v0.1.0

**No code changes required!** This is a documentation-only bugfix release.

**What to do:**
1. Upgrade packages: `pip install --upgrade detectk detectk-detectors ...`
2. Review new documentation (INSTALLATION.md, CONFIGURATION.md)
3. Check your queries match the correct pattern (see examples)
4. Continue using as before

**If your configs already had correct time filters:**
- ✅ No changes needed
- ✅ Everything works as before

**If your configs were based on broken examples:**
- ⚠️ Update queries to include `{{ period_start }}` and `{{ period_finish }}`
- ⚠️ See CONFIGURATION.md for correct patterns
- ⚠️ Use `dtk validate` to check configs

---

## Known Issues & Limitations

Same as v0.1.0:

1. **No standalone scheduler** - Use cron, systemd, Airflow, or Prefect
2. **No integration tests** - Only unit tests (real DB tests planned for v2.0)
3. **ML detectors not included** - Prophet, IQR planned for v2.0
4. **Limited alerters** - Telegram and Email planned for v2.0

**None of these are blockers for production use.**

---

## Breaking Changes

❌ **None** - Fully backward compatible with v0.1.0

---

## Bug Fixes

### Documentation
- **Fixed:** 65+ SQL queries missing required time filters
- **Fixed:** Incorrect query patterns in examples
- **Fixed:** Missing GROUP BY and ORDER BY in aggregations
- **Added:** Database-specific query syntax for PostgreSQL, MySQL, SQLite
- **Added:** Proper column mapping examples

### Repository
- **Added:** .venv-build/ to .gitignore
- **Removed:** Accidentally committed build artifacts

---

## Statistics

### Code Changes
- **Files Changed:** 38 (documentation and examples)
- **Lines Added:** ~1,850 (documentation)
- **Lines Removed:** ~150 (incorrect examples)
- **Commits:** 3
  - ccab4f6: Fix SQL queries in documentation
  - 7ad264f: Add INSTALLATION.md and CONFIGURATION.md
  - f8ac4a7: Update README with doc links

### Package Sizes (PyPI)
- detectk: 55.8 KB (unchanged)
- detectk-detectors: ~30 KB (unchanged)
- Total: ~140 KB for full installation

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

## Roadmap (V2.0)

Planned features for next major release:

- Standalone scheduler (`dtk standalone start/stop`)
- Prophet detector (ML-based forecasting)
- IQR detector (Interquartile Range)
- Telegram and Email alerters
- Integration tests with real databases
- Performance benchmarks

---

## Thank You!

Thank you for using DetectK! This bugfix release ensures all examples work correctly out of the box.

**Highlights:**
- ✅ All SQL queries validated and working
- ✅ Comprehensive documentation (3,000+ lines)
- ✅ Production-ready for ClickHouse, PostgreSQL, MySQL, SQLite
- ✅ Ready for Prefect/Airflow integration

**Start monitoring your metrics today:**
```bash
pip install detectk detectk-detectors detectk-collectors-clickhouse
dtk init my_metric.yaml
dtk validate my_metric.yaml
dtk run my_metric.yaml
```

🎉 **Happy monitoring!**
