<p align="center">
<img src="icon.png" width="50" height="50">
<h1 align="center">Nuki OTP Integration for Home Assistant</h1>
</p>
This custom integration for Home Assistant allows users to generate and manage One-Time Passwords (OTPs) for Nuki Smart Locks directly from Home Assistant.

## Features


- Generate OTP codes with a specified lifetime.
- Automatically delete expired or used OTPs.
- Display current active OTP codes and their expiry times.
- Integrate with Nuki Smart Lock API to manage access.

## Installation

### HACS Installation

If you have HACS installed, you can easily add this repository as a custom integration:

1. Open HACS in the Home Assistant frontend.
2. Navigate to "Integrations" section.
3. Click on the "..." button in the top right corner and select "Custom repositories".
4. Add the URL of this repository.
5. Choose "Integration" as the category and click "Add".
6. You should now be able to search for and install the Nuki OTP integration directly through HACS.

### Manual Installation

To manually install this integration, follow these steps:

1. Ensure you have a Home Assistant instance running.
2. Download this repository and copy the `custom_components/nuki_otp` folder to the `custom_components` directory of your Home Assistant installation.
3. Restart Home Assistant to detect the new integration.

## Configuration

After installation, add the integration through the Home Assistant frontend:

1. Navigate to `Configuration` -> `Integrations`.
2. Click on the `+ Add Integration` button.
3. Search for `Nuki OTP` and select it.
4. Enter the required configuration details:
   - API Token
   - API URL
   - OTP Username
   - Nuki Name
   - OTP Lifetime Hours

## Usage

Once configured, the integration will provide a sensor and a switch within Home Assistant:

- **Sensor**: Displays the currently active OTP and its expiry time.
- **Switch**: Allows generating a new OTP or deleting the current one.

## Troubleshooting

If you encounter any issues, check the Home Assistant logs for errors and ensure your configuration details are correct. If problems persist, please report them on the GitHub repository.

## Version Management

This integration uses GitHub releases for version management in HACS. The version in `manifest.json` is the source of truth and should match the release tag.

### Creating a New Release in VSCode

1. Update version in `manifest.json`
2. Stage and commit the change:
   - Open the Source Control panel (Ctrl+Shift+G or Command+Shift+G)
   - Stage the manifest.json change
   - Enter commit message: "chore: bump version to X.Y.Z"
   - Click the checkmark to commit

3. Create a tag:
   - Open the Command Palette (Ctrl+Shift+P or Command+Shift+P)
   - Type "Git: Create Tag"
   - Enter tag name: `vX.Y.Z` (e.g., v1.1.0)
   - Enter tag message:
     ```
     Version X.Y.Z

     Changes:
     - Change 1
     - Change 2
     ```

4. Push changes with tag:
   - Open the Command Palette
   - Type "Git: Push"
   - Select "Push Tags"
   - Choose "Push all tags"

The GitHub Action will automatically:
- Create a GitHub release from the tag
- Use the tag message as release notes
- Make the release available in HACS

## License

This integration is released under the [MIT License](LICENSE).

## Disclaimer

This integration is not officially affiliated with Nuki and is provided "as is" without warranty of any kind.
