from pydantic import BaseModel
from typing import Literal, Any

class ReportSummary(BaseModel):
    """Summary of an inspection report."""
    id: str
    filename: str
    title: str
    config_name: str | None = None
    executed_at: str
    device_count: int = 0
    check_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    status: str = "unknown"  # "passed", "needs attention", "critical issues"

class ReportListResponse(BaseModel):
    """Response for report list endpoint."""
    reports: list[ReportSummary]
    total: int

class ReportDetail(BaseModel):
    """Full inspection report details."""
    id: str
    filename: str
    content: str  # Raw markdown content
    title: str
    config_name: str | None = None
    description: str | None = None
    executed_at: str
    duration: str | None = None
    device_count: int = 0
    check_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    pass_rate: float = 0.0
    status: str = "unknown"
    warnings: list[str] = []

class InspectionCheck(BaseModel):
    """A single check within an inspection configuration."""
    name: str
    description: str | None = None
    tool: str
    enabled: bool = True
    parameters: dict = {}

class InspectionConfig(BaseModel):
    """Inspection configuration from YAML file."""
    id: str
    name: str
    description: str | None = None
    filename: str
    devices: list[str] | dict = []
    checks: list[InspectionCheck] = []
    parallel: bool = True
    max_workers: int = 5
    stop_on_failure: bool = False
    output_format: str = "table"
    schedule: str | None = None  # Cron expression or "daily", "hourly"

class InspectionCreateRequest(BaseModel):
    """Request to create a new inspection."""
    name: str
    description: str | None = None
    devices: list[str] | dict = []
    checks: list[InspectionCheck] = []
    schedule: str | None = None

class InspectionListResponse(BaseModel):
    """Response for inspection list endpoint."""
    inspections: list[InspectionConfig]
    total: int

class InspectionRunRequest(BaseModel):
    """Request to run an inspection."""
    devices: list[str] | None = None  # Override devices if provided
    checks: list[str] | None = None   # Run only specific checks if provided

class InspectionRunResponse(BaseModel):
    """Response from running an inspection."""
    status: str  # "started", "completed", "failed"
    message: str
    job_id: str | None = None  # Async job ID for tracking
    report_id: str | None = None

class JobStatusResponse(BaseModel):
    """Response for job status query."""
    job_id: str
    inspection_id: str
    status: str  # "pending", "running", "completed", "failed"
    progress: int  # 0-100
    current_device: str | None = None

    # Timestamps
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None

    # Results (available when completed)
    report_id: str | None = None
    error: str | None = None
    total_devices: int = 0
    processed_devices: int = 0
    pass_count: int = 0
    fail_count: int = 0

class JobListResponse(BaseModel):
    """Response for job list endpoint."""
    jobs: list[JobStatusResponse]
    total: int

class InspectionUpdateRequest(BaseModel):
    """Request to update an inspection configuration."""
    content: str
