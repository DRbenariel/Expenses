"""
setup_credentials.py — Run this ONCE to store bank credentials in Windows Credential Manager.
Credentials are encrypted by Windows and never written to any file.

Usage:
    python setup_credentials.py
"""
import sys
try:
    import keyring
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "keyring"])
    import keyring

def prompt(label, secret=False):
    if secret:
        import getpass
        return getpass.getpass(f"  {label}: ").strip()
    return input(f"  {label}: ").strip()

def store(service, fields):
    print(f"\n── {service} ──")
    for key, label, is_secret in fields:
        val = prompt(label, secret=is_secret)
        keyring.set_password(service, key, val)
        print(f"  ✓ {key} saved")

store("hapoalim", [
    ("username", "Username (מספר משתמש)", False),
    ("password", "Password (סיסמה)", True),
])

store("max", [
    ("id_number",      "Israeli ID (ת.ז.)", False),
    ("account_number", "Account/Card number", False),
])

store("cal", [
    ("id_number",    "Israeli ID (ת.ז.)", False),
    ("card_4digits", "Last 4 digits of credit card", False),
])

print("\n✅ All credentials saved to Windows Credential Manager.")
print("   Run 'python downloader.py' to start the automated download.")
