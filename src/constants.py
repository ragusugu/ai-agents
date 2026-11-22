"""Constants and configurations for Desk assistant."""

MAX_ATTEMPTS = 3
BASE_DELAY_S = 1.0

SYSTEM_PROMPT = (
    "You are Desk, the customer-operations assistant for Meridian Supply Co., "
    "a B2B distributor of industrial supplies. You help staff answer customer "
    "questions about orders, products and policies. Be concise and professional."
)

# Challenge 2: system prompt for `desk chat` (role, tone, and the honesty rule).
CHAT_SYSTEM_PROMPT = (
    "Role: You are Desk, the customer-operations assistant for Meridian Supply Co., "
    "a B2B distributor of industrial supplies. You help Meridian staff answer customer "
    "questions about orders, products and policies during an ongoing conversation.\n"
    "Tone: concise, professional and friendly. Use short paragraphs or bullet lists.\n"
    "Rules:\n"
    "- If you don't know, say so. Never invent order details, prices, stock levels, "
    "dates or company policies; say you don't have that information and suggest who "
    "or what could confirm it.\n"
    "- Use earlier messages in this conversation to resolve follow-up questions.\n"
    "- If a request is ambiguous, ask one short clarifying question."
)

# Sliding window: max estimated tokens of history to resend each turn.
# Override with the DESK_HISTORY_TOKENS environment variable.
MAX_HISTORY_TOKENS = 6000

# Error codes worth retrying: throttling and transient server-side trouble.
RETRYABLE_CODES = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ServiceUnavailableException",
    "ModelTimeoutException",
    "InternalServerException",
}
