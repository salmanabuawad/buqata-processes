# Current state — September 2026

Inventory of the repository before the "Smart Municipal Processes Platform"
work (master prompt: RFQ + Tender + Scholarship on one engine). It records
what exists, what is missing, and what to reuse or change. Verified by reading
the code and running it, not only the other documents — where those documents
describe something the code does not do, this file says so.

## 1. How it was checked

| Check | Result |
|---|---|
| Backend test suite (SQLite, Python 3.14 venv) | 39 passed, 1 deprecation warning (Starlette `httpx` test client) |
| Frontend `tsc --noEmit` | clean |
| Frontend `next build` (static export) | 16 static routes, clean |
| i18n key parity he / ar / en | 655 keys each, identical |
| `app.cli dev-setup` on a fresh SQLite database | migrations, baseline and demo seed succeed (45 suppliers, 6 processes) |
| API smoke run (uvicorn) | `/health`, `/process-types`, `/categories`, demo sign-in, `/dashboard/staff`, `/processes` respond correctly |
| Test suite on PostgreSQL / Python 3.10 | **not run** in this pass (no local PostgreSQL); required before deploy |

## 2. Stack (keep it)

| Layer | Technology | Notes |
|---|---|---|
| Frontend | Next.js 16.3 (App Router), React 19.2, TypeScript, Tailwind 4, lucide-react | Static export served by nginx; no dynamic routes (`?id=`), trailing slashes |
| Backend | FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 | Python ≥ 3.10 (host runs 3.10) |
| Database | PostgreSQL (host), SQLite (dev/tests only) | 2 migrations: `0001_initial_schema`, `0002_rfq_flexibility` |
| Worker | `python -m app.worker` | Notification outbox, retries, `DEADLINE_REACHED` |
| Crypto | AES-256-GCM per submission version, RSA-OAEP vault key per process, KMS wrap | `LocalKms` only; refuses production |
| Deployment | nginx + systemd on Ubuntu (`tender.kortexd.com`) | **No Docker, by decision** (`CLAUDE.md`, `DEPLOY_SERVER.md`). The master prompt's "inspect Docker" step has nothing to inspect; none should be added |

## 3. Architecture as built

```
api/         auth, catalog (meta, categories, admin), processes, suppliers, platform (notifications, audit, dashboard)
services/    processes (+ workflow), distribution, submissions, vault, opening, evaluation,
             protocols, notifications, audit, authorization, identity, suppliers, categories,
             documents, reporting, admin
processes/   base.ProcessDefinition, rfq.RFQProcess, registry (+ PLANNED_TYPES)
engines/     matching (category branches), opening_policy (6 rules)
adapters/    kms, mail, storage, scanning
models/      identity, suppliers, processes, platform
```

The master prompt's "Process Engine" already exists in this shape: shared
services + a `ProcessDefinition` per type, registered in
`app/processes/registry.py`. Mapping of the prompt's concepts:

| Prompt concept | Where it lives | State |
|---|---|---|
| Process | `models.Process` | done |
| ProcessType | `models.ProcessType` + `ProcessDefinition` subclass | done (only `rfq` implemented) |
| ProcessVersion | `models.ProcessVersion` (frozen snapshot + SHA-256 at publish) | done |
| Workflow | `services/processes.py` `TRANSITIONS`, `phase()`, `timeline()` | done, one state machine for all types |
| Submission | `Submission` / `SubmissionVersion` / `SubmissionDocument` | done for suppliers; `applicant_user_id` column exists but unused |
| Document | `StoredFile`, `ProcessDocument`, `SupplierDocument`, `SubmissionDocument` | done |
| Deadline | `Process.submission_deadline`, server-time checks, worker event | done; no deadline-exception workflow |
| OpeningPolicy | `OpeningPolicyRecord` + `engines/opening_policy.py` (time, network, device, identity, role, multi-approval) | engine done and tested |
| Committee | — | **missing** (only roles `tender_committee`, `scholarship_committee` and participation value `COMMITTEE`) |
| Decision | `models.Decision` | done for RFQ (AWARD / NO_AWARD, one per process) |
| Protocol | `models.Protocol`, `services/protocols.py`, `templates/protocol.html` | done for RFQ (he/ar/en, hash + audit head) |
| Notification | `Notification` + `NotificationDelivery` outbox, templates in 3 languages | done (EMAIL + IN_APP; SMS/WhatsApp slots) |
| AuditEvent | hash-chained, DB triggers block UPDATE/DELETE, `verify_audit_chain()` | done |

## 4. Functionality that works today

* **Identity & RBAC** — local accounts, opaque hashed session cookies, CSRF
  double-submit, login rate limit, role → permission map in code
  (`core/rbac.py`, 8 roles, 28 permissions), per-process participation
  (need-to-know), admin cannot grant roles to self, demo sign-in only when
  `DEMO_MODE` is on.
* **Supplier registry** — self-registration (creates user + supplier + contact
  + categories), profile edit, category change (triggers supplemental
  invitations), certificate upload with issue/expiry dates, staff search by
  text/status/category subtree, staff status change (ACTIVE / INACTIVE /
  SUSPENDED, reasoned, audited).
* **Category engine** — hierarchical, trilingual, materialised paths, admin
  create/rename/reorder/deactivate, supplier counts; seeded with the tree in
  `seed/baseline.py` (IT → Computers → Desktop / Laptops / Tablets, electricity,
  maintenance, construction, …). Branch matching: exact, supplier broader,
  supplier narrower; optional service regions.
* **RFQ end to end** — draft → live match preview → publish (frozen version,
  vault, INITIAL distribution snapshot, invitations) → manual add/remove with
  reason (MANUAL snapshot / `removed_at`) → sealed submission with receipt and
  versions → opening per `opening_mode` (`visible`, `sealed_anytime`,
  `sealed_after_deadline`) → comparison (no ranking) → reasoned decision →
  protocol → close. Fairness report per supplier.
* **Opening** — request + approvals, policy re-evaluated at the moment of
  opening, typed security events in their own transaction, oversight alerts,
  file hash verification.
* **Dashboard** — cards (active RFQs/tenders/scholarships, waiting for opening,
  waiting for my approval, submissions today, suppliers, expiring documents,
  security alerts), participation chart, status breakdown, e-mail delivery,
  recent activity.
* **UI** — trilingual he/ar/en with RTL/LTR switch on `<html dir>`, logical CSS,
  all strings in `frontend/src/i18n/messages/*.json`, responsive shell with
  sidebar, notification bell, audit viewer with chain verification, admin
  users and categories pages, supplier portal (opportunities, profile,
  opportunity/submission page).

## 5. Gap analysis against the master prompt

### 5.1 Sections 1–7

| § | Requirement | Status | Gap |
|---|---|---|---|
| 1 | Reusable engine, RFQ / Tender / Scholarship modules, no duplicated code | engine yes, RFQ only | `TenderProcess`, `ScholarshipProcess` definitions; shared services still assume "submitter = invited supplier" (see §6) |
| 2 | he / ar / en, RTL, translation files | done | Files live in `frontend/src/i18n/messages/` (not `locales/`) — keep the existing location |
| 3 | Sidebar: Dashboard, Processes, RFQs, Tenders, Scholarships, Suppliers, Committees, Documents, Notifications, Reports, Audit, Administration | partial | Have Dashboard, Processes, New process, Suppliers, Audit, Categories, Users. Missing: per-type lists (can be `/processes/?type=`), Committees, Documents, Notifications page, Reports, grouped Administration |
| 4 | Dashboard cards and charts | mostly | Cards exist (tenders/scholarships show 0). Missing charts: processes by type (data returned, not drawn), RFQs by category, scholarship applications, processing time. Dashboard queries hard-code `"rfq"` |
| 5 | "+ פתיחת הליך חדש" with type cards and per-type wizard | partial | Cards exist (RFQ active; tender, scholarship, call for proposals, support, recruitment disabled). Only an RFQ form; cards are hard-coded in the page rather than read from `/process-types`; the menu item requires `process.create.rfq` |
| 6 | Supplier registry fields, categories, documents, pages | mostly | All fields exist (`registered_at` = createdAt). Missing: supplier **document status** (only `expired` derived from date; no pending/approved/rejected review), staff **supplier details page** (API `GET /suppliers/{id}` exists, UI does not), staff edit of a supplier, supplier document download for staff |
| 7 | Hierarchical categories in the database, `parent_id`, management UI | done | Seeded tree matches the example (IT → Computers → Desktop / Laptops / Tablets, networking, printers, software, cyber; electricity, maintenance, AC, construction, engineering, transport, office, consulting, …). No re-parenting (move) or delete (deactivate only, which is the safe choice) |

### 5.2 Sections 8–53

| § | Requirement | Status | Gap |
|---|---|---|---|
| 8 | Employee cannot deselect matched suppliers; enforced server-side | **conflicts with current code** | See §10.1 — RFQ distribution is currently editable by design |
| 9 | 5-step RFQ wizard (basics, requirements, dates, matching, review) | partial | One-page form with live matching. Missing: stepper, publication date (publishes immediately), explicit delivery/warranty requirement fields (only free-text "additional requirements") |
| 10 | `SupplierMatchingService.findEligibleSuppliers`, per-supplier match record, immutable snapshot | done | `distribution.preview` + `engines/matching.py`; `DistributionRecipient.match_reason` stores supplier/process category and relation; `notified_at` = matchedAt; snapshots hashed; supplier category changes only add SUPPLEMENTAL snapshots |
| 11 | `RFQ_PUBLISHED` notification per supplier, he/ar templates with number, title, category, deadline, link | done under another name | Template is `RFQ_INVITATION` (he/ar/en). Check category is included when touching templates |
| 12 | Supplier portal: opportunities, closing soon, my submissions, profile, categories, documents, notifications | partial | Have opportunities list, profile (with categories and documents), opportunity/submission page, notification bell. Missing: closing-soon and my-submissions sections, notifications page |
| 13 | Submission fields, SHA-256 per file, receipt, SEALED, "ההצעה הוגשה וננעלה." | done | VAT computed server-side; receipt with hashes and salted payload hash |
| 14 | Before opening staff see "submitted: yes", time, submission ID — not content | **differs** | Staff currently see only the *count* before opening (stricter, `SECURITY_MODEL.md` §4). `visible` opening mode shows content immediately — see §10.2 |
| 15 | Lightweight RFQ opening after the deadline, confirmation, all together, `RFQ_OPENED` | done / **differs** | All-together opening done; event name is `VAULT_OPENED`. `sealed_anytime` allows opening before the deadline — see §10.2 |
| 16 | Comparison without winner, record decision with supplier, reason, notes, date | done | Notes and decision date are not separate fields (reason only; date = recorded time) |
| 17–18 | Tender sealed until authorized opening; `OpeningPolicyEngine` with `evaluate(context) → PolicyResult(passed, reason, metadata)` | engine done, tender missing | Engine returns PASS/FAIL/PENDING with reason and details — equivalent. `TenderProcess` not written |
| 19 | `allowedIpRanges`, never trust client IP headers blindly, proxy config documented | done | `client_ip` honours `X-Real-IP` only from `TRUSTED_PROXIES`; nginx sets it. VLAN/Entra/Intune are adapter slots |
| 20 | M-of-N with conditions panel and named approvers, LOCKED state | backend done, UI missing | Approval model and policy exist; tender page and designated-official naming (treasurer, legal advisor, chair) missing. MFA condition needs §6 TOTP work |
| 21 | `SecureVaultService`, envelope encryption, KMS-ready, key never beside data | done | Production KMS adapter not written (documented) |
| 22 | Re-verify policies, approvals, deadline, hashes at opening; `VAULT_OPENED` with participants, results, count | done | Verify metadata includes all listed items when building the tender page |
| 23 | Notify every submitter on opening, no competitor data, delivery status recorded | done | Wording for tenders to be added to templates |
| 24 | Security events + security dashboard | events done, dashboard partial | Card with 30-day critical count and audit filter by severity; no dedicated security view |
| 25–31 | Scholarships: program fields, applicant portal, 11 application states, eligibility engine, scoring engine, conflict of interest, privacy | **missing** | Only roles/permissions exist. Needs models, applicant registration, engines, committee, encrypted document handling |
| 32 | Central `DocumentService`, hash on upload, verify before sensitive download, block on mismatch | mostly | Upload validation + SHA-256 central; submission downloads verify and raise `FILE_INTEGRITY_FAILURE`. Plain (non-sealed) downloads do not re-verify; `StoredFile` has no `process_id`/`submission_id` columns (links live on the owning rows) |
| 33 | Hash-chained audit, `verifyAuditChain()`, audit page with filters: process, user, event type, date, security | mostly | Filters exist for process, event type, severity. Missing: user and date filters (API and UI), event-type picker in UI |
| 34 | Event-driven notifications, email + in-app, SMS/WhatsApp-ready, queue, retries, no rollback on failure | done | Outbox + worker + backoff; tested |
| 35 | Process detail page with header and type-relevant tabs | partial | Single RFQ page with sections, not tabs; must become a shared template with per-type tabs |
| 36 | Visual timeline per type | RFQ done | Tender and scholarship timelines come with their definitions |
| 37 | Protocols: RFQ opening/decision, tender opening/committee, scholarship committee/decision; print layout | RFQ done | Other four types missing |
| 38 | Fairness dashboard numbers | done | Eligible / notified / delivered / failed / opened / started / submitted |
| 39 | Innovation KPI dashboard with MEASURED / CALCULATED / ESTIMATED labels | **missing** | Only measured figures on the staff dashboard |
| 40–42 | Visual language, responsive, WCAG 2.1 AA | largely followed | Palette and principles match; skip link, focus styles, ARIA on shell. No systematic accessibility or viewport testing yet |
| 43 | Database entities | mostly | All procurement entities exist. Missing: committees, committee_members, scholarships, scholarship_applications, eligibility_rules/results, scoring_criteria, review_scores, conflict_declarations |
| 44 | Demo data: 30 suppliers, desktop RFQ 27 matched / 11 viewed / 6 submitted | partial | 45 suppliers and 6 RFQs incl. "רכישת 20 מחשבים נייחים"; exact target numbers not verified. Demo data exists only in local development (`DEMO_MODE`) |
| 45–46 | Demo tender 17/2026 (5 sealed, 2/3 approvals), demo scholarship (78 applications) | missing | Depend on phases 6–7 |
| 47 | Mandatory tests | RFQ/vault/audit covered | 39 tests cover exclusion refusal (tenders), completeness, snapshots, sealing, admin bypass, all-together opening, early opening, network, M-of-N, `VAULT_OPENED`, notifications, tampered file, tampered audit. Scholarship tests missing |
| 48 | Security baseline | done | RBAC, cookies, CSRF, rate limit, Pydantic `extra=forbid`, ORM, upload checks, headers, env secrets |
| 49–50 | Phased order; formatter, linter, typecheck, tests, build after each change | tooling partial | Typecheck, tests, build exist; no linter or formatter configured |
| 51 | Prohibitions | one conflict | "Let employee manually remove suppliers from RFQ distribution" — current code allows it with a reason (§10.1) |
| 52 | Definition of done, scenarios A–G | A–D work (with the §10 caveats) | E (tender), F (scholarship) missing; G works for RFQ |

## 6. Technical debt and doc/code drift

**Shared services that assume the RFQ shape** (these block Tender and
Scholarship and must be generalised through the definition, not by switching
on type keys):

* `submissions._recipient_or_403` / `authorization.supplier_recipient` /
  `can_view_process` — admission is "an active distribution recipient". Tenders
  need public admission for any active supplier; scholarships need applicants
  (`User.kind == "applicant"`, `Submission.applicant_user_id`). Needs an
  admission hook on `ProcessDefinition`.
* `Submission` unique constraint is `(process_id, supplier_id)`; applicants
  need `(process_id, applicant_user_id)`.
* `evaluation.record_decision` hard-codes AWARD / NO_AWARD and one decision per
  process. Scholarships decide per application (approve / reject / waitlist)
  with amounts.
* `reporting.staff_dashboard` filters `process_type == "rfq"` and counts types
  by literal keys.
* `POST /distribution/preview` requires `process.create.rfq`.
* `POST /processes/{id}/documents` accepts only `specification` / `attachment`.
* Supplier opportunities list only processes where the supplier is a
  recipient; public tenders will need a "public opportunities" listing.

**Documentation that describes things the code does not have:**

* `ARCHITECTURE.md` §3 lists `CommitteeService` and `EligibilityService`, and
  `WORKFLOWS.md` §4 says the `CallForProposalProcess` class "exists and is
  disabled". None of these exist in code; call for proposals is only an entry
  in `PLANNED_TYPES`.
* `SECURITY_MODEL.md` §5 mentions "local TOTP step-up". `User.totp_secret`
  exists, but there is no enrolment or verification endpoint; `amr` is never
  set to include `mfa`/`otp`. A tender policy with `require_mfa: true` therefore
  cannot currently be satisfied by anyone.
* `ARCHITECTURE.md` §3 lists `WorkflowService` separately; it is part of
  `services/processes.py`.

**Other:**

* `frontend/src/app/process/page.tsx` is 683 lines and RFQ-specific; the
  tender and scholarship views should be separate components selected by type,
  not more branches in this file.
* `processes/new/page.tsx` embeds the whole RFQ form; each type's wizard
  should be its own component.
* No frontend lint or tests (`package.json` has no `lint` script; no ESLint
  config).
* Local venv is Python 3.14 while the host runs 3.10; syntax compatibility is
  only enforced by review. The PostgreSQL run of the suite is manual.
* Starlette deprecation warning on the test client (`httpx` → `httpx2`).
* Supplier documents are stored unencrypted (by design for registry
  certificates); scholarship documents must not reuse that path — they are
  sensitive personal data (`SECURITY_MODEL.md` §10).

## 7. Reuse as is

`ProcessDefinition` + registry, `TRANSITIONS`/`phase`/`timeline`, vault and
envelope encryption, `OpeningService` and all six policy rules, audit service
and chain verification, notification outbox and trilingual templates,
`DocumentService` upload validation, category engine and matching, supplier
registry services, protocol rendering, RBAC map, `AppShell`, `ui.tsx`
primitives, `CategoryPicker`, `Timeline`, `I18nProvider`, deploy scripts.

## 8. Change (extend, do not rewrite)

| Component | Change |
|---|---|
| `ProcessDefinition` | Add admission hook (`distribution`: `category_match` / `public` / `applicants`), decision options, per-submission vs per-process decisions, document requirements for process attachments |
| `submissions`, `authorization` | Ask the definition who may view and submit; support applicants |
| `evaluation` | Decision options from the definition; per-application decisions for scholarships |
| `reporting.staff_dashboard` | Group by type generically; add by-category and processing-time series |
| New models + migration `0003` | Committees (members, conflict-of-interest declarations, assignments), supplier document review status, applicant profile / scholarship application fields as needed |
| Identity | TOTP enrolment + step-up so tender MFA rules can pass |
| `AppShell` nav | Sections per the prompt, shown by permission |
| `processes/new` | Cards from `/process-types`; one wizard component per type |
| `process/page.tsx` | Split into shared header/timeline + per-type panels |
| Docs | Correct the drift listed in §6 as each piece lands |

## 9. Constraints the new work must respect

From `CLAUDE.md` / `SECURITY_MODEL.md`; relevant to the prompt's new features:

* Tenders are **always sealed until the deadline** and their distribution is
  **never** editable.
* Scoring and eligibility **advise**; a person records every decision with a
  reason. No automatic selection of scholarship recipients.
* Scholarship applications are personal data: need-to-know access, every view
  audited, administrators have no access, nothing personal in audit metadata.
* Shared services must not branch on process type keys.
* New UI text in all three message files with identical keys.
* Backend stays Python 3.10-compatible; no Docker.

## 10. Open policy decisions (prompt vs. current code)

These are municipal policy, not engineering choices. The code implements the
policy recorded in `CLAUDE.md` (commit `346bee7`, 2026-09-26). The master
prompt asks for the opposite. Nothing here changes until the council decides.

### 10.1 Editing the RFQ distribution list

* **Prompt §8, §47, §51:** the employee cannot deselect or remove any matched
  supplier; enforce server-side; test that the creator cannot exclude one.
* **Code today:** `RFQProcess.distribution_editable = True`. Staff may exclude
  at publication, add later, or remove while submissions are open — each with
  a mandatory reason, audited, shown in the fairness report and protocol.
  Tenders refuse all edits (`403 distribution_not_editable`, tested).
* **To adopt the prompt:** set `distribution_editable = False` on
  `RFQProcess`, remove the edit controls from the RFQ UI, and turn the
  existing tender refusal tests into RFQ tests. The mechanism (flag checked in
  the service) already exists.

### 10.2 RFQ opening modes

* **Prompt §14–15:** RFQ offers are sealed; staff see only who submitted and
  when; opening happens after the deadline.
* **Code today:** `opening_mode` per request — `visible` (default: team reads
  offers on arrival), `sealed_anytime` (opening before the deadline closes
  submissions), `sealed_after_deadline` (the prompt's behaviour).
* **To adopt the prompt:** restrict `opening_mode` to `sealed_after_deadline`
  (or make it the only option offered), and additionally show per-supplier
  "submitted / time / submission ID" to staff before opening — which relaxes
  the current rule that staff see only the count until opening.
