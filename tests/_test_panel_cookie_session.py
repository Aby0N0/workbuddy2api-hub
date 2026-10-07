"""The panel remembers the browser, so a new tab does not ask for the password.

The dashboard used to keep the panel token in sessionStorage only: that store is
per-tab and dies with the tab, so every new tab (and every browser restart) put
the password prompt back. /panel/login now also sets a first-party HttpOnly
cookie, and a request may authenticate with either the header token or that
cookie.

Every case below drives a real gateway over a socket - no fake upstream, no
mocked handler - and each check names the status code it expects, so the cookie
is proven by the round trip rather than by reading the code:

  1. the login sets a usable cookie (HttpOnly, SameSite=Lax, Max-Age = TTL);
  2. a request with ONLY the cookie opens a panel route;
  3. the header token still works on its own (nothing regressed);
  4. the cookie parser picks the right value out of a crowded Cookie header,
     and a decoy name (wb_panel_token_decoy) does not count;
  5. logout and an invalid token both clear the cookie instead of leaving a
     stale one behind;
  6. changing the password invalidates the old cookie and issues a new one.
"""

import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import wb_settings as settings  # noqa: E402

COOKIE = settings.PANEL_COOKIE_NAME
FIRST_PASSWORD = "panel-secret-1"
SECOND_PASSWORD = "panel-secret-2"

PASS = 0
FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  [PASS] %s" % label)
    else:
        FAIL += 1
        print("  [FAIL] %s %s" % (label, detail))


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def call(port, method, path, body=None, cookie=None, token=None):
    """One request on its own connection; returns (status, parsed, set_cookie)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    headers = {"Connection": "close"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if cookie:
        headers["Cookie"] = cookie
    if token:
        headers["X-Panel-Token"] = token
    payload = None if body is None else json.dumps(body)
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    status = resp.status
    set_cookie = resp.getheader("Set-Cookie") or ""
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception:
        parsed = {}
    conn.close()
    return status, parsed, set_cookie


def cookie_value(set_cookie):
    """The `name=value` half of a Set-Cookie header, as a Cookie header."""
    first = set_cookie.split(";")[0].strip()
    name, _, value = first.partition("=")
    return name.strip(), value.strip()


def wait_ready(port, proc, log_path):
    for _ in range(40):
        time.sleep(0.5)
        if proc.poll() is not None:
            break
        try:
            status, _, _ = call(port, "GET", "/health")
            if status == 200:
                return True
        except Exception:
            pass
    try:
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            print("  gateway output:\n" + fh.read()[-2000:])
    except OSError:
        pass
    return False


work = tempfile.mkdtemp(prefix="panelcookie_")
store = os.path.join(work, "accounts")
os.makedirs(store)
log_path = os.path.join(work, "gateway.log")
port = free_port()

log_fh = open(log_path, "w", encoding="utf-8")
proc = subprocess.Popen(
    [sys.executable, os.path.join(ROOT, "wb_proxy.py"), "--port", str(port),
     "--host", "127.0.0.1", "--accounts-dir", store,
     "--panel-password", FIRST_PASSWORD],
    cwd=ROOT, stdout=log_fh, stderr=subprocess.STDOUT,
    env=dict(os.environ, WB_PROXY_USAGE_DIR=os.path.join(work, "usage")),
)

try:
    if not wait_ready(port, proc, log_path):
        print("  [FAIL] the gateway did not come up - nothing else can be checked")
        sys.exit(1)

    print("[1] the password prompt is the only way in, and it hands out a cookie")
    status, _, _ = call(port, "GET", "/settings")
    check("a panel route without any credential is refused", status == 401, status)

    status, info, set_cookie = call(port, "GET", "/panel/status")
    check("panel status answers without a credential", status == 200, status)
    check("and reports not authenticated", info.get("authenticated") is False, info)
    check("a stale cookie is cleared, not kept",
          "Max-Age=0" in set_cookie, set_cookie)

    status, _, _ = call(port, "POST", "/panel/login", {"password": "wrong-password"})
    check("a wrong password is refused", status == 401, status)

    status, login, set_cookie = call(port, "POST", "/panel/login",
                                     {"password": FIRST_PASSWORD})
    check("the right password is accepted", status == 200, (status, login))
    name, value = cookie_value(set_cookie)
    check("the cookie is the panel cookie", name == COOKIE, set_cookie)
    check("the cookie carries a token", bool(value) and len(value) > 10, set_cookie)
    check("the cookie is HttpOnly", "HttpOnly" in set_cookie, set_cookie)
    check("the cookie is SameSite=Lax", "SameSite=Lax" in set_cookie, set_cookie)
    check("the cookie covers the whole panel", "Path=/" in set_cookie, set_cookie)
    check("the cookie expires with the session TTL",
          "Max-Age=%d" % settings.SESSION_TTL in set_cookie, set_cookie)
    check("the response still returns the header token", bool(login.get("token")), login)

    print()
    print("[2] either credential opens the panel on its own")

    status, _, _ = call(port, "GET", "/settings", cookie="%s=%s" % (COOKIE, value))
    check("COOKIE ONLY opens a panel route (the bug this fixes)", status == 200, status)
    status, info, _ = call(port, "GET", "/panel/status",
                           cookie="%s=%s" % (COOKIE, value))
    check("cookie only reports authenticated", info.get("authenticated") is True, info)

    status, _, _ = call(port, "GET", "/settings", token=login.get("token"))
    check("the header token still works alone", status == 200, status)

    print()
    print("[3] the cookie parser finds the right name in a crowded header")

    crowded = "theme=dark; %s_decoy=nope; %s=%s; last=1" % (COOKIE, COOKIE, value)
    status, _, _ = call(port, "GET", "/settings", cookie=crowded)
    check("a decoy name does not win, the real cookie does", status == 200, status)

    decoy_only = "%s_decoy=%s" % (COOKIE, value)
    status, _, _ = call(port, "GET", "/settings", cookie=decoy_only)
    check("a decoy alone is refused", status == 401, status)

    status, _, _ = call(port, "GET", "/settings", cookie="%s=not-a-real-token" % COOKIE)
    check("a forged cookie is refused", status == 401, status)

    print()
    print("[4] logging out clears the cookie and revokes the session")

    status, _, set_cookie = call(port, "POST", "/panel/logout", {},
                                 cookie="%s=%s" % (COOKIE, value))
    check("logout is accepted with the cookie alone", status == 200, status)
    check("logout clears the cookie", "Max-Age=0" in set_cookie, set_cookie)
    status, _, _ = call(port, "GET", "/settings", cookie="%s=%s" % (COOKIE, value))
    check("the revoked cookie no longer opens the panel", status == 401, status)

    print()
    print("[5] changing the password rotates the cookie")

    status, login, set_cookie = call(port, "POST", "/panel/login",
                                     {"password": FIRST_PASSWORD})
    check("logged back in after the logout", status == 200, status)
    old = cookie_value(set_cookie)[1]
    status, changed, set_cookie = call(
        port, "POST", "/panel/password",
        {"current": FIRST_PASSWORD, "new": SECOND_PASSWORD},
        cookie="%s=%s" % (COOKIE, old))
    check("the password change is accepted with the cookie alone", status == 200, status)
    fresh = cookie_value(set_cookie)[1]
    check("a fresh cookie comes back", bool(fresh) and fresh != old, set_cookie)
    status, _, _ = call(port, "GET", "/settings", cookie="%s=%s" % (COOKIE, old))
    check("the old cookie is dead after the rotation", status == 401, status)
    status, _, _ = call(port, "GET", "/settings", cookie="%s=%s" % (COOKIE, fresh))
    check("the fresh cookie works", status == 200, status)
    check("the header token from before the rotation is dead too",
          call(port, "GET", "/settings", token=login.get("token"))[0] == 401)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    log_fh.close()

print()
print("  %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
