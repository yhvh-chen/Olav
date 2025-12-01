"""Inspection Scheduler - Background daemon for periodic inspections.

Provides scheduled execution of inspection profiles:
- Daily/weekly scheduling via cron expressions
- Interval-based execution for testing
- Background daemon mode
- Graceful shutdown handling

Usage:
    # Start scheduler daemon
    uv run python -m olav.main inspect --daemon

    # Or run scheduler directly
    python -m olav.inspection.scheduler
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Any

from config.settings import InspectionConfig

logger = logging.getLogger("olav.inspection.scheduler")


class InspectionScheduler:
    """Schedule and run periodic inspections."""

    def __init__(self) -> None:
        self.running = False
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        """Start the scheduler daemon."""
        if not InspectionConfig.ENABLED:
            logger.warning("Inspection scheduler is disabled (InspectionConfig.ENABLED=False)")
            logger.info("To enable, set InspectionConfig.ENABLED = True in config/settings.py")
            return

        self.running = True
        logger.info("Inspection scheduler starting...")

        # Setup signal handlers for graceful shutdown
        if sys.platform != "win32":
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, self._signal_handler)

        try:
            await self._run_loop()
        except asyncio.CancelledError:
            logger.info("Scheduler cancelled")
        finally:
            self.running = False
            logger.info("Inspection scheduler stopped")

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        logger.info("Shutdown signal received")
        self._stop_event.set()

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self._stop_event.set()

        # Cancel any running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _run_loop(self) -> None:
        """Main scheduler loop."""
        # 1. Load individual profile schedules
        from config.settings import Paths
        import yaml
        
        scheduled_tasks = []
        
        if Paths.INSPECTIONS_DIR.exists():
            for yaml_file in Paths.INSPECTIONS_DIR.glob("*.yaml"):
                try:
                    content = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
                    schedule = content.get("schedule")
                    profile_name = yaml_file.stem
                    
                    if schedule:
                        logger.info(f"Scheduling profile '{profile_name}' with schedule: {schedule}")
                        task = asyncio.create_task(
                            self._run_profile_schedule(profile_name, schedule)
                        )
                        self._tasks.append(task)
                        scheduled_tasks.append(profile_name)
                except Exception as e:
                    logger.error(f"Failed to load schedule for {yaml_file}: {e}")

        if scheduled_tasks:
            logger.info(f"Started {len(scheduled_tasks)} individual inspection schedules")
            # Wait for all tasks (or stop signal)
            await asyncio.gather(*self._tasks, return_exceptions=True)
            return

        # 2. Fallback to global config if no individual schedules found
        logger.info("No individual profile schedules found, falling back to global config")
        
        # Determine schedule type
        if InspectionConfig.SCHEDULE_INTERVAL_MINUTES:
            # Interval-based (for testing)
            interval = InspectionConfig.SCHEDULE_INTERVAL_MINUTES * 60
            logger.info(
                f"Running inspections every {InspectionConfig.SCHEDULE_INTERVAL_MINUTES} minutes"
            )
            await self._run_interval_loop(interval)
        elif InspectionConfig.SCHEDULE_CRON:
            # Cron-based
            logger.info(f"Running inspections on cron schedule: {InspectionConfig.SCHEDULE_CRON}")
            await self._run_cron_loop()
        else:
            # Daily at specific time
            logger.info(f"Running inspections daily at {InspectionConfig.SCHEDULE_TIME}")
            await self._run_daily_loop()

    async def _run_profile_schedule(self, profile_name: str, schedule: str) -> None:
        """Run a specific profile on its own schedule."""
        # Check if it's a simple alias like "daily" or "hourly"
        if schedule.lower() == "daily":
            schedule = "0 9 * * *"  # Default to 9 AM
        elif schedule.lower() == "hourly":
            schedule = "0 * * * *"
            
        try:
            from croniter import croniter
        except ImportError:
            logger.error("croniter package not installed. Install with: uv add croniter")
            return

        try:
            cron = croniter(schedule)
        except Exception as e:
            logger.error(f"Invalid cron expression for {profile_name}: {schedule} ({e})")
            return

        logger.info(f"Started scheduler for {profile_name} ({schedule})")

        while not self._stop_event.is_set():
            # Get next run time
            next_run = cron.get_next(datetime)
            now = datetime.now()
            wait_seconds = (next_run - now).total_seconds()

            if wait_seconds > 0:
                # logger.debug(f"Profile {profile_name} next run at {next_run}")
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=wait_seconds,
                    )
                    break  # Stop event was set
                except TimeoutError:
                    pass  # Time to run

            # Run inspection
            await self._execute_inspection(profile_name)

    async def _run_interval_loop(self, interval_seconds: int) -> None:
        """Run inspections at fixed intervals."""
        while not self._stop_event.is_set():
            # Run inspection
            await self._execute_inspection()

            # Wait for next interval or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=interval_seconds,
                )
                break  # Stop event was set
            except TimeoutError:
                pass  # Continue to next iteration

    async def _run_daily_loop(self) -> None:
        """Run inspections daily at configured time."""
        while not self._stop_event.is_set():
            # Parse schedule time
            try:
                hour, minute = map(int, InspectionConfig.SCHEDULE_TIME.split(":"))
            except ValueError:
                logger.error(f"Invalid SCHEDULE_TIME format: {InspectionConfig.SCHEDULE_TIME}")
                hour, minute = 9, 0

            # Calculate next run time
            now = datetime.now()
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if next_run <= now:
                # Already passed today, schedule for tomorrow
                next_run = next_run.replace(day=now.day + 1)

            wait_seconds = (next_run - now).total_seconds()
            logger.info(
                f"Next inspection scheduled at {next_run.strftime('%Y-%m-%d %H:%M:%S')} ({wait_seconds / 3600:.1f} hours)"
            )

            # Wait until scheduled time or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=wait_seconds,
                )
                break  # Stop event was set
            except TimeoutError:
                pass  # Time to run

            # Run inspection
            await self._execute_inspection()

    async def _run_cron_loop(self) -> None:
        """Run inspections based on cron expression."""
        try:
            from croniter import croniter
        except ImportError:
            logger.error("croniter package not installed. Install with: uv add croniter")
            return

        cron = croniter(InspectionConfig.SCHEDULE_CRON)

        while not self._stop_event.is_set():
            # Get next run time
            next_run = cron.get_next(datetime)
            now = datetime.now()
            wait_seconds = (next_run - now).total_seconds()

            if wait_seconds > 0:
                logger.info(f"Next inspection at {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=wait_seconds,
                    )
                    break  # Stop event was set
                except TimeoutError:
                    pass  # Time to run

            # Run inspection
            await self._execute_inspection()

    async def _execute_inspection(self, profile_name: str | None = None) -> dict[str, Any]:
        """Execute the configured inspection profile."""
        from olav.inspection.runner import run_inspection

        profile = profile_name or InspectionConfig.DEFAULT_PROFILE
        logger.info(f"Starting scheduled inspection: {profile}")

        try:
            result = await run_inspection(profile=profile)

            if result.get("status") == "success":
                logger.info(
                    f"Inspection completed: {result.get('passed')}/{result.get('total_checks')} passed, "
                    f"report: {result.get('report_path')}"
                )

                # Check for critical failures
                if result.get("critical", 0) > 0 and InspectionConfig.NOTIFY_ON_FAILURE:
                    await self._send_notification(result)
            else:
                logger.error(f"Inspection failed: {result.get('message')}")

            return result

        except Exception as e:
            logger.exception(f"Inspection execution error: {e}")
            return {"status": "error", "message": str(e)}

    async def _send_notification(self, result: dict[str, Any]) -> None:
        """Send notification for critical failures."""
        if not InspectionConfig.NOTIFY_WEBHOOK_URL:
            return

        try:
            import aiohttp

            payload = {
                "text": f"🚨 OLAV Inspection Alert: {result.get('critical')} critical issues found",
                "attachments": [
                    {
                        "title": f"Profile: {result.get('profile')}",
                        "text": f"Report: {result.get('report_path')}",
                        "color": "danger",
                    }
                ],
            }

            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    InspectionConfig.NOTIFY_WEBHOOK_URL,
                    json=payload,
                ) as resp,
            ):
                if resp.status != 200:
                    logger.warning(f"Notification webhook failed: {resp.status}")
        except Exception as e:
            logger.warning(f"Failed to send notification: {e}")


async def run_scheduler() -> None:
    """Run the inspection scheduler."""
    scheduler = InspectionScheduler()
    await scheduler.start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_scheduler())
