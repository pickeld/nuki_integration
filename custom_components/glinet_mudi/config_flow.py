import voluptuous as vol
from homeassistant import config_entries

DOMAIN = "glinet_mudi"


class NukiOtpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required('api_url', default='https://api.nuki.io'): vol.All(str, vol.Length(min=1)),
                    vol.Required('api_token'): vol.All(str, vol.Length(min=1)),
                    vol.Required('nuki_name'): vol.All(str, vol.Length(min=1)),
                    vol.Required('otp_username', default='OTP'): vol.All(str, vol.Length(min=1)),
                    vol.Required('otp_lifetime_hours', default=12): vol.All(int, vol.Range(min=0)),
                })
            )
        await self.async_set_unique_id(f"{DOMAIN}_unique")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Nuki OTP", data=user_input)
