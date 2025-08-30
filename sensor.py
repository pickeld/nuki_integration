"""Improved Nuki OTP Sensor implementation."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .helpers import NukiAPIClient, NukiConfig
from .const import DOMAIN, CUSTOM_EVENT

logger = logging.getLogger(__name__)

NO_CODE = "------"


class NukiOTPDataCoordinator(DataUpdateCoordinator):
    """Data coordinator for Nuki OTP integration."""

    def __init__(self, hass: HomeAssistant, api_client: NukiAPIClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            logger,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
        )
        self.api_client = api_client

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API endpoint."""
        try:
            # Clean up expired codes first
            await self.api_client.cleanup_expired_codes()
            
            # Get current auth codes
            auth_codes = await self.api_client.get_auth_codes()
            
            return {
                "auth_codes": auth_codes,
                "current_code": auth_codes[0] if auth_codes else None,
                "has_active_code": len(auth_codes) > 0,
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")


class NukiOTPSensor(CoordinatorEntity, SensorEntity):
    """Nuki OTP Code sensor with improved implementation."""

    def __init__(
        self, 
        coordinator: NukiOTPDataCoordinator, 
        config: NukiConfig
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.config = config
        self._attr_unique_id = f"{DOMAIN}_otp_code"
        self._attr_name = "Nuki OTP Code"
        self._attr_device_class = SensorDeviceClass.ENUM
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        
    @property
    def device_info(self) -> Dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, "nuki_otp")},
            "name": "Nuki OTP Generator",
            "manufacturer": "Nuki",
            "model": "OTP Generator",
            "sw_version": "1.1.0",
        }

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
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

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
                "code": str(current_code.get("code", "")),
                "name": current_code.get("name", ""),
                "enabled": current_code.get("enabled", False),
                "remote_allowed": current_code.get("remoteAllowed", False),
                "lock_count": current_code.get("lockCount", 0),
                "creation_date": creation_date,
                "expiry_date": expiry_date,
                "status": "Active",
            }
        except Exception as err:
            logger.warning(f"Error building attributes: {err}")
            return {"status": "Error"}

    def _calculate_expiry_date(self, creation_date: str) -> str:
        """Calculate expiry date from creation date."""
        try:
            # Handle timezone suffix
            if creation_date.endswith('Z'):
                creation_date = creation_date[:-1] + '+00:00'
            
            utc_time = datetime.fromisoformat(creation_date)
            expiry_time = utc_time + timedelta(hours=self.config.otp_lifetime_hours)
            return expiry_time.isoformat()
        except (ValueError, TypeError) as err:
            logger.warning(f"Error calculating expiry date: {err}")
            return "Unknown"

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        
        # Listen for custom events from switch
        self.async_on_remove(
            self.hass.bus.async_listen(CUSTOM_EVENT, self._handle_custom_event)
        )

    @callback
    def _handle_custom_event(self, event) -> None:
        """Handle custom event from switch."""
        logger.debug(f"Received custom event: {event.data}")
        # Trigger coordinator refresh
        self.async_schedule_update_ha_state(force_refresh=True)
        
        # Schedule a delayed update to ensure data consistency
        async_call_later(self.hass, 2, self._delayed_update)

    @callback
    def _delayed_update(self, _=None) -> None:
        """Perform delayed update."""
        self.async_schedule_update_ha_state(force_refresh=True)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Set up Nuki OTP sensor from config entry."""
    config = NukiConfig(
        api_token=entry.data["api_token"],
        api_url=entry.data["api_url"],
        otp_username=entry.data["otp_username"],
        nuki_name=entry.data["nuki_name"],
        otp_lifetime_hours=int(entry.data["otp_lifetime_hours"]),
    )
    
    api_client = NukiAPIClient(hass, config)
    coordinator = NukiOTPDataCoordinator(hass, api_client)
    
    # Store coordinator in hass data for switch to use
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "api_client": api_client,
        "config": config,
    }
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    async_add_entities([NukiOTPSensor(coordinator, config)])
    return True