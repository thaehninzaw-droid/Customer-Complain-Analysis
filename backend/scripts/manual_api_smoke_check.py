"""
Manual, real-HTTP smoke check for Loopline's customer + admin flows.

Unlike backend/tests/test_api.py (which uses FastAPI's in-process
TestClient), this drives an *actually running* uvicorn process over
real HTTP with `requests` - closer to what a browser does, and a
useful quick check after touching auth/routing code.

Deliberately named *_check.py, not *_test.py or test_*.py: pytest's
default discovery would otherwise try to collect and import this file
as a test module, which fails immediately (it makes real network calls
at collection time with no server running) - see docs/DECISIONS.md #20
for how that mistake was caught the first time this script existed.

Usage:
    # terminal 1
    cd backend && uvicorn app.main:app --reload

    # terminal 2
    cd backend && python scripts/manual_api_smoke_check.py

This uses the in-memory DB fallback and the template chatbot fallback
by default (same as a fresh clone with no .env configured) - it does
NOT exercise real MongoDB/Gemini/Qdrant. See docs/TESTING.md.
"""
import argparse
import sys
import time

import requests


class Checker:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.ok_count = 0
        self.fail_count = 0

    def check(self, label: str, condition: bool, extra: str = "") -> None:
        if condition:
            self.ok_count += 1
            print(f"  PASS  {label}")
        else:
            self.fail_count += 1
            print(f"  FAIL  {label}  {extra}")

    def summary(self) -> int:
        print(f"\n{'=' * 50}")
        print(f"TOTAL: {self.ok_count} passed, {self.fail_count} failed")
        print(f"{'=' * 50}")
        return 1 if self.fail_count else 0


def run_customer_flow(c: Checker):
    """Returns (bearer_headers, ticket_no) for use by the admin flow."""
    base = c.base_url
    uniq = str(int(time.time()))[-6:]

    signup = requests.post(f"{base}/auth/signup", json={
        "username": f"Smoke {uniq}",
        "email": f"smoketest_{uniq}@example.com",
        "password": "TestPass123!",
    })
    c.check("signup returns 200/201", signup.status_code in (200, 201), signup.text[:200])
    signup_data = signup.json() if signup.ok else {}
    token = signup_data.get("token")
    c.check("signup returns a session token", bool(token), str(signup_data)[:200])

    login = requests.post(f"{base}/auth/login", json={
        "email": f"smoketest_{uniq}@example.com",
        "password": "TestPass123!",
    })
    c.check("login returns 200", login.status_code == 200, login.text[:200])
    token = ((login.json() or {}).get("token") if login.ok else None) or token
    headers = {"Authorization": f"Bearer {token}"}

    complaint_text = "My internet bill charged me twice this month and nobody will refund it, I'm furious."
    filed = requests.post(f"{base}/complaints", json={
        "complaint": complaint_text,
        "city": "Yangon", "state": "Yangon Region", "zipcode": "11181",
    }, headers=headers)
    c.check("file complaint returns 200/201", filed.status_code in (200, 201), filed.text[:300])
    fc = filed.json() if filed.ok else {}
    ticket_no = fc.get("ticket_no")
    c.check("complaint got a ticket_no", bool(ticket_no), str(fc)[:300])
    c.check("complaint auto-assigned a known category",
             fc.get("category") in ["Billing", "Financial", "Technical", "Service", "Others"],
             str(fc.get("category")))
    print(f"    -> ticket_no={ticket_no} category={fc.get('category')} priority={fc.get('priority')}")

    too_short = requests.post(f"{base}/complaints", json={"complaint": "too short"}, headers=headers)
    c.check("server-side rejects a too-short complaint (400)",
             too_short.status_code == 400, f"got {too_short.status_code}")

    bad_city = requests.post(f"{base}/complaints", json={
        "complaint": "My service has been down for three days and nobody has responded.",
        "city": "Atlantis",
    }, headers=headers)
    c.check("server-side rejects an unrecognized city (400)",
             bad_city.status_code == 400, f"got {bad_city.status_code}")

    mine_resp = requests.get(f"{base}/complaints", headers=headers)
    c.check("list own complaints returns 200", mine_resp.status_code == 200, mine_resp.text[:200])
    mine = mine_resp.json() if mine_resp.ok else []
    c.check("filed complaint appears in own activities list",
             any(item.get("ticket_no") == ticket_no for item in mine), str(mine)[:300])

    no_auth = requests.get(f"{base}/complaints")
    c.check("listing complaints with NO token is rejected (401/403)",
             no_auth.status_code in (401, 403), f"got {no_auth.status_code}")

    cities = requests.get(f"{base}/cities")
    c.check("GET /cities returns 200 with the full city list",
             cities.status_code == 200 and len(cities.json()) == 63,
             f"got {cities.status_code}, {len(cities.json()) if cities.ok else '?'} entries")

    return headers, ticket_no


def run_admin_flow(c: Checker, customer_headers: dict, customer_ticket_no):
    base = c.base_url

    admin_login = requests.post(f"{base}/auth/login", json={
        "email": "admin@loopline.io", "password": "ChangeMe123!",
    })
    c.check("admin login returns 200", admin_login.status_code == 200, admin_login.text[:300])
    admin_token = (admin_login.json() or {}).get("token") if admin_login.ok else None
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    blocked = requests.get(f"{base}/admin/complaints", headers=customer_headers)
    c.check("customer token on /admin/complaints is rejected with 403",
             blocked.status_code == 403, f"got {blocked.status_code}")

    admin_list = requests.get(f"{base}/admin/complaints", headers=admin_headers)
    c.check("admin can list all complaints (200)", admin_list.status_code == 200, admin_list.text[:200])
    payload = admin_list.json() if admin_list.ok else {}
    items = payload.get("items") if isinstance(payload, dict) else payload
    c.check("admin complaint list contains at least the ticket just filed",
             bool(items), str(payload)[:200])

    manual = requests.post(f"{base}/admin/complaints", json={
        "complaint": "Manual entry from smoke check - technician never showed up.",
        "city": "Mandalay", "state": "Mandalay Region", "zipcode": "05011",
    }, headers=admin_headers)
    c.check("admin manual complaint entry returns 200/201", manual.status_code in (200, 201), manual.text[:300])
    manual_ticket = (manual.json() or {}).get("ticket_no") if manual.ok else None

    if manual_ticket:
        edit = requests.patch(f"{base}/admin/complaints/{manual_ticket}",
                               json={"status": "Resolved"}, headers=admin_headers)
        c.check("admin inline status edit returns 200", edit.status_code == 200, edit.text[:300])
        c.check("edited status reflects in response",
                 (edit.json() or {}).get("status") == "Resolved" if edit.ok else False,
                 edit.text[:200])

    analytics = requests.get(f"{base}/admin/analytics", headers=admin_headers)
    c.check("admin analytics endpoint returns 200", analytics.status_code == 200, analytics.text[:200])

    ml_status = requests.get(f"{base}/admin/ml-status", headers=admin_headers)
    c.check("admin ml-status endpoint returns 200", ml_status.status_code == 200, ml_status.text[:200])
    print(f"    -> ml-status: {str(ml_status.json() if ml_status.ok else ml_status.text)[:300]}")

    chatbot = requests.post(f"{base}/admin/chatbot/ask", json={
        "ticket_no": customer_ticket_no,
        "question": "What should I tell this customer about their billing complaint?",
    }, headers=admin_headers)
    c.check("admin chatbot ask returns 200 even without Gemini configured",
             chatbot.status_code == 200, chatbot.text[:300])
    chatbot_payload = chatbot.json() if chatbot.ok else {}
    c.check("chatbot response discloses used_rag: false (no GEMINI_API_KEY set)",
             chatbot_payload.get("used_rag") is False, str(chatbot_payload)[:300])
    print(f"    -> chatbot fallback answer: {str(chatbot_payload.get('answer'))[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000",
                         help="Base URL of a running Loopline backend (default: %(default)s)")
    args = parser.parse_args()

    c = Checker(args.base)
    try:
        requests.get(args.base, timeout=3)
    except requests.exceptions.ConnectionError:
        print(f"Could not reach {args.base} - is uvicorn running?")
        print("  cd backend && uvicorn app.main:app --reload")
        return 2

    print("== Customer flow ==")
    customer_headers, ticket_no = run_customer_flow(c)
    print("\n== Admin flow ==")
    run_admin_flow(c, customer_headers, ticket_no)
    return c.summary()


if __name__ == "__main__":
    sys.exit(main())
