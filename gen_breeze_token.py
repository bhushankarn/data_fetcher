#!/usr/bin/env python3
"""Generate a Breeze session token and update BREEZE_SESSION_TOKEN in .env."""

import os
import re
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv
from breeze_connect import BreezeConnect

ENV_FILE = Path(__file__).parent / ".env"
LOGIN_URL = "https://api.icicidirect.com/apiuser/login?api_key={api_key}"


def load_keys() -> tuple[str, str]:
    load_dotenv(ENV_FILE)
    api_key = os.getenv("BREEZE_API_KEY", "").strip()
    api_secret = os.getenv("BREEZE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        sys.exit("Error: BREEZE_API_KEY and BREEZE_API_SECRET must be set in .env")
    return api_key, api_secret


def extract_token_from_input(raw: str) -> str:
    raw = raw.strip()
    # If it looks like a full URL, parse the session_token param
    if raw.startswith("http"):
        qs = parse_qs(urlparse(raw).query)
        tokens = qs.get("session_token") or qs.get("SessionToken")
        if tokens:
            return tokens[0]
        sys.exit("Error: could not find session_token in the URL")
    return raw


def update_env(token: str) -> None:
    text = ENV_FILE.read_text()
    pattern = r"^(BREEZE_SESSION_TOKEN\s*=\s*).*$"
    if re.search(pattern, text, flags=re.MULTILINE):
        text = re.sub(pattern, rf"\g<1>{token}", text, flags=re.MULTILINE)
    else:
        text += f"\nBREEZE_SESSION_TOKEN={token}\n"
    ENV_FILE.write_text(text)


def main() -> None:
    api_key, api_secret = load_keys()

    url = LOGIN_URL.format(api_key=api_key)
    print(f"Opening ICICI Direct login page…\n  {url}\n")
    webbrowser.open(url)

    print("After logging in, copy the redirect URL (or just the session token) and paste it below.")
    raw = input("Paste URL or session token: ").strip()
    if not raw:
        sys.exit("Error: no input provided")

    session_token = extract_token_from_input(raw)
    print(f"\nSession token: {session_token}")

    print("Verifying with Breeze API…")
    breeze = BreezeConnect(api_key=api_key)
    breeze.generate_session(api_secret=api_secret, session_token=session_token)
    print("Session verified successfully.")

    update_env(session_token)
    print(f"Updated BREEZE_SESSION_TOKEN in {ENV_FILE}")

    # Export for the current shell invocation (printed so callers can eval)
    print(f"\nexport BREEZE_SESSION_TOKEN={session_token}")


if __name__ == "__main__":
    main()
