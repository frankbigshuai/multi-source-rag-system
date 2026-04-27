# DataFlow Pro Installation Guide

## Overview

DataFlow Pro is an enterprise-grade data pipeline management platform designed for real-time stream processing, ETL workflows, and multi-source data integration. This guide covers installation, configuration, and initial setup for version 2.3.

## System Requirements

Before installing DataFlow Pro, ensure your environment meets the following requirements:

### Hardware Requirements
- **CPU**: 4 cores minimum, 8 cores recommended
- **RAM**: 8 GB minimum, 16 GB recommended for production
- **Disk**: 20 GB free space for installation; 100 GB+ recommended for data storage
- **Network**: 100 Mbps minimum, 1 Gbps recommended

### Operating System Support
- Linux: Ubuntu 20.04+, CentOS 8+, Debian 11+
- macOS: 12.0 (Monterey) or later
- Windows: Windows Server 2019+ (limited support — multi-threading is not recommended on Windows; see Known Issues)

### Software Dependencies
- Python 3.9 or higher
- Java 11 or higher (required for the DataFlow engine)
- PostgreSQL 13+ (for metadata storage)
- Redis 6.2+ (for task queue)

## Installation Steps

### Step 1: Download the Package

```bash
wget https://releases.dataflowpro.io/v2.3/dataflow-pro-2.3.tar.gz
tar -xzf dataflow-pro-2.3.tar.gz
cd dataflow-pro-2.3
```

### Step 2: Run the Installer

```bash
sudo ./install.sh --prefix /opt/dataflow-pro
```

The installer will:
1. Check all dependencies
2. Create necessary directories
3. Set up the PostgreSQL schema
4. Configure Redis connection
5. Generate default configuration files

### Step 3: Configure Environment

Edit `/opt/dataflow-pro/config/settings.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 8080
  workers: 4

database:
  host: localhost
  port: 5432
  name: dataflow_meta

connection:
  timeout: 30        # Official default: 30 seconds
  max_retries: 3
  retry_delay: 5
  max_connections: 100
```

**Important**: The connection timeout default is **30 seconds**. This value is calibrated for typical LAN environments. Modifying it beyond recommended values may cause instability.

### Step 4: Start the Service

```bash
sudo systemctl enable dataflow-pro
sudo systemctl start dataflow-pro
```

Verify the service is running:

```bash
sudo systemctl status dataflow-pro
curl http://localhost:8080/health
```

Expected response:
```json
{"status": "healthy", "version": "2.3.0", "uptime": 12}
```

## Plugin Configuration (v2.3)

DataFlow Pro v2.3 introduced the new plugin architecture. Plugins are loaded from `/opt/dataflow-pro/plugins/`.

### Installing a Plugin

```bash
dataflow plugin install <plugin-name>
dataflow plugin list
```

### Plugin Configuration

Each plugin has its own configuration file at `/opt/dataflow-pro/plugins/<name>/config.yaml`. The main settings.yaml includes a plugins section:

```yaml
plugins:
  enabled:
    - kafka-connector
    - s3-exporter
    - postgres-sink
  config_dir: /opt/dataflow-pro/plugins
```

## Upgrading from v2.2

If you are upgrading from DataFlow Pro v2.2:

1. Back up your configuration: `dataflow backup --config`
2. Stop the service: `sudo systemctl stop dataflow-pro`
3. Run the upgrade script: `sudo ./upgrade.sh --from 2.2 --to 2.3`
4. Migrate plugin configs: `dataflow migrate-plugins`
5. Restart: `sudo systemctl start dataflow-pro`

Note: v2.3 plugins are **not backward compatible** with v2.2. All plugins must be reconfigured after upgrading.

## Uninstallation

```bash
sudo systemctl stop dataflow-pro
sudo ./uninstall.sh
```

## Troubleshooting

If the service fails to start, check logs at `/var/log/dataflow-pro/startup.log`. Common issues:
- Port 8080 already in use: change the port in settings.yaml
- PostgreSQL not running: ensure PostgreSQL service is active
- Insufficient permissions: run installer as root or with sudo
