"""Config flow for Nuki OTP integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    DEFAULT_API_URL,
    DEFAULT_OTP_USERNAME,
    DEFAULT_OTP_LIFETIME_HOURS,
)
from .helpers import NukiAPIClient, NukiConfig, NukiAPIError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("api_url", default=DEFAULT_API_URL): vol.All(
        str, vol.Length(min=1), vol.Url()
    ),
    vol.Required("api_token"): vol.All(str, vol.Length(min=1)),
    vol.Required("nuki_name"): vol.All(str, vol.Length(min=1)),
    vol.Optional("otp_username", default=DEFAULT_OTP_USERNAME): vol.All(
        str, vol.Length(min=1)
    ),
    vol.Optional("otp_lifetime_hours", default=DEFAULT_OTP_LIFETIME_HOURS): vol.All(
        int, vol.Range(min=1, max=168)  # 1 hour to 1 week
    ),
})


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class NukiNotFound(HomeAssistantError):
    """Error to indicate the specified Nuki device was not found."""


async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the user input allows us to connect."""
    config = NukiConfig(
        api_token=data["api_token"],
        api_url=data["api_url"],
        otp_username=data.get("otp_username", DEFAULT_OTP_USERNAME),
        nuki_name=data["nuki_name"],
        otp_lifetime_hours=data.get("otp_lifetime_hours", DEFAULT_OTP_LIFETIME_HOURS),
    )
    
    api_client = NukiAPIClient(hass, config)
    
    try:
        # Test API connection by getting smartlocks
        smartlock = await api_client.get_smartlock()
        if not smartlock:
            raise NukiNotFound("Specified Nuki device not found")
            
        # Test auth codes endpoint
        await api_client.get_auth_codes()
        
    except NukiAPIError as err:
        if "401" in str(err) or "403" in str(err):
            raise InvalidAuth("Invalid API token")
        raise CannotConnect(f"Cannot connect to Nuki API: {err}")
    except Exception as err:
        _LOGGER.exception("Unexpected error during validation")
        raise CannotConnect(f"Unexpected error: {err}")

    return {
        "title": f"Nuki OTP - {data['nuki_name']}",
        "smartlock_id": smartlock.get("smartlockId"),
    }


@config_entries.HANDLERS.register(DOMAIN)
class NukiConfigFlow(config_entries.ConfigFlow):
    """Handle a config flow for Nuki OTP."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLLING

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._errors: Dict[str, str] = {}

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors=self._errors,
            )

        try:
            info = await validate_input(self.hass, user_input)
        except CannotConnect:
            self._errors["base"] = "cannot_connect"
        except InvalidAuth:
            self._errors["base"] = "invalid_auth"
        except NukiNotFound:
            self._errors["nuki_name"] = "nuki_not_found"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            self._errors["base"] = "unknown"
        else:
            await self.async_set_unique_id(
                f"{DOMAIN}_{user_input['nuki_name'].lower().replace(' ', '_')}"
            )
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=self._errors,
        )

    async def async_step_import(self, import_data: Dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        return await self.async_step_user(import_data)