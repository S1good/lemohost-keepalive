import requests
import re
import os
import io
import sys
from PIL import Image
import pytesseract
import traceback

LEMOHOST_URL = "https://lemehost.com"
SERVER_ID = "10234023"
SESSION_COOKIE = os.environ.get("LEMO_SESSION_COOKIE")
MAX_RETRIES = 5

def log(msg):
    print(msg, flush=True)

def solve_captcha(session, html):
    match = re.search(r'id="extendfreeplanform-captcha-image"[^>]*src="([^"]+)"', html)
    if not match:
        return None
    img_url = match.group(1)
    img_resp = session.get(img_url)
    if img_resp.status_code != 200:
        return None

    img = Image.open(io.BytesIO(img_resp.content))
    w, h = img.size
    log(f"Captcha image: {w}x{h}")

    # Sharpen and upscale massively
    best = None
    for scale in [6, 8, 10]:
        copy = img.copy().resize((w * scale, h * scale), Image.LANCZOS)
        copy = copy.convert("L")
        for psm in [6, 7, 8, 13]:
            try:
                config = f"--psm {psm} --oem 3"
                text = pytesseract.image_to_string(copy, config=config).strip()
                text = re.sub(r'[^a-z]', '', text.lower())
                log(f"  psm={psm} scale={scale}: '{text}'")
                if 3 <= len(text) <= 12 and not best:
                    best = text
            except:
                pass

    if best:
        log(f"Captcha: '{best}'")
        return best
    log("Captcha failed")
    return None

def get_remaining_minutes(html):
    match = re.search(r'id="countdown-free-plan"[^>]*>(\d+):(\d+):(\d+)<', html)
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2))
        total = hours * 60 + minutes
        log(f"Shutdown: {match.group(1)}:{match.group(2)}:{match.group(3)} ({total} min)")
        return total
    log("No countdown timer found")
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

    log("Fetching view page...")
    resp = session.get(view_url, allow_redirects=False)
    log(f"View page: {resp.status_code} URL: {resp.url} Location: {resp.headers.get('Location','none')}")
    if resp.status_code == 302:
        log("Session cookie invalid - redirecting to login")
        return False
    if resp.status_code != 200:
        log(f"Unexpected status: {resp.status_code}")
        # Try following redirect
        resp = session.get(view_url)
    current = get_remaining_minutes(resp.text)
    if current and current >= 28:
        log(f"Already {current}min, skip")
        return True

    for attempt in range(1, MAX_RETRIES + 1):
        log(f"\nAttempt {attempt}/{MAX_RETRIES}")
        resp = session.get(form_url, allow_redirects=True)

        csrf_match = re.search(r'name="_csrf-frontend"[^>]*value="([^"]+)"', resp.text)
        csrf_token = csrf_match.group(1) if csrf_match else None
        if not csrf_token:
            log("No CSRF token")
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
        resp = session.post(form_url, data=data, allow_redirects=False)
        loc = resp.headers.get('Location', 'none')
        log(f"POST: {resp.status_code} (Location: {loc})")
        if resp.status_code == 200:
            err = re.search(r'class="help-block"[^>]*>([^<]+)<', resp.text)
            if err:
                log(f"Error: {err.group(1).strip()}")
            elif "incorrect" in resp.text.lower():
                log("Error: captcha incorrect")
            elif "csrf" in resp.text.lower():
                log("Error: CSRF issue")

        if resp.status_code == 302:
            resp = session.get(view_url)
            after = get_remaining_minutes(resp.text)
            if after and after >= 28:
                log("SUCCESS! Extended!")
                return True
        else:
            log("Captcha rejected, retrying...")

    log("All retries exhausted")
    return False

if __name__ == "__main__":
    if not SESSION_COOKIE:
        log("ERROR: No LEMO_SESSION_COOKIE")
        sys.exit(1)
    try:
        sys.exit(0 if keep_alive() else 1)
    except Exception as e:
        log(f"CRASH: {e}")
        traceback.print_exc()
        sys.exit(1)
