# Changelog

All notable changes to the Nuki OTP Generator integration are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [2.2.1] - 2026-06-09

### Fixed
- **Config flow no longer 500s when opened.** Adding the integration failed with
  *"Config flow could not be loaded: 500 Internal Server Error"*. The setup form
  validated the API URL with `voluptuous.Url()`, which Home Assistant cannot
  serialize to the frontend (`voluptuous_serialize` raised
  `Unable to convert schema: <function Url>`), so the form never rendered. The
  API URL field now uses a URL text selector and the URL format is validated
  server-side, surfacing an `invalid_url` error on the field for bad input. A
  regression test asserts the user-step schema contains no `vol.Url`.

## [2.2.0] - 2026-06-09

### Added
- **Reauthentication flow.** When the Nuki Web API rejects the configured token
  (HTTP 401/403 — e.g. revoked or expired), Home Assistant now surfaces a reauth
  prompt asking for a new token instead of only logging errors. Entering a valid
  token restores operation without removing and re-adding the integration. The
  coordinator raises `ConfigEntryAuthFailed` on auth failures so HA starts the
  flow automatically.
- **Options flow.** OTP username and OTP lifetime (hours) are now editable from
  the integration's *Configure* dialog in the Home Assistant UI. Saving reloads
  the config entry so the new values take effect immediately, without removing
  and re-adding the integration. Connection fields (API URL/token, Nuki name)
  remain set-at-install only, as changing them requires re-validation.
- **Config form help text.** Each setup and options field now carries
  `data_description` helper text explaining what it does (API URL/token, Nuki
  name, OTP username, OTP lifetime). A test guards `strings.json` and
  `translations/en.json` against drift and asserts every field stays documented.

## [2.1.0] - 2026-06-09

First HACS release built from the restructured `custom_components/nuki_otp/`
layout. If HACS previously offered you `v2.0.0` or earlier, this is the update
that finally moves you onto the current, working codebase.

### ⚠️ Breaking / upgrade notes
- **Repository was restructured into `custom_components/nuki_otp/`.** All
  releases up to and including `v2.0.0` shipped the integration files from the
  repository root, which HACS could not install correctly. `v2.1.0` is the
  first release with the standard layout.
- **Recommended upgrade path:** update through HACS as usual. If Home
  Assistant fails to load the integration after updating from a root-layout
  version, remove the old `custom_components/nuki_otp` folder, reinstall via
  HACS, and restart Home Assistant. No reconfiguration of your config entry is
  required — your existing settings are preserved.
- No configuration options or entity IDs changed in this release.

### Fixed
- Guard `get_auth_codes` / `get_smartlock` against non-list API responses so a
  `204`/error payload no longer raises a `TypeError` (PIC-21).
- Reset config-flow errors on each submission so a corrected value clears the
  previously shown error (PIC-22).
- Fix the README icon path after the `custom_components/` restructure (PIC-24).

### Changed
- Cut the N+1 polling in `cleanup_expired_codes` — the smartlock is now fetched
  once per cleanup cycle instead of once per expired code (PIC-23).
