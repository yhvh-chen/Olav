import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


def generate_suzieq_config() -> None:
    """Generate SuzieQ configuration and inventory from environment variables.
    
    Poller Configuration Best Practices:
    - period: Polling interval. For large networks (100+ devices), use 60-300s
    - connect-timeout: SSH/API connect timeout. Increase for slow WAN links
    - cmd-timeout: Per-command execution timeout (some show commands are slow)
    - max-cmd-pipeline: Commands to pipeline per device (reduce for memory)
    - chunked-poll: Enable for large inventories to avoid memory spikes
    - chunk-size: Devices per chunk when chunked-poll enabled
    
    Scaling Guidelines:
    - 1-50 devices: period=15, chunk-size=10
    - 50-200 devices: period=60, chunk-size=25
    - 200-500 devices: period=120, chunk-size=50, chunked-poll=true
    - 500+ devices: period=300, chunk-size=100, chunked-poll=true
    """
    # Use the data directory from docker-compose volume mount
    config_dir = Path("data/generated_configs")
    config_dir.mkdir(parents=True, exist_ok=True)

    # Get environment variables (no hardcoded defaults except for structure)
    rest_api_key = os.getenv("SUZIEQ_REST_API_KEY", os.urandom(16).hex())
    
    # Poller tuning parameters with sensible defaults for medium networks
    poller_period = int(os.getenv("SUZIEQ_POLLER_PERIOD", "60"))  # Increased from 15 to 60
    connect_timeout = int(os.getenv("SUZIEQ_CONNECT_TIMEOUT", "30"))  # Increased from 15 to 30
    cmd_timeout = int(os.getenv("SUZIEQ_CMD_TIMEOUT", "60"))  # Per-command timeout
    max_cmd_pipeline = int(os.getenv("SUZIEQ_MAX_CMD_PIPELINE", "10"))  # Commands in parallel
    
    # Chunked polling for large inventories
    chunked_poll = os.getenv("SUZIEQ_CHUNKED_POLL", "true").lower() == "true"
    chunk_size = int(os.getenv("SUZIEQ_CHUNK_SIZE", "25"))  # Devices per chunk
    
    inventory_update_period = int(os.getenv("SUZIEQ_INVENTORY_UPDATE_PERIOD", "3600"))
    coalescer_period = os.getenv("SUZIEQ_COALESCER_PERIOD", "1h")
    log_level = os.getenv("SUZIEQ_LOG_LEVEL", "WARNING")

    # Generate suzieq-cfg.yml
    config_path = config_dir / "suzieq_config.yml"
    suzieq_config = {
        "data-directory": "/suzieq/parquet",
        "temp-directory": "/tmp/suzieq",
        "rest": {
            "API_KEY": rest_api_key,
            "logging-level": log_level,
            "address": "0.0.0.0",
            "port": 8000,
            "no-https": True,
        },
        "poller": {
            "logging-level": log_level,
            "period": poller_period,
            "connect-timeout": connect_timeout,
            "cmd-timeout": cmd_timeout,
            "max-cmd-pipeline": max_cmd_pipeline,
            "chunked-poll": chunked_poll,
            "chunk-size": chunk_size,
            "log-stdout": True,
            "inventory-file": "/suzieq/config/inventory.yml",
            "update-period": inventory_update_period,
            # Retry configuration for resilience
            "retries-on-auth-fail": 2,
            "ssh-config-file": None,  # Use default SSH config
        },
        "coalescer": {
            "period": coalescer_period,
            "logging-level": log_level,
            "log-stdout": True,
        },
        "analyzer": {
            "timezone": "UTC",
        },
    }

    with open(config_path, "w") as f:
        yaml.dump(suzieq_config, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Generated SuzieQ config at {config_path}")

    # Generate inventory.yml with actual env values (not placeholders)
    # SuzieQ doesn't support ${VAR} substitution except for password: env:VAR
    inventory_path = config_dir / "inventory.yml"

    # Get environment variables - REQUIRED, no defaults for security
    netbox_url = os.getenv("NETBOX_URL")
    netbox_token = os.getenv("NETBOX_TOKEN")
    device_username = os.getenv("DEVICE_USERNAME")
    netbox_tag = os.getenv("NETBOX_DEVICE_TAG", "olav-managed")

    if not all([netbox_url, netbox_token, device_username]):
        msg = "Missing required environment variables: NETBOX_URL, NETBOX_TOKEN, DEVICE_USERNAME"
        raise ValueError(msg)

    inventory_config = {
        "sources": [
            {
                "name": "netbox-olav",
                "type": "netbox",
                "url": netbox_url,
                "token": netbox_token,
                "tag": [netbox_tag],
                "period": inventory_update_period,
            }
        ],
        "devices": [
            {
                "name": "olav-devices",
                "transport": "ssh",
                "ignore-known-hosts": True,
            }
        ],
        "auths": [
            {
                "name": "olav-auth",
                "username": device_username,
                "password": "env:DEVICE_PASSWORD",
            }
        ],
        "namespaces": [
            {
                "name": "default",
                "source": "netbox-olav",
                "device": "olav-devices",
                "auth": "olav-auth",
            }
        ],
    }

    with open(inventory_path, "w") as f:
        yaml.dump(inventory_config, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Generated SuzieQ inventory at {inventory_path}")


def generate_nornir_config() -> None:
    """Generate Nornir configuration from environment variables."""
    # Also use generated_configs directory (same as SuzieQ)
    config_dir = Path("data/generated_configs")
    config_dir.mkdir(parents=True, exist_ok=True)

    # Get environment variables - REQUIRED
    netbox_url = os.getenv("NETBOX_URL")
    netbox_token = os.getenv("NETBOX_TOKEN")
    device_username = os.getenv("DEVICE_USERNAME")
    netbox_tag = os.getenv("NETBOX_DEVICE_TAG", "olav-managed")
    num_workers = int(os.getenv("NORNIR_NUM_WORKERS", "20"))

    if not all([netbox_url, netbox_token, device_username]):
        msg = "Missing required environment variables: NETBOX_URL, NETBOX_TOKEN, DEVICE_USERNAME"
        raise ValueError(msg)

    # Generate nornir_config.yml with placeholders (actual substitution in Python code)
    config_path = config_dir / "nornir_config.yml"
    nornir_config = {
        "inventory": {
            "plugin": "NetBoxInventory2",
            "options": {
                "nb_url": netbox_url,
                "nb_token": netbox_token,
                "ssl_verify": False,
                "filter_parameters": {
                    "tag": [netbox_tag],
                },
                "defaults": {
                    "username": device_username,
                    "password": "${DEVICE_PASSWORD}",  # Placeholder for runtime substitution
                    "platform": "cisco_ios",
                },
            },
        },
        "runner": {
            "plugin": "threaded",
            "options": {
                "num_workers": num_workers,
            },
        },
        "logging": {
            "enabled": False,
        },
    }

    with open(config_path, "w") as f:
        # Add comment header
        f.write("---\n")
        f.write("# Nornir Configuration - Generated from environment variables\n")
        f.write("# Password placeholder ${DEVICE_PASSWORD} is substituted at runtime\n")
        f.write("# See scripts/nornir_verify.py for programmatic configuration\n\n")
        yaml.dump(nornir_config, f, default_flow_style=False, sort_keys=False)

    logger.info(f"Generated Nornir config at {config_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_suzieq_config()
    generate_nornir_config()
