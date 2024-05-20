import logging

from homeassistant.components.switch import SwitchEntity

from .helpers import get_auth, del_auths, set_auth, initialize

CUSTOM_EVENT = "nuki_otp_switch_state_changed"
DOMAIN = "nuki_otp"

logger = logging.getLogger(__name__)


class NukiOTPButton(SwitchEntity):
    def __init__(self):
        self._is_on = False
        self._unique_id = "nuki_otp_switch"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "nuki_otp")},
            "name": "Nuki OTP",
            "model": "OTP Generator",
            "sw_version": "1.0"
        }

    @property
    def name(self):
        """Return the name of the switch."""
        return 'Nuki OTP'

    @property
    def is_on(self):
        """Return the state of the switch."""
        return self._is_on

    @property
    def unique_id(self):
        return self._unique_id

    async def async_update(self):
        """Update the sensor state."""
        auths: list = await get_auth()
        self._is_on = True if len(auths) else False
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        auths: list = await get_auth()
        if auths:
            await del_auths(auths=auths)
        await set_auth()
        self.hass.bus.async_fire(CUSTOM_EVENT, {"state": "on"})
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        auths: list = await get_auth()
        if auths:
            await del_auths(auths=auths)
        self.hass.bus.async_fire(CUSTOM_EVENT, {"state": "off"})
        self._is_on = False
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        await self.async_update()


async def async_setup_entry(hass, entry, add_entities):
    data = entry.data
    api_token = data["api_token"]
    api_url = data["api_url"]
    otp_username = data["otp_username"]
    nuki_name = data["nuki_name"]
    otp_lifetime_hours = int(data["otp_lifetime_hours"])

    initialize(api_token, api_url, otp_username, nuki_name, otp_lifetime_hours)
    add_entities([NukiOTPButton()])
    return True
