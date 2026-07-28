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
        "Referer": f"{LEMOHOST_URL}/server/view?id={SERVER_ID}",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })

    page_url = f"{LEMOHOST_URL}/server/view?id={SERVER_ID}"
    resp = session.get(page_url, allow_redirects=True)
    print(f"GET page: {resp.status_code}")
    print(f"Final URL: {resp.url}")

    csrf_token = None

    # Method 1: search in HTML form
    csrf_match = re.search(r'name="_csrf-frontend"\s+value="([^"]+)"', resp.text)
    if csrf_match:
        csrf_token = csrf_match.group(1)
        print(f"CSRF from form: {csrf_token[:20]}...")

    # Method 2: search with flexible spacing
    if not csrf_token:
        csrf_match = re.search(r'name=["\']_csrf-frontend["\'].*?value=["\']([^"\']+)["\']', resp.text, re.DOTALL)
        if csrf_match:
            csrf_token = csrf_match.group(1)
            print(f"CSRF from form (flexible): {csrf_token[:20]}...")

    # Method 3: extract from _csrf-frontend cookie
    if not csrf_token:
        csrf_cookie = session.cookies.get("_csrf-frontend")
        if csrf_cookie:
            decoded = urllib.parse.unquote(csrf_cookie)
            token_match = re.search(r'"([a-zA-Z0-9]{32,})"', decoded)
            if token_match:
                csrf_token = token_match.group(1)
                print(f"CSRF from cookie: {csrf_token[:20]}...")

    # Method 4: search entire page for any csrf hidden input
    if not csrf_token:
        all_csrf = re.findall(r'csrf[^"]*"([^"]{20,})"', resp.text, re.IGNORECASE)
        if all_csrf:
            print(f"Found {len(all_csrf)} csrf values:")
            for i, val in enumerate(all_csrf):
                print(f"  [{i}] {val[:40]}...")
            csrf_token = all_csrf[0]

    if not csrf_token:
        print("ERROR: Could not find CSRF token anywhere")
        forms = re.findall(r'<form[^>]*>(.*?)</form>', resp.text[:5000], re.DOTALL)
        print(f"Found {len(forms)} forms in first 5000 chars")
        return False

    print(f"Using CSRF token: {csrf_token}")

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
