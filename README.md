# Buq'ata Digital Processes

**מערכת רכש והגשות דיגיטלית — מועצה מקומית בוקעאתא**

A municipal platform for processes that need publication, sealed submissions,
controlled opening, decisions, protocols and a complete audit trail. One engine,
several process types: requests for quotation today; formal tenders,
scholarships and calls for proposals on the same foundation next.

Four principles run through every screen and every rule:
**Efficiency · Transparency · Equal opportunity · Security**
(יעילות · שקיפות · שוויון הזדמנויות · אבטחה).

## What works today (MVP, phases 1–5)

* **Supplier registry** — self-registration, multilingual category tree stored
  in the database, certificates with expiry, profile and category changes.
* **Request for quotation, end to end** — create → live "N suppliers match"
  preview → publish → **automatic distribution** (editable with a recorded reason) to every
  matching active supplier (immutable, hashed snapshot; late registrants get a
  supplemental snapshot) → e-mail + in-app invitations → sealed submission with
  receipt → deadline → **opening of all offers together** under an opening
  policy → comparison table (no automatic winner) → recorded decision →
  printable protocol (he/ar/en) → close.
* **Secure vault** — per-offer AES-256-GCM keys wrapped with a per-process RSA
  public key; the private key exists only as KMS ciphertext until opening.
  SHA-256 verification of every file at opening and download.
* **Opening-policy engine** — time, network, device, identity/MFA, role and
  M-of-N approval rules, with typed security events (`EARLY_OPEN_ATTEMPT`, …).
* **Hash-chained audit trail** with database append-only triggers and
  `verify_audit_chain()`.
* **Fairness report** — eligible / notified / delivered / failed / opened /
  started / submitted, per supplier, with match reasons.
* **RBAC with separation of duties** — administrators cannot read offers and
  cannot grant themselves roles.
* **Trilingual, RTL-first UI** — Hebrew and Arabic (RTL), English (LTR).

Planned next: formal tenders with multi-official approval and MFA step-up
(phase 7), scholarships (phase 8), KPI dashboard (phase 9). See
`docs/ARCHITECTURE.md` §9.

## Repository

```
backend/     FastAPI, SQLAlchemy 2, Alembic — engines, services, API, tests
frontend/    Next.js (static export), TypeScript, Tailwind — he/ar/en
deploy/      setup-server.sh (one-time), systemd units, nginx site for tender.kortexd.com
docs/        ARCHITECTURE, SECURITY_MODEL, DATABASE_SCHEMA, WORKFLOWS, RBAC,
             API_DESIGN, DEMO_GUIDE, ADMIN_GUIDE
deploy-*.ps1 deploy scripts (frontend, backend, all) — see DEPLOY_SERVER.md
```

## Run locally

Requirements: Python ≥ 3.10, Node ≥ 20. No database server needed — local
development uses SQLite, local-disk storage and a generated development key.

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # Linux/macOS: .venv/bin/pip
cp .env.example .env
.venv/Scripts/python -m app.cli dev-setup             # migrate + baseline + demo data
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm install
npm run dev            # http://localhost:3000, proxies /api to :8000
```

Optional background worker (e-mail delivery with retries, deadline events):
`python -m app.worker`. Demo e-mails are written to `backend/var/outbox/`.

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest                        # SQLite
TEST_DATABASE_URL=postgresql+psycopg://user:pw@host/db .venv/Scripts/python -m pytest   # PostgreSQL
```

The suite covers the critical rules: no manual exclusion of suppliers, complete
and correct distribution, offers unreadable before opening, administrators
unable to bypass the seal, no opening before the deadline, all offers opened
together with notifications to every submitter, tampered files blocked,
tampered audit records detected, M-of-N and network policies, and notification
failures not rolling back submissions.

## Deploy

`.\deploy-all-to-server.ps1` (or `npm run deploy:server:all` from `frontend/`) — see `DEPLOY_SERVER.md`.
