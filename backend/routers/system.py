"""System management endpoints.

Safety: Destructive operations (reboot/shutdown) require:
1. Request comes from localhost/LAN (checked by default)
2. Explicit confirmation in request body
"""

import logging
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..cleanup import cleanup_old_readings, get_reading_stats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/system", tags=["system"])

# Read version from VERSION file
_version_file = Path(__file__).parent.parent.parent / "VERSION"
VERSION = _version_file.read_text().strip() if _version_file.exists() else "0.0.0"


class SystemInfo(BaseModel):
    hostname: str
    ip_addresses: list[str]
    uptime_seconds: Optional[float]
    version: str = VERSION


class SystemAction(BaseModel):
    confirm: bool = False


class TimezoneUpdate(BaseModel):
    timezone: str


def get_ip_addresses() -> list[str]:
    """Get all non-loopback IP addresses."""
    ips = []
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            ips = result.stdout.strip().split()
    except Exception:
        pass
    return ips


def get_uptime() -> Optional[float]:
    """Get system uptime in seconds."""
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except Exception:
        return None


def is_local_request(request: Request) -> bool:
    """Check if request is from localhost or local network."""
    client_ip = request.client.host if request.client else ""
    # Allow localhost
    if client_ip in ("127.0.0.1", "::1", "localhost"):
        return True
    # Allow private network ranges
    if client_ip.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                             "172.20.", "172.21.", "172.22.", "172.23.",
                             "172.24.", "172.25.", "172.26.", "172.27.",
                             "172.28.", "172.29.", "172.30.", "172.31.",
                             "192.168.")):
        return True
    return False


@router.get("/info", response_model=SystemInfo)
async def get_system_info():
    """Get system information."""
    return SystemInfo(
        hostname=socket.gethostname(),
        ip_addresses=get_ip_addresses(),
        uptime_seconds=get_uptime(),
    )


@router.post("/reboot")
async def reboot_system(action: SystemAction, request: Request):
    """Reboot the system. Requires confirmation."""
    if not is_local_request(request):
        raise HTTPException(
            status_code=403,
            detail="System controls only available from local network",
        )
    if not action.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true to proceed with reboot",
        )
    try:
        # Use systemctl if available, fallback to reboot command
        subprocess.Popen(["sudo", "systemctl", "reboot"])
        return {"status": "rebooting"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown")
async def shutdown_system(action: SystemAction, request: Request):
    """Shutdown the system. Requires confirmation."""
    if not is_local_request(request):
        raise HTTPException(
            status_code=403,
            detail="System controls only available from local network",
        )
    if not action.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true to proceed with shutdown",
        )
    try:
        subprocess.Popen(["sudo", "systemctl", "poweroff"])
        return {"status": "shutting_down"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timezones")
async def list_timezones():
    """List available timezones."""
    timezones = []
    zoneinfo_path = Path("/usr/share/zoneinfo")
    if zoneinfo_path.exists():
        for region in ["America", "Europe", "Asia", "Australia", "Pacific", "UTC"]:
            region_path = zoneinfo_path / region
            if region_path.is_dir():
                for tz in region_path.iterdir():
                    if tz.is_file():
                        timezones.append(f"{region}/{tz.name}")
            elif region == "UTC" and (zoneinfo_path / "UTC").exists():
                timezones.append("UTC")
    return {"timezones": sorted(timezones)}


@router.get("/timezone")
async def get_timezone():
    """Get current timezone."""
    try:
        # Use timedatectl (most reliable on modern systems) - use full path
        result = subprocess.run(
            ["/usr/bin/timedatectl", "show", "--property=Timezone", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        logger.info(f"timedatectl returncode: {result.returncode}, stdout: '{result.stdout.strip()}', stderr: '{result.stderr.strip()}'")
        if result.returncode == 0 and result.stdout.strip():
            tz = result.stdout.strip()
            logger.info(f"Returning timezone from timedatectl: {tz}")
            return {"timezone": tz}
        # Fallback to /etc/timezone
        tz_file = Path("/etc/timezone")
        if tz_file.exists():
            tz = tz_file.read_text().strip()
            logger.info(f"Returning timezone from /etc/timezone: {tz}")
            return {"timezone": tz}
    except Exception as e:
        logger.error(f"Error getting timezone: {e}")
    logger.warning("Falling back to UTC timezone")
    return {"timezone": "UTC"}


@router.put("/timezone")
async def set_timezone(update: TimezoneUpdate, request: Request):
    """Set system timezone."""
    if not is_local_request(request):
        raise HTTPException(
            status_code=403,
            detail="System controls only available from local network",
        )
    # Validate timezone exists
    tz_path = Path(f"/usr/share/zoneinfo/{update.timezone}")
    if not tz_path.exists():
        raise HTTPException(status_code=400, detail=f"Unknown timezone: {update.timezone}")
    try:
        subprocess.run(
            ["/usr/bin/sudo", "/usr/bin/timedatectl", "set-timezone", update.timezone],
            check=True,
            timeout=10,
        )
        return {"timezone": update.timezone}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to set timezone: {e}")


@router.get("/storage")
async def get_storage_stats():
    """Get database storage statistics."""
    stats = await get_reading_stats()
    total = stats.get("total_readings") or 0
    stats["estimated_size_bytes"] = int(total) * 100  # rough estimate
    return stats


class CleanupRequest(BaseModel):
    retention_days: int = 30
    confirm: bool = False


@router.post("/cleanup")
async def trigger_cleanup(cleanup: CleanupRequest, request: Request):
    """Manually trigger data cleanup. Requires confirmation."""
    if not is_local_request(request):
        raise HTTPException(
            status_code=403,
            detail="System controls only available from local network",
        )
    if not cleanup.confirm:
        # Return preview of what would be deleted
        from datetime import timedelta
        from sqlalchemy import func, select
        from ..database import async_session_factory
        from ..models import Reading

        cutoff = datetime.now(timezone.utc) - timedelta(days=cleanup.retention_days)
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Reading).where(Reading.timestamp < cutoff)
            )
            count = result.scalar() or 0

        return {
            "status": "preview",
            "retention_days": cleanup.retention_days,
            "readings_to_delete": count,
            "message": "Set confirm=true to proceed with deletion",
        }

    deleted = await cleanup_old_readings(cleanup.retention_days)
    return {
        "status": "completed",
        "retention_days": cleanup.retention_days,
        "deleted_readings": deleted,
    }
