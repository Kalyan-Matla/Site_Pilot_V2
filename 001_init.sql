-- Postgres-dialect mirror of app/migrations/001_init.sql for hosted deployment
-- (Neon / any Postgres via DATABASE_URL). Same tables, checks, and indexes;
-- only the id/REAL/timestamp/citext syntax differs from the SQLite version.

CREATE EXTENSION IF NOT EXISTS citext;

-- Reproduces sqlite's datetime('now') format (UTC, space-separated, no tz
-- suffix) so every created_at/timestamp column behaves identically to local
-- dev and nothing downstream (Python slicing, JS date parsing) needs to change.
CREATE OR REPLACE FUNCTION now_utc_text() RETURNS text AS $$
  SELECT to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24:MI:SS')
$$ LANGUAGE sql STABLE;

CREATE TABLE vendors (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  contact_person TEXT,
  phone TEXT,
  email TEXT,
  gst_no TEXT,
  address TEXT,
  vendor_type TEXT NOT NULL DEFAULT 'material' CHECK (vendor_type IN ('material','labour','service','equipment')),
  payment_terms TEXT,
  credit_period_days INTEGER NOT NULL DEFAULT 45,
  credit_limit DOUBLE PRECISION NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  email CITEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('owner','pm','site','store','accountant','vendor')),
  phone TEXT,
  vendor_id INTEGER REFERENCES vendors(id),
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE projects (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  client_name TEXT,
  location TEXT,
  start_date TEXT,
  end_date TEXT,
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','active','on_hold','completed','cancelled')),
  description TEXT,
  budget DOUBLE PRECISION NOT NULL DEFAULT 0,
  contract_value DOUBLE PRECISION NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE project_members (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE (project_id, user_id)
);

CREATE TABLE tasks (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  is_milestone INTEGER NOT NULL DEFAULT 0,
  planned_start TEXT,
  planned_end TEXT,
  actual_start TEXT,
  actual_end TEXT,
  status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','in_progress','done','blocked')),
  assignee_id INTEGER REFERENCES users(id),
  progress_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
  weight DOUBLE PRECISION NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE issues (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  description TEXT,
  severity TEXT NOT NULL DEFAULT 'medium' CHECK (severity IN ('low','medium','high','critical')),
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','resolved','closed')),
  raised_by INTEGER REFERENCES users(id),
  assigned_to INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT now_utc_text(),
  resolved_at TEXT
);

CREATE TABLE progress_logs (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
  log_date TEXT NOT NULL,
  work_description TEXT,
  quantity_done DOUBLE PRECISION,
  unit TEXT,
  labour_count INTEGER,
  notes TEXT,
  issues_text TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE progress_photos (
  id SERIAL PRIMARY KEY,
  progress_log_id INTEGER NOT NULL REFERENCES progress_logs(id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  original_name TEXT,
  uploaded_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE documents (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
  issue_id INTEGER REFERENCES issues(id) ON DELETE SET NULL,
  category TEXT NOT NULL DEFAULT 'other' CHECK (category IN ('drawing','boq','schedule','contract','approval','other')),
  title TEXT NOT NULL,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE document_versions (
  id SERIAL PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version_no INTEGER NOT NULL,
  file_path TEXT NOT NULL,
  original_name TEXT,
  notes TEXT,
  uploaded_by INTEGER REFERENCES users(id),
  uploaded_at TEXT NOT NULL DEFAULT now_utc_text(),
  UNIQUE (document_id, version_no)
);

CREATE TABLE materials (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  category TEXT,
  unit TEXT NOT NULL,
  default_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE stock (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  material_id INTEGER NOT NULL REFERENCES materials(id),
  qty DOUBLE PRECISION NOT NULL DEFAULT 0,
  min_level DOUBLE PRECISION NOT NULL DEFAULT 0,
  reserved_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
  UNIQUE (project_id, material_id)
);

CREATE TABLE material_requests (
  id SERIAL PRIMARY KEY,
  request_no TEXT NOT NULL UNIQUE,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  requested_by INTEGER REFERENCES users(id),
  required_date TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','ordered','fulfilled','cancelled')),
  notes TEXT,
  decision_by INTEGER REFERENCES users(id),
  decision_at TEXT,
  decision_notes TEXT,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE material_request_items (
  id SERIAL PRIMARY KEY,
  request_id INTEGER NOT NULL REFERENCES material_requests(id) ON DELETE CASCADE,
  material_id INTEGER NOT NULL REFERENCES materials(id),
  qty DOUBLE PRECISION NOT NULL,
  remarks TEXT
);

CREATE TABLE purchase_orders (
  id SERIAL PRIMARY KEY,
  po_number TEXT NOT NULL UNIQUE,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  vendor_id INTEGER NOT NULL REFERENCES vendors(id),
  request_id INTEGER REFERENCES material_requests(id),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','partially_received','received','closed','cancelled')),
  order_date TEXT,
  expected_date TEXT,
  notes TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE po_items (
  id SERIAL PRIMARY KEY,
  po_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
  material_id INTEGER NOT NULL REFERENCES materials(id),
  qty DOUBLE PRECISION NOT NULL,
  rate DOUBLE PRECISION NOT NULL DEFAULT 0,
  received_qty DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE TABLE grns (
  id SERIAL PRIMARY KEY,
  grn_number TEXT NOT NULL UNIQUE,
  po_id INTEGER NOT NULL REFERENCES purchase_orders(id),
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  received_date TEXT NOT NULL,
  vehicle_no TEXT,
  notes TEXT,
  received_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE grn_items (
  id SERIAL PRIMARY KEY,
  grn_id INTEGER NOT NULL REFERENCES grns(id) ON DELETE CASCADE,
  po_item_id INTEGER NOT NULL REFERENCES po_items(id),
  material_id INTEGER NOT NULL REFERENCES materials(id),
  qty_received DOUBLE PRECISION NOT NULL,
  remarks TEXT
);

CREATE TABLE material_usage (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
  material_id INTEGER NOT NULL REFERENCES materials(id),
  usage_date TEXT NOT NULL,
  qty DOUBLE PRECISION NOT NULL,
  notes TEXT,
  logged_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE labourers (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'unskilled' CHECK (category IN ('skilled','semi_skilled','unskilled','staff')),
  vendor_id INTEGER REFERENCES vendors(id),
  base_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
  ot_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE attendance (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  labourer_id INTEGER NOT NULL REFERENCES labourers(id) ON DELETE CASCADE,
  att_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'present' CHECK (status IN ('present','absent','half_day')),
  ot_hours DOUBLE PRECISION NOT NULL DEFAULT 0,
  marked_by INTEGER REFERENCES users(id),
  UNIQUE (labourer_id, att_date)
);

CREATE TABLE work_orders (
  id SERIAL PRIMARY KEY,
  wo_number TEXT NOT NULL UNIQUE,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  vendor_id INTEGER NOT NULL REFERENCES vendors(id),
  title TEXT NOT NULL,
  description TEXT,
  amount DOUBLE PRECISION NOT NULL DEFAULT 0,
  start_date TEXT,
  end_date TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','completed','cancelled')),
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE invoices (
  id SERIAL PRIMARY KEY,
  invoice_number TEXT NOT NULL,
  vendor_id INTEGER NOT NULL REFERENCES vendors(id),
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  po_id INTEGER REFERENCES purchase_orders(id),
  wo_id INTEGER REFERENCES work_orders(id),
  invoice_date TEXT NOT NULL,
  due_date TEXT NOT NULL,
  amount DOUBLE PRECISION NOT NULL,
  tax_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
  total_amount DOUBLE PRECISION NOT NULL,
  status TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','under_review','approved','paid','overdue','rejected')),
  notes TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT now_utc_text(),
  UNIQUE (vendor_id, invoice_number)
);

CREATE TABLE payments (
  id SERIAL PRIMARY KEY,
  payment_no TEXT NOT NULL UNIQUE,
  invoice_id INTEGER REFERENCES invoices(id),
  vendor_id INTEGER NOT NULL REFERENCES vendors(id),
  project_id INTEGER REFERENCES projects(id),
  pay_date TEXT NOT NULL,
  amount DOUBLE PRECISION NOT NULL,
  mode TEXT NOT NULL DEFAULT 'bank' CHECK (mode IN ('cash','bank','upi','cheque')),
  reference TEXT,
  notes TEXT,
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE comments (
  id SERIAL PRIMARY KEY,
  entity_type TEXT NOT NULL CHECK (entity_type IN ('task','issue','material_request','purchase_order','invoice','project','document','equipment','checklist')),
  entity_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE notifications (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ntype TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT,
  entity_type TEXT,
  entity_id INTEGER,
  is_read INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE activity (
  id SERIAL PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
  user_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL,
  entity_type TEXT,
  entity_id INTEGER,
  detail TEXT,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE audit_log (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id INTEGER,
  before_json TEXT,
  after_json TEXT,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE equipment (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  code TEXT UNIQUE,
  category TEXT,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','in_use','maintenance','retired')),
  usage_hours DOUBLE PRECISION NOT NULL DEFAULT 0,
  maintenance_interval_hours DOUBLE PRECISION NOT NULL DEFAULT 0,
  hours_at_last_maintenance DOUBLE PRECISION NOT NULL DEFAULT 0,
  last_maintenance_date TEXT,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE equipment_logs (
  id SERIAL PRIMARY KEY,
  equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
  project_id INTEGER REFERENCES projects(id),
  log_date TEXT NOT NULL,
  hours_used DOUBLE PRECISION NOT NULL DEFAULT 0,
  is_maintenance INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  logged_by INTEGER REFERENCES users(id)
);

CREATE TABLE checklists (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  ctype TEXT NOT NULL DEFAULT 'safety' CHECK (ctype IN ('safety','quality')),
  title TEXT NOT NULL,
  check_date TEXT NOT NULL,
  inspector_id INTEGER REFERENCES users(id),
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','passed','failed','closed')),
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT now_utc_text()
);

CREATE TABLE checklist_items (
  id SERIAL PRIMARY KEY,
  checklist_id INTEGER NOT NULL REFERENCES checklists(id) ON DELETE CASCADE,
  item TEXT NOT NULL,
  outcome TEXT NOT NULL DEFAULT 'na' CHECK (outcome IN ('pass','fail','na')),
  remarks TEXT,
  photo_path TEXT
);

CREATE INDEX idx_tasks_project ON tasks(project_id);
CREATE INDEX idx_tasks_assignee ON tasks(assignee_id);
CREATE INDEX idx_issues_project ON issues(project_id, status);
CREATE INDEX idx_progress_project_date ON progress_logs(project_id, log_date);
CREATE INDEX idx_documents_project ON documents(project_id);
CREATE INDEX idx_stock_project ON stock(project_id);
CREATE INDEX idx_mr_project_status ON material_requests(project_id, status);
CREATE INDEX idx_po_project ON purchase_orders(project_id);
CREATE INDEX idx_po_vendor ON purchase_orders(vendor_id);
CREATE INDEX idx_grn_po ON grns(po_id);
CREATE INDEX idx_usage_project_date ON material_usage(project_id, usage_date);
CREATE INDEX idx_labourers_project ON labourers(project_id);
CREATE INDEX idx_attendance_project_date ON attendance(project_id, att_date);
CREATE INDEX idx_invoices_vendor ON invoices(vendor_id, status);
CREATE INDEX idx_invoices_project ON invoices(project_id);
CREATE INDEX idx_invoices_due ON invoices(due_date);
CREATE INDEX idx_payments_vendor ON payments(vendor_id);
CREATE INDEX idx_payments_invoice ON payments(invoice_id);
CREATE INDEX idx_comments_entity ON comments(entity_type, entity_id);
CREATE INDEX idx_notifications_user ON notifications(user_id, is_read);
CREATE INDEX idx_activity_project ON activity(project_id, created_at);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
