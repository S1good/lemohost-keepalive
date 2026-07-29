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
        print("Captcha image not found")
        return None

    img_url = match.group(1)
    img_resp = session.get(img_url, timeout=15)
    if img_resp.status_code != 200:
        print(f"Failed to download captcha: {img_resp.status_code}")
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

def check_remaining_time(session):
    resp = session.get(f"{LEMOHOST_URL}/server/view?id={SERVER_ID}", timeout=15)
    match = re.search(r'(\d+)\s*:\s*(\d+)', resp.text)
    if match:
        mins = int(match.group(1))
        print(f"Server remaining time: {match.group(0)} minutes")
        return mins
    print("Could not read remaining time from page")
    return None

def keep_alive():
    session = requests.Session()
    session.cookies.set("_identity-frontend", SESSION_COOKIE, domain="lemehost.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })

    time_before = check_remaining_time(session)
    if time_before is not None and time_before >= 28:
        print(f"Already {time_before}min remaining, no extend needed")
        return True

    form_url = f"{LEMOHOST_URL}/server/{SERVER_ID}/free-plan"

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
        resp = session.post(form_url, data=data, allow_redirects=True, timeout=15)

        time_after = check_remaining_time(session)
        if time_after is not None and time_after >= 28:
            print("SUCCESS! Server time extended!")
            return True
        elif "captcha" in resp.text.lower():
            print("Captcha wrong, retrying...")
            continue
        else:
            print("Extend submitted but time not confirmed, retrying...")
            continue

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
