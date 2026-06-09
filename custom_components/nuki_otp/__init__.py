"""The Nuki OTP integration."""
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DEFAULT_OTP_LIFETIME_HOURS,
    DEFAULT_OTP_USERNAME,
    DOMAIN,
)
from .coordinator import NukiOTPDataCoordinator
from .frontend import async_register_card
from .helpers import NukiAPIClient, NukiConfig

PLATFORMS = ["sensor", "switch"]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Nuki OTP component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Nuki OTP from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Serve and auto-load the bundled Lovelace card so HACS users get it
    # without copying files into config/www or adding dashboard resources.
    await async_register_card(hass)

    # Options (set via the OptionsFlow) override the original setup data so
    # editable fields like OTP username/lifetime take effect on reload.
    otp_username = entry.options.get(
        "otp_username", entry.data.get("otp_username", DEFAULT_OTP_USERNAME)
    )
    otp_lifetime_hours = entry.options.get(
        "otp_lifetime_hours",
        entry.data.get("otp_lifetime_hours", DEFAULT_OTP_LIFETIME_HOURS),
    )

    config = NukiConfig(
        api_token=entry.data["api_token"],
        api_url=entry.data["api_url"],
        otp_username=otp_username,
        nuki_name=entry.data["nuki_name"],
        otp_lifetime_hours=int(otp_lifetime_hours),
    )

    api_client = NukiAPIClient(hass, config)
    coordinator = NukiOTPDataCoordinator(hass, api_client, entry)
    await coordinator.async_config_entry_first_refresh()

    # Expired/used code cleanup runs on its own schedule, separate from the
    # read poll, so deletion never blocks or fails the data refresh. Register
    # the unsubscribe so the interval is cancelled when the entry unloads.
    entry.async_on_unload(coordinator.async_start_cleanup())

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api_client": api_client,
        "config": config,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
