"""API client and helpers for the Nuki OTP integration."""
import asyncio
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional, Tuple, Union

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Constants
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 1


@dataclass
class NukiConfig:
    """Configuration data for Nuki integration."""
    api_token: str
    api_url: str
    otp_username: str
    nuki_name: str
    otp_lifetime_hours: int


class NukiAPIError(Exception):
    """Custom exception for Nuki API errors."""


class NukiAPIClient:
    """Nuki API client with proper error handling and async support."""

    def __init__(self, hass: HomeAssistant, config: NukiConfig):
        self.hass = hass
        self.config = config
        self._session = async_get_clientsession(hass)
        # Cache of generated OTP codes keyed by auth name. The Nuki API never
        # returns the secret code on read (it is write-only), so we keep the
        # code we generated locally to surface it through the sensor. Sensitive:
        # never log the values stored here.
        self._code_cache: Dict[str, str] = {}

    @property
    def headers(self) -> Dict[str, str]:
        """Get API headers."""
        return {
            "Authorization": f"Bearer {self.config.api_token}",
            "Accept": "application/json",
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Union[Dict, List]] = None,
        retries: int = MAX_RETRIES,
    ):
        """Make HTTP request with retry logic."""
        url = f"{self.config.api_url}/{endpoint}"

        for attempt in range(retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
                async with self._session.request(
                    method, url, headers=self.headers, json=json_data, timeout=timeout
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    if response.status == 204:
                        return {}
                    error_text = await response.text()
                    raise NukiAPIError(
                        f"API request failed: {response.status} - {error_text}"
                    )

            except asyncio.TimeoutError:
                if attempt < retries:
                    _LOGGER.warning("Request timeout, retrying in %ss...", RETRY_DELAY)
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise NukiAPIError("Request timeout after retries")

            except aiohttp.ClientError as err:
                if attempt < retries:
                    _LOGGER.warning("Client error, retrying: %s", err)
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise NukiAPIError(f"Client error: {err}") from err

        raise NukiAPIError("Max retries exceeded")

    async def get_auth_codes(self) -> List[Dict]:
        """Get all OTP auth codes created by this integration."""
        try:
            # Nuki Web API filters auth types via the plural "types" query
            # param (comma-separated). 13 = keypad code.
            results = await self._make_request("GET", "smartlock/auth?types=13")
            prefix = self.config.otp_username
            return [
                auth for auth in results
                if auth.get("name", "").startswith(prefix)
            ]
        except NukiAPIError:
            _LOGGER.exception("Failed to get auth codes")
            return []

    async def get_smartlock(self) -> Optional[Dict]:
        """Get smartlock by name."""
        try:
            locks = await self._make_request("GET", "smartlock")
            for lock in locks:
                if lock.get("name") == self.config.nuki_name:
                    return lock
            _LOGGER.error("Smartlock '%s' not found", self.config.nuki_name)
            return None
        except NukiAPIError:
            _LOGGER.exception("Failed to get smartlock")
            return None

    async def create_auth_code(self) -> bool:
        """Create new OTP auth code."""
        try:
            smartlock = await self.get_smartlock()
            if not smartlock:
                return False

            start_date, end_date = self._get_time_range()
            code = self._generate_otp_code()
            name = f"{self.config.otp_username}_code"

            data = {
                "name": name,
                # Nuki Web API SmartlocksAuthCreate uses allowedFromDate/
                # allowedUntilDate (ISO-8601). The old start_date/end_date keys
                # are not in the schema and were silently ignored, so codes
                # never honored otp_lifetime_hours.
                "allowedFromDate": start_date,
                "allowedUntilDate": end_date,
                "allowedWeekDays": 127,
                "allowedFromTime": 0,
                "allowedUntilTime": 0,
                "smartlockIds": [smartlock["smartlockId"]],
                "remoteAllowed": True,
                "smartActionsEnabled": False,
                "type": 13,
                "code": code,
            }

            await self._make_request("PUT", "smartlock/auth", data)
            # Cache the generated code so the sensor can surface it; the API
            # will not return it on subsequent reads.
            self._code_cache[name] = str(code)
            _LOGGER.info("New OTP auth code created")
            return True

        except NukiAPIError:
            _LOGGER.exception("Failed to create auth code")
            return False

    async def delete_auth_codes(self, auth_codes: List[Dict]) -> bool:
        """Delete auth codes."""
        if not auth_codes:
            return True

        try:
            # Nuki Web API DELETE /smartlock/auth expects a bare JSON array of
            # string auth ids (e.g. ["id1", "id2"]), NOT an object such as
            # {"ids": [...]}. The wrapped shape fails schema validation and the
            # codes are never removed. The auth "id" field is a string.
            ids = [auth["id"] for auth in auth_codes]
            await self._make_request("DELETE", "smartlock/auth", ids)
            # Drop the cached codes for the deleted auths so the sensor falls
            # back to "no code" once they are gone.
            for auth in auth_codes:
                self._code_cache.pop(auth.get("name", ""), None)
            _LOGGER.info("Deleted %d auth code(s)", len(ids))
            return True
        except NukiAPIError:
            _LOGGER.exception("Failed to delete auth codes")
            return False

    def get_cached_code(self, name: str) -> Optional[str]:
        """Return the locally cached code for an auth name, if known.

        The Nuki API never returns the secret code on read, so this is the
        only way to surface the currently active code.
        """
        return self._code_cache.get(name)

    async def get_smartlock_logs(self, smartlock_id: str, auth_id: str) -> List[Dict]:
        """Get smartlock usage logs."""
        try:
            result = await self._make_request(
                "GET",
                f"smartlock/{smartlock_id}/log?action=1&authId={auth_id}",
            )
            return result if isinstance(result, list) else []
        except NukiAPIError:
            _LOGGER.exception("Failed to get smartlock logs")
            return []

    def _generate_otp_code(self, length: int = 6) -> int:
        """Generate a cryptographically secure random OTP code."""
        code_str = "".join(secrets.choice("123456789") for _ in range(length))
        return int(code_str)

    def _get_time_range(self) -> Tuple[str, str]:
        """Get time range for OTP validity."""
        now = dt_util.utcnow()
        end_time = now + timedelta(hours=self.config.otp_lifetime_hours)

        start_date = now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        end_date = end_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        return start_date, end_date

    async def is_auth_expired(self, auth: Dict) -> bool:
        """Check if auth code is expired."""
        try:
            creation_date = dt_util.parse_datetime(auth["creationDate"])
            if creation_date is None:
                return True
            lifetime = dt_util.utcnow() - creation_date
            return lifetime.total_seconds() >= self.config.otp_lifetime_hours * 3600
        except (KeyError, ValueError):
            return True

    async def is_auth_used(self, auth: Dict, smartlock: Optional[Dict] = None) -> bool:
        """Check if auth code has been used.

        Pass ``smartlock`` to reuse an already-fetched smartlock and avoid
        re-fetching it per call; falls back to fetching when omitted.
        """
        try:
            if smartlock is None:
                smartlock = await self.get_smartlock()
            if not smartlock:
                return False

            logs = await self.get_smartlock_logs(
                smartlock["smartlockId"],
                auth["id"],
            )
            return len(logs) > 0
        except Exception:
            _LOGGER.exception("Error checking auth usage")
            return False

    async def cleanup_expired_codes(self) -> None:
        """Clean up expired or used auth codes."""
        try:
            auth_codes = await self.get_auth_codes()
            if not auth_codes:
                return

            # Fetch the smartlock once per cleanup cycle and reuse it for every
            # is_auth_used() check, instead of re-fetching the full smartlock
            # list per code (an N+1 against the Nuki cloud API).
            smartlock = await self.get_smartlock()

            to_delete = []
            for auth in auth_codes:
                if await self.is_auth_expired(auth) or await self.is_auth_used(auth, smartlock):
                    to_delete.append(auth)
                    _LOGGER.debug("Marking for deletion: %s", auth.get("name"))

            if to_delete:
                await self.delete_auth_codes(to_delete)

        except Exception:
            _LOGGER.exception("Error during cleanup")
