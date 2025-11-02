# Contributing to DetectK

Thank you for your interest in contributing to DetectK! This document provides guidelines and standards for development.

---

## Development Setup

### Prerequisites

- Python 3.10+ (we use modern type hints: `str | None`, `list[str]`)
- Poetry or pip for package management
- Git for version control

### Installation

```bash
# Clone repository
git clone https://github.com/alexeiveselov92/detectk.git
cd detectk

# Install core package in editable mode
pip install -e packages/core

# Install collectors (optional)
pip install -e packages/collectors/clickhouse
pip install -e packages/collectors/sql
pip install -e packages/collectors/http

# Install detectors (optional)
pip install -e packages/detectors

# Install alerters (optional)
pip install -e packages/alerters/mattermost
pip install -e packages/alerters/slack

# Install development dependencies
pip install pytest pytest-cov black ruff mypy requests-mock
```

### Running Tests

```bash
# Run all core tests
pytest packages/core/tests/ -v

# Run with coverage
pytest packages/core/tests/ --cov=detectk --cov-report=term-missing

# Run specific test file
pytest packages/core/tests/test_check.py -v

# Run tests for specific package
pytest packages/collectors/clickhouse/tests/ -v
```

### Code Quality Tools

```bash
# Format code
black packages/

# Lint code
ruff check packages/

# Type checking
mypy packages/core/detectk
```

---

## Code Standards

### Language

- **All production code MUST be in English**: code, docstrings, comments, variable names, commit messages
- **Russian is allowed ONLY in**:
  - Internal documentation files (CLAUDE.md, TODO.md, ARCHITECTURE.md - gitignored)
  - Internal team communications
- **Public documentation** (README.md, DECISIONS.md, guides) - English only

### Python Style

#### Type Hints

- Use Python 3.10+ modern syntax
- Always annotate function parameters and return types

```python
# ✅ Good - modern union syntax
def collect_bulk(
    self,
    period_start: datetime,
    period_finish: datetime,
) -> list[DataPoint]:
    pass

# ❌ Bad - old Optional syntax
from typing import Optional, List
def collect_bulk(
    self,
    period_start: datetime,
    period_finish: datetime,
) -> List[DataPoint]:
    pass

# ✅ Good - modern list/dict syntax
def process(self, items: list[str], mapping: dict[str, int]) -> tuple[int, int]:
    pass

# ❌ Bad - old typing module
from typing import List, Dict, Tuple
def process(self, items: List[str], mapping: Dict[str, int]) -> Tuple[int, int]:
    pass
```

#### Docstrings

Use Google-style docstrings for all public classes and methods:

```python
def collect_bulk(
    self,
    period_start: datetime,
    period_finish: datetime,
) -> list[DataPoint]:
    """Collect time series data for specified period.

    Args:
        period_start: Start of time range to collect
        period_finish: End of time range to collect

    Returns:
        List of DataPoints with timestamps and values.
        Can return 1 point (real-time) or thousands (bulk load).

    Raises:
        CollectionError: If collection fails

    Example:
        >>> collector = ClickHouseCollector(config)
        >>> # Real-time: 10 minutes
        >>> points = collector.collect_bulk(
        ...     period_start=datetime(2024, 11, 2, 14, 0),
        ...     period_finish=datetime(2024, 11, 2, 14, 10),
        ... )
        >>> len(points)
        1
        >>> # Bulk load: 30 days
        >>> points = collector.collect_bulk(
        ...     period_start=datetime(2024, 1, 1),
        ...     period_finish=datetime(2024, 1, 31),
        ... )
        >>> len(points)
        4464
    """
```

#### Naming Conventions

**Domain-specific method names** (NOT generic):

```python
# ✅ Good - self-documenting
class BaseCollector:
    def collect_bulk(self, period_start, period_finish) -> list[DataPoint]:
        """Collect time series data from source."""

class BaseDetector:
    def detect(self, metric_name, value, timestamp) -> DetectionResult:
        """Detect anomalies."""

class BaseAlerter:
    def send(self, result) -> bool:
        """Send alert notification."""

# ❌ Bad - too generic
class BaseCollector:
    def execute(self):  # What does it execute?
        pass

    def process(self):  # What does it process?
        pass

    def run(self):  # Run what?
        pass
```

**Consistent parameter naming:**
- Use `period_start`, `period_finish` for time ranges (NOT `start_time`, `end_time`)
- Use `metric_name` (NOT `name`, `metric`, `metric_id`)
- Use `config` for configuration dictionaries
- Use `params` for detector/alerter parameters

**Registry naming:**
- Lowercase, descriptive strings
- Examples: `"clickhouse"`, `"sql"`, `"http"`, `"threshold"`, `"mad"`, `"mattermost"`

### Error Handling

Use custom exception hierarchy with context:

```python
# ✅ Good - specific exception with context
raise CollectionError(
    "Failed to connect to ClickHouse",
    source="clickhouse",
    details={"host": self.host, "database": self.database}
)

# ❌ Bad - generic exception without context
raise Exception("Connection failed")

# ❌ Bad - wrong exception type
raise ValueError("Failed to collect data")  # Should be CollectionError
```

**Exception hierarchy:**
- `DetectKError` (base)
  - `ConfigurationError` (invalid configs)
  - `CollectionError` (data collection failures)
  - `DetectionError` (anomaly detection failures)
  - `StorageError` (storage operations failures)
  - `AlertError` (alert sending failures)
  - `RegistryError` (component registration failures)

### Logging

Use structured logging with appropriate levels:

```python
import logging

logger = logging.getLogger(__name__)

# ✅ Good - structured logging with context
logger.info(f"Collecting data for metric: {metric_name}")
logger.warning(f"Partial failure for {metric_name}: {error}")
logger.error(f"Failed to send alert for {metric_name}", exc_info=True)
logger.debug(f"Detection result: {result}")

# ❌ Bad - print statements
print("Collecting data...")  # Never use print in production code

# ❌ Bad - logging sensitive data
logger.info(f"Password: {password}")  # Never log credentials
```

### Testing

**Requirements:**
- Minimum 80% code coverage for core package
- Unit tests with mocks for external dependencies
- Integration tests with real databases (where feasible)
- Test behavior, not implementation

**Test structure:**

```python
class TestClickHouseCollector:
    """Test suite for ClickHouse collector."""

    def test_collect_bulk_success(self):
        """Test successful bulk data collection."""
        # Arrange
        config = {
            "query": "SELECT timestamp, value FROM ...",
            "host": "localhost",
            "timestamp_column": "timestamp",
            "value_column": "value",
        }
        collector = ClickHouseCollector(config)

        # Act
        points = collector.collect_bulk(
            period_start=datetime(2024, 1, 1),
            period_finish=datetime(2024, 1, 2),
        )

        # Assert
        assert len(points) > 0
        assert all(isinstance(p, DataPoint) for p in points)

    def test_collect_bulk_connection_error(self):
        """Test handling of connection errors."""
        config = {
            "query": "SELECT 1",
            "host": "invalid-host",
            "timestamp_column": "ts",
            "value_column": "val",
        }
        collector = ClickHouseCollector(config)

        with pytest.raises(CollectionError, match="Failed to connect"):
            collector.collect_bulk(
                period_start=datetime(2024, 1, 1),
                period_finish=datetime(2024, 1, 2),
            )
```

**Test naming:**
- Class: `Test<ComponentName>` (e.g., `TestClickHouseCollector`)
- Method: `test_<what>_<condition>` (e.g., `test_collect_bulk_connection_error`)

---

## Architecture Principles

### Core Principles

1. **Configuration over code** - Analysts configure YAML files, not Python code
2. **Orchestrator-agnostic** - Core library works standalone (no Prefect/Airflow dependency)
3. **Single responsibility** - Collector collects, Detector detects, Alerter alerts
4. **Dependency injection** - Pass dependencies explicitly (e.g., storage to detector)
5. **Registry pattern** - Components auto-register via decorators
6. **Optional storage** - Each pipeline stage can optionally save results
7. **No hardcoded assumptions** - Time intervals, seasonal features are configurable
8. **Time series first** - Analyst writes ONE query, system handles everything

### Time Series Architecture

**CRITICAL:** DetectK uses time series architecture where queries return multiple rows.

**Query Pattern:**

```sql
SELECT
    toStartOfInterval(timestamp, INTERVAL {{ interval }}) AS period_time,
    count() AS value
FROM events
WHERE timestamp >= toDateTime('{{ period_start }}')
  AND timestamp < toDateTime('{{ period_finish }}')
GROUP BY period_time
ORDER BY period_time
```

**Key Points:**
- Analyst writes query ONCE with `{{ period_start }}`, `{{ period_finish }}` variables
- Collector stores query as Jinja2 template (NOT rendered at config load)
- Collector renders query on EACH `collect_bulk()` call with different periods
- Same query works for real-time (10 min) and bulk load (30 days)
- ConfigLoader does NOT render `collector.params.query` field (critical!)

### Component Design

**Base Classes:**
- All components inherit from abstract base classes
- Abstract methods defined with `@abstractmethod`
- Type hints on all methods
- Comprehensive docstrings

**Registry Pattern:**

```python
from detectk.registry import CollectorRegistry

@CollectorRegistry.register("mydb")
class MyDatabaseCollector(BaseCollector):
    """Custom database collector."""

    def collect_bulk(
        self,
        period_start: datetime,
        period_finish: datetime,
    ) -> list[DataPoint]:
        # Implementation
        pass
```

**Dependency Injection:**

```python
# ✅ Good - explicit dependencies
class MADDetector(BaseDetector):
    def __init__(self, storage: BaseStorage, **params):
        self.storage = storage  # Injected dependency
        self.params = params

# ❌ Bad - hidden dependencies (global state)
class MADDetector(BaseDetector):
    def __init__(self, **params):
        self.storage = get_global_storage()  # Hidden dependency
```

### Don't Repeat Yourself (DRY)

**Use configuration profiles** for shared connection parameters:

```yaml
# detectk_profiles.yaml
profiles:
  clickhouse_prod:
    type: "clickhouse"
    host: "${CLICKHOUSE_HOST}"
    database: "analytics"

# metric.yaml - reference profile
collector:
  profile: "clickhouse_prod"
  params:
    query: |
      SELECT ... WHERE timestamp >= '{{ period_start }}'
    timestamp_column: "period_time"
    value_column: "value"
```

**Extract common code** into base classes or utility functions.

---

## Git Workflow

### Commit Messages

Follow **Conventional Commits** format:

```
<type>(scope): <subject>

<body>

🤖 Generated with Claude Code https://claude.com/claude-code

Co-Authored-By: Claude <noreply@anthropic.com>
```

**Types:**
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation changes
- `style` - Code style changes (formatting, no logic change)
- `refactor` - Code refactoring
- `test` - Adding or updating tests
- `chore` - Maintenance tasks

**Scopes:**
- `core` - Core package changes
- `clickhouse` - ClickHouse collector/storage
- `detectors` - Detector implementations
- `alerters` - Alerter implementations
- `cli` - CLI commands
- `docs` - Documentation

**Examples:**

```bash
feat(clickhouse): add support for custom port configuration

Add optional port parameter to ClickHouse collector config.
Defaults to 9000 if not specified.

Related to TODO.md Phase 2 - ClickHouse Implementation

🤖 Generated with Claude Code https://claude.com/claude-code
Co-Authored-By: Claude <noreply@anthropic.com>
```

```bash
fix(detectors): correct MAD calculation for weighted statistics

Fix bug where weighted MAD calculation was using mean instead of
median for center calculation. Added regression test.

Fixes #123

🤖 Generated with Claude Code https://claude.com/claude-code
Co-Authored-By: Claude <noreply@anthropic.com>
```

### Branch Naming

- `feat/feature-name` - New features
- `fix/bug-description` - Bug fixes
- `docs/documentation-update` - Documentation
- `refactor/refactoring-description` - Refactoring

### Pull Requests

**Before submitting PR:**
1. ✅ All tests passing (`pytest packages/core/tests/ -v`)
2. ✅ Code formatted (`black packages/`)
3. ✅ Linting clean (`ruff check packages/`)
4. ✅ Type checking clean (`mypy packages/core/detectk`)
5. ✅ Documentation updated (docstrings, README if needed)

**PR Description Template:**

```markdown
## Summary
Brief description of changes

## Changes
- List of specific changes
- Another change

## Testing
- Describe how you tested the changes
- List new test cases added

## Related Issues
Closes #123
```

---

## Adding New Components

### Adding a New Collector

1. Create package: `packages/collectors/mydb/`
2. Implement `BaseCollector`:

```python
from datetime import datetime
from detectk.base import BaseCollector
from detectk.registry import CollectorRegistry
from detectk.models import DataPoint
from detectk.exceptions import CollectionError, ConfigurationError

@CollectorRegistry.register("mydb")
class MyDatabaseCollector(BaseCollector):
    """Collector for MyDatabase.

    Supports collecting time series metrics from MyDatabase via SQL queries.
    Query must return multiple rows with timestamp and value columns.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize collector.

        Args:
            config: Configuration dictionary with keys:
                   - connection_string: Database connection string
                   - query: SQL query with {{ period_start }}, {{ period_finish }} variables
                   - timestamp_column: Name of timestamp column (default: "period_time")
                   - value_column: Name of value column (default: "value")
                   - context_columns: Optional list of context column names

        Raises:
            ConfigurationError: If required config keys missing or query invalid
        """
        self.connection_string = config["connection_string"]
        self.query_template = config["query"]
        self.timestamp_column = config.get("timestamp_column", "period_time")
        self.value_column = config.get("value_column", "value")
        self.context_columns = config.get("context_columns", [])

        # Validate query has required variables
        self.validate_config()

    def validate_config(self) -> None:
        """Validate query has required Jinja2 variables."""
        if "{{ period_start }}" not in self.query_template:
            raise ConfigurationError("Query must contain {{ period_start }}")
        if "{{ period_finish }}" not in self.query_template:
            raise ConfigurationError("Query must contain {{ period_finish }}")

    def collect_bulk(
        self,
        period_start: datetime,
        period_finish: datetime,
    ) -> list[DataPoint]:
        """Collect time series data for specified period.

        Args:
            period_start: Start of time range
            period_finish: End of time range

        Returns:
            List of DataPoints (can be 1 point or thousands)

        Raises:
            CollectionError: If query fails or returns no data
        """
        # 1. Render query with time range
        from jinja2 import Template
        query = Template(self.query_template).render(
            period_start=period_start.isoformat(),
            period_finish=period_finish.isoformat(),
        )

        # 2. Execute query
        try:
            result = self._execute_query(query)
        except Exception as e:
            raise CollectionError(f"Query failed: {e}")

        # 3. Parse rows into DataPoints
        datapoints = []
        for row in result:
            timestamp = row[self.timestamp_column]
            value = row[self.value_column]
            context = {col: row[col] for col in self.context_columns}

            datapoints.append(DataPoint(
                timestamp=timestamp,
                value=value,
                is_missing=value is None,
                context=context if context else None,
            ))

        return datapoints

    def close(self) -> None:
        """Close database connection."""
        pass
```

3. Add tests in `packages/collectors/mydb/tests/`
4. Add example config in `examples/mydb/`
5. Update documentation

### Adding a New Detector

1. Implement `BaseDetector` in `packages/detectors/`

```python
from datetime import datetime
from detectk.base import BaseDetector, BaseStorage
from detectk.registry import DetectorRegistry
from detectk.models import DetectionResult
from detectk.exceptions import DetectionError

@DetectorRegistry.register("myalgorithm")
class MyAlgorithmDetector(BaseDetector):
    """My custom anomaly detection algorithm.

    Detects anomalies using [description of algorithm].
    """

    def __init__(self, storage: BaseStorage, **params) -> None:
        """Initialize detector.

        Args:
            storage: Storage backend for historical data
            **params: Algorithm parameters:
                     - window_size: Historical window (e.g., "30 days")
                     - threshold: Detection threshold

        Raises:
            ConfigurationError: If invalid parameters
        """
        self.storage = storage
        self.window_size = params["window_size"]
        self.threshold = params["threshold"]

    def detect(
        self,
        metric_name: str,
        value: float | None,
        timestamp: datetime,
    ) -> DetectionResult:
        """Detect anomalies using MyAlgorithm.

        Args:
            metric_name: Name of metric being checked
            value: Current metric value (can be None for missing data)
            timestamp: Timestamp of current value

        Returns:
            DetectionResult with anomaly status and bounds

        Raises:
            DetectionError: If detection fails
        """
        # 1. Query historical data
        df = self.storage.query_datapoints(
            metric_name=metric_name,
            window=self.window_size,
            end_time=timestamp,
        )

        # 2. Apply algorithm
        is_anomaly = value > self.threshold if value else False

        # 3. Return DetectionResult
        return DetectionResult(
            metric_name=metric_name,
            timestamp=timestamp,
            value=value,
            is_anomaly=is_anomaly,
            score=value / self.threshold if value and self.threshold > 0 else 0,
            lower_bound=0,
            upper_bound=self.threshold,
        )
```

2. Add comprehensive tests
3. Add example configs
4. Document algorithm in docstrings

### Adding a New Alerter

1. Implement `BaseAlerter` in `packages/alerters/myservice/`

```python
from detectk.base import BaseAlerter
from detectk.registry import AlerterRegistry
from detectk.models import DetectionResult
from detectk.exceptions import AlertError

@AlerterRegistry.register("myservice")
class MyServiceAlerter(BaseAlerter):
    """Alerter for MyService notifications.

    Sends alerts via MyService webhooks.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize alerter.

        Args:
            config: Configuration with keys:
                   - webhook_url: MyService webhook URL
                   - cooldown_minutes: Alert cooldown period

        Raises:
            ConfigurationError: If webhook_url missing
        """
        self.webhook_url = config["webhook_url"]
        self.cooldown_minutes = config.get("cooldown_minutes", 60)

    def send(self, result: DetectionResult) -> bool:
        """Send alert to MyService.

        Args:
            result: Detection result with anomaly info

        Returns:
            True if alert sent, False if skipped (cooldown)

        Raises:
            AlertError: If sending fails
        """
        # Implementation
        pass
```

2. Add tests with mocked HTTP requests (`requests-mock`)
3. Add example configs
4. Document message format

---

## Documentation

### Docstring Examples

All public APIs should have examples in docstrings:

```python
def collect_bulk(
    self,
    period_start: datetime,
    period_finish: datetime,
) -> list[DataPoint]:
    """Collect time series data.

    Example:
        >>> collector = ClickHouseCollector(config)
        >>> # Real-time: 10 minutes
        >>> points = collector.collect_bulk(
        ...     period_start=datetime(2024, 11, 2, 14, 0),
        ...     period_finish=datetime(2024, 11, 2, 14, 10),
        ... )
        >>> print(len(points))
        1

        >>> # Bulk load: 30 days
        >>> points = collector.collect_bulk(
        ...     period_start=datetime(2024, 1, 1),
        ...     period_finish=datetime(2024, 1, 31),
        ... )
        >>> print(len(points))
        4464
    """
```

### Configuration Examples

Create example configs in `examples/` directory:

```
examples/
├── clickhouse/
│   ├── simple_timeseries.yaml
│   └── seasonal_mad.yaml
├── sql/
│   ├── postgresql_sessions.yaml
│   └── mysql_orders.yaml
└── threshold/
    └── threshold_simple.yaml
```

Each example should be:
- **Self-contained** - can be run independently
- **Commented** - explain each section
- **Realistic** - based on real-world use cases

---

## Questions?

- Open an issue on GitHub
- Check existing documentation: README.md, DECISIONS.md, ARCHITECTURE.md
- Review examples in `examples/` directory

---

**Thank you for contributing to DetectK!** 🎉
