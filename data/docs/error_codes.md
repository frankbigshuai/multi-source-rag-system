# DataFlow Pro Error Codes Reference

## Overview

This document describes all error codes returned by DataFlow Pro. Each error includes a code, a human-readable message, likely causes, and recommended remediation steps.

## Connection Errors (ERR_6xx)

### ERR_601 — Connection Timeout

**Description**: The connection to a data source or sink timed out before completing the handshake.

**Default timeout**: 30 seconds (configurable via `connection.timeout` in settings.yaml)

**Common Causes**:
- Remote host is unreachable or behind a firewall
- Network latency exceeds the configured timeout
- The target service is overloaded and not responding

**Resolution**:
1. Verify the host is reachable: `ping <host>` or `telnet <host> <port>`
2. Check firewall rules to ensure the port is open
3. If the network is high-latency (e.g., cross-region cloud), consider increasing `connection.timeout` slightly, but do not exceed 60 seconds as it may indicate a deeper infrastructure problem
4. Check the target service's health status

**Example Log Entry**:
```
ERROR [connector] ERR_601: Connection timeout after 30s to kafka-prod:9092
```

### ERR_602 — Authentication Failure

**Description**: The provided credentials were rejected by the remote service.

**Common Causes**:
- Expired API token or password
- Incorrect username/password
- IP address not whitelisted in the remote service

**Resolution**:
1. Regenerate credentials in the target service
2. Update the source/sink configuration in DataFlow Pro
3. Test the connection using `POST /sources/{source_id}/test`

### ERR_603 — Connection Refused

**Description**: The target host actively refused the connection, meaning the port is closed or the service is not running.

**Resolution**:
1. Ensure the target service is running
2. Verify the port number in the source configuration
3. Check if a firewall or security group is blocking the port

### ERR_604 — DNS Resolution Failure

**Description**: The hostname could not be resolved to an IP address.

**Resolution**:
1. Verify the hostname is correct
2. Check DNS configuration on the DataFlow Pro host
3. Use an IP address directly to test if DNS is the issue

### ERR_605 — SSL/TLS Handshake Failed

**Description**: The SSL/TLS negotiation with the remote service failed.

**Common Causes**:
- Certificate expired or invalid
- Mismatched TLS version (DataFlow Pro requires TLS 1.2+)
- Self-signed certificate not trusted

**Resolution**:
1. Check certificate expiry: `openssl s_client -connect <host>:<port>`
2. Add the certificate to the trusted store if self-signed
3. Ensure `security_protocol` in source config matches the remote service

## Pipeline Errors (ERR_7xx)

### ERR_701 — Transform Script Error

**Description**: The pipeline's transform script threw an exception during execution.

**Resolution**:
Check the pipeline logs for the specific script exception. Common issues: syntax errors, missing fields in the data schema, division by zero.

### ERR_702 — Schema Validation Failed

**Description**: The incoming data does not match the expected schema.

**Resolution**:
1. Review the schema definition in the pipeline configuration
2. Enable `options.schema_evolution: true` to allow new fields
3. Check the source data for unexpected nulls or type changes

### ERR_703 — Sink Write Failed

**Description**: Data could not be written to the sink.

**Common Causes**:
- Disk full on the sink host
- Database table locked or write permissions revoked
- Kafka topic partition leader not available

### ERR_704 — Pipeline Overload

**Description**: The pipeline's input queue exceeded the maximum size (`max_queue_size`).

**Resolution**:
1. Increase `options.parallelism` to process faster
2. Reduce `options.batch_size` to flush more frequently
3. Scale horizontally by adding more worker nodes

## System Errors (ERR_9xx)

### ERR_901 — Out of Memory

**Description**: The DataFlow engine ran out of heap memory.

**Resolution**:
Increase Java heap size in `/opt/dataflow-pro/bin/engine.conf`:
```
JAVA_OPTS="-Xms4g -Xmx8g"
```

### ERR_902 — License Expired

**Description**: The DataFlow Pro license has expired. All pipelines will be suspended.

**Resolution**:
Contact sales@dataflowpro.io to renew your license.

### ERR_999 — Unknown Internal Error

**Description**: An unexpected internal error occurred. This is a catch-all for errors not covered by other codes.

**Resolution**:
1. Check the full stack trace in `/var/log/dataflow-pro/error.log`
2. If the error is reproducible, collect the logs and contact support at support@dataflowpro.io
3. Include the `trace_id` from the log entry when filing a support ticket

## Error Code Summary Table

| Code    | Category    | Short Description              |
|---------|-------------|-------------------------------|
| ERR_601 | Connection  | Connection timeout             |
| ERR_602 | Connection  | Authentication failure         |
| ERR_603 | Connection  | Connection refused             |
| ERR_604 | Connection  | DNS resolution failure         |
| ERR_605 | Connection  | SSL/TLS handshake failed       |
| ERR_701 | Pipeline    | Transform script error         |
| ERR_702 | Pipeline    | Schema validation failed       |
| ERR_703 | Pipeline    | Sink write failed              |
| ERR_704 | Pipeline    | Pipeline overload              |
| ERR_901 | System      | Out of memory                  |
| ERR_902 | System      | License expired                |
| ERR_999 | System      | Unknown internal error         |
