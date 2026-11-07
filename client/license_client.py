"""
Online License Client
Put this file in your Python app and call check_license() at startup.
"""

import hashlib
import uuid
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

# ============================================================
# CONFIGURATION - Change these two values
# ============================================================
SERVER_URL = "https://your-app-name.onrender.com"   # ← Your Render URL (no trailing slash)
PRODUCT_ID = "MyApp-Pro"                            # ← Must match what you generate

LICENSE_FILE = "license.key"   # Where the key is saved locally


def get_machine_id() -> str:
    """Create a reasonably unique ID for this computer."""
    mac = uuid.getnode()
    raw = f"{mac}-{os.getenv('COMPUTERNAME', os.getenv('HOSTNAME', ''))}-{os.getenv('USERNAME', os.getenv('USER', ''))}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20].upper()


def _post(endpoint: str, data: dict) -> dict:
    url = f"{SERVER_URL}{endpoint}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "message": f"Server error {e.code}"}
    except Exception as e:
        return {"ok": False, "message": f"Connection error: {str(e)}"}


def activate(license_key: str) -> tuple[bool, str]:
    """Activate a license key on this machine."""
    machine_id = get_machine_id()
    result = _post("/api/activate", {
        "license_key": license_key.strip(),
        "machine_id": machine_id,
        "product_id": PRODUCT_ID
    })
    return result.get("ok", False), result.get("message", "Unknown error")


def check(license_key: str) -> tuple[bool, str]:
    """Quick validity check (can be called periodically)."""
    machine_id = get_machine_id()
    result = _post("/api/check", {
        "license_key": license_key.strip(),
        "machine_id": machine_id
    })
    return result.get("ok", False), result.get("message", "Unknown error")


def check_license(force_ask: bool = False) -> bool:
    """
    Main function to call at the start of your app.

    Returns True if the license is valid, False otherwise.
    """
    machine_id = get_machine_id()
    print(f"Machine ID: {machine_id}")

    # Load saved key
    license_key = None
    if not force_ask and os.path.exists(LICENSE_FILE):
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            license_key = f.read().strip()

    # Ask user if we don't have a key
    if not license_key:
        print("\n=== License Activation Required ===")
        print(f"Product  : {PRODUCT_ID}")
        print(f"Machine  : {machine_id}")
        print("Please enter your license key:")
        license_key = input("> ").strip()
        if not license_key:
            print("No key entered.")
            return False

    # Try to activate / check
    ok, message = activate(license_key)

    if ok:
        # Save key for next time
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            f.write(license_key)
        print(f"✓ {message}")
        return True
    else:
        print(f"✗ {message}")
        # If the saved key is bad, delete it so user can try again
        if os.path.exists(LICENSE_FILE):
            os.remove(LICENSE_FILE)
        return False


# ========== EXAMPLE USAGE ==========
if __name__ == "__main__":
    if check_license():
        print("\nLicense OK – starting application...")
        # Your real app code would continue here
    else:
        print("\nLicense check failed. Exiting.")
        input("Press Enter to close...")
