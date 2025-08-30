"""The Nuki OTP integration."""
import asyncio
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .helpers import NukiAPIClient, NukiConfig

PLATFORMS = ["sensor", "switch"]

async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Nuki OTP component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Nuki OTP from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    config = NukiConfig(
        api_token=entry.data["api_token"],
        api_url=entry.data["api_url"],
        otp_username=entry.data.get("otp_username"),
        nuki_name=entry.data["nuki_name"],
        otp_lifetime_hours=entry.data.get("otp_lifetime_hours"),
    )
    
    hass.data[DOMAIN][entry.entry_id] = config
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        
    return unload_ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
