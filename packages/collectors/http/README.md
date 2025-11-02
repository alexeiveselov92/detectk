# DetectK HTTP Collector

HTTP/REST API collector for DetectK with support for various response formats and authentication methods.

## Installation

```bash
pip install detectk-collectors-http
```

## Features

- **Response Formats**: JSON, plain text, CSV
- **Authentication**: API key, Bearer token, Basic Auth, custom headers
- **Flexible Value Extraction**: JSONPath, regex, direct value
- **Error Handling**: Retry logic, timeout configuration
- **HTTP Methods**: GET, POST
- **SSL Verification**: Configurable

## Usage

### JSON API (JSONPath extraction)

```yaml
name: "prometheus_metric"
description: "Collect metric from Prometheus API"

collector:
  type: "http"
  params:
    url: "http://prometheus:9090/api/v1/query"
    method: "GET"
    params:
      query: "up{job='api'}"
    response_format: "json"
    value_path: "data.result[0].value[1]"  # JSONPath
    timeout: 10

detector:
  type: "threshold"
  params:
    threshold: 0.5
    operator: "less_than"
```

### Plain Text Response

```yaml
collector:
  type: "http"
  params:
    url: "http://api.example.com/metrics/count"
    response_format: "text"
    # Response is direct numeric value
```

### With Authentication

```yaml
collector:
  type: "http"
  params:
    url: "https://api.example.com/metrics"
    headers:
      Authorization: "Bearer ${API_TOKEN}"
    response_format: "json"
    value_path: "metrics.active_users"
```

### POST Request

```yaml
collector:
  type: "http"
  params:
    url: "https://api.example.com/query"
    method: "POST"
    json:
      query: "SELECT COUNT(*) FROM events"
      time_range: "1h"
    headers:
      X-API-Key: "${API_KEY}"
    response_format: "json"
    value_path: "result.count"
```

## Configuration

### Required Parameters

- `url`: API endpoint URL
- `response_format`: Response format ("json", "text", "csv")
- `value_path`: Path to extract value (for JSON/CSV)

### Optional Parameters

- `method`: HTTP method (default: "GET")
- `headers`: Custom HTTP headers
- `params`: Query parameters (GET)
- `json`: JSON body (POST)
- `data`: Form data (POST)
- `timeout`: Request timeout in seconds (default: 30)
- `verify_ssl`: Verify SSL certificates (default: True)
- `retry_count`: Number of retries (default: 3)
- `retry_delay`: Delay between retries in seconds (default: 1)

### Authentication Examples

**API Key (Header):**
```yaml
headers:
  X-API-Key: "${API_KEY}"
```

**Bearer Token:**
```yaml
headers:
  Authorization: "Bearer ${TOKEN}"
```

**Basic Auth:**
```yaml
headers:
  Authorization: "Basic ${BASE64_CREDENTIALS}"
```

### JSONPath Syntax

Use dot notation and array indexing:
- `data.value` - Simple path
- `data.result[0].value` - Array indexing
- `metrics.active_users` - Nested objects

## Examples

See `examples/http/` directory for complete configurations:
- Prometheus query
- Grafana API
- Custom REST API
- Health check endpoint

## License

MIT
