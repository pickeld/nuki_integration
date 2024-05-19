import voluptuous as vol
from homeassistant import config_entries

DOMAIN = "glinet"


class GLiNetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required('router_url', default='http://192.168.8.1'): vol.All(str, vol.Length(min=1)),
                    vol.Required('router_username', default='root'): vol.All(str, vol.Length(min=1)),
                    vol.Required('router_password'): vol.All(str, vol.Length(min=1)),
                    vol.Required('router_name'): vol.All(str, vol.Length(min=1)),
                })
            )
        await self.async_set_unique_id(f"{DOMAIN}_unique")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="GL.iNET", data=user_input)
