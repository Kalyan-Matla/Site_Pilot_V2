"""Seed demo data: one login per role, two projects, and a full workflow chain.

Run:  uv run python -m app.seed
"""
from datetime import date, timedelta

from .db import connect, insert, migrate, row, scalar
from .security import hash_password

PASSWORD = "Password123!"


def seed():
    migrate()
    conn = connect()
    if scalar(conn, "SELECT COUNT(*) FROM users"):
        print("Database already has users — skipping seed. Delete data/sitepilot.db to reseed.")
        return
    today = date.today()
    d = lambda days: (today + timedelta(days=days)).isoformat()

    # ---- vendors ----
    v_steel = insert(conn, "vendors", {"name": "Shree Steel Traders", "contact_person": "Ramesh Gupta",
        "phone": "+91 98100 11111", "email": "sales@shreesteel.example", "gst_no": "07AABCS1111A1Z5",
        "vendor_type": "material", "payment_terms": "45 days credit", "credit_period_days": 45,
        "credit_limit": 1500000})
    v_cement = insert(conn, "vendors", {"name": "BuildMart Cement Co", "contact_person": "Suresh Kumar",
        "phone": "+91 98100 22222", "email": "orders@buildmart.example", "gst_no": "07AABCB2222B1Z4",
        "vendor_type": "material", "payment_terms": "30 days credit", "credit_period_days": 30,
        "credit_limit": 800000})
    v_labour = insert(conn, "vendors", {"name": "Kisan Labour Contractors", "contact_person": "Vijay Singh",
        "phone": "+91 98100 33333", "email": "kisan@labour.example", "gst_no": "07AABCK3333C1Z3",
        "vendor_type": "labour", "payment_terms": "Weekly settlement", "credit_period_days": 15,
        "credit_limit": 400000})

    # ---- users (one per role) ----
    users = {}
    for key, name, email, role, vid in [
        ("owner", "Arun Mehta (Owner)", "owner@sitepilot.test", "owner", None),
        ("pm", "Priya Sharma (PM)", "pm@sitepilot.test", "pm", None),
        ("site", "Sanjay Verma (Site Engineer)", "site@sitepilot.test", "site", None),
        ("store", "Deepak Yadav (Storekeeper)", "store@sitepilot.test", "store", None),
        ("accountant", "Meena Iyer (Accountant)", "accounts@sitepilot.test", "accountant", None),
        ("vendor", "Ramesh Gupta (Shree Steel)", "vendor@sitepilot.test", "vendor", v_steel),
    ]:
        users[key] = insert(conn, "users", {"name": name, "email": email,
            "password_hash": hash_password(PASSWORD), "role": role, "vendor_id": vid})

    # ---- projects ----
    p1 = insert(conn, "projects", {"name": "Sunrise Apartments — Block A", "client_name": "Sunrise Developers LLP",
        "location": "Sector 45, Gurugram", "start_date": d(-90), "end_date": d(180), "status": "active",
        "description": "G+8 residential tower, RCC frame with brick infill.",
        "budget": 42500000, "contract_value": 52000000, "created_by": users["owner"]})
    p2 = insert(conn, "projects", {"name": "Metro Warehouse Extension", "client_name": "FastTrack Logistics",
        "location": "Bhiwandi, Thane", "start_date": d(-30), "end_date": d(120), "status": "active",
        "description": "PEB warehouse extension 20,000 sq ft with docking bays.",
        "budget": 18000000, "contract_value": 21500000, "created_by": users["owner"]})
    for pid in (p1, p2):
        for key in ("pm", "site", "store"):
            insert(conn, "project_members", {"project_id": pid, "user_id": users[key]})

    # ---- tasks ----
    tasks_p1 = [
        ("Site mobilisation", 1, -90, -80, "done", 100),
        ("Excavation & foundation", 0, -78, -45, "done", 100),
        ("Plinth beam & backfilling", 1, -44, -30, "done", 100),
        ("RCC frame — floors 1-4", 0, -29, 10, "in_progress", 65),
        ("RCC frame — floors 5-8", 0, 11, 60, "todo", 0),
        ("Brickwork & plastering", 0, 30, 120, "todo", 0),
        ("MEP first fix", 0, 50, 130, "todo", 0),
        ("Finishing & handover", 1, 130, 180, "todo", 0),
    ]
    t_ids = {}
    for name, mile, s, e, status, pct in tasks_p1:
        t_ids[name] = insert(conn, "tasks", {"project_id": p1, "name": name, "is_milestone": mile,
            "planned_start": d(s), "planned_end": d(e), "status": status, "progress_pct": pct,
            "assignee_id": users["site"], "actual_start": d(s) if status != "todo" else None,
            "actual_end": d(e) if status == "done" else None})
    for name, s, e, status, pct in [
        ("Foundation & flooring", -30, -5, "done", 100),
        ("Steel structure erection", -4, 40, "in_progress", 45),
        ("Roofing & cladding", 30, 80, "todo", 0),
        ("Docking bays & finishing", 70, 120, "todo", 0),
    ]:
        insert(conn, "tasks", {"project_id": p2, "name": name, "planned_start": d(s), "planned_end": d(e),
                               "status": status, "progress_pct": pct, "assignee_id": users["site"]})

    # ---- issues ----
    i1 = insert(conn, "issues", {"project_id": p1, "task_id": t_ids["RCC frame — floors 1-4"],
        "title": "Shuttering material shortage on floor 3", "severity": "high", "status": "open",
        "description": "Plywood shuttering sheets damaged; slab casting may slip by 3 days.",
        "raised_by": users["site"], "assigned_to": users["pm"]})
    insert(conn, "issues", {"project_id": p1, "title": "Water logging near ramp after rain",
        "severity": "medium", "status": "in_progress", "raised_by": users["site"], "assigned_to": users["site"]})

    # ---- materials & stock ----
    mats = {}
    for name, cat, unit, rate in [
        ("OPC 53 Cement", "Cement", "bag", 385), ("TMT Steel 12mm", "Steel", "kg", 62),
        ("TMT Steel 16mm", "Steel", "kg", 61.5), ("River Sand", "Aggregate", "cft", 55),
        ("Coarse Aggregate 20mm", "Aggregate", "cft", 42), ("Fly Ash Bricks", "Masonry", "nos", 7.5),
        ("Shuttering Plywood 12mm", "Formwork", "sheet", 1450), ("Binding Wire", "Steel", "kg", 78),
    ]:
        mats[name] = insert(conn, "materials", {"name": name, "category": cat, "unit": unit, "default_rate": rate})
    for pid, name, qty, min_l in [
        (p1, "OPC 53 Cement", 420, 200), (p1, "TMT Steel 12mm", 5200, 2000), (p1, "TMT Steel 16mm", 3100, 1500),
        (p1, "River Sand", 900, 500), (p1, "Shuttering Plywood 12mm", 34, 50), (p1, "Binding Wire", 120, 50),
        (p2, "OPC 53 Cement", 150, 100), (p2, "TMT Steel 16mm", 800, 1000),
    ]:
        insert(conn, "stock", {"project_id": pid, "material_id": mats[name], "qty": qty, "min_level": min_l})

    # ---- request -> PO -> GRN chain ----
    mr1 = insert(conn, "material_requests", {"request_no": "MR-0001", "project_id": p1,
        "requested_by": users["site"], "required_date": d(5), "status": "ordered",
        "notes": "Steel for floor 4 slab casting", "decision_by": users["pm"], "decision_at": d(-3)})
    insert(conn, "material_request_items", {"request_id": mr1, "material_id": mats["TMT Steel 12mm"], "qty": 3000})
    insert(conn, "material_request_items", {"request_id": mr1, "material_id": mats["TMT Steel 16mm"], "qty": 2000})
    mr2 = insert(conn, "material_requests", {"request_no": "MR-0002", "project_id": p1,
        "requested_by": users["site"], "required_date": d(4), "status": "pending",
        "notes": "Shuttering plywood urgently needed — see issue on floor 3"})
    insert(conn, "material_request_items", {"request_id": mr2, "material_id": mats["Shuttering Plywood 12mm"], "qty": 60})

    po1 = insert(conn, "purchase_orders", {"po_number": "PO-0001", "project_id": p1, "vendor_id": v_steel,
        "request_id": mr1, "status": "partially_received", "order_date": d(-2), "expected_date": d(5),
        "created_by": users["pm"], "notes": "Deliver to Block A gate 2"})
    poi1 = insert(conn, "po_items", {"po_id": po1, "material_id": mats["TMT Steel 12mm"], "qty": 3000, "rate": 62, "received_qty": 2000})
    poi2 = insert(conn, "po_items", {"po_id": po1, "material_id": mats["TMT Steel 16mm"], "qty": 2000, "rate": 61.5, "received_qty": 0})
    g1 = insert(conn, "grns", {"grn_number": "GRN-0001", "po_id": po1, "project_id": p1,
        "received_date": d(-1), "vehicle_no": "HR55 AB 1234", "received_by": users["store"]})
    insert(conn, "grn_items", {"grn_id": g1, "po_item_id": poi1, "material_id": mats["TMT Steel 12mm"], "qty_received": 2000})

    for days_ago, mat, qty in [(2, "OPC 53 Cement", 60), (2, "TMT Steel 12mm", 800), (1, "River Sand", 120),
                               (1, "OPC 53 Cement", 45), (0, "TMT Steel 12mm", 400)]:
        insert(conn, "material_usage", {"project_id": p1, "task_id": t_ids["RCC frame — floors 1-4"],
            "material_id": mats[mat], "usage_date": d(-days_ago), "qty": qty, "logged_by": users["site"]})

    # ---- labour & attendance (last 7 days) ----
    lab_ids = []
    for name, cat, vid, base, ot in [
        ("Mohan Lal", "skilled", v_labour, 950, 120), ("Rajesh Kumar", "skilled", v_labour, 950, 120),
        ("Sita Devi", "semi_skilled", v_labour, 700, 90), ("Gopal Das", "semi_skilled", v_labour, 700, 90),
        ("Ramu Yadav", "unskilled", v_labour, 550, 70), ("Shyam Pal", "unskilled", v_labour, 550, 70),
        ("Anil Supervisor", "staff", None, 1200, 0),
    ]:
        lab_ids.append(insert(conn, "labourers", {"project_id": p1, "name": name, "category": cat,
                                                  "vendor_id": vid, "base_rate": base, "ot_rate": ot}))
    for day in range(7, 0, -1):
        att_date = d(-day)
        if date.fromisoformat(att_date).weekday() == 6:  # Sunday off
            continue
        for idx, lid in enumerate(lab_ids):
            status = "absent" if (day + idx) % 9 == 0 else ("half_day" if (day + idx) % 7 == 0 else "present")
            ot = 2 if status == "present" and idx % 3 == 0 else 0
            insert(conn, "attendance", {"project_id": p1, "labourer_id": lid, "att_date": att_date,
                                        "status": status, "ot_hours": ot, "marked_by": users["site"]})

    # ---- progress logs ----
    for day, task, desc, qty, unit, count in [
        (3, "RCC frame — floors 1-4", "Column casting floor 3 grid A-D", 18, "columns", 22),
        (2, "RCC frame — floors 1-4", "Slab reinforcement floor 3 — 60% laid", 420, "sqm", 25),
        (1, "RCC frame — floors 1-4", "Slab reinforcement completed, shuttering checks", 700, "sqm", 24),
    ]:
        insert(conn, "progress_logs", {"project_id": p1, "task_id": t_ids[task], "log_date": d(-day),
            "work_description": desc, "quantity_done": qty, "unit": unit, "labour_count": count,
            "notes": "Weather clear", "issues_text": "Plywood shortage" if day == 1 else None,
            "created_by": users["site"]})

    # ---- work order, invoices, payments ----
    insert(conn, "work_orders", {"wo_number": "WO-0001", "project_id": p1, "vendor_id": v_labour,
        "title": "RCC labour contract — Block A", "amount": 3600000, "start_date": d(-60), "end_date": d(60),
        "status": "active", "created_by": users["pm"]})

    inv1 = insert(conn, "invoices", {"invoice_number": "SST/2026/104", "vendor_id": v_steel, "project_id": p1,
        "po_id": po1, "invoice_date": d(-50), "due_date": d(-5), "amount": 124000, "tax_amount": 22320,
        "total_amount": 146320, "status": "overdue", "created_by": users["accountant"],
        "notes": "First steel delivery"})
    inv2 = insert(conn, "invoices", {"invoice_number": "BMC/889", "vendor_id": v_cement, "project_id": p1,
        "invoice_date": d(-20), "due_date": d(10), "amount": 92400, "tax_amount": 16632,
        "total_amount": 109032, "status": "approved", "created_by": users["accountant"]})
    inv3 = insert(conn, "invoices", {"invoice_number": "KLC/W26", "vendor_id": v_labour, "project_id": p1,
        "invoice_date": d(-10), "due_date": d(5), "amount": 180000, "tax_amount": 0,
        "total_amount": 180000, "status": "paid", "created_by": users["accountant"],
        "notes": "Labour bill — fortnight"})
    insert(conn, "payments", {"payment_no": "PAY-0001", "invoice_id": inv3, "vendor_id": v_labour,
        "project_id": p1, "pay_date": d(-6), "amount": 180000, "mode": "bank",
        "reference": "NEFT-3341", "created_by": users["accountant"]})
    insert(conn, "payments", {"payment_no": "PAY-0002", "invoice_id": inv1, "vendor_id": v_steel,
        "project_id": p1, "pay_date": d(-2), "amount": 50000, "mode": "bank",
        "reference": "NEFT-3388", "notes": "Part payment", "created_by": users["accountant"]})

    # ---- equipment & checklist ----
    eq1 = insert(conn, "equipment", {"name": "Tower Crane TC-5013", "code": "EQ-001", "category": "Crane",
        "project_id": p1, "status": "in_use", "usage_hours": 512, "maintenance_interval_hours": 250,
        "hours_at_last_maintenance": 200, "last_maintenance_date": d(-25)})
    insert(conn, "equipment", {"name": "Concrete Mixer 10/7", "code": "EQ-002", "category": "Mixer",
        "project_id": p1, "status": "in_use", "usage_hours": 130, "maintenance_interval_hours": 200,
        "hours_at_last_maintenance": 0})
    insert(conn, "equipment_logs", {"equipment_id": eq1, "project_id": p1, "log_date": d(-1),
        "hours_used": 8, "logged_by": users["site"]})

    cl = insert(conn, "checklists", {"project_id": p1, "ctype": "safety", "title": "Weekly safety walk — floor 3",
        "check_date": d(-2), "inspector_id": users["site"], "status": "failed",
        "notes": "Two harness violations found"})
    for item, outcome, remark in [
        ("Guard rails on slab edges", "pass", None), ("Workers wearing helmets", "pass", None),
        ("Safety harness above 2m", "fail", "2 workers without harness on grid C"),
        ("Electrical DB boards locked", "pass", None), ("Housekeeping / debris cleared", "fail", "Debris on staircase"),
    ]:
        insert(conn, "checklist_items", {"checklist_id": cl, "item": item, "outcome": outcome, "remarks": remark})

    # ---- comments / activity / notifications ----
    insert(conn, "comments", {"entity_type": "issue", "entity_id": i1, "user_id": users["pm"],
        "body": "Raised MR-0002 for 60 sheets. Vendor promises delivery in 3 days."})
    insert(conn, "comments", {"entity_type": "material_request", "entity_id": mr2, "user_id": users["site"],
        "body": "Please expedite — slab casting blocked without shuttering."})
    insert(conn, "activity", {"project_id": p1, "user_id": users["site"], "action": "logged progress",
        "entity_type": "progress_log", "detail": "Slab reinforcement completed"})
    insert(conn, "notifications", {"user_id": users["pm"], "ntype": "material_request",
        "title": "New material request MR-0002", "body": "Shuttering plywood, required in 4 days",
        "entity_type": "material_request", "entity_id": mr2})

    conn.commit()
    conn.close()
    print("Seeded demo data. Logins (password for all: %s)" % PASSWORD)
    for label, email in [("Owner", "owner@sitepilot.test"), ("Project Manager", "pm@sitepilot.test"),
                         ("Site Engineer", "site@sitepilot.test"), ("Storekeeper", "store@sitepilot.test"),
                         ("Accountant", "accounts@sitepilot.test"), ("Vendor", "vendor@sitepilot.test")]:
        print(f"  {label:16s} {email}")


if __name__ == "__main__":
    seed()
