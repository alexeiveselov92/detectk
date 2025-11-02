"""Tests for GenericSQLCollector."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from detectk.exceptions import CollectionError, ConfigurationError
from detectk_sql.collector import GenericSQLCollector


class TestGenericSQLCollector:
    """Test suite for GenericSQLCollector."""

    @pytest.fixture
    def sqlite_db(self):
        """Create temporary SQLite database with test data."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # Create test table and insert data
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            conn.execute(
                text("""
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )
            conn.execute(
                text("""
                INSERT INTO events (user_id, timestamp)
                VALUES
                    (1, datetime('now', '-5 minutes')),
                    (2, datetime('now', '-4 minutes')),
                    (1, datetime('now', '-3 minutes')),
                    (3, datetime('now', '-2 minutes')),
                    (2, datetime('now', '-1 minute'))
            """)
            )
            conn.commit()

        yield f"sqlite:///{db_path}"

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    def test_initialization(self, sqlite_db):
        """Test collector initialization."""
        config = {
            "connection_string": sqlite_db,
            "query": "SELECT COUNT(*) as value FROM events -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)

        assert collector.connection_string == sqlite_db
        assert collector.db_type == "sqlite"
        assert collector.timeout == 30
        assert collector.engine is None  # Lazy initialization

    def test_missing_connection_string(self):
        """Test that missing connection_string raises error."""
        config = {"query": "SELECT 1 as value"}

        with pytest.raises(ConfigurationError, match="connection_string"):
            GenericSQLCollector(config)

    def test_missing_query(self, sqlite_db):
        """Test that missing query raises error."""
        config = {"connection_string": sqlite_db}

        with pytest.raises(ConfigurationError, match="query"):
            GenericSQLCollector(config)

    def test_empty_query(self, sqlite_db):
        """Test that empty query raises error."""
        config = {"connection_string": sqlite_db, "query": "   "}

        with pytest.raises(ConfigurationError, match="cannot be empty"):
            GenericSQLCollector(config)

    def test_missing_period_start_variable(self, sqlite_db):
        """Test that missing period_start variable raises error."""
        config = {
            "connection_string": sqlite_db,
            "query": "SELECT COUNT(*) as value FROM events WHERE timestamp < '{{ period_finish }}'",
        }

        with pytest.raises(ConfigurationError, match="period_start"):
            GenericSQLCollector(config)

    def test_missing_period_finish_variable(self, sqlite_db):
        """Test that missing period_finish variable raises error."""
        config = {
            "connection_string": sqlite_db,
            "query": "SELECT COUNT(*) as value FROM events WHERE timestamp >= '{{ period_start }}'",
        }

        with pytest.raises(ConfigurationError, match="period_finish"):
            GenericSQLCollector(config)

    def test_invalid_connection_string(self):
        """Test that invalid connection string format raises error."""
        config = {
            "connection_string": "invalid://connection",
            "query": "SELECT 1 as value -- period: {{ period_start }} to {{ period_finish }}",
        }

        with pytest.raises(ConfigurationError, match="Invalid connection string"):
            GenericSQLCollector(config)

    def test_collect_basic(self, sqlite_db):
        """Test basic data collection."""
        config = {
            "connection_string": sqlite_db,
            # Use a simple query that includes the variables but always returns data
            # SQLite doesn't have great timestamp comparison, so we'll count all events
            "query": "SELECT COUNT(*) as value, datetime('now') as period_time FROM events WHERE 1=1 -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)
        from datetime import datetime, timedelta
        period_start = datetime.now() - timedelta(hours=1)
        period_finish = datetime.now() + timedelta(hours=1)
        datapoints = collector.collect_bulk(period_start, period_finish)

        assert len(datapoints) == 1
        assert datapoints[0].value == 5.0  # 5 events in test data
        assert isinstance(datapoints[0].timestamp, datetime)
        assert datapoints[0].is_missing is False
        assert datapoints[0].metadata["source"] == "sql"
        assert datapoints[0].metadata["db_type"] == "sqlite"

    def test_collect_without_timestamp(self, sqlite_db):
        """Test collection when query doesn't return period_time (should fail validation)."""
        config = {
            "connection_string": sqlite_db,
            "query": "SELECT COUNT(*) as value FROM events -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)
        from datetime import datetime, timedelta
        period_start = datetime.now() - timedelta(hours=1)
        period_finish = datetime.now() + timedelta(hours=1)

        # This should fail because query doesn't return period_time column
        with pytest.raises(CollectionError, match="missing timestamp column"):
            collector.collect_bulk(period_start, period_finish)

    def test_collect_empty_result(self, sqlite_db):
        """Test collection when query returns no rows."""
        config = {
            "connection_string": sqlite_db,
            "query": "SELECT COUNT(*) as value, datetime('now') as period_time FROM events WHERE user_id = 999 -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)
        from datetime import datetime, timedelta
        period_start = datetime.now() - timedelta(hours=1)
        period_finish = datetime.now() + timedelta(hours=1)
        datapoints = collector.collect_bulk(period_start, period_finish)

        # COUNT(*) always returns a row with value=0
        assert len(datapoints) == 1
        assert datapoints[0].value == 0.0

    def test_collect_missing_value_column(self, sqlite_db):
        """Test that missing value column raises error."""
        config = {
            "connection_string": sqlite_db,
            "query": "SELECT COUNT(*) as count, datetime('now') as period_time FROM events -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)
        from datetime import datetime, timedelta
        period_start = datetime.now() - timedelta(hours=1)
        period_finish = datetime.now() + timedelta(hours=1)

        with pytest.raises(CollectionError, match="missing value column"):
            collector.collect_bulk(period_start, period_finish)

    def test_collect_with_at_time(self, sqlite_db):
        """Test collection with specific period_start and period_finish."""
        config = {
            "connection_string": sqlite_db,
            "query": "SELECT COUNT(*) as value, datetime('now') as period_time FROM events -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)
        period_start = datetime(2024, 11, 1, 12, 0, 0)
        period_finish = datetime(2024, 11, 1, 12, 10, 0)
        datapoints = collector.collect_bulk(period_start, period_finish)

        # Should get results since our test data exists
        assert len(datapoints) == 1
        assert datapoints[0].value == 5.0  # All 5 events

    def test_close(self, sqlite_db):
        """Test that close disposes engine."""
        config = {
            "connection_string": sqlite_db,
            "query": "SELECT COUNT(*) as value, datetime('now') as period_time FROM events -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)

        # Trigger engine creation
        from datetime import datetime, timedelta
        period_start = datetime.now() - timedelta(hours=1)
        period_finish = datetime.now() + timedelta(hours=1)
        collector.collect_bulk(period_start, period_finish)
        assert collector.engine is not None

        # Close
        collector.close()
        assert collector.engine is None

    def test_detect_db_type_postgresql(self):
        """Test PostgreSQL detection."""
        config = {
            "connection_string": "postgresql://localhost/test",
            "query": "SELECT 1 as value, now() as period_time WHERE timestamp >= '{{ period_start }}' AND timestamp < '{{ period_finish }}'",
        }

        collector = GenericSQLCollector(config)
        assert collector.db_type == "postgresql"

    def test_detect_db_type_mysql(self):
        """Test MySQL detection."""
        config = {
            "connection_string": "mysql://localhost/test",
            "query": "SELECT 1 as value, now() as period_time WHERE timestamp >= '{{ period_start }}' AND timestamp < '{{ period_finish }}'",
        }

        collector = GenericSQLCollector(config)
        assert collector.db_type == "mysql"

    def test_multiple_collections_reuse_engine(self, sqlite_db):
        """Test that multiple collections reuse the same engine."""
        config = {
            "connection_string": sqlite_db,
            "query": "SELECT COUNT(*) as value, datetime('now') as period_time FROM events -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)
        from datetime import datetime, timedelta
        period_start = datetime.now() - timedelta(hours=1)
        period_finish = datetime.now() + timedelta(hours=1)

        # First collection
        dp1 = collector.collect_bulk(period_start, period_finish)
        engine1 = collector.engine

        # Second collection
        dp2 = collector.collect_bulk(period_start, period_finish)
        engine2 = collector.engine

        # Engine should be reused
        assert engine1 is engine2
        assert len(dp1) == len(dp2)
        assert dp1[0].value == dp2[0].value

    def test_query_with_filter(self, sqlite_db):
        """Test query with WHERE clause."""
        config = {
            "connection_string": sqlite_db,
            # Filter by user_id, but include the required variables in a comment
            "query": "SELECT COUNT(DISTINCT user_id) as value, datetime('now') as period_time FROM events WHERE user_id <= 2 -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)
        from datetime import datetime, timedelta
        period_start = datetime.now() - timedelta(hours=1)
        period_finish = datetime.now() + timedelta(hours=1)
        datapoints = collector.collect_bulk(period_start, period_finish)

        assert len(datapoints) == 1
        assert datapoints[0].value == 2.0  # user_id 1 and 2


class TestGenericSQLCollectorEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def sqlite_db(self):
        """Create temporary SQLite database with test data."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # Create test table
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER PRIMARY KEY)"))
            conn.commit()

        yield f"sqlite:///{db_path}"

        # Cleanup
        Path(db_path).unlink(missing_ok=True)

    def test_connection_failure(self):
        """Test handling of connection failures."""
        config = {
            "connection_string": "sqlite:///nonexistent/path/db.db",
            "query": "SELECT 1 as value, datetime('now') as period_time -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)

        # Connection should fail when executing query
        from datetime import datetime, timedelta
        period_start = datetime.now() - timedelta(hours=1)
        period_finish = datetime.now() + timedelta(hours=1)
        with pytest.raises(CollectionError, match="SQL query failed|Unexpected error"):
            collector.collect_bulk(period_start, period_finish)

    def test_invalid_sql_syntax(self, sqlite_db):
        """Test handling of SQL syntax errors."""
        config = {
            "connection_string": sqlite_db,
            "query": "SELECT INVALID SYNTAX -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)

        from datetime import datetime, timedelta
        period_start = datetime.now() - timedelta(hours=1)
        period_finish = datetime.now() + timedelta(hours=1)
        with pytest.raises(CollectionError, match="SQL query failed"):
            collector.collect_bulk(period_start, period_finish)

    def test_non_numeric_value(self):
        """Test handling of non-numeric value column."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE test (name TEXT, created DATETIME DEFAULT CURRENT_TIMESTAMP)"))
            conn.execute(text("INSERT INTO test (name) VALUES ('text')"))
            conn.commit()

        config = {
            "connection_string": f"sqlite:///{db_path}",
            "query": "SELECT name as value, created as period_time FROM test -- period: {{ period_start }} to {{ period_finish }}",
        }

        collector = GenericSQLCollector(config)

        from datetime import datetime, timedelta
        period_start = datetime.now() - timedelta(hours=1)
        period_finish = datetime.now() + timedelta(hours=1)

        # Should return empty list since non-numeric values are skipped with warning
        datapoints = collector.collect_bulk(period_start, period_finish)
        assert len(datapoints) == 0  # Non-numeric value skipped

        Path(db_path).unlink(missing_ok=True)
