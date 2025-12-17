from fastapi import APIRouter, HTTPException, Depends
import logging
from datetime import datetime
import asyncpg
import json

from config.settings import settings
from olav.server.core import state
from olav.server.models.session import SessionInfo, SessionListResponse
from olav.server.auth import CurrentUser

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get(
    "/sessions",
    response_model=SessionListResponse,
    tags=["sessions"],
    summary="List chat sessions",
    responses={
        200: {
            "description": "List of chat sessions",
            "content": {
                "application/json": {
                    "example": {
                        "sessions": [
                            {
                                "thread_id": "session-123",
                                "created_at": "2025-01-27T10:00:00Z",
                                "updated_at": "2025-01-27T10:05:00Z",
                                "message_count": 5,
                                "first_message": "Query R1 BGP status",
                                "workflow_type": "query_diagnostic"
                            }
                        ],
                        "total": 1
                    }
                }
            },
        },
    },
)
async def list_sessions(
    current_user: CurrentUser,
    limit: int = 50,
    offset: int = 0,
) -> SessionListResponse:
    """
    List chat sessions from PostgreSQL checkpointer.

    Sessions are ordered by most recent activity (newest first).

    **Required**: Bearer token authentication

    **Query Parameters**:
    - `limit`: Maximum sessions to return (default: 50)
    - `offset`: Pagination offset (default: 0)

    **Example Request**:
    ```bash
    curl http://localhost:8000/sessions?limit=10 \\
      -H "Authorization: Bearer <token>"
    ```
    """
    sessions: list[SessionInfo] = []

    try:
        # Direct PostgreSQL query for session list
        conn = await asyncpg.connect(settings.postgres_uri)
        try:
            # Query unique thread_ids with metadata
            query = """
                SELECT
                    thread_id,
                    MIN(checkpoint_id) as first_checkpoint,
                    MAX(checkpoint_id) as last_checkpoint,
                    COUNT(*) as checkpoint_count,
                    MIN(checkpoint::jsonb->>'ts') as created_at,
                    MAX(checkpoint::jsonb->>'ts') as updated_at
                FROM checkpoints
                WHERE thread_id NOT LIKE 'invoke-%'
                  AND thread_id NOT LIKE 'stream-%'
                GROUP BY thread_id
                ORDER BY MAX(checkpoint_id) DESC
                LIMIT $1 OFFSET $2
            """
            rows = await conn.fetch(query, limit, offset)

            # Get total count
            count_query = """
                SELECT COUNT(DISTINCT thread_id) as total
                FROM checkpoints
                WHERE thread_id NOT LIKE 'invoke-%'
                  AND thread_id NOT LIKE 'stream-%'
            """
            total_row = await conn.fetchrow(count_query)
            total = total_row["total"] if total_row else 0

            for row in rows:
                # Try to extract first message from checkpoint data
                first_message = None
                workflow_type = None

                try:
                    # Get first checkpoint to extract initial user message
                    first_cp_query = """
                        SELECT checkpoint
                        FROM checkpoints
                        WHERE thread_id = $1
                        ORDER BY checkpoint_id ASC
                        LIMIT 1
                    """
                    first_cp = await conn.fetchrow(first_cp_query, row["thread_id"])
                    if first_cp and first_cp["checkpoint"]:
                        cp_data = json.loads(first_cp["checkpoint"]) if isinstance(first_cp["checkpoint"], str) else first_cp["checkpoint"]

                        # Extract messages from channel_values
                        channel_values = cp_data.get("channel_values", {})
                        messages = channel_values.get("messages", [])

                        # Find first user message
                        for msg in messages:
                            if isinstance(msg, dict):
                                if msg.get("type") == "human" or msg.get("role") == "user":
                                    content = msg.get("content", "")
                                    if content:
                                        first_message = content[:100] + ("..." if len(content) > 100 else "")
                                        break

                        # Try to get workflow type
                        workflow_type = channel_values.get("workflow_type")
                except Exception as e:
                    logger.debug(f"Failed to extract message from checkpoint: {e}")

                # Fallback: Use checkpointer to get latest state if first message missing
                if not first_message and state.checkpointer:
                    try:
                        config = {"configurable": {"thread_id": row["thread_id"], "checkpoint_ns": ""}}
                        # This gets the LATEST state, which contains the full history
                        cp_tuple = await state.checkpointer.aget_tuple(config)
                        if cp_tuple and cp_tuple.checkpoint:
                            msgs = cp_tuple.checkpoint.get("channel_values", {}).get("messages", [])
                            for msg in msgs:
                                # Handle BaseMessage or dict
                                content = ""
                                role = ""
                                if hasattr(msg, "content"):
                                    content = msg.content
                                    role = "user" if msg.type == "human" else msg.type
                                elif isinstance(msg, dict):
                                    content = msg.get("content", "")
                                    role = "user" if msg.get("type") == "human" else msg.get("role")

                                if role == "user" and content:
                                    first_message = content[:100] + ("..." if len(content) > 100 else "")
                                    break

                            # Also try to get workflow type from latest state
                            if not workflow_type:
                                workflow_type = cp_tuple.checkpoint.get("channel_values", {}).get("workflow_type")
                    except Exception as e:
                        logger.debug(f"Failed to get title via checkpointer: {e}")

                # Parse timestamps
                created_at = row["created_at"] or datetime.now().isoformat()
                updated_at = row["updated_at"] or datetime.now().isoformat()

                sessions.append(SessionInfo(
                    thread_id=row["thread_id"],
                    created_at=created_at if isinstance(created_at, str) else created_at.isoformat(),
                    updated_at=updated_at if isinstance(updated_at, str) else updated_at.isoformat(),
                    message_count=row["checkpoint_count"],
                    first_message=first_message,
                    workflow_type=workflow_type,
                ))

        finally:
            await conn.close()

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        # Return empty list on error
        return SessionListResponse(sessions=[], total=0)

    return SessionListResponse(sessions=sessions, total=total)

@router.get(
    "/sessions/{thread_id}",
    tags=["sessions"],
    summary="Get session messages",
    responses={
        200: {
            "description": "Session messages",
        },
        404: {
            "description": "Session not found",
        },
    },
)
async def get_session(
    thread_id: str,
    current_user: CurrentUser,
) -> dict:
    """
    Get messages from a specific session.

    **Required**: Bearer token authentication

    **Example Request**:
    ```bash
    curl http://localhost:8000/sessions/session-123 \\
      -H "Authorization: Bearer <token>"
    ```
    """
    # Use global checkpointer if available (preferred method for LangGraph v2)
    if state.checkpointer:
        logger.info(f"Attempting to get session {thread_id} via checkpointer")
        try:
            config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
            # aget_tuple retrieves the latest checkpoint, handling checkpoint_writes automatically
            checkpoint_tuple = await state.checkpointer.aget_tuple(config)

            if not checkpoint_tuple or not checkpoint_tuple.checkpoint:
                # Fallback to SQL check to see if it really doesn't exist or just no state
                logger.warning(f"Checkpointer returned None for {thread_id}, falling back to SQL")
            else:
                checkpoint = checkpoint_tuple.checkpoint
                channel_values = checkpoint.get("channel_values", {})
                logger.info(f"Session {thread_id} channel_values keys: {list(channel_values.keys())}")

                # DEBUG: Dump structure if messages missing
                if "messages" not in channel_values:
                    logger.warning(f"Session {thread_id} missing messages! Dump: {str(channel_values)[:500]}")
                    # Try to find messages in other keys
                    for k, v in channel_values.items():
                        if isinstance(v, dict) and "messages" in v:
                            logger.info(f"Found messages in sub-key {k}")
                            messages = v["messages"]
                            break
                        if k == "messages": # Should be covered by get
                            messages = v
                            break
                else:
                    messages = channel_values.get("messages", [])

                logger.info(f"Session {thread_id} messages count: {len(messages)}")

                # Convert to standard format
                formatted_messages = []
                for msg in messages:
                    # Handle both dict and BaseMessage objects
                    if hasattr(msg, "type") and hasattr(msg, "content"):
                        role = "user" if msg.type == "human" else "assistant"
                        formatted_messages.append({
                            "role": role,
                            "content": msg.content,
                        })
                    elif isinstance(msg, dict):
                        role = "user" if msg.get("type") == "human" else "assistant"
                        formatted_messages.append({
                            "role": role,
                            "content": msg.get("content", ""),
                        })

                return {
                    "thread_id": thread_id,
                    "messages": formatted_messages,
                    "workflow_type": channel_values.get("workflow_type"),
                }
        except Exception as e:
            logger.error(f"Failed to get session via checkpointer {thread_id}: {e}")
            # Fallback to SQL below
    else:
        logger.warning("Checkpointer not available, using SQL fallback")

    try:
        conn = await asyncpg.connect(settings.postgres_uri)
        try:
            # Get latest checkpoint for this thread
            query = """
                SELECT checkpoint
                FROM checkpoints
                WHERE thread_id = $1
                ORDER BY checkpoint_id DESC
                LIMIT 1
            """
            row = await conn.fetchrow(query, thread_id)

            if not row:
                raise HTTPException(status_code=404, detail="Session not found")

            cp_data = json.loads(row["checkpoint"]) if isinstance(row["checkpoint"], str) else row["checkpoint"]

            # Extract messages
            channel_values = cp_data.get("channel_values", {})
            messages = channel_values.get("messages", [])

            # Convert to standard format
            formatted_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    role = "user" if msg.get("type") == "human" else "assistant"
                    formatted_messages.append({
                        "role": role,
                        "content": msg.get("content", ""),
                    })

            return {
                "thread_id": thread_id,
                "messages": formatted_messages,
                "workflow_type": channel_values.get("workflow_type"),
            }

        finally:
            await conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete(
    "/sessions/{thread_id}",
    tags=["sessions"],
    summary="Delete a session",
    responses={
        200: {
            "description": "Session deleted",
        },
        404: {
            "description": "Session not found",
        },
    },
)
async def delete_session(
    thread_id: str,
    current_user: CurrentUser,
) -> dict:
    """
    Delete a session and all its checkpoints.

    **Required**: Bearer token authentication (admin only)

    **Example Request**:
    ```bash
    curl -X DELETE http://localhost:8000/sessions/session-123 \\
      -H "Authorization: Bearer <token>"
    ```
    """
    try:
        conn = await asyncpg.connect(settings.postgres_uri)
        try:
            # Delete checkpoints for this thread
            result = await conn.execute(
                "DELETE FROM checkpoints WHERE thread_id = $1",
                thread_id
            )

            # Also delete from checkpoint_writes if exists
            await conn.execute(
                "DELETE FROM checkpoint_writes WHERE thread_id = $1",
                thread_id
            )

            if "DELETE 0" in result:
                raise HTTPException(status_code=404, detail="Session not found")

            return {"status": "deleted", "thread_id": thread_id}

        finally:
            await conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
