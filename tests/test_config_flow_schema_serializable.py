"""Regression tests for the config-flow schema serialization bug (PIC-13).

The user step schema used ``vol.Url()`` to validate the API URL field. When
Home Assistant renders a config flow it serializes the data schema to JSON for
the frontend via ``voluptuous_serialize.convert``. That library has no
serializer for ``vol.Url`` and raises ``ValueError: Unable to convert schema:
<function Url ...>``, which surfaces to the user as:

    Config flow could not be loaded: 500 Internal Server Error

i.e. the integration could not be set up at all. The fix renders the URL field
with a URL ``TextSelector`` (which serializes cleanly) and moves the URL-format
check server-side into ``validate_input``.

These tests load ``config_flow.py`` behind lightweight stubs (no full Home
Assistant install needed) and assert:

* the user data schema contains **no** ``vol.Url`` validator (the thing that
  could not be serialized);
* ``_validate_api_url`` accepts valid http(s) URLs and rejects junk, raising
  ``InvalidUrl`` so the flow can map it to the ``api_url`` field.
"""
import sys
import types
import unittest
from pathlib import Path


def _install_stub_modules():
    """Register minimal HA/voluptuous-selector stubs before importing."""
    import voluptuous as vol

    # --- homeassistant package tree --------------------------------------
    if "homeassistant" not in sys.modules:
        ha = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = ha
    else:
        ha = sys.modules["homeassistant"]

    # The stubs below are filled in *additively*: another test module
    # (test_make_request_retry) may have already created some of these
    # homeassistant submodules with a different subset of attributes, and
    # Python shares sys.modules. So we check for the specific attribute, not
    # just module presence, or symbols like ``callback`` go missing.
    def _submod(name, attr):
        full = "homeassistant." + name
        mod = sys.modules.get(full)
        if mod is None:
            mod = types.ModuleType(full)
            sys.modules[full] = mod
        if getattr(ha, attr, None) is None:
            setattr(ha, attr, mod)
        return mod

    # homeassistant.config_entries
    config_entries = _submod("config_entries", "config_entries")
    if not hasattr(config_entries, "ConfigFlow"):
        class ConfigFlow:
            def __init_subclass__(cls, **kwargs):  # accepts domain=...
                super().__init_subclass__()

        class OptionsFlow:
            pass

        class ConfigEntry:
            pass

        config_entries.ConfigFlow = ConfigFlow
        config_entries.OptionsFlow = OptionsFlow
        config_entries.ConfigEntry = ConfigEntry

    # homeassistant.core
    core = _submod("core", "core")
    if not hasattr(core, "HomeAssistant"):
        class HomeAssistant:
            pass

        core.HomeAssistant = HomeAssistant
    if not hasattr(core, "callback"):
        def callback(func):
            return func

        core.callback = callback

    # homeassistant.data_entry_flow
    def_mod = _submod("data_entry_flow", "data_entry_flow")
    if not hasattr(def_mod, "FlowResult"):
        def_mod.FlowResult = dict

    # homeassistant.exceptions
    exc_mod = _submod("exceptions", "exceptions")
    if not hasattr(exc_mod, "HomeAssistantError"):
        class HomeAssistantError(Exception):
            pass

        exc_mod.HomeAssistantError = HomeAssistantError

    # homeassistant.helpers + homeassistant.helpers.selector
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
            """Stand-in that mirrors how HA's selector serializes itself.

            Crucially it is *callable as a voluptuous validator* (so it can sit
            in a schema) and is NOT a vol.Url, which is the whole point.
            """

            def __init__(self, config=None):
                self.config = config

            def __call__(self, value):
                return value

        selector.TextSelectorType = TextSelectorType
        selector.TextSelectorConfig = TextSelectorConfig
        selector.TextSelector = TextSelector
        sys.modules["homeassistant.helpers.selector"] = selector
        helpers_pkg.selector = selector


# voluptuous must be importable for these tests to mean anything.
try:
    import voluptuous as vol  # noqa: F401
    _HAVE_VOLUPTUOUS = True
except ImportError:  # pragma: no cover - environment without voluptuous
    _HAVE_VOLUPTUOUS = False


@unittest.skipUnless(_HAVE_VOLUPTUOUS, "voluptuous not installed")
class ConfigFlowSchemaSerializableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo_root = Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        # Load helpers.py (config_flow imports NukiAPIClient etc. from it).
        # Import the retry harness FIRST so its aiohttp / HA core / util.dt
        # stubs are installed on a clean slate; otherwise _install_stub_modules
        # creates ``homeassistant.helpers`` as a non-package and helpers.py's
        # ``from homeassistant.helpers.aiohttp_client import …`` fails. (This
        # ordering bug was invisible while voluptuous was absent and the whole
        # class self-skipped.)
        from test_make_request_retry import helpers as _helpers  # noqa: F401
        sys.modules.setdefault("nuki_otp_helpers", _helpers)

        _install_stub_modules()

        import importlib.util

        repo_component = repo_root / "custom_components" / "nuki_otp"

        # Stub the sibling modules config_flow imports so we don't drag in the
        # whole package __init__ / coordinator.
        if "nuki_otp_const" not in sys.modules:
            const = types.ModuleType("nuki_otp_const")
            const.DOMAIN = "nuki_otp"
            const.DEFAULT_API_URL = "https://api.nuki.io"
            const.DEFAULT_OTP_USERNAME = "OTP"
            const.DEFAULT_OTP_LIFETIME_HOURS = 12
            sys.modules["nuki_otp_const"] = const

        # config_flow.py does ``from .const import ...`` and
        # ``from .helpers import ...``; rewrite those by loading it as a module
        # whose package provides those names. Simplest: load by path after
        # injecting a fake package.
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

    def test_user_schema_has_no_vol_url(self):
        """The serialization-breaking vol.Url must be gone from the schema."""
        import voluptuous as vol

        schema = self.cf.STEP_USER_DATA_SCHEMA.schema
        for key, validator in schema.items():
            # vol.Url() returns a function named 'Url'; vol.All wraps a list.
            validators = getattr(validator, "validators", [validator])
            for v in validators:
                self.assertNotEqual(
                    getattr(v, "__name__", ""),
                    "Url",
                    f"field {key!r} still uses vol.Url(), which cannot be "
                    "serialized to the frontend (causes the config-flow 500)",
                )

    def test_api_url_uses_text_selector(self):
        """api_url is rendered with a URL TextSelector (serializable)."""
        from homeassistant.helpers import selector

        schema = self.cf.STEP_USER_DATA_SCHEMA.schema
        api_url_validator = None
        for key, validator in schema.items():
            if str(key) == "api_url":
                api_url_validator = validator
        self.assertIsInstance(api_url_validator, selector.TextSelector)

    def test_validate_api_url_accepts_valid(self):
        for url in ("https://api.nuki.io", "http://localhost:8080/path"):
            with self.subTest(url=url):
                self.assertEqual(self.cf._validate_api_url(url), url)

    def test_validate_api_url_rejects_invalid(self):
        for bad in ("", "not-a-url", "ftp://api.nuki.io", "api.nuki.io", "https://"):
            with self.subTest(url=bad):
                with self.assertRaises(self.cf.InvalidUrl):
                    self.cf._validate_api_url(bad)


if __name__ == "__main__":
    unittest.main()
