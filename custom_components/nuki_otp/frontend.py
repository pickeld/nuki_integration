"""Frontend (Lovelace card) registration for the Nuki OTP integration.

The integration ships the ``ha-otp-card`` Lovelace card in its ``www`` folder.
On setup we serve that file from a static URL and register it as a Lovelace
"extra module URL" so the card's custom element is loaded automatically. This
means a user who installs the integration through HACS gets the card without
copying files into ``config/www`` or hand-editing dashboard resources.

The work is guarded so it runs at most once per Home Assistant instance even
when several config entries are set up.
"""
from __future__ import annotations

import logging
import os

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import IntegrationNotFound, async_get_integration

from .const import CARD_FILENAME, CARD_URL_PATH, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Marker stored in hass.data so registration only happens once.
_REGISTERED_KEY = f"{DOMAIN}_frontend_registered"


async def _integration_version(hass: HomeAssistant) -> str:
    """Return the integration version (for cache busting).

    Home Assistant parses each integration's ``manifest.json`` at startup and
    caches it on the loader, so the version is read from that cache rather than
    opening the file ourselves. The previous ``open()`` ran inside the event
    loop during setup and was flagged by HA's async loop protection.
    """
    try:
        integration = await async_get_integration(hass, DOMAIN)
    except IntegrationNotFound:
        return "0"
    return str(integration.version or "0")


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled card and add it as a Lovelace module resource."""
    if hass.data.get(_REGISTERED_KEY):
        return

    card_path = os.path.join(os.path.dirname(__file__), "www", CARD_FILENAME)
    if not os.path.exists(card_path):
        _LOGGER.warning(
            "Bundled OTP card not found at %s; skipping registration", card_path
        )
        return

    # Serve the JS file from a stable URL. cache_headers=False so a card update
    # shipped with a new integration version is not served stale by HA itself.
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_PATH, card_path, False)]
    )

    # Add the card to the frontend's extra module URLs so its custom element is
    # loaded on every dashboard. The version query string busts the browser
    # cache whenever the bundled card changes.
    versioned_url = f"{CARD_URL_PATH}?v={await _integration_version(hass)}"
    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, versioned_url)
    except ImportError:  # pragma: no cover - frontend always present in HA
        _LOGGER.debug("frontend component unavailable; card auto-load skipped")
        return

    hass.data[_REGISTERED_KEY] = True
    _LOGGER.debug("Registered bundled OTP card at %s", versioned_url)
