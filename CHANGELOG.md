# Changelog

All notable changes to the Nuki OTP Generator integration are documented here.
This project follows [Semantic Versioning](https://semver.org/).

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
