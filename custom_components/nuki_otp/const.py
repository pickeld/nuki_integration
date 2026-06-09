"""Constants for the Nuki OTP integration."""

DOMAIN = "nuki_otp"

# Default values
DEFAULT_API_URL = "https://api.nuki.io"
DEFAULT_OTP_USERNAME = "OTP"
DEFAULT_OTP_LIFETIME_HOURS = 12
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 1

# Sensor constants
NO_CODE = "------"

# Frontend (Lovelace) card bundled with the integration. The card JS lives in
# the integration's ``www`` folder and is served from this URL so HACS users
# get the card automatically, without manually copying files or adding a
# dashboard resource.
CARD_FILENAME = "ha-otp-card.js"
CARD_URL_PATH = "/nuki_otp/ha-otp-card.js"