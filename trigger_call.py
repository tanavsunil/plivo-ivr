"""Place an outbound IVR call via the Plivo REST API.

Usage:
    python trigger_call.py              # calls TARGET_NUMBER from .env
    python trigger_call.py 14155550123  # calls the given number
"""
import os
import sys

import plivo
from dotenv import load_dotenv

load_dotenv()


def _require(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def place_call(to_number):
    """Start an outbound call to `to_number`; Plivo fetches XML from BASE_URL/answer."""
    client = plivo.RestClient(_require("PLIVO_AUTH_ID"), _require("PLIVO_AUTH_TOKEN"))
    base_url = _require("BASE_URL").rstrip("/")
    return client.calls.create(
        from_=_require("PLIVO_NUMBER"),
        to_=to_number,
        answer_url=f"{base_url}/answer",
        answer_method="POST",
    )


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else _require("TARGET_NUMBER")
    print(f"Calling {target} ...")
    response = place_call(target)
    print(f"Call queued: {response}")


if __name__ == "__main__":
    main()
