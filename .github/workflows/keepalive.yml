import requests
import re
import os

LEMOHOST_URL = "https://lemehost.com"
SERVER_ID = "10234023"
SESSION_COOKIE = os.environ.get("LEMO_SESSION_COOKIE")

def keep_alive():
    session = requests.Session()
    session.cookies.set("_identity-frontend", SESSION_COOKIE, domain="lemehost.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
        "Referer": f"{LEMOHOST_URL}/server/view?id={SERVER_ID}",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })

    page_url = f"{LEMOHOST_URL}/server/view?id={SERVER_ID}"
    resp = session.get(page_url, allow_redirects=True)
    print(f"GET page: {resp.status_code}")
    print(f"Final URL: {resp.url}")

    csrf_match = re.search(r'name="_csrf-frontend"\s+value="([^"]+)"', resp.text)
    if not csrf_match:
        print("ERROR: Could not find CSRF token")
        print(f"Page length: {len(resp.text)}")
        print(f"First 500 chars: {resp.text[:500]}")
        print(f"Cookies sent: {dict(session.cookies)}")
        return False

    csrf_token = csrf_match.group(1)
    print(f"CSRF token found: {csrf_token[:20]}...")

    post_url = f"{LEMOHOST_URL}/server/{SERVER_ID}/free-plan"
    data = {
        "_csrf-frontend": csrf_token,
        "ExtendFreePlanForm[captcha]": "",
        "ExtendFreePlanForm[extendTill]": "1785239936"
    }
    resp = session.post(post_url, data=data, allow_redirects=True)
    print(f"POST extend: {resp.status_code}")
    print(f"Final URL after POST: {resp.url}")

    if resp.status_code == 200 or resp.status_code == 302:
        print("SUCCESS: Server time extended!")
        return True
    else:
        print(f"FAILED: {resp.status_code}")
        return False

if __name__ == "__main__":
    if not SESSION_COOKIE:
        print("ERROR: No session cookie found")
    else:
        keep_alive()
