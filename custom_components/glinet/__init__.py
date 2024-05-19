import asyncio

DOMAIN = "glinet"


async def async_setup(hass, config):
    return True


async def async_setup_entry(hass, entry):
    for platform in ["sensor", "switch"]:
        hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, platform))
    return True


async def async_unload_entry(hass, entry):
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in ["sensor", "switch"]
            ]
        )
    )
    return unload_ok
