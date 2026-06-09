"""Unit tests for ``NukiAPIClient._make_request`` retry behavior.

Focus (PIC-26): only idempotent GET requests may be retried. A create-side
call (PUT/POST/DELETE) that times out might already have been processed by the
Nuki server, so retrying it could create a duplicate OTP code on the lock.
These calls must be attempted exactly once.

The integration depends on ``homeassistant`` and ``aiohttp``, which are not
available in this test environment. We install lightweight stand-ins for the
symbols ``helpers.py`` imports so the module can be loaded and its retry logic
exercised in isolation, without a full Home Assistant install.
"""
import asyncio
import sys
import types
import unittest
from pathlib import Path


def _install_stub_modules():
    """Register minimal stubs for homeassistant/aiohttp before importing."""

    # --- aiohttp ----------------------------------------------------------
    if "aiohttp" not in sys.modules:
        aiohttp = types.ModuleType("aiohttp")

        class ClientError(Exception):
            """Stand-in for aiohttp.ClientError."""

        class ClientTimeout:  # noqa: D401 - simple data holder
            def __init__(self, total=None):
                self.total = total

        aiohttp.ClientError = ClientError
        aiohttp.ClientTimeout = ClientTimeout
        sys.modules["aiohttp"] = aiohttp

    # --- homeassistant.core ----------------------------------------------
    if "homeassistant" not in sys.modules:
        ha = types.ModuleType("homeassistant")
        sys.modules["homeassistant"] = ha

        core = types.ModuleType("homeassistant.core")

        class HomeAssistant:  # noqa: D401 - placeholder type
            pass

        core.HomeAssistant = HomeAssistant
        sys.modules["homeassistant.core"] = core
        ha.core = core

        # homeassistant.helpers.aiohttp_client.async_get_clientsession
        helpers_pkg = types.ModuleType("homeassistant.helpers")
        sys.modules["homeassistant.helpers"] = helpers_pkg
        ha.helpers = helpers_pkg

        aiohttp_client = types.ModuleType("homeassistant.helpers.aiohttp_client")

        def async_get_clientsession(hass):
            return getattr(hass, "_session", None)

        aiohttp_client.async_get_clientsession = async_get_clientsession
        sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client
        helpers_pkg.aiohttp_client = aiohttp_client

        # homeassistant.util.dt
        util_pkg = types.ModuleType("homeassistant.util")
        sys.modules["homeassistant.util"] = util_pkg
        ha.util = util_pkg

        dt_mod = types.ModuleType("homeassistant.util.dt")
        from datetime import datetime, timezone

        def utcnow():
            return datetime.now(timezone.utc)

        def parse_datetime(value):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None

        dt_mod.utcnow = utcnow
        dt_mod.parse_datetime = parse_datetime
        sys.modules["homeassistant.util.dt"] = dt_mod
        util_pkg.dt = dt_mod


_install_stub_modules()

# Make ``custom_components`` importable from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import importlib.util  # noqa: E402

import aiohttp  # noqa: E402  (stubbed above)

# Load helpers.py directly by path. Importing it as
# ``custom_components.nuki_otp.helpers`` would execute the package __init__,
# which pulls in many more Home Assistant modules we don't stub here.
_HELPERS_PATH = _REPO_ROOT / "custom_components" / "nuki_otp" / "helpers.py"
_spec = importlib.util.spec_from_file_location("nuki_otp_helpers", _HELPERS_PATH)
helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helpers)

NukiAPIClient = helpers.NukiAPIClient
NukiAPIError = helpers.NukiAPIError
NukiConfig = helpers.NukiConfig


class _FakeHass:
    def __init__(self, session):
        self._session = session


class _FakeResponse:
    """Async context manager mimicking an aiohttp response."""

    def __init__(self, status=200, payload=None):
        self.status = status
        self._payload = payload if payload is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._payload

    async def text(self):
        return "error body"


class _FakeSession:
    """Records each request and yields scripted outcomes.

    ``outcomes`` is a list; each entry is either an exception instance to
    raise, or a ``_FakeResponse`` to return. The session walks the list as
    requests come in; if it runs out, it reuses the last entry.
    """

    def __init__(self, outcomes):
        self._outcomes = outcomes
        self.calls = []  # (method, url) per request attempt

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        idx = min(len(self.calls) - 1, len(self._outcomes) - 1)
        outcome = self._outcomes[idx]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _make_client(session):
    config = NukiConfig(
        api_token="token",
        api_url="https://api.example/test",
        otp_username="otpuser",
        nuki_name="Front Door",
        otp_lifetime_hours=24,
    )
    return NukiAPIClient(_FakeHass(session), config)


def _run(coro):
    return asyncio.run(coro)


class MakeRequestRetryTest(unittest.TestCase):
    def test_get_retries_on_timeout(self):
        """GET is idempotent: it should retry, then succeed."""
        session = _FakeSession([
            asyncio.TimeoutError(),
            asyncio.TimeoutError(),
            _FakeResponse(status=200, payload=[{"ok": True}]),
        ])
        client = _make_client(session)
        result = _run(client._make_request("GET", "smartlock"))
        self.assertEqual(result, [{"ok": True}])
        # 2 timeouts + 1 success == 3 attempts.
        self.assertEqual(len(session.calls), 3)

    def test_get_exhausts_retries_then_raises(self):
        """GET that always times out raises after MAX_RETRIES+1 attempts."""
        session = _FakeSession([asyncio.TimeoutError()])
        client = _make_client(session)
        with self.assertRaises(NukiAPIError):
            _run(client._make_request("GET", "smartlock"))
        # MAX_RETRIES (3) + initial attempt == 4 attempts.
        self.assertEqual(len(session.calls), 4)

    def test_put_not_retried_on_timeout(self):
        """PUT (create) must be attempted exactly once on timeout."""
        session = _FakeSession([asyncio.TimeoutError()])
        client = _make_client(session)
        with self.assertRaises(NukiAPIError):
            _run(client._make_request("PUT", "smartlock/auth", {"code": 123}))
        self.assertEqual(len(session.calls), 1)

    def test_put_not_retried_on_client_error(self):
        """PUT must not retry on aiohttp.ClientError either."""
        session = _FakeSession([aiohttp.ClientError("boom")])
        client = _make_client(session)
        with self.assertRaises(NukiAPIError):
            _run(client._make_request("PUT", "smartlock/auth", {"code": 123}))
        self.assertEqual(len(session.calls), 1)

    def test_post_not_retried_on_timeout(self):
        session = _FakeSession([asyncio.TimeoutError()])
        client = _make_client(session)
        with self.assertRaises(NukiAPIError):
            _run(client._make_request("POST", "smartlock/auth", {"code": 123}))
        self.assertEqual(len(session.calls), 1)

    def test_delete_not_retried_on_timeout(self):
        session = _FakeSession([asyncio.TimeoutError()])
        client = _make_client(session)
        with self.assertRaises(NukiAPIError):
            _run(client._make_request("DELETE", "smartlock/auth", ["id1"]))
        self.assertEqual(len(session.calls), 1)

    def test_create_auth_code_does_not_duplicate_on_timeout(self):
        """A single create_auth_code() call issues at most one PUT.

        The GET smartlock lookup succeeds; the PUT times out. The create must
        not be retried, so exactly one PUT reaches the lock (no duplicate OTP).
        """
        smartlock_payload = [{"name": "Front Door", "smartlockId": 42}]
        session = _FakeSession([
            _FakeResponse(status=200, payload=smartlock_payload),  # GET
            asyncio.TimeoutError(),  # PUT create times out
        ])
        client = _make_client(session)
        result = _run(client.create_auth_code())
        self.assertFalse(result)
        put_calls = [c for c in session.calls if c[0] == "PUT"]
        self.assertEqual(len(put_calls), 1)

    def test_method_case_insensitive(self):
        """Lowercase 'put' is still treated as non-idempotent."""
        session = _FakeSession([asyncio.TimeoutError()])
        client = _make_client(session)
        with self.assertRaises(NukiAPIError):
            _run(client._make_request("put", "smartlock/auth", {"code": 123}))
        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
