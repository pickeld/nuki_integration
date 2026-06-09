# HACS Default Store Submission

This document tracks getting **Nuki OTP Generator** into the
[HACS default store](https://www.hacs.xyz/docs/publish/include/) so users can
install it without adding a custom repository URL.

## Repository prerequisites (all done)

- [x] `hacs.json` present at repo root with a `name`.
- [x] `manifest.json` valid with `domain`, `documentation`, `issue_tracker`,
      `codeowners`, `name`, `version`.
- [x] CI runs the **HACS Action** and **Hassfest** on push / PR / release
      (`.github/workflows/validate.yml`).
- [x] `main` pushed to `origin`.
- [x] Repo has a **description**, **Issues enabled**, and **topics**.
- [x] A **full GitHub release** exists (`v2.5.0`, created by the Auto Release
      workflow — visible under *Releases*, not just *Tags*).
- [x] Local **brand assets** present at `custom_components/nuki_otp/brand/`
      (`icon.png` 256×256, `icon@2x.png` 512×512).

## Brand assets — local, no upstream PR needed

As of Home Assistant **2026.3.0**, custom integrations ship their own brand
images in a `brand/` subdirectory and `home-assistant/brands` **no longer
accepts** custom-integration icons
([announcement](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api)).

HACS's brands validator
([`brands.py`](https://github.com/hacs/integration/blob/main/custom_components/hacs/validate/brands.py))
checks for `<integration content path>/brand/icon.png` in the repo tree and
passes when it exists — only falling back to the brands repository if it's
missing. We provide that file at `custom_components/nuki_otp/brand/icon.png`,
so the **HACS Action passes the brands check with no `ignore` key**. (The
earlier plan to PR `home-assistant/brands` is obsolete; that PR was
auto-closed by their bot under the new policy.)

## Submit to hacs/default

1. Fork [`hacs/default`](https://github.com/hacs/default).
2. Create a **new branch off `master`** (don't commit on `master`).
3. Add `pickeld/nuki_integration` to the **`integration`** file —
   **alphabetically**.
4. Open a PR from a personal account (not an org account), filling out the PR
   template — including links to a release, a passing HACS action run **without
   any `ignore`**, and a passing hassfest run.
5. CI on that PR runs: brands, manifest, hacs-validation, releases, owner,
   `lint jq`, `lint sorted`. All must pass.

Review can take months; track the
[backlog](https://github.com/hacs/default/pulls?q=is%3Apr+is%3Aopen+draft%3Afalse+sort%3Acreated-asc).
