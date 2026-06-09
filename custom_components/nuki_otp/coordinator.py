"""Data update coordinator for the Nuki OTP integration."""
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .helpers import NukiAPIClient, NukiAuthError

_LOGGER = logging.getLogger(__name__)

# Expired/used codes are deleted on this cadence, independent of the read
# poll, so deletion latency or failures never couple into the data refresh.
CLEANUP_INTERVAL = timedelta(hours=1)


class NukiOTPDataCoordinator(DataUpdateCoordinator):
    """Data coordinator for Nuki OTP integration."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_client: NukiAPIClient,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=5),
            config_entry=config_entry,
        )
        self.api_client = api_client

    @callback
    def async_start_cleanup(self) -> CALLBACK_TYPE:
        """Start periodic expired-code cleanup on its own schedule.

        Returns the unsubscribe callback so the caller can register it with
        the config entry and cancel cleanup on unload.
        """
        return async_track_time_interval(
            self.hass, self._async_cleanup, CLEANUP_INTERVAL
        )

    async def _async_cleanup(self, _now=None) -> None:
        """Delete expired/used codes; isolated from the read poll."""
        try:
            await self.api_client.cleanup_expired_codes()
        except NukiAuthError:
            # Reauth is driven by the read poll (_async_update_data); from this
            # scheduled callback we can only ask HA to start the flow. Avoid
            # logging a traceback for an expected credential failure.
            _LOGGER.debug("Cleanup skipped: API authentication failed")
            if self.config_entry is not None:
                self.config_entry.async_start_reauth(self.hass)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from API endpoint.

        This is a read-only refresh: it must not mutate lock state. Expired/
        used code cleanup runs on its own scheduled path (async_start_cleanup)
        so a slow or failing delete never couples into the 5-minute refresh.
        """
        try:
            # Get current auth codes
            auth_codes = await self.api_client.get_auth_codes()

            current_code = auth_codes[0] if auth_codes else None
            if current_code is not None:
                # The API never returns the secret code on read; surface the
                # code we cached locally when we generated it.
                cached = self.api_client.get_cached_code(current_code.get("name", ""))
                if cached is not None:
                    current_code = {**current_code, "code": cached}

            return {
                "auth_codes": auth_codes,
                "current_code": current_code,
                "has_active_code": len(auth_codes) > 0,
            }
        except NukiAuthError as err:
            # Token revoked/expired: trigger HA's reauth flow so the user can
            # supply a new token without re-adding the integration.
            raise ConfigEntryAuthFailed(
                "Nuki API token rejected; reauthentication required"
            ) from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
