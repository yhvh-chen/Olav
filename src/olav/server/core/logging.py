import logging

# ============================================
# Health Check Log Filter
# ============================================
class HealthCheckFilter(logging.Filter):
    """Filter out noisy health check log messages from uvicorn access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        # Filter out GET /health requests (Docker health checks)
        if "GET /health" in message and "200" in message:
            return False
        return True

def configure_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Apply filter to uvicorn access logger
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.addFilter(HealthCheckFilter())
