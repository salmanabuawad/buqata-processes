# Architecture

Buq'ata Digital Processes is one municipal platform that runs several controlled
digital processes — quotation requests, formal tenders, scholarships, and later
calls for proposals, grants and recruitment — on a shared engine.

The guiding rule: **a process type is configuration plus a small amount of
process-specific behaviour, running on shared services.** RFQ, Tender and
Scholarship are not three applications.

## 1. System context

```
            Suppliers / Applicants                Municipal staff
                     │                                  │
                     ▼                                  ▼
              ┌───────────────────── nginx (TLS, rate limits, headers) ─────────┐
              │  static Next.js export (/)          FastAPI (/api/v1)           │
              └───────────────────────────────────────────┬────────────────────┘
                                                          │
         ┌──────────────┬──────────────┬─────────────────┼───────────────┬──────────────┐
         ▼              ▼              ▼                 ▼               ▼              ▼
    PostgreSQL     Object storage   Key management   Notification     Identity      Device / network
    (state, audit)  (S3 / MinIO /   (Local KMS dev,   worker (outbox,   provider      posture provider
                    local disk)     AWS/Azure KMS,    Redis wake-up,    (local dev,   (mock dev,
                                    HSM)              SMTP)             Entra OIDC)   Intune)
```

* **Frontend** — Next.js (App Router, TypeScript, Tailwind), built as a static
  export and served by nginx. It holds no secrets and makes no security
  decisions; every guard it shows is repeated server-side.
* **API** — FastAPI (Python ≥ 3.10), SQLAlchemy 2, Alembic, Pydantic v2.
  The spec preferred NestJS; the repository owner chose FastAPI to match the
  council's other systems (Buq'ata portal, ScholarFlow) and their deployment
  tooling.
* **Worker** — `python -m app.worker`. Drains the notification outbox, retries
  failed deliveries, and detects deadlines (`DEADLINE_REACHED`).
* **PostgreSQL** in every deployed environment. SQLite is supported for local
  development and the test suite only.
* **Redis** is optional: when `REDIS_URL` is set the API pushes a wake-up signal
  so the worker delivers immediately; without it the worker polls.

## 2. Layering

```
api/            HTTP only: parse, authenticate, call a service, shape the response
  │
services/       Shared platform services (below). Own transactions and audit.
  │
processes/      Process definitions: RFQProcess, TenderProcess, ScholarshipProcess,
  │             CallForProposalProcess (prepared). Declarative rules + hooks.
  │
engines/        Pure logic with no I/O: opening policies, eligibility, scoring,
  │             category matching, timeline derivation, audit hashing.
  │
adapters/       Replaceable integrations behind Protocols: storage, KMS, mail,
                identity provider, device posture, malware scanner, clock.
```

Routers never touch the database directly for business rules, and never decide
authorization by themselves — they call `AuthorizationService.require(...)`,
which is the single place a permission is checked.

## 3. Shared services

| Service | Responsibility |
|---|---|
| `IdentityService` | Local accounts (dev) or OIDC claims (Entra ID); sessions; the `AuthContext` (user, roles, MFA, network, device). |
| `AuthorizationService` | Role → permission resolution, per-process participation (need-to-know), explicit content grants. |
| `ProcessService` | Create, edit draft, publish, cancel. Delegates rules to the process definition. |
| `WorkflowService` | Validated state transitions per process type; derives the timeline. |
| `CategoryService` | Multilingual category tree stored in the database. |
| `DistributionService` | Automatic, non-editable supplier matching and the immutable recipient snapshot. |
| `DocumentService` | Upload validation (size, MIME, magic bytes, malware scan hook), SHA-256, storage references. |
| `SecureVaultService` | Envelope encryption of sealed submissions; releases keys only through an approved opening. |
| `OpeningService` | Evaluates the `OpeningPolicy`, gathers approvals (M-of-N), opens the vault, raises security events. |
| `NotificationService` | Transactional outbox, multilingual templates, email + in-app channels, retries. |
| `AuditService` | Append-only, hash-chained audit log; `verify_audit_chain()`. |
| `CommitteeService` | Committees, members, conflict-of-interest declarations, assignments. |
| `ProtocolService` | Renders printable HTML protocols from process data and audit references; stores their hash. |
| `EligibilityService` | Rule evaluation returning ELIGIBLE / POTENTIALLY_ELIGIBLE / MISSING_INFORMATION / NOT_ELIGIBLE with per-rule explanations. |
| `ReportingService` | Dashboards, fairness report, KPIs with measured / calculated / estimated labels. |

## 4. Process definitions

A process type is a `ProcessDefinition` subclass registered in
`app/processes/registry.py`. It declares:

| Aspect | Declared as |
|---|---|
| Who may create | a permission (`process.create.rfq`, …) |
| Who may submit | a submitter kind (`supplier` / `applicant`) and an admission rule (e.g. "in the distribution snapshot") |
| Required fields | a Pydantic model for process details and one for the submission payload |
| Required documents | a list of `DocumentRequirement` (kind, required, allowed types, max size) — extendable per process |
| Publication | a distribution strategy (`category_match` for RFQ, `public` for tenders and scholarships) |
| Eligibility | an eligibility rule set (scholarships; suppliers' certificates later) |
| Deadline | whether late submissions are refused, and the exception workflow if any |
| Sealing | whether submissions go to the vault (RFQ and Tender: yes) |
| Opening | the default `OpeningPolicy` (copied onto the process so it can be tuned per process) |
| Review / scoring | comparison columns (RFQ), scoring criteria (Tender, Scholarship) |
| Decision | decision options and who may record them — never automatic |
| Notifications | which events notify whom |
| Timeline | the ordered stages shown to users |
| Protocols | the protocol templates it produces |

**Behaviour lives in code; parameters live in the database.** The definition
supplies defaults (for example "Tender: 3 of 5 approvals, municipal network,
MFA"). Those defaults are copied into the process's own `opening_policies` row
when the process is created, where an authorized manager can tune them before
publication. After publication the policy is frozen with the process version.
This keeps municipal/legal policy (how many approvers? which network?) separate
from technical enforcement (the vault will not open until whatever was
configured is satisfied).

Adding a process type (e.g. `CallForProposalProcess`) means: a definition
class, its Pydantic models, its templates and timeline, a registry entry and a
`process_types` seed row. No shared service changes.

## 5. Key flows (summary — details in WORKFLOWS.md)

* **Publish RFQ** → freeze version → create vault → match suppliers → snapshot
  recipients → enqueue notifications → audit. One database transaction; mail is
  delivered afterwards by the worker, so a mail failure cannot undo publication.
* **Submit** → validate → encrypt payload + files with a fresh data key → wrap
  the data key with the vault public key → store ciphertext → receipt with hashes.
* **Open** → evaluate policy (time, network, device, identity, role, approvals)
  → unwrap the vault private key via KMS → verify every file hash → mark all
  submissions opened together → `VAULT_OPENED` → notify submitters.

## 6. Time

All business time comes from `app.core.clock.now()` (UTC). Tests freeze it.
Deadlines are enforced by comparing server time only; the client clock is never
trusted. Times are stored as UTC and displayed in `Asia/Jerusalem`.

## 7. Internationalisation

Hebrew and Arabic are primary (RTL), English secondary (LTR). UI strings live in
`frontend/src/i18n/messages/{he,ar,en}.json`; switching language flips `dir` on
`<html>` and all layout uses logical properties (`ms-`, `pe-`, `start`, `end`).
Category names, notification templates and protocol templates are stored or
authored in all three languages. The API returns error **codes**; the frontend
translates them.

## 8. Deployment shapes

* **Local development** — SQLite, local-disk storage, local KMS key file, mail
  written to `var/outbox/*.eml`, no Redis. `python -m app.cli dev-setup` creates
  and seeds everything.
* **Docker Compose** — PostgreSQL, Redis, MinIO, API, worker, frontend. For
  parity testing where Docker is available.
* **Ubuntu host (tender.kortexd.com)** — nginx serving the static export and
  proxying `/api/` to uvicorn on loopback; PostgreSQL 16; systemd units for API
  and worker; secrets in `/opt/buqata-processes/.env` (mode 600). See
  `DEPLOYMENT.md`.

## 9. Delivery phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Architecture documents | done |
| 2 | Skeleton: backend, frontend, migrations, tests, compose | done (compose file written, not yet run — no Docker on the dev machine) |
| 3 | Identity, RBAC, organizations, audit foundation | done (local accounts; Entra ID OIDC adapter not yet written) |
| 4 | Supplier registry, categories, supplier documents | done |
| 5 | RFQ end to end (incl. vault sealing needed by RFQ) | done |
| 6 | Vault hardening, full OpeningPolicy set | engine complete (all six rules, tested); managed KMS adapter and device-posture provider pending |
| 7 | Formal tender, M-of-N, device policy, MFA step-up | planned — approval flow exists in the opening service |
| 8 | Scholarships | planned |
| 9 | Dashboards, KPIs, reports | partial — staff dashboard and fairness report; KPI module planned |
| 10 | Security testing, demo polish | ongoing |

The table is kept current as phases land.
