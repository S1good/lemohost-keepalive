import requests
import re
import os
import io
import sys
import traceback

try:
    import easyocr
    EASYOCR_READER = easyocr.Reader(['en'], gpu=False)
    HAVE_EASYOCR = True
except:
    HAVE_EASYOCR = False

try:
    from PIL import Image
    HAVE_PIL = True
except:
    HAVE_PIL = False

try:
    import pytesseract
    HAVE_TESSERACT = True
except:
    HAVE_TESSERACT = False

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

    img_bytes = img_resp.content
    log(f"Captcha image: {len(img_bytes)} bytes")

    candidates = {}

    # EasyOCR (best)
    if HAVE_EASYOCR:
        try:
            results = EASYOCR_READER.readtext(img_bytes, detail=0, paragraph=False)
            for text in results:
                text = re.sub(r'[^a-zA-Z]', '', text).lower()
                if 3 <= len(text) <= 12:
                    candidates['easyocr'] = text
                    log(f"  EasyOCR: '{text}'")
        except Exception as e:
            log(f"  EasyOCR error: {e}")

    # pytesseract (fallback)
    if HAVE_TESSERACT and HAVE_PIL:
        try:
            img = Image.open(io.BytesIO(img_bytes))
            w, h = img.size
            best_t = None
            for scale in [4, 6]:
                for psm in [6, 7, 8]:
                    for oem in [1, 3]:
                        for thresh in [None, 90, 100, 110]:
                            try:
                                copy = img.copy().resize((w * scale, h * scale), Image.LANCZOS).convert("L")
                                if thresh is not None:
                                    copy = copy.point(lambda x, t=thresh: 0 if x < t else 255)
                                config = f"--psm {psm} --oem {oem}"
                                text = pytesseract.image_to_string(copy, config=config).strip()
                                text = re.sub(r'[^a-z]', '', text.lower())
                                if 3 <= len(text) <= 12:
                                    if not best_t or len(text) > len(best_t):
                                        best_t = text
                            except:
                                pass
            if best_t:
                candidates['tesseract'] = best_t
                log(f"  Tesseract: '{best_t}'")
        except Exception as e:
            log(f"  PIL error: {e}")

    # Pick best result (prefer EasyOCR, then longer text)
    if 'easyocr' in candidates:
        chosen = candidates['easyocr']
        log(f"Captcha: '{chosen}' (EasyOCR)")
        return chosen
    if 'tesseract' in candidates:
        chosen = candidates['tesseract']
        log(f"Captcha: '{chosen}' (Tesseract)")
        return chosen

    log("Captcha failed")
    return None

def keep_alive():
    session = requests.Session()
    session.cookies.set("_identity-frontend", SESSION_COOKIE, domain="lemehost.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })

    form_url = f"{LEMOHOST_URL}/server/{SERVER_ID}/free-plan"

    log("Opening free-plan page...")
    resp = session.get(form_url, allow_redirects=True)
    log(f"Form page: {resp.status_code}")

    # Check if already extended
    ext_match = re.search(r'id="countdown-free-plan"[^>]*>(\d+):(\d+):(\d+)<', resp.text)
    if ext_match:
        h, m, s = int(ext_match.group(1)), int(ext_match.group(2)), int(ext_match.group(3))
        total = h * 60 + m
        log(f"Countdown: {h}:{m:02d}:{s:02d} ({total} min)")
        if total >= 28:
            log(f"Already {total}min, skip")
            return True

    for attempt in range(1, MAX_RETRIES + 1):
        log(f"\nAttempt {attempt}/{MAX_RETRIES}")

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

        if resp.status_code == 302:
            resp = session.get(form_url, allow_redirects=True)
            ext2 = re.search(r'id="countdown-free-plan"[^>]*>(\d+):(\d+):(\d+)<', resp.text)
            if ext2:
                h2, m2 = int(ext2.group(1)), int(ext2.group(2))
                total2 = h2 * 60 + m2
                log(f"After: {h2}:{m2:02d}:{ext2.group(3)} ({total2} min)")
                if total2 >= 28:
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
