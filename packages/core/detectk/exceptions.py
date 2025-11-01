"""Custom exceptions for DetectK framework.

All exceptions inherit from DetectKError base exception for easy catching.
"""


class DetectKError(Exception):
    """Base exception for all DetectK errors.

    All custom exceptions in the framework inherit from this class,
    allowing users to catch all DetectK-specific errors with a single except clause.

    Example:
        >>> try:
        ...     collector.collect()
        ... except DetectKError as e:
        ...     logger.error(f"DetectK error: {e}")
    """

    pass


class ConfigurationError(DetectKError):
    """Raised when configuration is invalid or incomplete.

    Examples:
        - Missing required field in YAML config
        - Invalid detector type
        - Malformed connection string
        - Environment variable not set

    Attributes:
        config_path: Optional path to configuration file
        field: Optional field name that caused error
    """

    def __init__(
        self,
        message: str,
        config_path: str | None = None,
        field: str | None = None,
    ) -> None:
        self.config_path = config_path
        self.field = field
        super().__init__(message)


class CollectionError(DetectKError):
    """Raised when data collection from source fails.

    Examples:
        - Database connection failed
        - Query execution error
        - Network timeout
        - Invalid query result format

    Attributes:
        source: Data source identifier (e.g., database host)
        query: Optional query that failed
    """

    def __init__(
        self,
        message: str,
        source: str | None = None,
        query: str | None = None,
    ) -> None:
        self.source = source
        self.query = query
        super().__init__(message)


class DetectionError(DetectKError):
    """Raised when anomaly detection fails.

    Examples:
        - Insufficient historical data
        - Invalid detector parameters
        - Calculation error (e.g., division by zero)
        - Storage query failed

    Attributes:
        metric_name: Name of metric being detected
        detector_type: Type of detector that failed
    """

    def __init__(
        self,
        message: str,
        metric_name: str | None = None,
        detector_type: str | None = None,
    ) -> None:
        self.metric_name = metric_name
        self.detector_type = detector_type
        super().__init__(message)


class StorageError(DetectKError):
    """Raised when storage operation fails.

    Examples:
        - Table doesn't exist
        - Insert failed
        - Query timeout
        - Connection pool exhausted

    Attributes:
        operation: Operation that failed (save, query, delete)
        table: Table name involved
    """

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        table: str | None = None,
    ) -> None:
        self.operation = operation
        self.table = table
        super().__init__(message)


class AlertError(DetectKError):
    """Raised when alert sending fails.

    Examples:
        - Webhook URL invalid
        - Network timeout
        - Authentication failed
        - Rate limit exceeded

    Attributes:
        channel: Alert channel type (mattermost, slack, etc.)
        endpoint: Endpoint URL that failed
    """

    def __init__(
        self,
        message: str,
        channel: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.channel = channel
        self.endpoint = endpoint
        super().__init__(message)


class RegistryError(DetectKError):
    """Raised when component registration or lookup fails.

    Examples:
        - Component type not found
        - Duplicate registration
        - Component not installed

    Attributes:
        component_type: Type of component (collector, detector, alerter)
        component_name: Name being registered/looked up
    """

    def __init__(
        self,
        message: str,
        component_type: str | None = None,
        component_name: str | None = None,
    ) -> None:
        self.component_type = component_type
        self.component_name = component_name
        super().__init__(message)
