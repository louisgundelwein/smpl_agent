"""Utility to scrub sensitive values from error messages and output."""

import os
import re


def scrub_secrets(text: str) -> str:
    """Remove sensitive environment variable values from text.

    Scans environment variables for keys containing KEY, TOKEN, PASSWORD, or SECRET
    and replaces their values in the text with [REDACTED].

    Args:
        text: The text to scrub.

    Returns:
        Text with sensitive values replaced by [REDACTED].
    """
    scrubbed = text
    sensitive_patterns = ("KEY", "TOKEN", "PASSWORD", "SECRET")

    for env_var, value in os.environ.items():
        if any(pattern in env_var.upper() for pattern in sensitive_patterns):
            if value and len(value) > 0:
                # Escape regex special characters in the value
                escaped_value = re.escape(value)
                scrubbed = re.sub(escaped_value, "[REDACTED]", scrubbed)

    return scrubbed
