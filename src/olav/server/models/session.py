from pydantic import BaseModel

class SessionInfo(BaseModel):
    """Session information from checkpointer."""
    thread_id: str
    created_at: str
    updated_at: str
    message_count: int
    first_message: str | None = None
    workflow_type: str | None = None

class SessionListResponse(BaseModel):
    """Response for session list endpoint."""
    sessions: list[SessionInfo]
    total: int
