"""Guard against drift between the two hand-copied translation files (PIC-29).

Home Assistant reads ``translations/en.json`` at runtime, while ``strings.json``
is the source of truth that HA tooling (e.g. ``hassfest``) checks. Because both
files must physically ship in the integration, they are maintained as
byte-identical copies. Nothing in the build generates one from the other, so
they drift easily when only one is edited.

These tests fail loudly the moment the two files diverge, and assert that every
configurable field carries ``data_description`` helper text so the config form
keeps explaining what each field means.
"""
import json
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMPONENT = _REPO_ROOT / "custom_components" / "nuki_otp"
_STRINGS = _COMPONENT / "strings.json"
_EN = _COMPONENT / "translations" / "en.json"


class TranslationsInSyncTest(unittest.TestCase):
    def test_strings_and_en_are_byte_identical(self):
        """``strings.json`` is the source of truth; en.json must match it exactly."""
        strings_bytes = _STRINGS.read_bytes()
        en_bytes = _EN.read_bytes()
        self.assertEqual(
            strings_bytes,
            en_bytes,
            "strings.json and translations/en.json have drifted apart. "
            "Edit strings.json, then copy it verbatim to translations/en.json.",
        )

    def test_files_are_valid_json(self):
        """Both files must parse so HA can load them."""
        for path in (_STRINGS, _EN):
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))

    def test_every_data_field_has_a_description(self):
        """Each config field must carry data_description helper text."""
        config = json.loads(_STRINGS.read_text(encoding="utf-8"))["config"]
        user_step = config["step"]["user"]
        data = user_step["data"]
        descriptions = user_step.get("data_description", {})

        missing = sorted(set(data) - set(descriptions))
        self.assertEqual(
            missing,
            [],
            f"Config fields without data_description help text: {missing}",
        )

        # No stray descriptions for fields that don't exist in the form.
        extra = sorted(set(descriptions) - set(data))
        self.assertEqual(
            extra,
            [],
            f"data_description entries with no matching field: {extra}",
        )


if __name__ == "__main__":
    unittest.main()
