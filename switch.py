"""Improved Nuki OTP Switch implementation."""
import logging
from typing import Any, Dict

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CUSTOM_EVENT
from .helpers import NukiAPIClient, NukiConfig

logger = logging.getLogger(__name__)


class NukiOTPSwitch(CoordinatorEntity, SwitchEntity):
    """Nuki OTP Switch with improved implementation."""

    def __init__(self, coordinator, api_client: NukiAPIClient) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.api_client = api_client
        self._attr_unique_id = f"{DOMAIN}_otp_switch"
        self._attr_name = "Nuki OTP Generator"

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
    def is_on(self) -> bool:
        """Return the state of the switch."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("has_active_code", False)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on - generate new OTP code."""
        try:
            # Delete existing codes first
            auth_codes = await self.api_client.get_auth_codes()
            if auth_codes:
                await self.api_client.delete_auth_codes(auth_codes)
            
            # Create new code
            success = await self.api_client.create_auth_code()
            if success:
                # Fire event to notify sensor
                self.hass.bus.async_fire(CUSTOM_EVENT, {"state": "on"})
                # Refresh coordinator data
                await self.coordinator.async_request_refresh()
            else:
                logger.error("Failed to create OTP code")
                
        except Exception as err:
            logger.exception(f"Error turning on OTP switch: {err}")

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off - delete OTP codes."""
        try:
            auth_codes = await self.api_client.get_auth_codes()
            if auth_codes:
                await self.api_client.delete_auth_codes(auth_codes)
            
            # Fire event to notify sensor
            self.hass.bus.async_fire(CUSTOM_EVENT, {"state": "off"})
            # Refresh coordinator data
            await self.coordinator.async_request_refresh()
            
        except Exception as err:
            logger.exception(f"Error turning off OTP switch: {err}")

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Set up Nuki OTP switch from config entry."""
    # Get the coordinator and api_client from hass data (set by sensor)
    integration_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = integration_data["coordinator"]
    api_client = integration_data["api_client"]
    
    async_add_entities([NukiOTPSwitch(coordinator, api_client)])
    return True