"""Regression tests for the smart-lock discovery flow (PIC-13).

Setup used to ask the user to type the lock name *exactly* as it appears in
their Nuki account. Typing anything else (e.g. "Home") failed validation with::

    Smartlock 'Home' not found
    NukiNotFound: Specified Nuki device not found

and the integration could not be added. The flow is now two steps:

1. ``async_step_user`` collects the API URL + token, validates the token, and
   *discovers* the account's smart locks (``discover_smartlocks``).
2. ``async_step_select_lock`` shows those locks in a dropdown so the user picks
   one — a mistyped/non-existent name is impossible.

These tests load ``config_flow.py`` behind lightweight stubs (no full Home
Assistant install) and assert the discovery + selection behaviour, including the
"account has no locks" path.
"""
import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _install_stub_modules():
    """Register minimal HA / selector stubs before importing config_flow."""
    import voluptuous as vol  # noqa: F401  (ensures dependency present)

    if "homeassistant" not in sys.modules:
        ha = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = ha
    else:
        ha = sys.modules["homeassistant"]

    if "homeassistant.config_entries" not in sys.modules:
        config_entries = types.ModuleType("homeassistant.config_entries")

        class ConfigFlow:
            def __init_subclass__(cls, **kwargs):  # accepts domain=...
                super().__init_subclass__()

            # Helpers the flow calls; recorded/no-op for the tests.
            async def async_set_unique_id(self, unique_id):
                self._unique_id = unique_id
                return None

            def _abort_if_unique_id_configured(self):
                return None

            def async_show_form(self, **kwargs):
                return {"type": "form", **kwargs}

            def async_create_entry(self, **kwargs):
                return {"type": "create_entry", **kwargs}

        class OptionsFlow:
            pass

        class ConfigEntry:
            pass

        config_entries.ConfigFlow = ConfigFlow
        config_entries.OptionsFlow = OptionsFlow
        config_entries.ConfigEntry = ConfigEntry
        sys.modules["homeassistant.config_entries"] = config_entries
        ha.config_entries = config_entries

    if "homeassistant.core" not in sys.modules:
        core = types.ModuleType("homeassistant.core")

        class HomeAssistant:
            pass

        def callback(func):
            return func

        core.HomeAssistant = HomeAssistant
        core.callback = callback
        sys.modules["homeassistant.core"] = core
        ha.core = core

    if "homeassistant.data_entry_flow" not in sys.modules:
        def_mod = types.ModuleType("homeassistant.data_entry_flow")
        def_mod.FlowResult = dict
        sys.modules["homeassistant.data_entry_flow"] = def_mod
        ha.data_entry_flow = def_mod

    if "homeassistant.exceptions" not in sys.modules:
        exc_mod = types.ModuleType("homeassistant.exceptions")

        class HomeAssistantError(Exception):
            pass

        exc_mod.HomeAssistantError = HomeAssistantError
        sys.modules["homeassistant.exceptions"] = exc_mod
        ha.exceptions = exc_mod

    if "homeassistant.helpers" not in sys.modules:
        helpers_pkg = types.ModuleType("homeassistant.helpers")
        sys.modules["homeassistant.helpers"] = helpers_pkg
        ha.helpers = helpers_pkg
    else:
        helpers_pkg = sys.modules["homeassistant.helpers"]

    if "homeassistant.helpers.selector" not in sys.modules:
        selector = types.ModuleType("homeassistant.helpers.selector")

        class TextSelectorType:
            URL = "url"

        class TextSelectorConfig:
            def __init__(self, type=None):
                self.type = type

        class TextSelector:
            def __init__(self, config=None):
                self.config = config

            def __call__(self, value):
                return value

        class SelectSelectorMode:
            DROPDOWN = "dropdown"

        class SelectOptionDict(dict):
            def __init__(self, value=None, label=None):
                super().__init__(value=value, label=label)

        class SelectSelectorConfig:
            def __init__(self, options=None, mode=None):
                self.options = options or []
                self.mode = mode

        class SelectSelector:
            def __init__(self, config=None):
                self.config = config

            def __call__(self, value):
                # Mirror HA: only allow values present in the option list.
                valid = {opt["value"] for opt in (self.config.options if self.config else [])}
                if value not in valid:
                    import voluptuous as vol
                    raise vol.Invalid(f"{value} is not a valid option")
                return value

        selector.TextSelectorType = TextSelectorType
        selector.TextSelectorConfig = TextSelectorConfig
        selector.TextSelector = TextSelector
        selector.SelectSelectorMode = SelectSelectorMode
        selector.SelectOptionDict = SelectOptionDict
        selector.SelectSelectorConfig = SelectSelectorConfig
        selector.SelectSelector = SelectSelector
        sys.modules["homeassistant.helpers.selector"] = selector
        helpers_pkg.selector = selector


try:
    import voluptuous as vol  # noqa: F401
    _HAVE_VOLUPTUOUS = True
except ImportError:  # pragma: no cover
    _HAVE_VOLUPTUOUS = False


def _run(coro):
    return asyncio.run(coro)


@unittest.skipUnless(_HAVE_VOLUPTUOUS, "voluptuous not installed")
class ConfigFlowDiscoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _install_stub_modules()

        repo_root = Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        if "nuki_otp_const" not in sys.modules:
            const = types.ModuleType("nuki_otp_const")
            const.DOMAIN = "nuki_otp"
            const.DEFAULT_API_URL = "https://api.nuki.io"
            const.DEFAULT_OTP_USERNAME = "OTP"
            const.DEFAULT_OTP_LIFETIME_HOURS = 12
            sys.modules["nuki_otp_const"] = const

        repo_component = repo_root / "custom_components" / "nuki_otp"

        # Reuse the helpers harness (installs aiohttp/HA stubs + loads helpers).
        from test_make_request_retry import helpers as _helpers  # noqa: F401
        sys.modules.setdefault("nuki_otp_helpers", _helpers)

        pkg_name = "nuki_otp_pkg"
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = [str(repo_component)]
            sys.modules[pkg_name] = pkg
            sys.modules[pkg_name + ".const"] = sys.modules["nuki_otp_const"]
            sys.modules[pkg_name + ".helpers"] = _helpers

        spec = importlib.util.spec_from_file_location(
            pkg_name + ".config_flow", repo_component / "config_flow.py"
        )
        cf = importlib.util.module_from_spec(spec)
        sys.modules[pkg_name + ".config_flow"] = cf
        spec.loader.exec_module(cf)
        cls.cf = cf
        cls.helpers = _helpers

    def _patch_list_smartlocks(self, result=None, exc=None):
        """Patch NukiAPIClient.list_smartlocks for the duration of a test."""
        async def fake(self_client):
            if exc is not None:
                raise exc
            return result if result is not None else []

        original = self.helpers.NukiAPIClient.list_smartlocks
        self.helpers.NukiAPIClient.list_smartlocks = fake
        self.addCleanup(
            setattr, self.helpers.NukiAPIClient, "list_smartlocks", original
        )

    def test_user_schema_only_has_connection_fields(self):
        """Step 1 must only ask for api_url + api_token (no nuki_name)."""
        keys = {str(k) for k in self.cf.STEP_USER_DATA_SCHEMA.schema}
        self.assertEqual(keys, {"api_url", "api_token"})

    def test_discover_returns_locks(self):
        self._patch_list_smartlocks(
            result=[{"name": "Front Door"}, {"name": "Back Door"}]
        )
        locks = _run(self.cf.discover_smartlocks(
            None, {"api_url": "https://api.nuki.io", "api_token": "t"}
        ))
        self.assertEqual([l["name"] for l in locks], ["Front Door", "Back Door"])

    def test_discover_invalid_auth(self):
        self._patch_list_smartlocks(exc=self.helpers.NukiAuthError("401"))
        with self.assertRaises(self.cf.InvalidAuth):
            _run(self.cf.discover_smartlocks(
                None, {"api_url": "https://api.nuki.io", "api_token": "bad"}
            ))

    def test_discover_no_locks_raises_not_found(self):
        self._patch_list_smartlocks(result=[])
        with self.assertRaises(self.cf.NukiNotFound):
            _run(self.cf.discover_smartlocks(
                None, {"api_url": "https://api.nuki.io", "api_token": "t"}
            ))

    def test_discover_bad_url(self):
        with self.assertRaises(self.cf.InvalidUrl):
            _run(self.cf.discover_smartlocks(
                None, {"api_url": "not-a-url", "api_token": "t"}
            ))

    def test_lock_step_schema_is_a_dropdown_of_discovered_names(self):
        from homeassistant.helpers import selector

        schema = self.cf._build_lock_step_schema(["Front Door", "Back Door"])
        nuki_validator = None
        for key, validator in schema.schema.items():
            if str(key) == "nuki_name":
                nuki_validator = validator
        self.assertIsInstance(nuki_validator, selector.SelectSelector)
        # A discovered name validates; an off-list name is rejected.
        self.assertEqual(nuki_validator("Front Door"), "Front Door")
        import voluptuous as vol
        with self.assertRaises(vol.Invalid):
            nuki_validator("Home")

    def test_full_flow_user_then_select(self):
        """End-to-end: connection step discovers, select step creates entry."""
        self._patch_list_smartlocks(result=[{"name": "Front Door"}])
        flow = self.cf.NukiConfigFlow()

        # Step 1: submit connection -> should advance to select_lock form.
        res1 = _run(flow.async_step_user(
            {"api_url": "https://api.nuki.io", "api_token": "tok"}
        ))
        self.assertEqual(res1.get("step_id"), "select_lock")
        self.assertEqual(flow._lock_names, ["Front Door"])

        # Step 2: pick the lock -> create entry with merged data.
        res2 = _run(flow.async_step_select_lock({
            "nuki_name": "Front Door",
            "otp_username": "OTP",
            "otp_lifetime_hours": 12,
        }))
        self.assertEqual(res2.get("type"), "create_entry")
        self.assertEqual(res2["data"]["nuki_name"], "Front Door")
        self.assertEqual(res2["data"]["api_token"], "tok")
        self.assertIn("Front Door", res2["title"])

    def test_user_step_surfaces_no_smartlocks_error(self):
        self._patch_list_smartlocks(result=[])
        flow = self.cf.NukiConfigFlow()
        res = _run(flow.async_step_user(
            {"api_url": "https://api.nuki.io", "api_token": "tok"}
        ))
        self.assertEqual(res.get("step_id"), "user")
        self.assertEqual(res["errors"].get("base"), "no_smartlocks")


if __name__ == "__main__":
    unittest.main()
