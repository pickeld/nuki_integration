# HACS Default Store Submission

This document is the checklist for getting **Nuki OTP Generator** into the
[HACS default store](https://www.hacs.xyz/docs/publish/include/) so users can
install it without adding a custom repository URL.

The repository side is done (valid `hacs.json` / `manifest.json`, CI running
the HACS Action + hassfest — see `.github/workflows/validate.yml`). The
remaining steps **must be performed from the repository owner's GitHub
account** — HACS only accepts default-store submissions from the owner or a
major contributor, and the PRs must be editable by maintainers.

## Prerequisites (one-time, on the repo)

- [x] `hacs.json` present at repo root with a `name`.
- [x] `manifest.json` valid with `domain`, `documentation`, `issue_tracker`,
      `codeowners`, `name`, `version`.
- [x] CI runs the **HACS Action** and **Hassfest** on push / PR / release.
- [ ] Push `main` to `origin` (currently ahead — owner action).
- [ ] Repo has a **description**, **Issues enabled**, and **topics** set on
      GitHub. Suggested topics: `home-assistant`, `hacs`, `nuki`, `otp`,
      `home-assistant-integration`, `custom-component`.
- [ ] A **full GitHub release** exists (not just a tag). The Auto Release
      workflow creates one when `manifest.json`'s version changes; confirm the
      latest (`v2.5.0`) shows under *Releases*, not just *Tags*.

## Step 1 — Register the brand (home-assistant/brands)

The HACS default store requires the HACS Action to pass **with no `ignore`**.
Today the workflow uses `ignore: brands` because the `nuki_otp` domain is not
in [home-assistant/brands](https://github.com/home-assistant/brands). Register
it first:

1. Fork `home-assistant/brands`.
2. Add the integration icons under `custom_integrations/nuki_otp/`:
   - `icon.png` — **256×256** PNG, trimmed, transparent background.
   - `icon@2x.png` — **512×512** PNG (optional but recommended).
   You can derive both from `custom_components/nuki_otp/icon.png` (already
   512×512). For the 256px version, e.g.:
   ```bash
   # with ImageMagick
   convert custom_components/nuki_otp/icon.png -resize 256x256 icon.png
   cp custom_components/nuki_otp/icon.png icon@2x.png
   ```
3. Open a PR to `home-assistant/brands`. Wait for it to merge.
4. **After it merges**, remove `ignore: brands` from
   `.github/workflows/validate.yml` and confirm the HACS Action still passes.

## Step 2 — Submit to hacs/default

1. Fork [`hacs/default`](https://github.com/hacs/default).
2. Create a **new branch off `master`** (don't commit on `master`).
3. Add `pickeld/nuki_integration` to the **`integration`** file —
   **alphabetically**, not at the end.
4. Open a PR from your personal account (not an org account), filling out the
   PR template accurately.
5. CI on that PR runs: brands, manifest, hacs-validation, releases, owner,
   images, `lint jq`, `lint sorted`. All must pass.

Review can take months; track the
[backlog](https://github.com/hacs/default/pulls?q=is%3Apr+is%3Aopen+draft%3Afalse+sort%3Acreated-asc).

## Why this can't be fully automated here

Submitting requires the owner's authenticated GitHub account and two upstream
PRs (brands + hacs/default). This repo's CI and metadata — everything HACS
validates on our side — is in place and green.
