"""Constants for the Nuki OTP integration."""

DOMAIN = "nuki_otp"

# Default values
DEFAULT_API_URL = "https://api.nuki.io"
DEFAULT_OTP_USERNAME = "OTP"
DEFAULT_OTP_LIFETIME_HOURS = 12
# Bounds for the configurable OTP lifetime. The value is passed straight to the
# Nuki Web API as the authorization's ``allowedUntilDate`` offset, which the API
# accepts as an arbitrary future timestamp (Nuki authorizations may run up to a
# year). The previous 168-hour (1 week) ceiling was an arbitrary UI limit, not an
# API constraint, and made multi-week stays (e.g. long-term rentals) impossible
# without an external re-mint workaround. 8760 hours (365 days) matches Nuki's own
# maximum authorization duration.
MIN_OTP_LIFETIME_HOURS = 1
MAX_OTP_LIFETIME_HOURS = 8760
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