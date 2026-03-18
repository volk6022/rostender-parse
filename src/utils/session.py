from datetime import datetime
import secrets


def generate_session_id() -> str:
    """
    Generates a unique session ID in the format: YYYYMMDD-HHMMSS-xxxxxx

    Returns:
        str: Human-readable unique session identifier.
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = secrets.token_hex(3)  # 6 characters
    return f"{timestamp}-{suffix}"
