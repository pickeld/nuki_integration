"""Constants for the Nuki OTP integration."""

DOMAIN = "nuki_otp"
CUSTOM_EVENT = "nuki_otp_switch_state_changed"

# Default values
DEFAULT_API_URL = "https://api.nuki.io"
DEFAULT_OTP_USERNAME = "OTP"
DEFAULT_OTP_LIFETIME_HOURS = 12
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 1

# Sensor constants
NO_CODE = "------"