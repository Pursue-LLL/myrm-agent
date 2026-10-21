"""Mobile ADB Service Package.

Public API:
- MobileDeviceService: Mobile device discovery and management
- get_mobile_device_service: Singleton provider
"""

from app.services.mobile_adb.service import (
    MobileDeviceService,
    get_mobile_device_service,
)

__all__ = ["MobileDeviceService", "get_mobile_device_service"]
