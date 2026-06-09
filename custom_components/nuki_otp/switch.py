"""Nuki OTP Switch implementation."""
import logging
from typing import Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
        # Optimistic state. Generating an OTP is a multi-second round trip to
        # the Nuki cloud, and this is a CoordinatorEntity whose authoritative
        # state is the *last poll*. Without an override the UI would snap back
        # to the pre-press state mid-operation (off→on flicker on turn-on),
        # then jump again once the next refresh lands. We assume the requested
        # state immediately and clear the override once the coordinator
        # delivers data that confirms it.
        self._optimistic_state: Optional[bool] = None

    @property
    def assumed_state(self) -> bool:
        """Report optimistic writes while an OTP operation is in flight."""
        return self._optimistic_state is not None

    @property
    def is_on(self) -> bool:
        """Return the state of the switch.

        While an operation is in flight we report the optimistically-assumed
        state so the toggle does not flicker; otherwise we reflect the
        coordinator's authoritative view.
        """
        if self._optimistic_state is not None:
            return self._optimistic_state
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("has_active_code", False)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Clear the optimistic override once the poll confirms it.

        The coordinator's data is authoritative; as soon as it agrees with the
        state we assumed (or once the operation has otherwise settled), we drop
        the override and let ``is_on`` reflect real data again.
        """
        if self._optimistic_state is not None and self.coordinator.data is not None:
            actual = self.coordinator.data.get("has_active_code", False)
            if actual == self._optimistic_state:
                self._optimistic_state = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on - generate new OTP code."""
        # Assume on immediately so the UI does not flap while the (slow) OTP
        # generation round trip is in progress.
        self._optimistic_state = True
        self.async_write_ha_state()
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
                # Generation failed: drop the optimistic state so the UI
                # reflects reality rather than a stuck "on".
                self._optimistic_state = None
                self.async_write_ha_state()
        except Exception as err:
            _LOGGER.exception("Error turning on OTP switch: %s", err)
            self._optimistic_state = None
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off - delete OTP codes."""
        # Assume off immediately for a smooth toggle while deletion runs.
        self._optimistic_state = False
        self.async_write_ha_state()
        try:
            auth_codes = await self.api_client.get_auth_codes()
            if auth_codes:
                await self.api_client.delete_auth_codes(auth_codes)

            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.exception("Error turning off OTP switch: %s", err)
            self._optimistic_state = None
            self.async_write_ha_state()


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
