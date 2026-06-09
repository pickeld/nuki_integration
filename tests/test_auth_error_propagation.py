"""Unit tests for auth-error propagation (PIC-28).

When the Nuki API token is revoked or expires the API answers 401/403. For HA
to drive a reauth flow, that failure must reach the coordinator instead of
being swallowed like a transient error. These tests assert that:

* ``_make_request`` maps 401/403 to ``NukiAuthError`` (a ``NukiAPIError``);
* the otherwise error-swallowing read methods (``get_auth_codes`` and
  ``get_smartlock``) re-raise ``NukiAuthError`` rather than returning [] / None;
* a non-auth API error is still swallowed as before.

Reuses the lightweight homeassistant/aiohttp stubs and the direct-by-path
module load from ``test_make_request_retry`` so no full HA install is needed.
"""
import asyncio
import unittest

from test_make_request_retry import (
    NukiAPIError,
    _FakeResponse,
    _FakeSession,
    _make_client,
    _run,
    helpers,
)

NukiAuthError = helpers.NukiAuthError


class AuthErrorPropagationTest(unittest.TestCase):
    def test_make_request_maps_401_to_auth_error(self):
        """A 401 raises NukiAuthError (a subclass of NukiAPIError)."""
        session = _FakeSession([_FakeResponse(status=401)])
        client = _make_client(session)
        with self.assertRaises(NukiAuthError):
            _run(client._make_request("GET", "smartlock"))

    def test_make_request_maps_403_to_auth_error(self):
        """A 403 raises NukiAuthError too."""
        session = _FakeSession([_FakeResponse(status=403)])
        client = _make_client(session)
        with self.assertRaises(NukiAuthError):
            _run(client._make_request("GET", "smartlock"))

    def test_get_auth_codes_reraises_auth_error(self):
        """get_auth_codes must surface auth failures, not swallow them."""
        session = _FakeSession([_FakeResponse(status=401)])
        client = _make_client(session)
        with self.assertRaises(NukiAuthError):
            _run(client.get_auth_codes())

    def test_get_smartlock_reraises_auth_error(self):
        """get_smartlock must surface auth failures, not return None."""
        session = _FakeSession([_FakeResponse(status=403)])
        client = _make_client(session)
        with self.assertRaises(NukiAuthError):
            _run(client.get_smartlock())

    def test_cleanup_reraises_auth_error(self):
        """cleanup_expired_codes must not swallow auth failures."""
        session = _FakeSession([_FakeResponse(status=401)])
        client = _make_client(session)
        with self.assertRaises(NukiAuthError):
            _run(client.cleanup_expired_codes())

    def test_non_auth_error_still_swallowed(self):
        """A non-auth API error keeps the old graceful-degradation behavior."""
        session = _FakeSession([_FakeResponse(status=500)])
        client = _make_client(session)
        # 500 -> NukiAPIError (not auth) -> get_auth_codes returns [].
        self.assertEqual(_run(client.get_auth_codes()), [])

    def test_auth_error_is_api_error_subclass(self):
        """Existing ``except NukiAPIError`` handlers still catch auth errors."""
        self.assertTrue(issubclass(NukiAuthError, NukiAPIError))


if __name__ == "__main__":
    unittest.main()
