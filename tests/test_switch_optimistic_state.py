"""Unit tests for the OTP switch's optimistic state (PIC-13 wake).

Symptom reported by the user: pressing the OTP switch turns it *off* for a few
seconds and then back *on* once the code is generated. Root cause: the switch
is a ``CoordinatorEntity`` whose authoritative state is the last poll, while
generating an OTP is a multi-second cloud round trip. Without an optimistic
override the toggle snaps back to the pre-press state mid-operation.

These tests assert the switch:
  * reports the requested state immediately on turn-on/turn-off (no flap);
  * keeps reporting it until the coordinator confirms it, then defers to data;
  * reverts to real state (does not get stuck "on") when generation fails.

We stub only the homeassistant symbols ``switch.py`` imports so the module can
be loaded and exercised without a full Home Assistant install, mirroring the
by-path module load used by the other test modules.
"""
import asyncio
import sys
import types
import unittest
from pathlib import Path


def _install_switch_stubs():
    """Register minimal homeassistant stubs needed to import switch.py."""
    if "homeassistant" not in sys.modules:
        ha = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = ha
    else:
        ha = sys.modules["homeassistant"]

    def _ensure(name, attrs):
        """Create/extend a stub module additively (shared sys.modules safe)."""
        mod = sys.modules.get(name)
        if mod is None:
            mod = types.ModuleType(name)
            sys.modules[name] = mod
        for key, value in attrs.items():
            if not hasattr(mod, key):
                setattr(mod, key, value)
        return mod

    # homeassistant.core: HomeAssistant + callback (identity decorator).
    _ensure("homeassistant.core", {
        "HomeAssistant": type("HomeAssistant", (), {}),
        "callback": (lambda func: func),
    })
    # homeassistant.config_entries.ConfigEntry
    _ensure("homeassistant.config_entries", {
        "ConfigEntry": type("ConfigEntry", (), {}),
    })
    # homeassistant.components.switch.SwitchEntity
    components = _ensure("homeassistant.components", {})
    switch_mod = _ensure("homeassistant.components.switch", {
        "SwitchEntity": type("SwitchEntity", (), {}),
    })
    components.switch = switch_mod
    # homeassistant.helpers.* (device_registry, entity_platform, update_coordinator)
    helpers_pkg = _ensure("homeassistant.helpers", {})
    ha.helpers = helpers_pkg

    dr = _ensure("homeassistant.helpers.device_registry", {
        "DeviceInfo": (lambda **kwargs: dict(kwargs)),
    })
    helpers_pkg.device_registry = dr

    ep = _ensure("homeassistant.helpers.entity_platform", {
        "AddEntitiesCallback": object,
    })
    helpers_pkg.entity_platform = ep

    class _CoordinatorEntity:
        """Minimal CoordinatorEntity stand-in."""

        def __init__(self, coordinator):
            self.coordinator = coordinator
            # Record state writes so tests can observe optimistic transitions.
            self.write_calls = []

        def async_write_ha_state(self):
            self.write_calls.append(self.is_on)

        def _handle_coordinator_update(self):
            # Real HA writes state here; we record it like a write.
            self.write_calls.append(self.is_on)

    uc = _ensure("homeassistant.helpers.update_coordinator", {
        "CoordinatorEntity": _CoordinatorEntity,
    })
    helpers_pkg.update_coordinator = uc


_install_switch_stubs()

import importlib.util  # noqa: E402

_PKG_DIR = (
    Path(__file__).resolve().parent.parent / "custom_components" / "nuki_otp"
)
_SWITCH_PATH = _PKG_DIR / "switch.py"

# switch.py uses package-relative imports (from .const import DOMAIN, etc.). To
# resolve them without a full HA install, build a synthetic package
# "nuki_otp_pkg" holding the real const module plus light stubs for coordinator
# and helpers (switch.py only needs their names for type hints).
_PKG = "nuki_otp_pkg"
if _PKG not in sys.modules:
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(_PKG_DIR)]  # mark as a package
    sys.modules[_PKG] = pkg

    # Real const module under the package name.
    _const_spec = importlib.util.spec_from_file_location(
        f"{_PKG}.const", _PKG_DIR / "const.py"
    )
    _const = importlib.util.module_from_spec(_const_spec)
    sys.modules[f"{_PKG}.const"] = _const
    _const_spec.loader.exec_module(_const)
    pkg.const = _const

    # Stub coordinator/helpers (type-hint-only imports in switch.py).
    _coord = types.ModuleType(f"{_PKG}.coordinator")
    _coord.NukiOTPDataCoordinator = type("NukiOTPDataCoordinator", (), {})
    sys.modules[f"{_PKG}.coordinator"] = _coord
    pkg.coordinator = _coord

    _help = types.ModuleType(f"{_PKG}.helpers")
    _help.NukiAPIClient = type("NukiAPIClient", (), {})
    sys.modules[f"{_PKG}.helpers"] = _help
    pkg.helpers = _help

_spec = importlib.util.spec_from_file_location(f"{_PKG}.switch", _SWITCH_PATH)
nuki_switch = importlib.util.module_from_spec(_spec)
sys.modules[f"{_PKG}.switch"] = nuki_switch
_spec.loader.exec_module(nuki_switch)

NukiOTPSwitch = nuki_switch.NukiOTPSwitch


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeCoordinator:
    def __init__(self, data=None):
        self.data = data
        self.refresh_calls = 0

    async def async_request_refresh(self):
        self.refresh_calls += 1


class _FakeApiClient:
    """Records calls; simulates a slow OTP creation succeeding/failing."""

    def __init__(self, existing_codes=None, create_ok=True):
        self._existing = existing_codes or []
        self._create_ok = create_ok
        self.created = False
        self.deleted = False

    async def get_auth_codes(self):
        return list(self._existing)

    async def delete_auth_codes(self, codes):
        self.deleted = True
        return True

    async def create_auth_code(self):
        self.created = True
        return self._create_ok


def _make_switch(coordinator, api):
    sw = NukiOTPSwitch(coordinator, api, "entry123", "Front Door")
    return sw


class SwitchOptimisticStateTest(unittest.TestCase):
    def test_turn_on_reports_on_immediately(self):
        """On press, is_on flips to True before the slow create returns."""
        coord = _FakeCoordinator(data={"has_active_code": False})
        api = _FakeApiClient(create_ok=True)
        sw = _make_switch(coord, api)

        # Pre-press: authoritative state is off.
        self.assertFalse(sw.is_on)

        _run(sw.async_turn_on())

        # Code was created and a refresh requested.
        self.assertTrue(api.created)
        self.assertEqual(coord.refresh_calls, 1)
        # The very first state write during turn-on must already be "on" — no
        # off-flap. (write_calls[0] is the optimistic write.)
        self.assertTrue(sw.write_calls[0])
        # Still optimistic-on afterwards (coordinator hasn't confirmed yet).
        self.assertTrue(sw.is_on)
        self.assertTrue(sw.assumed_state)

    def test_optimistic_cleared_when_coordinator_confirms(self):
        """Once the poll reports has_active_code, the override is dropped."""
        coord = _FakeCoordinator(data={"has_active_code": False})
        api = _FakeApiClient(create_ok=True)
        sw = _make_switch(coord, api)
        _run(sw.async_turn_on())
        self.assertTrue(sw.assumed_state)

        # Poll lands confirming the code now exists.
        coord.data = {"has_active_code": True}
        sw._handle_coordinator_update()

        self.assertFalse(sw.assumed_state)  # override cleared
        self.assertTrue(sw.is_on)  # now from real data

    def test_turn_off_reports_off_immediately(self):
        """Turn-off assumes off at once, then defers to confirming poll."""
        coord = _FakeCoordinator(data={"has_active_code": True})
        api = _FakeApiClient(existing_codes=[{"id": "a", "name": "x_code"}])
        sw = _make_switch(coord, api)
        self.assertTrue(sw.is_on)

        _run(sw.async_turn_off())

        self.assertTrue(api.deleted)
        self.assertEqual(coord.refresh_calls, 1)
        self.assertFalse(sw.write_calls[0])  # first write is "off"
        self.assertFalse(sw.is_on)
        self.assertTrue(sw.assumed_state)

        coord.data = {"has_active_code": False}
        sw._handle_coordinator_update()
        self.assertFalse(sw.assumed_state)
        self.assertFalse(sw.is_on)

    def test_failed_generation_reverts_state(self):
        """If create fails, the switch must not get stuck optimistically on."""
        coord = _FakeCoordinator(data={"has_active_code": False})
        api = _FakeApiClient(create_ok=False)
        sw = _make_switch(coord, api)

        _run(sw.async_turn_on())

        # No refresh requested (create failed), override cleared, reads false.
        self.assertEqual(coord.refresh_calls, 0)
        self.assertFalse(sw.assumed_state)
        self.assertFalse(sw.is_on)

    def test_exception_during_turn_on_reverts_state(self):
        """An exception mid-operation also clears the optimistic override."""
        coord = _FakeCoordinator(data={"has_active_code": False})

        class _Boom(_FakeApiClient):
            async def create_auth_code(self):
                raise RuntimeError("network down")

        sw = _make_switch(coord, _Boom(create_ok=True))
        _run(sw.async_turn_on())

        self.assertFalse(sw.assumed_state)
        self.assertFalse(sw.is_on)


if __name__ == "__main__":
    unittest.main()
