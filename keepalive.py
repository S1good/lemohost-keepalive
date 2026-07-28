import requests
import re
import os
import urllib.parse

LEMOHOST_URL = "https://lemehost.com"
SERVER_ID = "10234023"
SESSION_COOKIE = os.environ.get("LEMO_SESSION_COOKIE")

def keep_alive():
    session = requests.Session()
    session.cookies.set("_identity-frontend", SESSION_COOKIE, domain="lemehost.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })

    resp = session.get(f"{LEMOHOST_URL}/server/view?id={SERVER_ID}", allow_redirects=True)
    print(f"GET page: {resp.status_code}")

    csrf_token = None
    csrf_cookie = session.cookies.get("_csrf-frontend")
    if csrf_cookie:
        decoded = urllib.parse.unquote(csrf_cookie)
        token_match = re.search(r'"([a-zA-Z0-9_-]{32,})"', decoded)
        if token_match:
            csrf_token = token_match.group(1)
            print(f"CSRF from cookie: {csrf_token}")

    if not csrf_token:
        print("ERROR: No CSRF token found")
        return False

    post_url = f"{LEMOHOST_URL}/server/{SERVER_ID}/free-plan"
    session.headers.update({
        "Referer": f"{LEMOHOST_URL}/server/view?id={SERVER_ID}",
        "Origin": LEMOHOST_URL,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    data = {
        "_csrf-frontend": csrf_token,
        "ExtendFreePlanForm[captcha]": "",
        "ExtendFreePlanForm[extendTill]": "1785239936"
    }
    resp = session.post(post_url, data=data, allow_redirects=True)
    print(f"POST extend: {resp.status_code}")
    print(f"Final URL: {resp.url}")

    if resp.status_code in (200, 302):
        print("SUCCESS!")
        return True
    else:
        print(f"FAILED: {resp.status_code}")
        return False

if __name__ == "__main__":
    if not SESSION_COOKIE:
        print("ERROR: No session cookie")
    else:
        keep_alive()
