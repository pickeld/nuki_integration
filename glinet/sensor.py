import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later

# from .helpers import get_auth, house_keeper, initialize

logger = logging.getLogger(__name__)

CUSTOM_EVENT = "nuki_otp_switch_state_changed"
DOMAIN = "nuki_otp"
NO_CODE = "------"


class GLiNetSensor(SensorEntity):
    def __init__(self, otp_lifetime_hours):
        self._state = NO_CODE
        self._unique_id = "nuki_otp_code"
        self.otp_lifetime_hours = otp_lifetime_hours

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "nuki_otp")},
            "name": "Nuki OTP",
            "model": "OTP Generator",
            "sw_version": "1.0"
        }

    def get_expiry(self, creation_date, offset):
        creation_date = creation_date.replace('Z', '+00:00')
        utc_time = datetime.fromisoformat(creation_date)
        expiry_time = utc_time + timedelta(hours=offset)
        return expiry_time.isoformat()

    @property
    def extra_state_attributes(self):
        if self._state and isinstance(self._state, dict):
            return {"Code": str(self._state.get('code')),
                    "Name": self._state.get('name'),
                    "Enabled": self._state.get('enabled'),
                    "Remote Allowed": self._state.get('remoteAllowed'),
                    "Lock Count": self._state.get('lockCount'),
                    "Creation Date": self._state.get('creationDate'),
                    "Expiry Date": self.get_expiry(creation_date=self._state.get('creationDate'),
                                                   offset=self.otp_lifetime_hours)
                    }
        return {}

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return 'Nuki OTP Code'

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self._state and isinstance(self._state, dict) and 'code' in self._state:
            return self._state['code']
        return NO_CODE

    async def async_update(self):
        """Update the sensor state."""
        await house_keeper()
        _ = self.extra_state_attributes
        auths: list[dict] = await get_auth()
        self._state = auths[0] if len(auths) else None

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        await self.async_update()
        # Listen for the custom event to trigger an update
        self.async_on_remove(self.hass.bus.async_listen(CUSTOM_EVENT, self._handle_custom_event))

    @callback
    def _handle_custom_event(self, event):
        """Handle the custom event."""
        # Trigger an update of the sensor
        self.async_schedule_update_ha_state(True)
        async_call_later(self.hass, 2, self._delayed_update)

    @callback
    def _delayed_update(self, _=None):
        """Update the sensor after the delay."""
        self.async_schedule_update_ha_state(True)


async def async_setup_entry(hass, entry, add_entities):
    data = entry.data
    api_token = data["api_token"]
    api_url = data["api_url"]
    otp_username = data["otp_username"]
    nuki_name = data["nuki_name"]
    otp_lifetime_hours = int(data["otp_lifetime_hours"])
    initialize(api_token, api_url, otp_username, nuki_name, otp_lifetime_hours)
    add_entities([NukiOTPSensor(otp_lifetime_hours=otp_lifetime_hours)])
    return True
