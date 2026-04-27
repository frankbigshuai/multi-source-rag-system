# DataFlow Pro API Reference

## Overview

The DataFlow Pro REST API allows programmatic control of pipelines, data sources, and monitoring. All endpoints are authenticated using Bearer tokens.

Base URL: `http://<host>:8080/api/v1`

## Authentication

All API calls require an `Authorization` header:

```
Authorization: Bearer <your-api-token>
```

Tokens are generated via:

```bash
dataflow token create --name "my-app" --expires 90d
```

## Pipeline Endpoints

### Create Pipeline

```
POST /pipelines
```

**Request Body:**

```json
{
  "name": "my-pipeline",
  "source": {
    "type": "kafka",
    "topic": "events",
    "broker": "localhost:9092"
  },
  "sink": {
    "type": "postgres",
    "table": "processed_events"
  },
  "transform": {
    "script": "base64-encoded-transform-script"
  },
  "options": {
    "batch_size": 500,
    "flush_interval": 10,
    "parallelism": 4
  }
}
```

**Response:**

```json
{
  "pipeline_id": "pip_abc123",
  "status": "created",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### List Pipelines

```
GET /pipelines
```

Query parameters:
- `status` (optional): filter by `running`, `stopped`, `failed`
- `limit` (optional): default 20, max 100
- `offset` (optional): for pagination

### Get Pipeline Status

```
GET /pipelines/{pipeline_id}
```

**Response:**

```json
{
  "pipeline_id": "pip_abc123",
  "name": "my-pipeline",
  "status": "running",
  "metrics": {
    "records_processed": 148230,
    "errors": 2,
    "throughput_rps": 1240,
    "lag_ms": 45
  }
}
```

### Start / Stop Pipeline

```
POST /pipelines/{pipeline_id}/start
POST /pipelines/{pipeline_id}/stop
```

### Delete Pipeline

```
DELETE /pipelines/{pipeline_id}
```

Returns `204 No Content` on success.

## Data Source Endpoints

### Register Data Source

```
POST /sources
```

**Request Body:**

```json
{
  "name": "prod-kafka",
  "type": "kafka",
  "config": {
    "brokers": ["kafka1:9092", "kafka2:9092"],
    "security_protocol": "SASL_SSL",
    "sasl_mechanism": "PLAIN"
  }
}
```

Supported source types: `kafka`, `postgres`, `mysql`, `s3`, `http`, `file`.

### Test Connection

```
POST /sources/{source_id}/test
```

Returns `{"connected": true, "latency_ms": 12}` or an error with the relevant error code.

## Monitoring Endpoints

### Get System Metrics

```
GET /metrics
```

Returns CPU, memory, disk usage, and pipeline statistics.

### Get Logs

```
GET /logs
```

Query parameters:
- `pipeline_id` (optional)
- `level`: `INFO`, `WARN`, `ERROR`
- `from` / `to`: ISO 8601 timestamps
- `limit`: default 100

## Webhook Configuration

DataFlow Pro can send webhook notifications on pipeline events:

```
POST /webhooks
```

```json
{
  "url": "https://your-service.com/hooks/dataflow",
  "events": ["pipeline.failed", "pipeline.completed", "error.critical"],
  "secret": "your-webhook-secret"
}
```

## Rate Limiting

The API enforces rate limits:
- Standard tier: 100 requests/minute
- Enterprise tier: 1000 requests/minute

When the limit is exceeded, the API returns `429 Too Many Requests` with a `Retry-After` header.

## SDK Libraries

Official SDKs are available:
- Python: `pip install dataflow-pro-sdk`
- Node.js: `npm install @dataflowpro/sdk`
- Java: available on Maven Central as `io.dataflowpro:sdk:2.3.0`

## Versioning

The current API version is `v1`. Breaking changes will be introduced in `v2` with a 6-month deprecation window.
