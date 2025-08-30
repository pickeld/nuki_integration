import logging
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import ConfigEntryNotReady

logger = logging.getLogger(__name__)

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
    pass


class NukiAPIClient:
    """Nuki API client with proper error handling and async support."""
    
    def __init__(self, hass: HomeAssistant, config: NukiConfig):
        self.hass = hass
        self.config = config
        self._session = async_get_clientsession(hass)
        
    @property
    def headers(self) -> Dict[str, str]:
        """Get API headers."""
        return {
            "Authorization": f"Bearer {self.config.api_token}",
            "Accept": "application/json"
        }
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        retries: int = MAX_RETRIES
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
                    elif response.status == 204:
                        return {}
                    else:
                        error_text = await response.text()
                        raise NukiAPIError(
                            f"API request failed: {response.status} - {error_text}"
                        )
                        
            except asyncio.TimeoutError:
                if attempt < retries:
                    logger.warning(f"Request timeout, retrying in {RETRY_DELAY}s...")
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise NukiAPIError("Request timeout after retries")
                
            except aiohttp.ClientError as e:
                if attempt < retries:
                    logger.warning(f"Client error, retrying: {e}")
                    await asyncio.sleep(RETRY_DELAY)
                    continue
                raise NukiAPIError(f"Client error: {e}")
        
        raise NukiAPIError("Max retries exceeded")
    
    async def get_auth_codes(self) -> List[Dict]:
        """Get all OTP auth codes."""
        try:
            results = await self._make_request("GET", "smartlock/auth?type=13")
            return [auth for auth in results if auth.get('name', '').startswith('OTP')]
        except NukiAPIError:
            logger.exception("Failed to get auth codes")
            return []
    
    async def get_smartlock(self) -> Optional[Dict]:
        """Get smartlock by name."""
        try:
            locks = await self._make_request("GET", "smartlock")
            for lock in locks:
                if lock.get('name') == self.config.nuki_name:
                    return lock
            logger.error(f"Smartlock '{self.config.nuki_name}' not found")
            return None
        except NukiAPIError:
            logger.exception("Failed to get smartlock")
            return None
    
    async def create_auth_code(self) -> bool:
        """Create new OTP auth code."""
        try:
            smartlock = await self.get_smartlock()
            if not smartlock:
                return False
                
            start_date, end_date = self._get_time_range()
            code = self._generate_otp_code()
            
            data = {
                "name": f"{self.config.otp_username}_code",
                "start_date": start_date,
                "end_date": end_date,
                "allowedWeekDays": 127,
                "allowedFromTime": 0,
                "allowedUntilTime": 0,
                "smartlockIds": [smartlock['smartlockId']],
                "remoteAllowed": True,
                "smartActionsEnabled": False,
                "type": 13,
                "code": code
            }
            
            await self._make_request("PUT", "smartlock/auth", data)
            logger.info(f"Auth code created: {code}")
            return True
            
        except NukiAPIError:
            logger.exception("Failed to create auth code")
            return False
    
    async def delete_auth_codes(self, auth_codes: List[Dict]) -> bool:
        """Delete auth codes."""
        if not auth_codes:
            return True
            
        try:
            ids = [auth['id'] for auth in auth_codes]
            await self._make_request("DELETE", "smartlock/auth", {"ids": ids})
            logger.info(f"Deleted auth codes: {ids}")
            return True
        except NukiAPIError:
            logger.exception("Failed to delete auth codes")
            return False
    
    async def get_smartlock_logs(self, smartlock_id: str, auth_id: str) -> List[Dict]:
        """Get smartlock usage logs."""
        try:
            result = await self._make_request(
                "GET",
                f"smartlock/{smartlock_id}/log?action=1&authId={auth_id}"
            )
            return result if isinstance(result, list) else []
        except NukiAPIError:
            logger.exception("Failed to get smartlock logs")
            return []
    
    def _generate_otp_code(self, length: int = 6) -> int:
        """Generate random OTP code."""
        code_str = ''.join(random.choice('123456789') for _ in range(length))
        return int(code_str)
    
    def _get_time_range(self) -> Tuple[str, str]:
        """Get time range for OTP validity."""
        now = datetime.utcnow()
        end_time = now + timedelta(hours=self.config.otp_lifetime_hours)
        
        start_date = now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        end_date = end_time.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        
        return start_date, end_date
    
    async def is_auth_expired(self, auth: Dict) -> bool:
        """Check if auth code is expired."""
        try:
            creation_date = datetime.strptime(
                auth['creationDate'], 
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )
            lifetime = datetime.utcnow() - creation_date
            return lifetime.total_seconds() >= self.config.otp_lifetime_hours * 3600
        except (KeyError, ValueError):
            return True
    
    async def is_auth_used(self, auth: Dict) -> bool:
        """Check if auth code has been used."""
        try:
            smartlock = await self.get_smartlock()
            if not smartlock:
                return False
                
            logs = await self.get_smartlock_logs(
                smartlock['smartlockId'], 
                auth['id']
            )
            return len(logs) > 0
        except Exception:
            logger.exception("Error checking auth usage")
            return False
    
    async def cleanup_expired_codes(self) -> None:
        """Clean up expired or used auth codes."""
        try:
            auth_codes = await self.get_auth_codes()
            if not auth_codes:
                return
                
            to_delete = []
            for auth in auth_codes:
                if await self.is_auth_expired(auth) or await self.is_auth_used(auth):
                    to_delete.append(auth)
                    logger.debug(f"Marking for deletion: {auth['name']}")
            
            if to_delete:
                await self.delete_auth_codes(to_delete)
                
        except Exception:
            logger.exception("Error during cleanup")