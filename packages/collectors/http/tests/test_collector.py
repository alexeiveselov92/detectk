"""Tests for HTTPCollector."""

from datetime import datetime

import pytest
import requests_mock

from detectk.exceptions import CollectionError, ConfigurationError
from detectk_http.collector import HTTPCollector


class TestHTTPCollector:
    """Test suite for HTTPCollector."""

    def test_initialization(self):
        """Test collector initialization."""
        config = {
            "url": "http://api.example.com/metrics",
            "response_format": "json",
            "value_path": "value",
        }

        collector = HTTPCollector(config)

        assert collector.url == "http://api.example.com/metrics"
        assert collector.method == "GET"
        assert collector.response_format == "json"
        assert collector.value_path == "value"
        assert collector.timeout == 30
        assert collector.retry_count == 3

    def test_missing_url(self):
        """Test that missing URL raises error."""
        config = {"response_format": "json", "value_path": "value"}

        with pytest.raises(ConfigurationError, match="url"):
            HTTPCollector(config)

    def test_missing_response_format(self):
        """Test that missing response_format raises error."""
        config = {"url": "http://example.com"}

        with pytest.raises(ConfigurationError, match="response_format"):
            HTTPCollector(config)

    def test_invalid_response_format(self):
        """Test that invalid response_format raises error."""
        config = {
            "url": "http://example.com",
            "response_format": "xml",  # Not supported
        }

        with pytest.raises(ConfigurationError, match="Invalid response_format"):
            HTTPCollector(config)

    def test_json_requires_value_path(self):
        """Test that JSON format requires value_path."""
        config = {
            "url": "http://example.com",
            "response_format": "json",
            # Missing value_path
        }

        with pytest.raises(ConfigurationError, match="value_path"):
            HTTPCollector(config)

    def test_invalid_http_method(self):
        """Test that invalid HTTP method raises error."""
        config = {
            "url": "http://example.com",
            "response_format": "text",
            "method": "DELETE",  # Not supported
        }

        with pytest.raises(ConfigurationError, match="Invalid HTTP method"):
            HTTPCollector(config)

    def test_collect_text_format(self, requests_mock):
        """Test collection with text response format."""
        config = {
            "url": "http://api.example.com/count",
            "response_format": "text",
        }

        # Mock HTTP response
        requests_mock.get("http://api.example.com/count", text="42.5")

        collector = HTTPCollector(config)
        datapoint = collector.collect()

        assert datapoint.value == 42.5
        assert isinstance(datapoint.timestamp, datetime)
        assert datapoint.is_missing is False
        assert datapoint.metadata["source"] == "http"
        assert datapoint.metadata["status_code"] == 200

    def test_collect_json_simple_path(self, requests_mock):
        """Test collection with JSON and simple path."""
        config = {
            "url": "http://api.example.com/metrics",
            "response_format": "json",
            "value_path": "count",
        }

        # Mock JSON response
        requests_mock.get("http://api.example.com/metrics", json={"count": 123})

        collector = HTTPCollector(config)
        datapoint = collector.collect()

        assert datapoint.value == 123.0

    def test_collect_json_nested_path(self, requests_mock):
        """Test collection with JSON and nested path."""
        config = {
            "url": "http://api.example.com/metrics",
            "response_format": "json",
            "value_path": "data.metrics.active_users",
        }

        # Mock nested JSON response
        requests_mock.get(
            "http://api.example.com/metrics",
            json={"data": {"metrics": {"active_users": 456}}},
        )

        collector = HTTPCollector(config)
        datapoint = collector.collect()

        assert datapoint.value == 456.0

    def test_collect_json_array_indexing(self, requests_mock):
        """Test collection with JSON array indexing."""
        config = {
            "url": "http://api.example.com/metrics",
            "response_format": "json",
            "value_path": "data.result[0].value[1]",
        }

        # Mock Prometheus-style response
        requests_mock.get(
            "http://api.example.com/metrics",
            json={"data": {"result": [{"value": [1699999999, "789"]}]}},
        )

        collector = HTTPCollector(config)
        datapoint = collector.collect()

        assert datapoint.value == 789.0

    def test_collect_with_headers(self, requests_mock):
        """Test collection with custom headers."""
        config = {
            "url": "http://api.example.com/secure",
            "response_format": "text",
            "headers": {
                "Authorization": "Bearer secret_token",
                "X-API-Key": "key123",
            },
        }

        # Mock with header verification
        def check_headers(request, context):
            assert request.headers["Authorization"] == "Bearer secret_token"
            assert request.headers["X-API-Key"] == "key123"
            return "100"

        requests_mock.get("http://api.example.com/secure", text=check_headers)

        collector = HTTPCollector(config)
        datapoint = collector.collect()

        assert datapoint.value == 100.0

    def test_collect_with_query_params(self, requests_mock):
        """Test collection with query parameters."""
        config = {
            "url": "http://api.example.com/query",
            "response_format": "text",
            "params": {"metric": "cpu_usage", "period": "5m"},
        }

        # Mock with query param verification
        def check_params(request, context):
            assert request.qs == {"metric": ["cpu_usage"], "period": ["5m"]}
            return "75.5"

        requests_mock.get("http://api.example.com/query", text=check_params)

        collector = HTTPCollector(config)
        datapoint = collector.collect()

        assert datapoint.value == 75.5

    def test_collect_post_with_json_body(self, requests_mock):
        """Test POST request with JSON body."""
        config = {
            "url": "http://api.example.com/query",
            "method": "POST",
            "response_format": "json",
            "value_path": "result.count",
            "json": {"query": "SELECT COUNT(*)", "time_range": "1h"},
        }

        # Mock POST request
        def check_json_body(request, context):
            assert request.json() == {"query": "SELECT COUNT(*)", "time_range": "1h"}
            return {"result": {"count": 999}}

        requests_mock.post("http://api.example.com/query", json=check_json_body)

        collector = HTTPCollector(config)
        datapoint = collector.collect()

        assert datapoint.value == 999.0

    def test_collect_csv_format(self, requests_mock):
        """Test collection with CSV response format."""
        config = {
            "url": "http://api.example.com/export.csv",
            "response_format": "csv",
            "value_path": "count",
        }

        # Mock CSV response
        csv_data = "timestamp,count\n2024-11-01,42\n2024-11-02,50\n"
        requests_mock.get("http://api.example.com/export.csv", text=csv_data)

        collector = HTTPCollector(config)
        datapoint = collector.collect()

        assert datapoint.value == 42.0  # First row

    def test_collect_csv_with_row_index(self, requests_mock):
        """Test collection with CSV and specific row index."""
        config = {
            "url": "http://api.example.com/export.csv",
            "response_format": "csv",
            "value_path": "count[1]",  # Second row
        }

        csv_data = "timestamp,count\n2024-11-01,42\n2024-11-02,50\n"
        requests_mock.get("http://api.example.com/export.csv", text=csv_data)

        collector = HTTPCollector(config)
        datapoint = collector.collect()

        assert datapoint.value == 50.0  # Second row

    def test_collect_with_at_time(self, requests_mock):
        """Test collection with specific at_time."""
        config = {
            "url": "http://api.example.com/count",
            "response_format": "text",
        }

        requests_mock.get("http://api.example.com/count", text="100")

        collector = HTTPCollector(config)
        at_time = datetime(2024, 11, 1, 12, 0, 0)
        datapoint = collector.collect(at_time=at_time)

        assert datapoint.timestamp == at_time

    def test_http_error_with_retry(self, requests_mock):
        """Test HTTP error with retry logic."""
        config = {
            "url": "http://api.example.com/unstable",
            "response_format": "text",
            "retry_count": 3,
            "retry_delay": 0.1,
        }

        # Mock: fail twice, then succeed
        responses = [
            {"status_code": 500},
            {"status_code": 503},
            {"text": "42", "status_code": 200},
        ]
        requests_mock.get("http://api.example.com/unstable", responses)

        collector = HTTPCollector(config)
        datapoint = collector.collect()

        assert datapoint.value == 42.0
        assert requests_mock.call_count == 3  # 2 failures + 1 success

    def test_http_error_exhausted_retries(self, requests_mock):
        """Test HTTP error with exhausted retries."""
        config = {
            "url": "http://api.example.com/broken",
            "response_format": "text",
            "retry_count": 2,
            "retry_delay": 0.1,
        }

        # Mock: always fail
        requests_mock.get("http://api.example.com/broken", status_code=500)

        collector = HTTPCollector(config)

        with pytest.raises(CollectionError, match="failed after 2 attempts"):
            collector.collect()

        assert requests_mock.call_count == 2

    def test_invalid_json_path(self, requests_mock):
        """Test error handling for invalid JSON path."""
        config = {
            "url": "http://api.example.com/metrics",
            "response_format": "json",
            "value_path": "nonexistent.path",
        }

        requests_mock.get("http://api.example.com/metrics", json={"count": 123})

        collector = HTTPCollector(config)

        with pytest.raises(CollectionError, match="Failed to extract value"):
            collector.collect()

    def test_invalid_numeric_value(self, requests_mock):
        """Test error handling for non-numeric text response."""
        config = {
            "url": "http://api.example.com/bad",
            "response_format": "text",
        }

        requests_mock.get("http://api.example.com/bad", text="not_a_number")

        collector = HTTPCollector(config)

        with pytest.raises(CollectionError, match="Failed to extract value"):
            collector.collect()

    def test_close(self, requests_mock):
        """Test that close() disposes session."""
        config = {
            "url": "http://api.example.com/count",
            "response_format": "text",
        }

        requests_mock.get("http://api.example.com/count", text="42")

        collector = HTTPCollector(config)

        # Trigger request
        collector.collect()
        assert collector.session is not None

        # Close
        collector.close()
        assert collector.session is None


class TestHTTPCollectorEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_response_text(self, requests_mock):
        """Test handling of empty text response."""
        config = {
            "url": "http://api.example.com/empty",
            "response_format": "text",
        }

        requests_mock.get("http://api.example.com/empty", text="")

        collector = HTTPCollector(config)

        with pytest.raises(CollectionError):
            collector.collect()

    def test_timeout_configuration(self):
        """Test custom timeout configuration."""
        config = {
            "url": "http://api.example.com/slow",
            "response_format": "text",
            "timeout": 5,
        }

        collector = HTTPCollector(config)
        assert collector.timeout == 5

    def test_ssl_verification_disabled(self, requests_mock):
        """Test disabling SSL verification."""
        config = {
            "url": "https://insecure.example.com/metrics",
            "response_format": "text",
            "verify_ssl": False,
        }

        requests_mock.get("https://insecure.example.com/metrics", text="100")

        collector = HTTPCollector(config)
        assert collector.verify_ssl is False

        datapoint = collector.collect()
        assert datapoint.value == 100.0
