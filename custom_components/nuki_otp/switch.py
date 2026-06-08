"""Nuki OTP Switch implementation."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NukiOTPDataCoordinator
from .helpers import NukiAPIClient

_LOGGER = logging.getLogger(__name__)


class NukiOTPSwitch(CoordinatorEntity, SwitchEntity):
    """Nuki OTP Switch."""

    def __init__(
        self,
        coordinator: NukiOTPDataCoordinator,
        api_client: NukiAPIClient,
        entry_id: str,
        nuki_name: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self.api_client = api_client
        self._attr_unique_id = f"{entry_id}_otp_switch"
        self._attr_name = "Nuki OTP Generator"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=f"Nuki OTP - {nuki_name}",
            manufacturer="Nuki",
            model="OTP Generator",
        )

    @property
    def is_on(self) -> bool:
        """Return the state of the switch."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("has_active_code", False)

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
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to create OTP code")
        except Exception as err:
            _LOGGER.exception("Error turning on OTP switch: %s", err)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off - delete OTP codes."""
        try:
            auth_codes = await self.api_client.get_auth_codes()
            if auth_codes:
                await self.api_client.delete_auth_codes(auth_codes)

            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.exception("Error turning off OTP switch: %s", err)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Nuki OTP switch from config entry."""
    integration_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = integration_data["coordinator"]
    api_client = integration_data["api_client"]
    config = integration_data["config"]

    async_add_entities(
        [NukiOTPSwitch(coordinator, api_client, entry.entry_id, config.nuki_name)]
    )
