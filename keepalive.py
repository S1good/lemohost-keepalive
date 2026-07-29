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
MAX_RETRIES = 5

def solve_captcha(session, html):
    match = re.search(r'id="extendfreeplanform-captcha-image"[^>]*src="([^"]+)"', html)
    if not match:
        return None
    img_url = match.group(1)
    img_resp = session.get(img_url, timeout=15)
    if img_resp.status_code != 200:
        return None
    img = Image.open(io.BytesIO(img_resp.content))
    img = img.convert("L")
    img = img.point(lambda x: 0 if x < 140 else 255)
    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
    text = pytesseract.image_to_string(
        img,
        config='--psm 8 --oem 3 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    ).strip()
    text = re.sub(r'[^a-zA-Z0-9]', '', text)
    print(f"Captcha solved: '{text}'")
    return text

def get_remaining_minutes(html):
    match = re.search(r'id="countdown-free-plan"[^>]*>(\d+):(\d+):(\d+)<', html)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        total = hours * 60 + minutes
        print(f"Server shutdown time: {match.group(1)}:{match.group(2)}:{match.group(3)} ({total} min)")
        return total
    print("Could not find countdown timer on page")
    return None

def keep_alive():
    session = requests.Session()
    session.cookies.set("_identity-frontend", SESSION_COOKIE, domain="lemehost.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })

    view_url = f"{LEMOHOST_URL}/server/view?id={SERVER_ID}"
    form_url = f"{LEMOHOST_URL}/server/{SERVER_ID}/free-plan"

    resp = session.get(view_url, timeout=15)
    current = get_remaining_minutes(resp.text)
    if current and current >= 28:
        print(f"Already {current}min remaining, no extend needed")
        return True

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\nAttempt {attempt}/{MAX_RETRIES}")

        resp = session.get(form_url, allow_redirects=True, timeout=15)

        csrf_token = None
        csrf_cookie = session.cookies.get("_csrf-frontend")
        if csrf_cookie:
            decoded = urllib.parse.unquote(csrf_cookie)
            token_match = re.search(r'"([a-zA-Z0-9_-]{32,})"', decoded)
            if token_match:
                csrf_token = token_match.group(1)
        if not csrf_token:
            body_match = re.search(r'name="_csrf-frontend"[^>]*value="([^"]+)"', resp.text)
            if body_match:
                csrf_token = body_match.group(1)
        if not csrf_token:
            print("No CSRF token")
            return False

        captcha_text = solve_captcha(session, resp.text)
        if captcha_text is None:
            return False

        session.headers.update({
            "Referer": form_url,
            "Origin": LEMOHOST_URL,
            "Content-Type": "application/x-www-form-urlencoded",
        })
        data = {
            "_csrf-frontend": csrf_token,
            "ExtendFreePlanForm[captcha]": captcha_text,
            "ExtendFreePlanForm[extendTill]": "1785239936"
        }

        resp = session.post(form_url, data=data, allow_redirects=False, timeout=15)
        print(f"POST: {resp.status_code}")

        if resp.status_code == 302:
            resp = session.get(view_url, timeout=15)
            after = get_remaining_minutes(resp.text)
            if after and after >= 28:
                print("SUCCESS! Server time extended!")
                return True
        else:
            print("Captcha wrong or failed, retrying...")

    print("All retries exhausted")
    return False

if __name__ == "__main__":
    if not SESSION_COOKIE:
        print("ERROR: No LEMO_SESSION_COOKIE set")
        sys.exit(1)
    if keep_alive():
        sys.exit(0)
    else:
        sys.exit(1)
