"""Nuki OTP Sensor implementation."""
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, NO_CODE
from .coordinator import NukiOTPDataCoordinator
from .helpers import NukiConfig

_LOGGER = logging.getLogger(__name__)


class NukiOTPSensor(CoordinatorEntity, SensorEntity):
    """Nuki OTP Code sensor."""

    def __init__(
        self,
        coordinator: NukiOTPDataCoordinator,
        config: NukiConfig,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.config = config
        self._attr_unique_id = f"{entry_id}_otp_code"
        self._attr_name = "Nuki OTP Code"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=f"Nuki OTP - {config.nuki_name}",
            manufacturer="Nuki",
            model="OTP Generator",
        )

    @property
    def native_value(self) -> str:
        """Return the current OTP code."""
        if not self.coordinator.data:
            return NO_CODE

        current_code = self.coordinator.data.get("current_code")
        if current_code and isinstance(current_code, dict):
            return str(current_code.get("code", NO_CODE))
        return NO_CODE

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return additional state attributes."""
        if not self.coordinator.data:
            return {}

        current_code = self.coordinator.data.get("current_code")
        if not current_code or not isinstance(current_code, dict):
            return {"status": "No active code"}

        try:
            creation_date = current_code.get("creationDate", "")
            expiry_date = self._calculate_expiry_date(creation_date)

            return {
                "name": current_code.get("name", ""),
                "enabled": current_code.get("enabled", False),
                "remote_allowed": current_code.get("remoteAllowed", False),
                "lock_count": current_code.get("lockCount", 0),
                "creation_date": creation_date,
                "expiry_date": expiry_date,
                "status": "Active",
            }
        except Exception as err:
            _LOGGER.warning("Error building attributes: %s", err)
            return {"status": "Error"}

    def _calculate_expiry_date(self, creation_date: str) -> str:
        """Calculate expiry date from creation date."""
        try:
            # Handle timezone suffix
            if creation_date.endswith("Z"):
                creation_date = creation_date[:-1] + "+00:00"

            utc_time = dt_util.parse_datetime(creation_date)
            if utc_time is None:
                return "Unknown"
            expiry_time = utc_time + timedelta(hours=self.config.otp_lifetime_hours)
            return expiry_time.isoformat()
        except (ValueError, TypeError) as err:
            _LOGGER.warning("Error calculating expiry date: %s", err)
            return "Unknown"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Nuki OTP sensor from config entry."""
    integration_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = integration_data["coordinator"]
    config = integration_data["config"]

    async_add_entities([NukiOTPSensor(coordinator, config, entry.entry_id)])
