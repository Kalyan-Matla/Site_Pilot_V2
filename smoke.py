"""End-to-end API smoke test against a seeded SitePilot instance.

Usage:  BASE=http://localhost:8000 python tests/smoke.py
Note: mutates data (creates a test project, PO, invoice, etc.) — run against
a disposable/seeded database, not production.
"""
import json
import os
import urllib.request

BASE = os.environ.get("BASE", "http://localhost:8000")
PASS_, FAIL = [], []


def req(method, path, token=None, body=None, raw=False, form=None):
    url = BASE + path
    headers = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        boundary = "XxBoundaryXx"
        parts = []
        for k, v in form.items():
            if isinstance(v, tuple):  # file: (filename, bytes)
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{v[0]}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + v[1] + b"\r\n")
            else:
                parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        data = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            payload = resp.read()
            return resp.status, payload if raw else json.loads(payload or b"{}")
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, payload


def check(name, cond, detail=""):
    (PASS_ if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  -> {detail}"))


def login(email):
    s, d = req("POST", "/api/auth/login", body={"email": email, "password": "Password123!"})
    assert s == 200, d
    return d["token"]

owner = login("owner@sitepilot.test")
pm = login("pm@sitepilot.test")
site = login("site@sitepilot.test")
store = login("store@sitepilot.test")
acct = login("accounts@sitepilot.test")
vendor = login("vendor@sitepilot.test")
print("all logins ok")

# --- auth / RBAC ---
s, d = req("GET", "/api/users", token=site)
check("site engineer cannot list users", s == 403, str(d))
s, d = req("GET", "/api/users?minimal=1", token=site)
check("minimal user list for dropdowns", s == 200 and len(d["data"]) >= 6, str(d)[:100])
s, d = req("POST", "/api/users", token=owner, body={"name": "Client Viewer", "email": "client@sitepilot.test", "password": "Password123!", "role": "accountant"})
check("owner creates user", s in (201, 409), str(d))
s, d = req("POST", "/api/auth/login", body={"email": "pm@sitepilot.test", "password": "wrong"})
check("bad password rejected", s == 401, str(d))

# --- projects ---
s, d = req("GET", "/api/projects", token=pm)
check("pm lists projects (assigned)", s == 200 and d["total"] >= 2, str(d)[:120])
P1 = next(p["id"] for p in d["data"] if p["name"].startswith("Sunrise"))
s, d = req("POST", "/api/projects", token=pm, body={"name": "Test Villa", "client_name": "Mr. X", "budget": 100000, "status": "planned"})
check("pm creates project", s == 201, str(d))
P3 = d["id"] if s == 201 else None
s, d = req("GET", f"/api/projects/{P3}", token=site)
check("unassigned site engineer blocked from new project", s == 403, str(d))
s, d = req("POST", f"/api/projects/{P3}/members", token=pm, body={"user_id": 3})
check("pm assigns site engineer to project", s == 201, str(d))
s, d = req("GET", f"/api/projects/{P3}", token=site)
check("site engineer can now view project", s == 200, str(d)[:100])

# --- tasks / issues / progress ---
s, d = req("POST", f"/api/projects/{P3}/tasks", token=pm, body={"name": "Layout marking", "planned_start": "2026-07-05", "planned_end": "2026-07-08", "assignee_id": 3})
check("create task", s == 201, str(d))
T = d.get("id")
s, d = req("PATCH", f"/api/tasks/{T}", token=site, body={"name": "Layout marking", "status": "done", "progress_pct": 50, "assignee_id": 3})
check("task done forces 100% progress", s == 200 and d.get("progress_pct") == 100, str(d)[:150])
s, d = req("POST", f"/api/projects/{P1}/issues", token=site, body={"title": "Smoke test issue", "severity": "low"})
check("raise issue", s == 201, str(d))
s, d = req("POST", f"/api/projects/{P1}/progress", token=site, body={"log_date": "2026-07-03", "work_description": "smoke log", "quantity_done": 5, "unit": "sqm"})
check("create progress log", s == 201, str(d))
LOG = d.get("id")
s, d = req("POST", f"/api/progress/{LOG}/photos", token=site, form={"file": ("site.jpg", b"\xff\xd8fakejpeg")})
check("upload progress photo", s == 201, str(d))
s, d = req("GET", f"/api/projects/{P1}/dpr?report_date=2026-07-03", token=pm)
check("DPR json", s == 200 and any(l["work_description"] == "smoke log" for l in d["logs"]), str(d)[:150])
s, d = req("GET", f"/api/projects/{P1}/wpr", token=pm)
check("WPR json", s == 200 and "labour" in d, str(d)[:100])

# --- documents & versioning ---
s, d = req("POST", f"/api/projects/{P1}/documents", token=pm, form={"title": "GA Drawing", "category": "drawing", "file": ("ga_r0.pdf", b"%PDF-1.4 fake")})
check("upload document v1", s == 201 and d.get("versions") and d["versions"][0]["version_no"] == 1, str(d)[:150])
DOC = d.get("id")
s, d = req("POST", f"/api/documents/{DOC}/versions", token=pm, form={"notes": "Revised cols", "file": ("ga_r1.pdf", b"%PDF-1.4 fake2")})
check("upload document v2", s == 201 and d["versions"][0]["version_no"] == 2, str(d)[:150])
VID = d["versions"][0]["id"]
s, raw = req("GET", f"/api/documents/versions/{VID}/download", token=pm, raw=True)
check("download version", s == 200 and raw.startswith(b"%PDF"), str(raw)[:60])
s, d = req("GET", f"/api/documents/{DOC}", token=vendor)
check("vendor blocked from documents", s == 403, str(d))

# --- materials flow ---
s, d = req("GET", "/api/materials", token=store)
check("materials master", s == 200 and d["total"] >= 8, str(d)[:100])
MAT = d["data"][0]["id"]
s, d = req("POST", "/api/material-requests", token=site, body={"project_id": P1, "required_date": "2026-07-10", "items": [{"material_id": MAT, "qty": 100}]})
check("site raises indent", s == 201 and d["status"] == "pending", str(d)[:150])
MR = d.get("id")
s, d = req("POST", f"/api/material-requests/{MR}/approve", token=site, body={})
check("site engineer cannot approve", s == 403, str(d))
s, d = req("POST", f"/api/material-requests/{MR}/approve", token=pm, body={"notes": "ok"})
check("pm approves indent", s == 200 and d["status"] == "approved", str(d)[:150])
s, d = req("POST", "/api/purchase-orders", token=pm, body={"project_id": P1, "vendor_id": 1, "request_id": MR, "items": [{"material_id": MAT, "qty": 100, "rate": 50}]})
check("PO from approved request", s == 201 and d["status"] == "issued" and d["total_amount"] == 5000, str(d)[:200])
PO = d.get("id")
POI = d["items"][0]["id"]
s, d = req("POST", "/api/grns", token=store, body={"po_id": PO, "items": [{"po_item_id": POI, "qty_received": 150}]})
check("GRN over-receipt rejected", s == 422, str(d))
s, d = req("POST", "/api/grns", token=store, body={"po_id": PO, "items": [{"po_item_id": POI, "qty_received": 60}]})
check("partial GRN accepted", s == 201, str(d)[:200])
s, d = req("GET", f"/api/purchase-orders/{PO}", token=pm)
check("PO partially_received", s == 200 and d["status"] == "partially_received", str(d)[:150])
s, d = req("POST", "/api/grns", token=store, body={"po_id": PO, "items": [{"po_item_id": POI, "qty_received": 40}]})
check("final GRN accepted", s == 201, str(d)[:150])
s, d = req("GET", f"/api/material-requests/{MR}", token=pm)
check("request auto-fulfilled after full receipt", s == 200 and d["status"] == "fulfilled", str(d)[:150])
s, d = req("POST", "/api/material-usage", token=site, body={"project_id": P1, "material_id": MAT, "qty": 99999})
check("usage beyond stock rejected", s == 422, str(d))
s, d = req("POST", "/api/material-usage", token=site, body={"project_id": P1, "material_id": MAT, "qty": 10})
check("usage logged", s == 201, str(d)[:120])
s, d = req("GET", f"/api/projects/{P1}/material-summary", token=pm)
check("material summary (req/recv/used)", s == 200 and len(d["data"]) > 0, str(d)[:200])
s, d = req("GET", f"/api/projects/{P1}/stock", token=store)
check("site stock", s == 200 and d["total"] > 0, str(d)[:100])

# --- vendor scoping on POs ---
s, d = req("GET", "/api/purchase-orders", token=vendor)
check("vendor sees only own POs", s == 200 and all(x["vendor_id"] == 1 for x in d["data"]), str(d)[:150])
s, d = req("GET", f"/api/purchase-orders/{PO}", token=vendor)
check("vendor opens own PO", s == 200, str(d)[:100])

# --- labour ---
s, d = req("GET", f"/api/projects/{P1}/labourers", token=site)
check("labourers list", s == 200 and d["total"] >= 7, str(d)[:100])
LAB = d["data"][0]["id"]
s, d = req("POST", f"/api/projects/{P1}/attendance", token=site, body={"att_date": "2026-07-03", "entries": [{"labourer_id": LAB, "status": "present", "ot_hours": 2}]})
check("mark attendance", s == 200, str(d))
s, d = req("POST", f"/api/projects/{P1}/attendance", token=site, body={"att_date": "2026-07-03", "entries": [{"labourer_id": LAB, "status": "half_day"}]})
check("attendance upsert (re-mark same day)", s == 200, str(d))
s, d = req("GET", f"/api/projects/{P1}/labour-payable?date_from=2026-06-01&date_to=2026-07-03", token=pm)
check("labour payable computed", s == 200 and d["total_payable"] > 0 and len(d["by_vendor"]) > 0, str(d)[:200])
s, d = req("GET", "/api/labour-summary?date_from=2026-06-01&date_to=2026-07-03", token=owner)
check("cross-project labour summary", s == 200 and len(d["data"]) > 0, str(d)[:150])

# --- finance ---
s, d = req("GET", "/api/vendors", token=acct)
check("vendors with outstanding", s == 200 and any(v["outstanding"] > 0 for v in d["data"]), str(d)[:150])
s, d = req("GET", "/api/vendors", token=vendor)
check("vendor sees only self", s == 200 and d["total"] == 1, str(d)[:150])
s, d = req("POST", "/api/invoices", token=vendor, body={"invoice_number": "SST/2026/200", "vendor_id": 2, "project_id": P1, "invoice_date": "2026-07-01", "amount": 1000})
check("vendor cannot invoice as another vendor", s == 403, str(d))
s, d = req("POST", "/api/invoices", token=vendor, body={"invoice_number": "SST/2026/200", "vendor_id": 1, "project_id": P1, "po_id": PO, "invoice_date": "2026-07-01", "amount": 5000, "tax_amount": 900})
check("vendor submits own invoice, due = date + 45d", s == 201 and d["due_date"] == "2026-08-15" and d["total_amount"] == 5900, str(d)[:200])
INV = d.get("id")
s, d = req("PATCH", f"/api/invoices/{INV}/status", token=acct, body={"status": "paid"})
check("cannot mark paid before payment", s == 422, str(d))
s, d = req("PATCH", f"/api/invoices/{INV}/status", token=acct, body={"status": "approved"})
check("accountant approves invoice", s == 200 and d["status"] == "approved", str(d)[:100])
s, d = req("POST", "/api/payments", token=pm, body={"invoice_id": INV, "vendor_id": 1, "pay_date": "2026-07-03", "amount": 5900})
check("pm cannot record payments", s == 403, str(d))
s, d = req("POST", "/api/payments", token=acct, body={"invoice_id": INV, "vendor_id": 1, "pay_date": "2026-07-03", "amount": 9000})
check("overpayment rejected", s == 422, str(d))
s, d = req("POST", "/api/payments", token=acct, body={"invoice_id": INV, "vendor_id": 1, "pay_date": "2026-07-03", "amount": 5900, "mode": "bank", "reference": "NEFT-1"})
check("full payment auto-marks invoice paid", s == 201, str(d)[:150])
s, d = req("GET", f"/api/invoices?project_id={P1}", token=acct)
inv_row = next((x for x in d["data"] if x["id"] == INV), {})
check("invoice now paid with zero balance", inv_row.get("status") == "paid" and inv_row.get("balance") == 0, str(inv_row)[:150])
s, d = req("GET", "/api/finance/payables", token=acct)
check("payables ledger", s == 200 and len(d["by_vendor"]) > 0 and len(d["by_project"]) > 0, str(d)[:150])
s, d = req("GET", "/api/finance/ageing", token=acct)
check("ageing buckets", s == 200 and len(d["buckets"]) == 4 and d["total_outstanding"] > 0, str(d)[:200])
check("46-60 bucket has seeded old invoice", any(b["label"] in ("46-60", "60+") and b["count"] > 0 for b in d["buckets"]), json.dumps(d["buckets"])[:300])
s, d = req("GET", "/api/finance/alerts", token=acct)
check("finance alerts include >45d invoice", s == 200 and any(a["type"] == "invoice_age" for a in d["alerts"]), str(d)[:300])
s, d = req("GET", "/api/payments?mode=cash", token=acct)
check("cash book filter", s == 200, str(d)[:100])

# --- comments & notifications ---
s, d = req("POST", "/api/comments", token=pm, body={"entity_type": "material_request", "entity_id": MR, "body": "Received in full, closing."})
check("comment on request", s == 201, str(d)[:120])
s, d = req("GET", f"/api/comments?entity_type=material_request&entity_id={MR}", token=site)
check("comment thread visible", s == 200 and len(d["data"]) >= 1, str(d)[:120])
s, d = req("GET", "/api/notifications", token=site)
check("site has notifications (approval etc.)", s == 200 and d["unread"] > 0, str(d)[:150])
NID = d["data"][0]["id"]
s, d = req("POST", "/api/notifications/read", token=site, body={"ids": [NID]})
check("mark notification read", s == 200, str(d))
s, d = req("GET", f"/api/projects/{P1}/activity", token=pm)
check("activity feed", s == 200 and d["total"] > 5, str(d)[:100])

# --- equipment & checklists ---
s, d = req("GET", "/api/equipment", token=pm)
check("equipment list, crane maintenance due", s == 200 and any(e["maintenance_due"] for e in d["data"]), str(d)[:200])
EQ = d["data"][0]["id"]
s, d = req("POST", f"/api/equipment/{EQ}/logs", token=site, body={"hours_used": 5})
check("equipment usage log", s == 201, str(d)[:120])
s, d = req("GET", f"/api/projects/{P1}/checklists", token=pm)
check("checklists with fail counts", s == 200 and any(c["failed_count"] > 0 for c in d["data"]), str(d)[:150])
s, d = req("POST", f"/api/projects/{P1}/checklists", token=site, body={"ctype": "quality", "title": "Rebar cover check", "items": [{"item": "Cover blocks 25mm", "outcome": "pass"}]})
check("create checklist with items", s == 201 and len(d["items"]) == 1, str(d)[:150])

# --- reports & exports ---
for name, path in [
    ("DPR pdf", f"/api/reports/dpr/{P1}?fmt=pdf&report_date=2026-07-03"),
    ("WPR pdf", f"/api/reports/wpr/{P1}?fmt=pdf"),
    ("stock csv", f"/api/reports/stock/{P1}?fmt=csv"),
    ("material flow csv", f"/api/reports/material-flow/{P1}?fmt=csv"),
    ("labour csv", "/api/reports/labour?date_from=2026-06-01&date_to=2026-07-03&fmt=csv"),
    ("ageing pdf", "/api/reports/ageing?fmt=pdf"),
    ("payables csv", "/api/reports/payables?fmt=csv"),
]:
    s, raw = req("GET", path, token=owner, raw=True)
    ok = s == 200 and (raw.startswith(b"%PDF") if "pdf" in name else len(raw) > 20)
    check(f"export {name}", ok, f"status {s} len {len(raw)} head {raw[:40]}")

# --- audit log ---
s, d = req("GET", "/api/audit-log?entity_type=payment", token=acct)
check("audit log records payments", s == 200 and d["total"] >= 1, str(d)[:150])
s, d = req("GET", "/api/audit-log", token=site)
check("site engineer blocked from audit log", s == 403, str(d))

print(f"\n{len(PASS_)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    raise SystemExit(1)
