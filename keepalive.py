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
    w, h = img.size

    best = None
    best_len = 99
    for invert in [False, True]:
        for scale in [2, 3, 4]:
            for thresh in [None, 130, 150, 170]:
                for psm in [6, 7, 8, 13]:
                    for whitelist in [
                        "abcdefghijklmnopqrstuvwxyz",
                        "abcdefghijklmnopqrstuvwxyz0123456789",
                        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
                    ]:
                        try:
                            copy = img.copy()
                            copy = copy.resize((w * scale, h * scale), Image.LANCZOS)
                            copy = copy.convert("L")
                            if invert:
                                copy = copy.point(lambda x: 255 - x)
                            if thresh is not None:
                                if invert:
                                    copy = copy.point(lambda x: 255 if x < thresh else 0)
                                else:
                                    copy = copy.point(lambda x: 0 if x < thresh else 255)
                            config = f"--psm {psm} --oem 3 -c tessedit_char_whitelist={whitelist}"
                            text = pytesseract.image_to_string(copy, config=config).strip()
                            text = re.sub(r'[^a-zA-Z0-9]', '', text)
                            if 4 <= len(text) <= 8 and len(text) < best_len:
                                best = text
                                best_len = len(text)
                        except:
                            pass

    # Also try raw grayscale with no threshold, various psms
    for scale in [2, 3]:
        for psm in [6, 7, 8]:
            copy = img.copy().resize((w * scale, h * scale), Image.LANCZOS).convert("L")
            config = f"--psm {psm} --oem 3"
            text = pytesseract.image_to_string(copy, config=config).strip()
            text = re.sub(r'[^a-zA-Z0-9]', '', text)
            if 4 <= len(text) <= 6 and len(text) < best_len:
                best = text
                best_len = len(text)

    if best:
        print(f"Captcha solved: '{best}'")
        return best
    print("Captcha: no valid text found")
    return None

def get_remaining_minutes(html):
    match = re.search(r'id="countdown-free-plan"[^>]*>(\d+):(\d+):(\d+)<', html)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        total = hours * 60 + minutes
        print(f"Server shutdown: {match.group(1)}:{match.group(2)}:{match.group(3)} ({total} min)")
        return total
    print("Could not find countdown timer")
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
        print(f"Already {current}min remaining, skip")
        return True

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\nAttempt {attempt}/{MAX_RETRIES}")
        resp = session.get(form_url, allow_redirects=True, timeout=15)

        csrf_match = re.search(r'name="_csrf-frontend"[^>]*value="([^"]+)"', resp.text)
        csrf_token = csrf_match.group(1) if csrf_match else None
        if not csrf_token:
            print("No CSRF token")
            return False

        till_match = re.search(r'name="ExtendFreePlanForm\[extendTill\]"[^>]*value="(\d+)"', resp.text)
        extend_till = till_match.group(1) if till_match else "1785315284"

        captcha_text = solve_captcha(session, resp.text)
        if not captcha_text:
            return False

        session.headers.update({
            "Referer": form_url,
            "Origin": LEMOHOST_URL,
            "Content-Type": "application/x-www-form-urlencoded",
        })

        data = {
            "_csrf-frontend": csrf_token,
            "ExtendFreePlanForm[captcha]": captcha_text,
            "ExtendFreePlanForm[extendTill]": extend_till
        }
        resp = session.post(form_url, data=data, allow_redirects=False, timeout=15)
        loc = resp.headers.get('Location', 'none')
        print(f"POST: {resp.status_code} (Location: {loc})")

        if resp.status_code == 302:
            resp = session.get(view_url, timeout=15)
            after = get_remaining_minutes(resp.text)
            if after and after >= 28:
                print("SUCCESS! Server time extended!")
                return True
        else:
            print("Captcha rejected, retrying...")

    print("All retries exhausted")
    return False

if __name__ == "__main__":
    if not SESSION_COOKIE:
        print("ERROR: No LEMO_SESSION_COOKIE")
        sys.exit(1)
    sys.exit(0 if keep_alive() else 1)
