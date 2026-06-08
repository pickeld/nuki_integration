"""Data update coordinator for the Nuki OTP integration."""
import logging
from datetime import timedelta
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .helpers import NukiAPIClient

_LOGGER = logging.getLogger(__name__)


class NukiOTPDataCoordinator(DataUpdateCoordinator):
    """Data coordinator for Nuki OTP integration."""

    def __init__(self, hass: HomeAssistant, api_client: NukiAPIClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
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
            raise UpdateFailed(f"Error communicating with API: {err}") from err
