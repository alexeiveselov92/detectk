"""HTTP/REST API collector for DetectK."""

import io
import json
import logging
import time
from datetime import datetime
from typing import Any

import pandas as pd
import requests
from requests.exceptions import RequestException

from detectk.base import BaseCollector
from detectk.exceptions import CollectionError, ConfigurationError
from detectk.models import DataPoint
from detectk.registry import CollectorRegistry

logger = logging.getLogger(__name__)


@CollectorRegistry.register("http")
class HTTPCollector(BaseCollector):
    """HTTP/REST API collector.

    Collects metrics from HTTP endpoints with support for various
    response formats (JSON, text, CSV) and authentication methods.

    Configuration:
        url: API endpoint URL (required)
        method: HTTP method - GET or POST (default: GET)
        headers: Custom HTTP headers (optional)
        params: Query parameters for GET (optional)
        json: JSON body for POST (optional)
        data: Form data for POST (optional)
        response_format: Response format - json, text, csv (required)
        value_path: Path to extract value from response (for JSON/CSV)
        timeout: Request timeout in seconds (default: 30)
        verify_ssl: Verify SSL certificates (default: True)
        retry_count: Number of retries on failure (default: 3)
        retry_delay: Delay between retries in seconds (default: 1)

    Response Formats:
        - json: Extract value using JSONPath (dot notation)
        - text: Response body is direct numeric value
        - csv: Extract value from CSV (requires value_path)

    Example (JSON):
        >>> config = {
        ...     "url": "http://api.example.com/metrics",
        ...     "response_format": "json",
        ...     "value_path": "data.active_users",
        ...     "headers": {"Authorization": "Bearer token"}
        ... }
        >>> collector = HTTPCollector(config)
        >>> datapoint = collector.collect()

    Example (Prometheus):
        >>> config = {
        ...     "url": "http://prometheus:9090/api/v1/query",
        ...     "params": {"query": "up{job='api'}"},
        ...     "response_format": "json",
        ...     "value_path": "data.result[0].value[1]"
        ... }
        >>> collector = HTTPCollector(config)
        >>> datapoint = collector.collect()

    Authentication:
        - API Key: headers: {"X-API-Key": "key"}
        - Bearer: headers: {"Authorization": "Bearer token"}
        - Basic Auth: headers: {"Authorization": "Basic base64"}
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize HTTP collector.

        Args:
            config: Collector configuration

        Raises:
            ConfigurationError: If configuration is invalid
        """
        self.config = config
        self.validate_config(config)

        # Extract parameters
        self.url = config["url"]
        self.method = config.get("method", "GET").upper()
        self.headers = config.get("headers", {})
        self.params = config.get("params", {})
        self.json_body = config.get("json")
        self.data = config.get("data")
        self.response_format = config["response_format"]
        self.value_path = config.get("value_path")
        self.timeout = config.get("timeout", 30)
        self.verify_ssl = config.get("verify_ssl", True)
        self.retry_count = config.get("retry_count", 3)
        self.retry_delay = config.get("retry_delay", 1)

        # Create session for connection pooling
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def validate_config(self, config: dict[str, Any]) -> None:
        """Validate collector configuration.

        Args:
            config: Configuration to validate

        Raises:
            ConfigurationError: If configuration is invalid
        """
        if "url" not in config:
            raise ConfigurationError(
                "HTTP collector requires 'url' parameter",
                config_path="collector.params",
            )

        if "response_format" not in config:
            raise ConfigurationError(
                "HTTP collector requires 'response_format' parameter",
                config_path="collector.params",
            )

        response_format = config["response_format"]
        if response_format not in ("json", "text", "csv"):
            raise ConfigurationError(
                f"Invalid response_format: {response_format}. Must be 'json', 'text', or 'csv'",
                config_path="collector.params.response_format",
            )

        # value_path required for json and csv
        if response_format in ("json", "csv") and "value_path" not in config:
            raise ConfigurationError(
                f"response_format '{response_format}' requires 'value_path' parameter",
                config_path="collector.params",
            )

        # Validate method
        method = config.get("method", "GET").upper()
        if method not in ("GET", "POST"):
            raise ConfigurationError(
                f"Invalid HTTP method: {method}. Must be 'GET' or 'POST'",
                config_path="collector.params.method",
            )

    def collect_bulk(
        self,
        period_start: datetime,
        period_finish: datetime,
    ) -> list[DataPoint]:
        """Collect metric value from HTTP endpoint.

        Note: Most HTTP APIs return current/latest value, not time series.
        This method returns a single datapoint with timestamp = period_finish.

        For time series HTTP APIs, the collector can be extended to parse
        multiple datapoints from the response.

        Args:
            period_start: Start of time range (for time series APIs)
            period_finish: End of time range (used as timestamp)

        Returns:
            List with single DataPoint (timestamp = period_finish)

        Raises:
            CollectionError: If HTTP request fails or response parsing fails
        """
        # Use period_finish as collection timestamp
        collection_time = period_finish

        # Retry logic
        last_error = None
        for attempt in range(self.retry_count):
            try:
                # Make HTTP request
                logger.debug(f"HTTP {self.method} request to {self.url} (attempt {attempt + 1})")

                if self.method == "GET":
                    response = self.session.get(
                        self.url,
                        params=self.params,
                        timeout=self.timeout,
                        verify=self.verify_ssl,
                    )
                else:  # POST
                    response = self.session.post(
                        self.url,
                        params=self.params,
                        json=self.json_body,
                        data=self.data,
                        timeout=self.timeout,
                        verify=self.verify_ssl,
                    )

                # Check HTTP status
                response.raise_for_status()

                # Parse response based on format
                value = self._parse_response(response)

                logger.debug(f"Collected value: {value}")

                return [DataPoint(
                    timestamp=collection_time,
                    value=value,
                    is_missing=False,
                    metadata={
                        "source": "http",
                        "url": self.url,
                        "status_code": response.status_code,
                    },
                )]

            except RequestException as e:
                last_error = e
                logger.warning(
                    f"HTTP request failed (attempt {attempt + 1}/{self.retry_count}): {e}"
                )

                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)
                continue

            except Exception as e:
                raise CollectionError(
                    f"Failed to parse HTTP response: {e}",
                    source="http",
                )

        # All retries exhausted
        raise CollectionError(
            f"HTTP request failed after {self.retry_count} attempts: {last_error}",
            source="http",
        )

    def _parse_response(self, response: requests.Response) -> float:
        """Parse HTTP response and extract value.

        Args:
            response: HTTP response object

        Returns:
            Extracted numeric value

        Raises:
            CollectionError: If parsing fails
        """
        try:
            if self.response_format == "text":
                # Response body is direct numeric value
                value_str = response.text.strip()
                return float(value_str)

            elif self.response_format == "json":
                # Parse JSON and extract value using path
                data = response.json()
                value = self._extract_json_value(data, self.value_path)
                return float(value)

            elif self.response_format == "csv":
                # Parse CSV and extract value
                df = pd.read_csv(io.StringIO(response.text))
                value = self._extract_csv_value(df, self.value_path)
                return float(value)

            else:
                raise CollectionError(
                    f"Unsupported response format: {self.response_format}",
                    source="http",
                )

        except (ValueError, TypeError, KeyError, IndexError) as e:
            raise CollectionError(
                f"Failed to extract value from {self.response_format} response: {e}",
                source="http",
            )

    def _extract_json_value(self, data: Any, path: str) -> Any:
        """Extract value from JSON using dot notation path.

        Args:
            data: JSON data (dict or list)
            path: Dot notation path (e.g., "data.result[0].value")

        Returns:
            Extracted value

        Raises:
            KeyError: If path not found
            IndexError: If array index out of bounds

        Examples:
            >>> data = {"metrics": {"count": 42}}
            >>> _extract_json_value(data, "metrics.count")
            42

            >>> data = {"data": {"result": [{"value": [0, "123"]}]}}
            >>> _extract_json_value(data, "data.result[0].value[1]")
            "123"
        """
        current = data

        # Split path by dots, handling array indexing
        parts = path.replace("]", "").replace("[", ".").split(".")

        for part in parts:
            if not part:  # Skip empty parts
                continue

            if part.isdigit():
                # Array index
                current = current[int(part)]
            else:
                # Object key
                current = current[part]

        return current

    def _extract_csv_value(self, df: pd.DataFrame, path: str) -> Any:
        """Extract value from CSV DataFrame.

        Args:
            df: pandas DataFrame
            path: Path in format "column_name" or "column_name[row_index]"

        Returns:
            Extracted value

        Examples:
            >>> df = pd.DataFrame({"value": [10, 20, 30]})
            >>> _extract_csv_value(df, "value")  # First row
            10

            >>> _extract_csv_value(df, "value[1]")  # Second row
            20
        """
        # Check if path includes row index
        if "[" in path:
            column, index_part = path.split("[")
            row_index = int(index_part.rstrip("]"))
            return df[column].iloc[row_index]
        else:
            # Default to first row
            return df[path].iloc[0]

    def close(self) -> None:
        """Close HTTP session and cleanup resources."""
        if self.session:
            logger.debug("Closing HTTP session")
            self.session.close()
            self.session = None
