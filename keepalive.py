import requests
import re
import os
import urllib.parse
import io
import sys
from PIL import Image
import pytesseract

LEMOHOST_URL = "https://lemehost.com"
SERVER_ID = "10234023"
SESSION_COOKIE = os.environ.get("LEMO_SESSION_COOKIE")

def solve_captcha(session, html):
    match = re.search(r'id="extendfreeplanform-captcha-image"[^>]*src="([^"]+)"', html)

    if not match:
        print("ERROR: Captcha image not found")
        return None

    img_url = match.group(1)
    if img_url.startswith("/"):
        img_url = LEMOHOST_URL + img_url

    img_resp = session.get(img_url, timeout=15)
    if img_resp.status_code != 200:
        print(f"ERROR: Failed to download captcha: {img_resp.status_code}")
        return None

    img = Image.open(io.BytesIO(img_resp.content))
    text = pytesseract.image_to_string(img, config='--psm 8 --oem 3').strip()
    text = re.sub(r'[^a-zA-Z0-9]', '', text)
    print(f"Captcha solved: '{text}'")
    return text

def keep_alive():
    session = requests.Session()
    session.cookies.set("_identity-frontend", SESSION_COOKIE, domain="lemehost.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })

    resp = session.get(f"{LEMOHOST_URL}/server/view?id={SERVER_ID}", allow_redirects=True, timeout=15)
    print(f"GET page: {resp.status_code}")

    if "captcha" in resp.text.lower() or "verify" in resp.text.lower():
        captcha_text = solve_captcha(session, resp.text)
        if not captcha_text:
            return False
    else:
        captcha_text = ""
        print("No captcha required")

    csrf_token = None
    csrf_cookie = session.cookies.get("_csrf-frontend")
    if csrf_cookie:
        decoded = urllib.parse.unquote(csrf_cookie)
        token_match = re.search(r'"([a-zA-Z0-9_-]{32,})"', decoded)
        if token_match:
            csrf_token = token_match.group(1)
            print(f"CSRF: {csrf_token}")

    if not csrf_token:
        print("ERROR: No CSRF token")
        return False

    post_url = f"{LEMOHOST_URL}/server/{SERVER_ID}/free-plan"
    session.headers.update({
        "Referer": f"{LEMOHOST_URL}/server/view?id={SERVER_ID}",
        "Origin": LEMOHOST_URL,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    data = {
        "_csrf-frontend": csrf_token,
        "ExtendFreePlanForm[captcha]": captcha_text,
        "ExtendFreePlanForm[extendTill]": "1785239936"
    }
    resp = session.post(post_url, data=data, allow_redirects=True, timeout=15)
    print(f"POST extend: {resp.status_code}")

    if "success" in resp.text.lower() or resp.status_code == 302:
        print("SUCCESS!")
        return True
    elif "captcha" in resp.text.lower():
        print("FAILED: Captcha wrong")
        return False
    else:
        print(f"FAILED: {resp.status_code}")
        return False

if __name__ == "__main__":
    if not SESSION_COOKIE:
        print("ERROR: No LEMO_SESSION_COOKIE set")
        sys.exit(1)
    if keep_alive():
        sys.exit(0)
    else:
        sys.exit(1)
