"""Constants and configurations for Desk assistant."""

MAX_ATTEMPTS = 3
BASE_DELAY_S = 1.0

SYSTEM_PROMPT = (
    "You are Desk, the customer-operations assistant for Meridian Supply Co., "
    "a B2B distributor of industrial supplies. You help staff answer customer "
    "questions about orders, products and policies. Be concise and professional."
)

# Error codes worth retrying: throttling and transient server-side trouble.
RETRYABLE_CODES = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceUnavailableException",
    "ModelTimeoutException",
    "InternalServerException",
}
