from typing import Any
from datetime import datetime, timezone
from pathlib import Path
import os
import logging
from fastapi import APIRouter, Request

from config.settings import settings
from olav.server.core import state
from olav.server.core.state import ensure_orchestrator_initialized
from olav.server.models.common import HealthResponse, StatusResponse, PublicConfigResponse
from olav.server.auth import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_hive_partition_dirname(dirname: str) -> str:
    """Parse Hive-style partition directory names like 'namespace=prod' -> 'prod'."""
    if "=" in dirname:
        return dirname.split("=", 1)[1]
    return dirname


def _inspect_sq_poller_parquet(
    parquet_root: Path,
    *,
    max_namespaces: int = 5,
    max_hosts: int = 10,
) -> tuple[float | None, int, int, list[str], list[str]]:
    """Inspect SuzieQ sqPoller parquet layout quickly.

    SuzieQ poller output is typically Hive-style partitioned:
      sqPoller/sqvers=*/namespace=*/hostname=*/*.parquet

    We avoid Path.rglob('*.parquet') because it can be slow on large datasets.

    Returns:
        (newest_parquet_mtime, host_dir_count, newest_host_parquet_files, namespaces_sample, hostnames_sample)
    """
    sq_poller_dir = parquet_root / "sqPoller"
    if not sq_poller_dir.exists():
        return None, 0, 0, [], []

    newest_parquet_mtime: float | None = None
    host_dir_count = 0
    newest_host_dir: str | None = None
    newest_host_dir_mtime: float | None = None
    namespaces_sample: list[str] = []
    hostnames_sample: list[str] = []

    try:
        for sqvers_entry in os.scandir(sq_poller_dir):
            if not sqvers_entry.is_dir():
                continue

            for ns_entry in os.scandir(sqvers_entry.path):
                if not ns_entry.is_dir():
                    continue

                namespace = _parse_hive_partition_dirname(ns_entry.name)
                if namespace not in namespaces_sample and len(namespaces_sample) < max_namespaces:
                    namespaces_sample.append(namespace)

                for host_entry in os.scandir(ns_entry.path):
                    if not host_entry.is_dir():
                        continue

                    host_dir_count += 1
                    hostname = _parse_hive_partition_dirname(host_entry.name)
                    if hostname not in hostnames_sample and len(hostnames_sample) < max_hosts:
                        hostnames_sample.append(hostname)

                    try:
                        host_stat = host_entry.stat()
                    except OSError:
                        continue

                    if newest_host_dir_mtime is None or host_stat.st_mtime > newest_host_dir_mtime:
                        newest_host_dir_mtime = host_stat.st_mtime
                        newest_host_dir = host_entry.path
    except FileNotFoundError:
        return None, 0, 0, namespaces_sample, hostnames_sample

    if not newest_host_dir:
        return None, 0, 0, namespaces_sample, hostnames_sample

    newest_host_parquet_files = 0
    try:
        for f in os.scandir(newest_host_dir):
            if not f.is_file() or not f.name.endswith(".parquet"):
                continue
            newest_host_parquet_files += 1
            try:
                stat = f.stat()
            except OSError:
                continue
            if newest_parquet_mtime is None or stat.st_mtime > newest_parquet_mtime:
                newest_parquet_mtime = stat.st_mtime
    except FileNotFoundError:
        return None, host_dir_count, 0, namespaces_sample, hostnames_sample

    return newest_parquet_mtime, host_dir_count, newest_host_parquet_files, namespaces_sample, hostnames_sample

@router.get(
    "/health",
    tags=["monitoring"],
    summary="System health check",
    response_model=HealthResponse,
    responses={
        503: {
            "description": "Service is degraded (database or orchestrator unavailable)",
            "content": {
                "application/json": {
                    "example": {
                        "status": "degraded",
                        "version": "0.4.0-beta",
                        "environment": "production",
                        "postgres_connected": False,
                        "orchestrator_ready": False,
                    }
                }
            },
        },
    },
)
async def health_check(request: Request) -> HealthResponse:
    """
    Health check endpoint (no authentication required).

    Use this endpoint for:
    - Load balancer health checks
    - Kubernetes liveness/readiness probes
    - Monitoring system status verification
    """
    # Attempt lazy initialization if not ready
    if not state.orchestrator or not state.checkpointer:
        logger.debug("/health: orchestrator or checkpointer missing, invoking lazy initializer")
        await ensure_orchestrator_initialized(request.app)
    else:
        logger.debug("/health: orchestrator & checkpointer already present")
    
    logger.debug(
        f"/health status snapshot: orch={type(state.orchestrator).__name__ if state.orchestrator else None}, cp={type(state.checkpointer).__name__ if state.checkpointer else None}"
    )
    
    return HealthResponse(
        status="healthy" if state.orchestrator else "degraded",
        version="0.4.0-beta",
        environment=settings.environment,
        postgres_connected=state.checkpointer is not None,
        orchestrator_ready=state.orchestrator is not None,
    )

@router.get(
    "/health/detailed",
    tags=["monitoring"],
    summary="Comprehensive health check for all infrastructure components",
    responses={
        200: {
            "description": "Detailed health status of all services",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "version": "0.4.0-beta",
                        "components": {
                            "server": {"status": "connected", "orchestrator_ready": True},
                            "postgresql": {"status": "connected", "version": "PostgreSQL 16.1"},
                            "opensearch": {"status": "green", "nodes": 1},
                            "redis": {"status": "connected"},
                            "netbox": {"status": "connected", "url": "http://netbox:8080"},
                            "llm": {"status": "connected", "provider": "openai", "model": "gpt-4-turbo"},
                            "suzieq": {"status": "available", "tables": 25}
                        }
                    }
                }
            },
        },
    },
)
async def detailed_health_check() -> dict[str, Any]:
    """
    Comprehensive health check endpoint that aggregates status of all infrastructure components.
    
    This endpoint is used by the CLI 'olav status' command to display a complete
    system health overview. Checks performed:
    
    - Server: Orchestrator readiness
    - PostgreSQL: LangGraph checkpointer connection
    - OpenSearch: Cluster health and node count
    - Redis: Cache availability (optional)
    - NetBox: API connectivity (optional)
    - LLM: Provider connectivity
    - SuzieQ: Parquet data availability
    
    Returns:
        Dict with overall status and component-level details
    """
    components: dict[str, Any] = {}
    overall_healthy = True

    # 1. Server/Orchestrator
    components["server"] = {
        "status": "connected" if state.orchestrator else "not_ready",
        "orchestrator_ready": state.orchestrator is not None,
        "version": "0.4.0-beta",
    }
    if not state.orchestrator:
        overall_healthy = False

    # 2. PostgreSQL
    try:
        import asyncpg
        # Use settings or fallback. Note: In Docker it uses 'postgres' host, locally we might need localhost if running outside
        postgres_uri = settings.postgres_uri or "postgresql://olav:OlavPG123!@postgres:5432/olav"
        
        # Connect directly
        conn = await asyncpg.connect(postgres_uri, timeout=5)
        try:
            version = await conn.fetchval("SELECT version()")
            pg_version = version[:50] if version else "unknown"
        finally:
            await conn.close()
            
        components["postgresql"] = {"status": "connected", "version": pg_version}
    except Exception as e:
        components["postgresql"] = {"status": "failed", "error": str(e)[:60]}
        overall_healthy = False

    # 3. OpenSearch
    try:
        import httpx
        opensearch_url = settings.opensearch_url or "http://opensearch:9200"
        
        request_kwargs: dict = {"timeout": 5}
        if settings.opensearch_username and settings.opensearch_password:
            request_kwargs["auth"] = (settings.opensearch_username, settings.opensearch_password)

        # trust_env=False is critical for Docker networking to bypass local proxies
        async with httpx.AsyncClient(
            verify=settings.opensearch_verify_certs,
            trust_env=False,
            **request_kwargs,
        ) as client:
            resp = await client.get(f"{opensearch_url}/_cluster/health")
            
            if resp.status_code == 200:
                health_data = resp.json()
                components["opensearch"] = {
                    "status": health_data.get("status", "unknown"),
                    "nodes": health_data.get("number_of_nodes", 0),
                }
                if health_data.get("status") == "red":
                    overall_healthy = False
            elif resp.status_code == 401:
                components["opensearch"] = {"status": "auth_failed"}
                overall_healthy = False
            else:
                components["opensearch"] = {
                    "status": "unhealthy",
                    "http_code": resp.status_code,
                }
                overall_healthy = False
    except Exception as e:
        components["opensearch"] = {"status": "failed", "error": str(e)[:60]}
        overall_healthy = False

    # 4. Redis (optional)
    try:
        import redis.asyncio as aioredis
        redis_url = settings.redis_url
        if redis_url:
            r = aioredis.from_url(redis_url, socket_timeout=3)
            await r.ping()
            await r.close()
            components["redis"] = {"status": "connected"}
        else:
            components["redis"] = {"status": "not_configured", "note": "Using in-memory cache"}
    except Exception:
        components["redis"] = {"status": "not_available", "fallback": "memory"}

    # 5. NetBox (optional but recommended)
    try:
        import httpx
        netbox_url = settings.netbox_url
        netbox_token = settings.netbox_token
        if netbox_url and netbox_token:
            async with httpx.AsyncClient(verify=False, timeout=5) as client:
                resp = await client.get(
                    f"{netbox_url}/api/status/",
                    headers={"Authorization": f"Token {netbox_token}"}
                )
                if resp.status_code == 200:
                    components["netbox"] = {"status": "connected", "url": netbox_url}
                else:
                    components["netbox"] = {"status": "error", "code": resp.status_code}
                    # Don't fail overall health for NetBox as it might be optional for some modes
    except Exception as e:
        components["netbox"] = {"status": "failed", "error": str(e)[:60]}

    # 6. LLM Provider
    try:
        # Simple check if API key is present
        if settings.llm_api_key:
            components["llm"] = {
                "status": "configured",
                "provider": settings.llm_provider,
                "model": settings.llm_model_name
            }
        else:
            components["llm"] = {"status": "missing_key"}
            overall_healthy = False
    except Exception:
        components["llm"] = {"status": "error"}

    # 7. SuzieQ (GUI reachability + Parquet data freshness)
    # We treat SuzieQ as REQUIRED in this stack: if GUI is unreachable or no recent parquet data,
    # overall health is degraded.
    try:
        import httpx

        suzieq_status: dict[str, Any] = {}

        # 7.1 GUI healthz
        # In docker-compose network, service name is 'suzieq'. When running locally, it may be localhost.
        candidate_urls = [
            "http://suzieq:8501/healthz",
            "http://localhost:8501/healthz",
        ]

        gui_ok = False
        last_gui_url: str | None = None
        for url in candidate_urls:
            try:
                async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                    resp = await client.get(url)
                if resp.status_code == 200:
                    gui_ok = True
                    last_gui_url = url
                    break
                last_gui_url = url
            except Exception:
                last_gui_url = url

        suzieq_status["gui"] = {
            "status": "healthy" if gui_ok else "unreachable",
            "url": last_gui_url,
        }

        # 7.2 Parquet data presence + freshness
        parquet_dir = Path(settings.suzieq_data_dir)
        (
            newest_mtime,
            host_dir_count,
            newest_host_parquet_files,
            namespaces_sample,
            hostnames_sample,
        ) = _inspect_sq_poller_parquet(parquet_dir)

        if not newest_mtime or host_dir_count == 0:
            suzieq_status["data"] = {
                "status": "no_data",
                "parquet_dir": str(parquet_dir),
                # Back-compat: this historically reported a count, but it was effectively host-dir count.
                "parquet_files": host_dir_count,
                "host_dirs": host_dir_count,
                "namespaces_sample": namespaces_sample,
                "hostnames_sample": hostnames_sample,
            }
            overall_healthy = False
        else:
            newest_dt = datetime.fromtimestamp(newest_mtime, tz=timezone.utc)
            age_seconds = max(0, int((datetime.now(tz=timezone.utc) - newest_dt).total_seconds()))

            # Default threshold: 2 hours. Override with SUZIEQ_MAX_DATA_AGE_SECONDS if set.
            max_age_seconds = int(getattr(settings, "suzieq_max_data_age_seconds", 7200))
            data_ok = age_seconds <= max_age_seconds

            suzieq_status["data"] = {
                "status": "fresh" if data_ok else "stale",
                "parquet_dir": str(parquet_dir),
                # Back-compat: keep existing key but also provide clearer counts.
                "parquet_files": host_dir_count,
                "host_dirs": host_dir_count,
                "newest_host_parquet_files": newest_host_parquet_files,
                "newest_parquet_utc": newest_dt.isoformat(),
                "age_seconds": age_seconds,
                "max_age_seconds": max_age_seconds,
                "namespaces_sample": namespaces_sample,
                "hostnames_sample": hostnames_sample,
            }

            if not data_ok:
                overall_healthy = False

        # 7.3 Overall SuzieQ component status
        if not gui_ok:
            overall_healthy = False

        suzieq_status["status"] = "healthy" if (gui_ok and suzieq_status.get("data", {}).get("status") == "fresh") else "degraded"
        components["suzieq"] = suzieq_status
    except Exception as e:
        components["suzieq"] = {"status": "failed", "error": str(e)[:120]}
        overall_healthy = False

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "version": "0.4.0-beta",
        "components": components
    }

@router.get(
    "/status",
    response_model=StatusResponse,
    tags=["auth"],
    summary="Get detailed server status and current user information",
    responses={
        200: {
            "description": "Server status and user info",
            "content": {
                "application/json": {
                    "example": {
                        "health": {
                            "status": "healthy",
                            "version": "0.4.0-beta",
                            "environment": "production",
                            "postgres_connected": True,
                            "orchestrator_ready": True,
                        },
                        "user": {
                            "username": "admin",
                            "role": "admin",
                            "disabled": False,
                        },
                    }
                }
            },
        },
        401: {
            "description": "Missing or invalid JWT token",
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
        },
    },
)
async def get_status(request: Request, current_user: CurrentUser) -> StatusResponse:
    """
    Get detailed server status and current user information.

    **Required**: Bearer token from `/auth/login`

    **Example Request**:
    ```bash
    curl http://localhost:8000/status \\
      -H "Authorization: Bearer eyJ0eXAi..."
    ```
    """
    health = await health_check(request)
    return StatusResponse(health=health, user=current_user)


@router.get(
    "/config",
    tags=["monitoring"],
    summary="Get public configuration for clients",
    responses={
        200: {
            "description": "Public configuration (non-sensitive)",
            "content": {
                "application/json": {
                    "example": {
                        "version": "0.4.0-beta",
                        "environment": "production",
                        "features": {
                            "expert_mode": False,
                            "agentic_rag_enabled": True,
                        },
                        "ui": {
                            "default_language": "zh-CN",
                            "streaming_enabled": True,
                        },
                        "limits": {
                            "max_query_length": 2000,
                            "session_timeout_minutes": 60,
                        },
                        "workflows": ["query_diagnostic", "device_execution", "netbox_management", "deep_dive"],
                    }
                }
            },
        },
    },
)
async def get_public_config() -> PublicConfigResponse:
    """
    Get public configuration for client initialization.

    This endpoint exposes **non-sensitive** settings that a client
    may need for initialization and feature detection.

    **No authentication required** - safe for public access.

    **Use Cases**:
    - Feature flag detection (enable/disable UI elements)
    - Timeout/limit configuration
    - Available workflow discovery
    - Environment detection (dev/prod styling)
    """
    return PublicConfigResponse(
        version="0.4.0-beta",
        environment=settings.environment,
        features={
            "expert_mode": settings.expert_mode,
            "agentic_rag_enabled": settings.enable_agentic_rag,
            "deep_dive_memory_enabled": settings.enable_deep_dive_memory,
            "dynamic_router_enabled": settings.use_dynamic_router,
        },
        ui={
            "default_language": "zh-CN",
            "streaming_enabled": settings.stream_stateless,
            "websocket_heartbeat_seconds": settings.websocket_heartbeat_interval,
        },
        limits={
            "max_query_length": 2000,
            "session_timeout_minutes": settings.token_max_age_hours * 60,  # Convert hours to minutes
            "rate_limit_rpm": settings.api_rate_limit_rpm if settings.api_rate_limit_enabled else None,
        },
        workflows=["query_diagnostic", "device_execution", "netbox_management", "deep_dive"],
    )
