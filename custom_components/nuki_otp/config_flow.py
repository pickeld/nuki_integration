"""Config flow for Nuki OTP integration."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    DEFAULT_API_URL,
    DEFAULT_OTP_USERNAME,
    DEFAULT_OTP_LIFETIME_HOURS,
)
from .helpers import NukiAPIClient, NukiConfig, NukiAPIError, NukiAuthError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    # NB: the URL format is validated server-side in validate_input(), not via
    # vol.Url() in the schema. voluptuous_serialize (used by HA to send the
    # form to the frontend) cannot serialize vol.Url and raises
    # "Unable to convert schema", which surfaces as a 500 when the config flow
    # form loads. A URL TextSelector renders a proper URL field and serializes
    # cleanly.
    vol.Required("api_url", default=DEFAULT_API_URL): selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
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

# Reauth only collects a fresh token; the rest of the connection config
# (URL, Nuki name) is reused from the existing entry.
STEP_REAUTH_DATA_SCHEMA = vol.Schema({
    vol.Required("api_token"): vol.All(str, vol.Length(min=1)),
})


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class NukiNotFound(HomeAssistantError):
    """Error to indicate the specified Nuki device was not found."""


class InvalidUrl(HomeAssistantError):
    """Error to indicate the API URL is not a valid http(s) URL."""


def _validate_api_url(value: str) -> str:
    """Validate the API URL has an http(s) scheme and a host.

    Done server-side rather than with vol.Url() in the schema because the
    latter cannot be serialized to the frontend (see STEP_USER_DATA_SCHEMA).
    """
    parsed = urlparse((value or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise InvalidUrl(f"Invalid API URL: {value!r}")
    return value


async def validate_input(hass: HomeAssistant, data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the user input allows us to connect."""
    _validate_api_url(data["api_url"])

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
        
    except NukiAuthError as err:
        raise InvalidAuth("Invalid API token") from err
    except NukiAPIError as err:
        raise CannotConnect(f"Cannot connect to Nuki API: {err}")
    except Exception as err:
        _LOGGER.exception("Unexpected error during validation")
        raise CannotConnect(f"Unexpected error: {err}")

    return {
        "title": f"Nuki OTP - {data['nuki_name']}",
        "smartlock_id": smartlock.get("smartlockId"),
    }


class NukiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nuki OTP."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._errors: Dict[str, str] = {}
        # Entry being reauthenticated, set when async_step_reauth runs.
        self._reauth_entry: Optional[config_entries.ConfigEntry] = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "NukiOptionsFlow":
        """Get the options flow for this handler."""
        return NukiOptionsFlow(config_entry)

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

        # Clear any errors from a prior submission so corrected input
        # doesn't keep showing the old error.
        self._errors = {}

        try:
            info = await validate_input(self.hass, user_input)
        except InvalidUrl:
            self._errors["api_url"] = "invalid_url"
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

    async def async_step_reauth(
        self, entry_data: Dict[str, Any]
    ) -> FlowResult:
        """Handle reauth triggered by a 401/403 from the API."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Prompt for a new API token and validate it against the existing entry."""
        assert self._reauth_entry is not None

        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=STEP_REAUTH_DATA_SCHEMA,
                description_placeholders={
                    "nuki_name": self._reauth_entry.data["nuki_name"],
                },
            )

        # Clear any errors from a prior submission so a corrected token
        # doesn't keep showing the old error.
        self._errors = {}

        # Validate the new token against the existing connection config.
        validation_data = {**self._reauth_entry.data, "api_token": user_input["api_token"]}

        try:
            await validate_input(self.hass, validation_data)
        except CannotConnect:
            self._errors["base"] = "cannot_connect"
        except InvalidAuth:
            self._errors["base"] = "invalid_auth"
        except NukiNotFound:
            self._errors["base"] = "nuki_not_found"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception during reauth")
            self._errors["base"] = "unknown"
        else:
            return self.async_update_reload_and_abort(
                self._reauth_entry,
                data={**self._reauth_entry.data, "api_token": user_input["api_token"]},
            )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=self._errors,
            description_placeholders={
                "nuki_name": self._reauth_entry.data["nuki_name"],
            },
        )


class NukiOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Nuki OTP.

    Exposes the safe-to-edit fields (OTP username and lifetime) so they can be
    changed after setup without removing and re-adding the integration.
    Connection fields (API URL/token, Nuki name) are intentionally omitted
    because changing them requires re-validation and a new unique id.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    def _current(self, key: str, default: Any) -> Any:
        """Return the current value, preferring options over original data."""
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, default)
        )

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema({
            vol.Required(
                "otp_username",
                default=self._current("otp_username", DEFAULT_OTP_USERNAME),
            ): vol.All(str, vol.Length(min=1)),
            vol.Required(
                "otp_lifetime_hours",
                default=self._current(
                    "otp_lifetime_hours", DEFAULT_OTP_LIFETIME_HOURS
                ),
            ): vol.All(int, vol.Range(min=1, max=168)),  # 1 hour to 1 week
        })

        return self.async_show_form(step_id="init", data_schema=options_schema)