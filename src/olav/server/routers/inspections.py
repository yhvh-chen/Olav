import asyncio
import re
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException

import logging
from config.settings import get_path
from olav.server.auth import CurrentUser
from olav.server.models import (
    InspectionCheck,
    InspectionConfig,
    InspectionCreateRequest,
    InspectionListResponse,
    InspectionRunRequest,
    InspectionRunResponse,
    InspectionUpdateRequest,
    JobListResponse,
    JobStatusResponse,
    ReportDetail,
    ReportListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================
# Inspection Reports API
# ============================================

def _parse_report_metadata(content: str, filename: str) -> dict:
    """Parse metadata from inspection report markdown content."""
    metadata = {
        "title": "Unknown Report",
        "config_name": "unknown",
        "description": None,
        "executed_at": None,
        "duration": None,
        "device_count": 0,
        "check_count": 0,
        "pass_count": 0,
        "fail_count": 0,
        "pass_rate": 0.0,
        "status": "unknown",
        "warnings": [],
    }

    # Extract title
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if title_match:
        metadata["title"] = title_match.group(1).strip()

    # Extract config name
    config_match = re.search(r"\*\*Inspection Config\*\*:\s*(.+)$|\*\*巡检配置\*\*:\s*(.+)$", content, re.MULTILINE)
    if config_match:
        metadata["config_name"] = config_match.group(1).strip()

    # Extract description
    desc_match = re.search(r"\*\*Description\*\*:\s*(.+)$|\*\*描述\*\*:\s*(.+)$", content, re.MULTILINE)
    if desc_match:
        metadata["description"] = desc_match.group(1).strip()

    # Extract execution time
    time_match = re.search(r"\*\*Execution Time\*\*:\s*(.+)$|\*\*执行时间\*\*:\s*(.+)$", content, re.MULTILINE)
    if time_match:
        time_str = time_match.group(1).strip()
        # Extract duration if present (e.g., "2025-11-27 23:10:51 → 23:10:51 (0.2秒)")
        dur_match = re.search(r"\(([^)]+)\)", time_str)
        if dur_match:
            metadata["duration"] = dur_match.group(1)
        # Extract start time
        start_match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", time_str)
        if start_match:
            metadata["executed_at"] = start_match.group(1)

    # Fallback: extract date from filename (e.g., inspection_xxx_20251127_231051.md)
    if not metadata["executed_at"]:
        date_match = re.search(r"(\d{8})_(\d{6})", filename)
        if date_match:
            d, t = date_match.groups()
            metadata["executed_at"] = f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}:{t[4:6]}"

    # Extract device count
    device_match = re.search(r"\*\*Devices\*\*:\s*(\d+)|\*\*设备数\*\*:\s*(\d+)", content)
    if device_match:
        metadata["device_count"] = int(device_match.group(1))

    # Extract check count
    check_match = re.search(r"\*\*Checks\*\*:\s*(\d+)|\*\*检查项\*\*:\s*(\d+)", content)
    if check_match:
        metadata["check_count"] = int(check_match.group(1))

    # Extract pass/fail counts
    pass_match = re.search(r"✅\s*\*\*Passed\*\*:\s*(\d+)|✅\s*\*\*通过\*\*:\s*(\d+)", content)
    if pass_match:
        metadata["pass_count"] = int(pass_match.group(1))

    fail_match = re.search(r"❌\s*\*\*Failed\*\*:\s*(\d+)|❌\s*\*\*失败\*\*:\s*(\d+)", content)
    if fail_match:
        metadata["fail_count"] = int(fail_match.group(1))

    # Calculate pass rate
    total = metadata["pass_count"] + metadata["fail_count"]
    if total > 0:
        metadata["pass_rate"] = round(metadata["pass_count"] / total * 100, 1)

    # Extract status
    status_match = re.search(r"Overall Status:\s*(.+)$|整体状态:\s*(.+)$", content, re.MULTILINE)
    if status_match:
        metadata["status"] = status_match.group(1).strip()

    # Extract warnings
    warning_section = re.search(r"## ⚠️ Warnings.*?\n((?:- .+\n)+)|## ⚠️ 警告.*?\n((?:- .+\n)+)", content)
    if warning_section:
        warnings = re.findall(r"- (.+)$", warning_section.group(1), re.MULTILINE)
        metadata["warnings"] = warnings[:10]  # Limit to 10 warnings

    return metadata

@router.get(
    "/reports",
    response_model=ReportListResponse,
    tags=["reports"],
    summary="List inspection reports",
    responses={
        200: {
            "description": "List of inspection reports",
            "content": {
                "application/json": {
                    "example": {
                        "reports": [
                            {
                                "id": "inspection_bgp_peer_audit_20251127_231051",
                                "filename": "inspection_bgp_peer_audit_20251127_231051.md",
                                "title": "🔍 Network Inspection Report",
                                "config_name": "bgp_peer_audit",
                                "executed_at": "2025-11-27 23:10:51",
                                "device_count": 3,
                                "check_count": 2,
                                "pass_count": 3,
                                "fail_count": 3,
                                "status": "needs attention"
                            }
                        ],
                        "total": 1
                    }
                }
            },
        },
    },
)
async def list_reports(
    current_user: CurrentUser,
    limit: int = 50,
    offset: int = 0,
) -> ReportListResponse:
    """
    List inspection reports from data/inspection-reports/.

    **Required**: Bearer token authentication

    **Query Parameters**:
    - `limit`: Max reports to return (default: 50)
    - `offset`: Pagination offset (default: 0)
    """
    reports_dir = Path("data/inspection-reports")
    reports: list[ReportDetail] = []

    try:
        if reports_dir.exists():
            # Get all markdown files
            md_files = sorted(reports_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
            total = len(md_files)

            # Apply pagination
            md_files = md_files[offset : offset + limit]

            for report_file in md_files:
                try:
                    content = report_file.read_text(encoding="utf-8")
                    metadata = _parse_report_metadata(content, report_file.name)

                    reports.append(ReportDetail(
                        id=report_file.stem,
                        filename=report_file.name,
                        content=None,  # Don't return full content in list
                        title=metadata["title"],
                        config_name=metadata["config_name"],
                        executed_at=metadata["executed_at"],
                        device_count=metadata["device_count"],
                        check_count=metadata["check_count"],
                        pass_count=metadata["pass_count"],
                        fail_count=metadata["fail_count"],
                        status=metadata["status"],
                    ))
                except Exception as e:
                    logger.warning(f"Failed to parse report {report_file.name}: {e}")
                    continue

            return ReportListResponse(reports=reports, total=total)

    except Exception as e:
        logger.error(f"Failed to list reports: {e}")

    return ReportListResponse(reports=[], total=0)

@router.get(
    "/reports/{report_id}",
    response_model=ReportDetail,
    tags=["reports"],
    summary="Get inspection report details",
    responses={
        200: {
            "description": "Inspection report details",
        },
        404: {
            "description": "Report not found",
        },
    },
)
async def get_report(
    report_id: str,
    current_user: CurrentUser,
) -> ReportDetail:
    """
    Get full details of an inspection report.

    **Required**: Bearer token authentication

    **Example Request**:
    ```bash
    curl http://localhost:8000/reports/inspection_bgp_peer_audit_20251127_231051 \\
      -H "Authorization: Bearer <token>"
    ```
    """
    reports_dir = Path("data/inspection-reports")
    report_file = reports_dir / f"{report_id}.md"

    if not report_file.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        content = report_file.read_text(encoding="utf-8")
        metadata = _parse_report_metadata(content, report_file.name)

        return ReportDetail(
            id=report_id,
            filename=report_file.name,
            content=content,
            title=metadata["title"],
            config_name=metadata["config_name"],
            description=metadata["description"],
            executed_at=metadata["executed_at"],
            duration=metadata["duration"],
            device_count=metadata["device_count"],
            check_count=metadata["check_count"],
            pass_count=metadata["pass_count"],
            fail_count=metadata["fail_count"],
            pass_rate=metadata["pass_rate"],
            status=metadata["status"],
            warnings=metadata["warnings"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to read report {report_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# Inspection Configuration API
# ============================================

def _parse_inspection_yaml(filepath) -> dict | None:
    """Parse inspection YAML file and return config dict."""
    try:
        content = Path(filepath).read_text(encoding="utf-8")
        return yaml.safe_load(content)
    except Exception as e:
        logger.warning(f"Failed to parse inspection YAML {filepath}: {e}")
        return None

@router.get(
    "/inspections",
    response_model=InspectionListResponse,
    tags=["inspections"],
    summary="List inspection configurations",
    responses={
        200: {
            "description": "List of inspection configurations",
            "content": {
                "application/json": {
                    "example": {
                        "inspections": [
                            {
                                "id": "bgp_peer_audit",
                                "name": "bgp_peer_audit",
                                "description": "Verify BGP peer counts and states",
                                "filename": "bgp_peer_audit.yaml",
                                "devices": ["R1", "R2", "R3"],
                                "checks": [
                                    {"name": "bgp_established_count", "tool": "suzieq_query", "enabled": True}
                                ],
                                "parallel": True,
                                "max_workers": 5
                            }
                        ],
                        "total": 1
                    }
                }
            },
        },
    },
)
async def list_inspections(current_user: CurrentUser) -> InspectionListResponse:
    """
    List all inspection configurations from config/inspections/.

    **Required**: Bearer token authentication

    **Example Request**:
    ```bash
    curl http://localhost:8000/inspections \\
      -H "Authorization: Bearer <token>"
    ```
    """
    inspections_dir = Path(get_path("inspections"))
    inspections: list[InspectionConfig] = []

    try:
        if inspections_dir.exists():
            yaml_files = sorted(inspections_dir.glob("*.yaml"))

            for yaml_file in yaml_files:
                config = _parse_inspection_yaml(yaml_file)
                if not config:
                    continue

                # Extract checks
                checks = []
                for check in config.get("checks", []):
                    checks.append(InspectionCheck(
                        name=check.get("name", ""),
                        description=check.get("description"),
                        tool=check.get("tool", ""),
                        enabled=check.get("enabled", True),
                        parameters=check.get("parameters", {}),
                    ))

                # Extract devices (can be list or dict with netbox_filter)
                devices = config.get("devices", [])

                inspections.append(InspectionConfig(
                    id=yaml_file.stem,
                    name=config.get("name", yaml_file.stem),
                    description=config.get("description"),
                    filename=yaml_file.name,
                    devices=devices,
                    checks=checks,
                    parallel=config.get("parallel", True),
                    max_workers=config.get("max_workers", 5),
                    stop_on_failure=config.get("stop_on_failure", False),
                    output_format=config.get("output_format", "table"),
                    schedule=config.get("schedule"),
                ))

            return InspectionListResponse(inspections=inspections, total=len(inspections))

    except Exception as e:
        logger.error(f"Failed to list inspections: {e}")

    return InspectionListResponse(inspections=[], total=0)

@router.post(
    "/inspections",
    response_model=InspectionConfig,
    tags=["inspections"],
    summary="Create new inspection configuration",
    responses={
        201: {"description": "Inspection created"},
        400: {"description": "Invalid configuration"},
        409: {"description": "Inspection already exists"},
    },
    status_code=201,
)
async def create_inspection(
    request: InspectionCreateRequest,
    current_user: CurrentUser,
) -> InspectionConfig:
    """
    Create a new inspection configuration.

    **Required**: Bearer token authentication
    """
    # Sanitize filename
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", request.name.lower())
    filename = f"{safe_name}.yaml"
    yaml_file = Path(get_path("inspections")) / filename

    if yaml_file.exists():
        raise HTTPException(status_code=409, detail=f"Inspection '{safe_name}' already exists")

    # Build config dict
    config = {
        "name": request.name,
        "description": request.description,
        "devices": request.devices,
        "checks": [check.model_dump() for check in request.checks],
        "schedule": request.schedule,
        # Defaults
        "parallel": True,
        "max_workers": 5,
        "stop_on_failure": False,
        "output_format": "table",
    }

    try:
        # Write to file
        yaml_file.write_text(yaml.dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")

        return InspectionConfig(
            id=safe_name,
            filename=filename,
            **config
        )
    except Exception as e:
        logger.error(f"Failed to create inspection {safe_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete(
    "/inspections/{inspection_id}",
    tags=["inspections"],
    summary="Delete inspection configuration",
    responses={
        200: {"description": "Inspection deleted"},
        404: {"description": "Inspection not found"},
    },
)
async def delete_inspection(
    inspection_id: str,
    current_user: CurrentUser,
) -> dict:
    """
    Delete an inspection configuration.

    **Required**: Bearer token authentication
    """
    yaml_file = Path(get_path("inspections")) / f"{inspection_id}.yaml"

    if not yaml_file.exists():
        raise HTTPException(status_code=404, detail="Inspection not found")

    try:
        yaml_file.unlink()
        return {"status": "deleted", "id": inspection_id}
    except Exception as e:
        logger.error(f"Failed to delete inspection {inspection_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get(
    "/inspections/{inspection_id}",
    response_model=InspectionConfig,
    tags=["inspections"],
    summary="Get inspection configuration details",
    responses={
        200: {"description": "Inspection configuration details"},
        404: {"description": "Inspection not found"},
    },
)
async def get_inspection(
    inspection_id: str,
    current_user: CurrentUser,
) -> InspectionConfig:
    """
    Get details of a specific inspection configuration.

    **Required**: Bearer token authentication
    """
    yaml_file = Path(get_path("inspections")) / f"{inspection_id}.yaml"

    if not yaml_file.exists():
        raise HTTPException(status_code=404, detail="Inspection not found")

    config = _parse_inspection_yaml(yaml_file)
    if not config:
        raise HTTPException(status_code=500, detail="Failed to parse inspection config")

    checks = []
    for check in config.get("checks", []):
        checks.append(InspectionCheck(
            name=check.get("name", ""),
            description=check.get("description"),
            tool=check.get("tool", ""),
            enabled=check.get("enabled", True),
            parameters=check.get("parameters", {}),
        ))

    devices = config.get("devices", [])

    return InspectionConfig(
        id=yaml_file.stem,
        name=config.get("name", yaml_file.stem),
        description=config.get("description"),
        filename=yaml_file.name,
        devices=devices,
        checks=checks,
        parallel=config.get("parallel", True),
        max_workers=config.get("max_workers", 5),
        stop_on_failure=config.get("stop_on_failure", False),
        output_format=config.get("output_format", "table"),
        schedule=config.get("schedule"),
    )

@router.put(
    "/inspections/{inspection_id}",
    response_model=InspectionConfig,
    tags=["inspections"],
    summary="Update inspection configuration",
    responses={
        200: {"description": "Inspection updated"},
        404: {"description": "Inspection not found"},
        500: {"description": "Failed to save inspection"},
    },
)
async def update_inspection(
    inspection_id: str,
    request: InspectionUpdateRequest,
    current_user: CurrentUser,
) -> InspectionConfig:
    """
    Update an inspection configuration YAML file.

    **Required**: Bearer token authentication
    """
    yaml_file = Path(get_path("inspections")) / f"{inspection_id}.yaml"

    if not yaml_file.exists():
        raise HTTPException(status_code=404, detail="Inspection not found")

    try:
        # Validate YAML content
        config = yaml.safe_load(request.content)
        if not config or not isinstance(config, dict):
            msg = "Invalid YAML content"
            raise ValueError(msg)

        # Write to file
        yaml_file.write_text(request.content, encoding="utf-8")

        # Return updated config
        return await get_inspection(inspection_id, current_user)

    except Exception as e:
        logger.error(f"Failed to update inspection {inspection_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/inspections/{inspection_id}/run",
    response_model=InspectionRunResponse,
    tags=["inspections"],
    summary="Run an inspection (async)",
    responses={
        200: {"description": "Inspection job created"},
        404: {"description": "Inspection not found"},
    },
)
async def run_inspection(
    inspection_id: str,
    request: InspectionRunRequest,
    current_user: CurrentUser,
) -> InspectionRunResponse:
    """
    Run an inspection asynchronously and get a job ID for tracking.

    **Required**: Bearer token authentication

    **Returns**: Job ID to track progress via GET /inspections/jobs/{job_id}

    **Request Body (optional)**:
    - `devices`: Override target devices
    - `checks`: Run only specific checks by name

    **Example Request**:
    ```bash
    curl -X POST http://localhost:8000/inspections/bgp_peer_audit/run \\
      -H "Authorization: Bearer <token>" \\
      -H "Content-Type: application/json" \\
      -d '{"devices": ["R1", "R2"]}'
    ```

    **Example Response**:
    ```json
    {
        "status": "started",
        "message": "Inspection queued",
        "job_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    ```
    """
    from olav.server.jobs import create_job, job_store

    yaml_file = Path(get_path("inspections")) / f"{inspection_id}.yaml"

    if not yaml_file.exists():
        raise HTTPException(status_code=404, detail="Inspection not found")

    # Parse config
    config = _parse_inspection_yaml(yaml_file)
    if not config:
        raise HTTPException(status_code=500, detail="Failed to parse inspection config")

    # Create async job
    triggered_by = current_user.client_id or current_user.username
    job = await create_job(
        inspection_id=inspection_id,
        triggered_by=triggered_by,
        devices=request.devices,
        checks=request.checks,
    )

    # Launch background task to run inspection
    async def _run_inspection_task() -> None:
        """Background task for inspection execution."""
        from olav.inspection import execute_inspection

        try:
            await job_store.start(job.job_id)

            # Execute unified inspection (saves report automatically)
            report = await execute_inspection(save_report=True)

            # Generate report ID (use config name + timestamp)
            report_id = f"{inspection_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"

            # Get pass/fail counts from InspectionReport
            pass_count = report.passed_count
            fail_count = report.failed_count

            await job_store.complete(
                job.job_id,
                report_id=report_id,
                pass_count=pass_count,
                fail_count=fail_count,
            )
            logger.info(f"Inspection job {job.job_id} completed: {report_id}")

        except Exception as e:
            logger.exception(f"Inspection job {job.job_id} failed: {e}")
            await job_store.fail(job.job_id, str(e))

    # Create background task (runs concurrently)
    asyncio.create_task(_run_inspection_task())

    return InspectionRunResponse(
        status="started",
        message=f"Inspection '{inspection_id}' queued. Use job_id to track progress.",
        job_id=job.job_id,
    )

@router.get(
    "/inspections/jobs",
    response_model=JobListResponse,
    tags=["inspections"],
    summary="List inspection jobs",
    responses={
        200: {"description": "List of jobs"},
    },
)
async def list_inspection_jobs(
    current_user: CurrentUser,
    inspection_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> JobListResponse:
    """
    List inspection jobs with optional filters.

    **Query Parameters**:
    - `inspection_id`: Filter by inspection config name
    - `status`: Filter by status (pending, running, completed, failed)
    - `limit`: Max jobs to return (default: 50)
    """
    from olav.server.jobs import JobStatus, list_jobs

    status_filter = None
    if status:
        with suppress(ValueError):
            status_filter = JobStatus(status)

    jobs = await list_jobs(
        inspection_id=inspection_id,
        status=status_filter,
        limit=limit,
    )

    job_responses = [
        JobStatusResponse(
            job_id=j.job_id,
            inspection_id=j.inspection_id,
            status=j.status.value,
            progress=j.progress,
            current_device=j.current_device,
            created_at=j.created_at.isoformat(),
            started_at=j.started_at.isoformat() if j.started_at else None,
            completed_at=j.completed_at.isoformat() if j.completed_at else None,
            report_id=j.report_id,
            error=j.error,
            total_devices=j.total_devices,
            processed_devices=j.processed_devices,
            pass_count=j.pass_count,
            fail_count=j.fail_count,
        )
        for j in jobs
    ]

    return JobListResponse(jobs=job_responses, total=len(job_responses))

@router.get(
    "/inspections/jobs/{job_id}",
    response_model=JobStatusResponse,
    tags=["inspections"],
    summary="Get job status",
    responses={
        200: {"description": "Job status"},
        404: {"description": "Job not found"},
    },
)
async def get_job_status(
    job_id: str,
    current_user: CurrentUser,
) -> JobStatusResponse:
    """
    Get the status of an inspection job.

    **Example Request**:
    ```bash
    curl http://localhost:8000/inspections/jobs/550e8400-e29b-41d4-a716-446655440000 \\
      -H "Authorization: Bearer <token>"
    ```
    """
    from olav.server.jobs import get_job

    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.job_id,
        inspection_id=job.inspection_id,
        status=job.status.value,
        progress=job.progress,
        current_device=job.current_device,
        created_at=job.created_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        report_id=job.report_id,
        error=job.error,
        total_devices=job.total_devices,
        processed_devices=job.processed_devices,
        pass_count=job.pass_count,
        fail_count=job.fail_count,
    )
