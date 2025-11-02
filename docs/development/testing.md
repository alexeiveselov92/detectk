# Testing Architecture

This document describes the testing strategy and architecture for DetectK development.

## Overview

DetectK uses a comprehensive testing approach with:
- **Unit tests** - Fast, isolated tests for individual components
- **Integration tests** - Real database interactions (ClickHouse, PostgreSQL)
- **End-to-end tests** - Full pipeline testing (collector → detector → alerter)

**Current status:** 160+ tests, all passing.

## Test Structure

### Package-Level Tests

Each package has its own test directory:

```
detectk/
├── packages/
│   ├── core/
│   │   ├── detectk/
│   │   │   ├── base/
│   │   │   ├── registry/
│   │   │   ├── config/
│   │   │   └── check.py
│   │   └── tests/              # Core package tests
│   │       ├── test_models.py
│   │       ├── test_registry.py
│   │       ├── test_config.py
│   │       ├── test_check.py
│   │       └── conftest.py
│   │
│   ├── collectors/
│   │   └── clickhouse/
│   │       └── tests/          # ClickHouse collector tests
│   │           ├── test_collector.py
│   │           ├── test_storage.py
│   │           └── conftest.py
│   │
│   ├── detectors/
│   │   └── core/
│   │       └── tests/          # Detector tests
│   │           ├── test_threshold.py
│   │           ├── test_mad.py
│   │           ├── test_zscore.py
│   │           └── conftest.py
│   │
│   └── alerters/
│       └── mattermost/
│           └── tests/          # Mattermost alerter tests
│               ├── test_alerter.py
│               └── conftest.py
```

### Test Categories

**Unit Tests** (packages/*/tests/test_*.py)
- Test individual functions/classes in isolation
- Mock external dependencies (databases, APIs)
- Fast execution (milliseconds per test)
- No network or disk I/O

**Integration Tests** (packages/*/tests/integration/test_*.py)
- Test with real databases (Docker containers)
- Test actual HTTP requests
- Slower execution (seconds per test)
- Requires setup/teardown

**E2E Tests** (tests/e2e/test_*.py)
- Test complete workflows
- Real configs, real databases
- Slowest execution (minutes)
- Production-like environment

## Running Tests

### Run All Tests

```bash
# From project root
pytest

# With coverage
pytest --cov=detectk --cov-report=html

# Verbose output
pytest -v
```

### Run Specific Package Tests

```bash
# Core package only
pytest packages/core/tests/

# ClickHouse collector only
pytest packages/collectors/clickhouse/tests/

# Detectors only
pytest packages/detectors/core/tests/

# Alerters only
pytest packages/alerters/mattermost/tests/
```

### Run Specific Test File

```bash
pytest packages/core/tests/test_config.py

# Specific test function
pytest packages/core/tests/test_config.py::test_env_var_substitution

# Specific test class
pytest packages/core/tests/test_registry.py::TestCollectorRegistry
```

### Run by Marker

```bash
# Only unit tests (fast)
pytest -m unit

# Only integration tests
pytest -m integration

# Skip integration tests
pytest -m "not integration"

# Slow tests only
pytest -m slow
```

## Test Markers

Mark tests with pytest markers:

```python
import pytest

@pytest.mark.unit
def test_datapoint_creation():
    """Unit test - no external dependencies."""
    point = DataPoint(timestamp=datetime.now(), value=100.0)
    assert point.value == 100.0

@pytest.mark.integration
def test_clickhouse_connection():
    """Integration test - requires real ClickHouse."""
    collector = ClickHouseCollector(config)
    result = collector.collect()
    assert result is not None

@pytest.mark.slow
@pytest.mark.integration
def test_backtest_30_days():
    """Slow integration test."""
    # Takes 30+ seconds
    pass
```

**Available markers:**
- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.integration` - Requires external services
- `@pytest.mark.slow` - Takes >5 seconds
- `@pytest.mark.skip` - Skip temporarily
- `@pytest.mark.parametrize` - Run with multiple inputs

## Core Package Tests

**Location:** `packages/core/tests/`

**Coverage:** 72+ tests

### Test Files

```
tests/
├── test_models.py           # DataPoint, DetectionResult, etc. (9 tests)
├── test_exceptions.py       # Exception hierarchy (9 tests)
├── test_registry.py         # Registry pattern (12 tests)
├── test_config.py           # Configuration parsing (29 tests)
├── test_check.py            # MetricCheck orchestrator (13 tests)
├── test_multi_detector.py   # Multi-detector support (21 tests)
└── conftest.py              # Shared fixtures
```

### Key Test Patterns

**Testing with mocks:**

```python
from unittest.mock import Mock, patch

def test_metric_check_with_mocked_components():
    # Mock collector
    mock_collector = Mock()
    mock_collector.collect.return_value = DataPoint(
        timestamp=datetime.now(),
        value=100.0
    )

    # Mock detector
    mock_detector = Mock()
    mock_detector.detect.return_value = DetectionResult(
        metric_name="test",
        timestamp=datetime.now(),
        value=100.0,
        is_anomaly=False
    )

    # Test orchestrator
    with patch('detectk.registry.CollectorRegistry.create', return_value=mock_collector):
        with patch('detectk.registry.DetectorRegistry.create', return_value=mock_detector):
            result = metric_check.execute(config)
            assert result.errors == []
```

**Testing configuration:**

```python
def test_env_var_substitution():
    """Test ${VAR_NAME} substitution."""
    os.environ['TEST_HOST'] = 'localhost'

    config_yaml = """
    collector:
      type: clickhouse
      params:
        host: "${TEST_HOST}"
    """

    config = ConfigLoader.load_from_string(config_yaml)
    assert config.collector.params['host'] == 'localhost'
```

**Testing exceptions:**

```python
def test_invalid_config_raises_error():
    """Test that invalid config raises ConfigurationError."""
    invalid_yaml = """
    collector:
      type: "unknown_type"
    """

    with pytest.raises(ConfigurationError, match="Unknown collector type"):
        ConfigLoader.load_from_string(invalid_yaml)
```

## Detector Tests

**Location:** `packages/detectors/core/tests/`

**Coverage:** 73 tests (Threshold: 23, MAD: 26, Z-Score: 24)

### Test Structure

```python
# test_threshold.py

class TestThresholdDetector:
    """Test threshold detector with all operators."""

    def test_greater_than(self):
        detector = ThresholdDetector(
            storage=Mock(),
            value=100,
            operator="greater_than"
        )

        result = detector.detect("test", value=150, timestamp=datetime.now())
        assert result.is_anomaly is True

        result = detector.detect("test", value=50, timestamp=datetime.now())
        assert result.is_anomaly is False

    def test_range_between(self):
        detector = ThresholdDetector(
            storage=Mock(),
            min_value=50,
            max_value=100,
            operator="between"
        )

        # Inside range (anomaly)
        result = detector.detect("test", value=75, timestamp=datetime.now())
        assert result.is_anomaly is True

        # Outside range (normal)
        result = detector.detect("test", value=150, timestamp=datetime.now())
        assert result.is_anomaly is False

    @pytest.mark.parametrize("value,expected", [
        (101, True),   # Above threshold
        (100, False),  # At threshold
        (99, False),   # Below threshold
    ])
    def test_parametrized_greater_than(self, value, expected):
        detector = ThresholdDetector(storage=Mock(), value=100, operator="greater_than")
        result = detector.detect("test", value=value, timestamp=datetime.now())
        assert result.is_anomaly is expected
```

### Testing Statistical Detectors

```python
# test_mad.py

def test_mad_basic_detection():
    """Test MAD detector with simple dataset."""
    # Mock storage with historical data
    mock_storage = Mock()
    historical_data = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=100, freq='10min'),
        'value': [100.0] * 95 + [200.0] * 5  # 5 outliers
    })
    mock_storage.query_datapoints.return_value = historical_data

    detector = MADDetector(
        storage=mock_storage,
        window_size="30 days",
        n_sigma=3.0
    )

    # Test normal value
    result = detector.detect("test", value=100.0, timestamp=datetime.now())
    assert result.is_anomaly is False
    assert 90 < result.lower_bound < 110

    # Test anomalous value
    result = detector.detect("test", value=300.0, timestamp=datetime.now())
    assert result.is_anomaly is True
    assert result.direction == "up"

def test_mad_with_seasonality():
    """Test MAD with hour_of_day seasonality."""
    # Mock storage with seasonal pattern
    mock_storage = Mock()
    timestamps = pd.date_range('2024-01-01', periods=2400, freq='10min')
    values = [
        100.0 if ts.hour < 9 or ts.hour > 17 else 500.0  # Business hours pattern
        for ts in timestamps
    ]
    historical_data = pd.DataFrame({
        'timestamp': timestamps,
        'value': values,
        'hour_of_day': [ts.hour for ts in timestamps]
    })
    mock_storage.query_datapoints.return_value = historical_data

    detector = MADDetector(
        storage=mock_storage,
        window_size="30 days",
        n_sigma=3.0,
        seasonal_features=[
            {"name": "hour_of_day", "expression": "toHour(timestamp)"}
        ]
    )

    # During business hours (10 AM), 500 is normal
    result = detector.detect(
        "test",
        value=500.0,
        timestamp=datetime(2024, 2, 1, 10, 0),
        hour_of_day=10
    )
    assert result.is_anomaly is False

    # During night (2 AM), 500 is anomalous
    result = detector.detect(
        "test",
        value=500.0,
        timestamp=datetime(2024, 2, 1, 2, 0),
        hour_of_day=2
    )
    assert result.is_anomaly is True
```

## Integration Tests

### Setup with Docker

```yaml
# docker-compose.test.yml
version: '3.8'

services:
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "9000:9000"
    environment:
      CLICKHOUSE_DB: test_db
      CLICKHOUSE_USER: default
      CLICKHOUSE_PASSWORD: ""
    healthcheck:
      test: ["CMD", "clickhouse-client", "--query", "SELECT 1"]
      interval: 5s
      timeout: 3s
      retries: 5

  postgres:
    image: postgres:15
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: test_db
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_password
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test_user"]
      interval: 5s
      timeout: 3s
      retries: 5
```

**Run integration tests:**

```bash
# Start services
docker-compose -f docker-compose.test.yml up -d

# Wait for health checks
docker-compose -f docker-compose.test.yml ps

# Run integration tests
pytest -m integration

# Cleanup
docker-compose -f docker-compose.test.yml down -v
```

### Integration Test Example

```python
# packages/collectors/clickhouse/tests/integration/test_collector.py

import pytest
from clickhouse_driver import Client

@pytest.fixture(scope="module")
def clickhouse_client():
    """Fixture providing real ClickHouse connection."""
    client = Client(host='localhost', port=9000)

    # Setup test table
    client.execute("""
        CREATE TABLE IF NOT EXISTS test_events (
            timestamp DateTime,
            user_id UInt32,
            event_type String
        ) ENGINE = MergeTree()
        ORDER BY timestamp
    """)

    # Insert test data
    client.execute("""
        INSERT INTO test_events VALUES
            (now() - INTERVAL 5 MINUTE, 1, 'login'),
            (now() - INTERVAL 3 MINUTE, 2, 'purchase'),
            (now() - INTERVAL 1 MINUTE, 3, 'login')
    """)

    yield client

    # Cleanup
    client.execute("DROP TABLE IF EXISTS test_events")

@pytest.mark.integration
def test_clickhouse_collector_real_db(clickhouse_client):
    """Test collector with real ClickHouse database."""
    config = {
        "host": "localhost",
        "port": 9000,
        "database": "default",
        "query": "SELECT count() as value FROM test_events"
    }

    collector = ClickHouseCollector(**config)
    result = collector.collect()

    assert result.value == 3.0
    assert result.timestamp is not None
```

## Fixtures and Conftest

### Shared Fixtures

```python
# packages/core/tests/conftest.py

import pytest
from datetime import datetime
from detectk.models import DataPoint, DetectionResult

@pytest.fixture
def sample_datapoint():
    """Reusable DataPoint fixture."""
    return DataPoint(
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        value=100.0,
        metadata={"source": "test"}
    )

@pytest.fixture
def sample_detection_result():
    """Reusable DetectionResult fixture."""
    return DetectionResult(
        metric_name="test_metric",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        value=100.0,
        is_anomaly=False,
        anomaly_score=1.5,
        lower_bound=80.0,
        upper_bound=120.0
    )

@pytest.fixture
def mock_storage():
    """Mock storage for testing detectors."""
    from unittest.mock import Mock
    import pandas as pd

    storage = Mock()
    storage.query_datapoints.return_value = pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=100, freq='1H'),
        'value': [100.0] * 100
    })
    return storage

@pytest.fixture
def temp_config_file(tmp_path):
    """Create temporary config file for testing."""
    config_content = """
    name: test_metric
    collector:
      type: clickhouse
      params:
        host: localhost
    detector:
      type: threshold
      params:
        value: 100
    """
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)
    return config_file
```

## Test Coverage

### Measure Coverage

```bash
# Generate HTML coverage report
pytest --cov=detectk --cov-report=html

# Open in browser
open htmlcov/index.html

# Terminal report
pytest --cov=detectk --cov-report=term-missing
```

### Coverage Requirements

**Current coverage:**
- Core package: ~85%
- Collectors: ~75%
- Detectors: ~90%
- Alerters: ~80%

**Target coverage:**
- Core package: >80%
- All other packages: >75%

**Excluded from coverage:**
- `__init__.py` files
- Type stubs
- Test files themselves

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      clickhouse:
        image: clickhouse/clickhouse-server:latest
        ports:
          - 9000:9000

      postgres:
        image: postgres:15
        ports:
          - 5432:5432
        env:
          POSTGRES_PASSWORD: test_password

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run unit tests
        run: pytest -m unit --cov=detectk

      - name: Run integration tests
        run: pytest -m integration

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Best Practices

### 1. Test Behavior, Not Implementation

```python
# ✓ GOOD - test behavior
def test_threshold_detector_alerts_when_above_limit():
    detector = ThresholdDetector(storage=Mock(), value=100, operator="greater_than")
    result = detector.detect("test", value=150, timestamp=datetime.now())
    assert result.is_anomaly is True  # Test outcome, not internal logic

# ✗ BAD - test implementation details
def test_threshold_detector_internal_calculation():
    detector = ThresholdDetector(storage=Mock(), value=100, operator="greater_than")
    assert detector._calculate_threshold() == 100  # Private method, implementation detail
```

### 2. Use Descriptive Test Names

```python
# ✓ GOOD - clear what's being tested
def test_mad_detector_raises_error_when_storage_not_provided():
    with pytest.raises(TypeError):
        MADDetector(window_size="30 days")

# ✗ BAD - unclear intent
def test_mad_1():
    ...
```

### 3. One Assertion Per Test (Generally)

```python
# ✓ GOOD - single concept
def test_anomaly_direction_up():
    result = detector.detect("test", value=200, timestamp=datetime.now())
    assert result.direction == "up"

def test_anomaly_direction_down():
    result = detector.detect("test", value=50, timestamp=datetime.now())
    assert result.direction == "down"

# ✗ BAD - testing multiple things
def test_anomaly_detection():
    result1 = detector.detect("test", value=200, timestamp=datetime.now())
    assert result1.direction == "up"
    result2 = detector.detect("test", value=50, timestamp=datetime.now())
    assert result2.direction == "down"
    result3 = detector.detect("test", value=100, timestamp=datetime.now())
    assert result3.is_anomaly is False
```

### 4. Use Parametrize for Similar Tests

```python
# ✓ GOOD - parameterized
@pytest.mark.parametrize("value,operator,expected", [
    (101, "greater_than", True),
    (100, "greater_than", False),
    (99, "less_than", True),
    (100, "less_than", False),
])
def test_threshold_operators(value, operator, expected):
    detector = ThresholdDetector(storage=Mock(), value=100, operator=operator)
    result = detector.detect("test", value=value, timestamp=datetime.now())
    assert result.is_anomaly is expected
```

### 5. Clean Up Resources

```python
@pytest.fixture
def temp_database():
    # Setup
    db = create_test_database()
    yield db
    # Teardown - always runs
    db.cleanup()

# Or use context managers
def test_with_temp_file():
    with tempfile.NamedTemporaryFile() as f:
        # Test uses f
        pass
    # File automatically deleted
```

## Troubleshooting Tests

### Tests Pass Locally, Fail in CI

**Causes:**
- Environment differences
- Timing issues (race conditions)
- Missing dependencies

**Solutions:**
```bash
# Reproduce CI environment locally
docker run -it python:3.10 bash
pip install -e ".[dev]"
pytest
```

### Flaky Tests

```python
# ✗ BAD - timing dependent
def test_cooldown():
    alerter.send(detection)
    time.sleep(1)  # Flaky - might not be enough
    assert alerter.in_cooldown() is True

# ✓ GOOD - deterministic
def test_cooldown():
    with freeze_time("2024-01-01 12:00:00"):
        alerter.send(detection)
    with freeze_time("2024-01-01 12:05:00"):
        assert alerter.in_cooldown() is True
```

### Slow Tests

```bash
# Find slowest tests
pytest --durations=10

# Profile tests
pytest --profile

# Run only fast tests
pytest -m "not slow"
```

## Next Steps

- **[Contributing Guide](contributing.md)** - How to contribute code
- **[Development Setup](development_setup.md)** - Local development environment
- **[Code Style Guide](code_style.md)** - Coding standards
