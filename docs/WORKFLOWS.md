# Workflows

State lives on `processes.status`; the phases between states (for example
"submission open" vs "awaiting opening") are **derived from time**, not stored,
so no scheduler has to flip them and a late worker cannot leave a process in a
wrong state.

| Stored status | Derived phase | Condition |
|---|---|---|
| `DRAFT` | draft | — |
| `PUBLISHED` | `submission_open` | `now < submission_deadline` |
| `PUBLISHED` | `awaiting_opening` | `now >= submission_deadline` |
| `OPENED` | `evaluation` | vault opened |
| `DECIDED` | `decided` | decision recorded |
| `CLOSED` | `closed` | protocol generated and closed |
| `CANCELLED` | `cancelled` | — |

Allowed transitions (enforced by `WorkflowService`; anything else is `409 invalid_transition`):

```
DRAFT ──publish──▶ PUBLISHED ──open (policy)──▶ OPENED ──decide──▶ DECIDED ──close──▶ CLOSED
  │                    │
  └──cancel──▶ CANCELLED ◀──cancel (before opening, with reason)
```

## 1. RFQ — Request for Quotation

Timeline: Draft → Published → Supplier notification → Submission → Deadline →
Opening → Evaluation → Decision → Closed.

### 1.1 Create (procurement manager, `process.create.rfq`)
Reference number (auto: `RFQ-2026-0184`, editable while draft), title,
description, categories (one or more nodes of the tree), technical
specification, quantity, expected delivery date, submission deadline, contact
details, additional requirements, attachments. Stored as `DRAFT` with the
creator as `OWNER`. `PROCESS_CREATED`.

While editing, the form calls the distribution preview and shows
**"27 registered suppliers match this request."** The preview lists them
read-only. There is no control — in the UI or the API — to remove one.

### 1.2 Publish (`process.manage`)
One transaction:

1. Validate the draft against the RFQ model (deadline in the future, at least
   one category, …).
2. Freeze `process_versions` v1 (snapshot + SHA-256). `PROCESS_PUBLISHED`.
3. Copy the opening policy and freeze it.
4. Create the vault: a new RSA key pair; the private key is wrapped by the KMS
   and its plaintext discarded.
5. Match suppliers (below) and write the `INITIAL` distribution snapshot and
   recipients. `SUPPLIERS_MATCHED` with the count and snapshot hash.
6. For every recipient, generate an invitation token and enqueue an email and
   an in-app notification (`RFQ_INVITATION`) in the supplier's language.
7. Commit. The worker delivers mail afterwards; each delivery writes
   `NOTIFICATION_SENT` or `NOTIFICATION_FAILED`.

The publish request body accepts no recipient fields; unknown fields are
rejected (`extra="forbid"`).

### 1.3 Matching rule
A supplier is matched when **all** hold:

* status `ACTIVE`;
* at least one of its categories is on the same branch as a process category —
  the same node, an ancestor (a "Computers" supplier gets a "Desktop computers"
  RFQ) or a descendant (a "Laptops" supplier gets a broad "Computers" RFQ);
* if the process restricts service regions, the supplier serves one of them.

`match_reason` records which supplier category matched which process category
and how (`exact` / `supplier_broader` / `supplier_narrower`).

**Supplemental distribution.** A supplier who registers, is activated, or adds
a category while an RFQ is still open for submission and matches it, is added
through a `SUPPLEMENTAL` snapshot and invited — the initial snapshot is never
edited.

### 1.4 Invitation
The email links to `/invite?token=…`. Opening it records `opened_at`
(first time only) and sends the supplier to sign in / the opportunity page.
Opening the opportunity's submission form records `submission_started_at` and
creates the `submissions` row (`STARTED`).

### 1.5 Submit (supplier, `submission.create`, recipient of this process)
Before the deadline only. Fields: price before VAT (VAT and total computed by
the server at the configured rate), delivery days, warranty months, payment
terms, notes; files: proposal PDF (required), technical specification,
supporting documents.

The server validates, encrypts (SECURITY_MODEL §4), stores, marks the previous
version superseded, and returns a receipt: RFQ number, submission id, receipt
number, timestamp, file names + SHA-256, salted payload hash.
`SUBMISSION_CREATED` / `SUBMISSION_UPDATED`, `SUBMISSION_SEALED`,
`FILE_UPLOADED` per file. An in-app + email receipt notification follows.

After the deadline: `409 deadline_passed`.

### 1.6 Deadline
Nothing changes in the database at the deadline; the derived phase becomes
`awaiting_opening`. The worker writes `DEADLINE_REACHED` once
(`deadline_recorded_at`).

### 1.7 Open (procurement manager, `opening.initiate`, participant)
RFQ default policy: `TimePolicy`, `RolePolicy`, `IdentityPolicy` (MFA off by
default, configurable), 1 approval (the initiator). The service creates an
opening request, records the approval, re-evaluates, unwraps the vault private key, verifies
every file, marks every current submission `OPENED` at the same timestamp,
sets the vault `OPENED`, writes `VAULT_OPENED`, and notifies every submitter
(`VAULT_OPENED` — no competitor data).

Attempt before the deadline → `EARLY_OPEN_ATTEMPT` (critical) and `403`.

### 1.8 Compare
Comparison table: supplier, price before VAT, VAT, total, delivery, warranty,
payment terms, required-documents status. Sortable. **No winner is computed or
highlighted.** Each view writes `PROPOSAL_VIEWED`; downloads verify the hash and
write `PROPOSAL_DOWNLOADED`.

### 1.9 Decide (`decision.record`, participant)
Selected supplier (or "no award"), mandatory reason. Records decision maker
and time. `DECISION_RECORDED`. Submitters are notified that a decision was
recorded.

### 1.10 Protocol and close
`ProtocolService` renders the RFQ opening/decision protocol: process metadata,
publication time and version hash, distribution count and snapshot hash,
submission count, opening request and approvals, integrity results,
comparison, decision and reason, and the audit head hash.
`PROTOCOL_GENERATED`. Closing requires a decision and a protocol.

## 2. Formal tender (phase 7)

Timeline: Draft → Published → Submission → Sealed → Deadline → Multi-approval
→ Vault opened → Evaluation → Decision → Closed.

Differences from RFQ:

* Distribution is **public** (anyone registered may submit), optionally also
  notifying matching categories.
* Default policy: Time + Network (municipal CIDRs) + Device (managed) +
  Identity (MFA required) + Role + MultiApproval (3 of 5 designated officials).
* Opening is a request that stays `PENDING`; each designated official approves
  independently with their own session and MFA step-up. The status screen
  shows each rule (✓ deadline passed, ✓ municipal network, ✓ authorized device,
  ✓ MFA, 2/3 approvals — `LOCKED`). On the M-th approval the policy is
  re-evaluated for the approver and the vault opens.
* `VAULT_OPENED` notification: "תיבת ההצעות הדיגיטלית למכרז 17/2026 נפתחה ביום
  26.09.2026 בשעה 12:04." to every submitter.
* Committee protocol with members, approvals and comments.

## 3. Scholarship (phase 8)

Timeline: Draft → Published → Applications → Deadline → Eligibility review →
Committee → Decision → Closed.

Application statuses: Draft, Incomplete, Submitted, Sealed, Missing documents,
Under administrative review, Additional information requested, Committee
review, Decision made, Approved, Rejected.

* Applicant saves drafts; checklist with completeness %; submit only when
  required items are present (enforced server-side).
* Submission produces application number, timestamp, document hashes, receipt.
* After the deadline the application is locked unless an authorized
  `deadline_exception` (reason, approver, time, allowed change) exists.
* `ScholarshipEligibilityEngine` returns per-rule PASS / FAIL / MISSING with an
  overall ELIGIBLE / POTENTIALLY_ELIGIBLE / MISSING_INFORMATION / NOT_ELIGIBLE.
  It advises; officials decide.
* `ScholarshipScoringEngine` computes a transparent weighted score from
  reviewer scores, showing every term. It never selects recipients unless a
  program explicitly configures an approved automatic policy.
* Committee members declare conflict of interest before seeing an
  application; a declared conflict blocks them and is recorded.

## 4. Call for proposals (prepared, not implemented)

`CallForProposalProcess` reuses: public distribution, vault sealing (optional
per call), eligibility rules, scoring criteria, committee review and protocols.
Its definition class exists and is disabled in `process_types`.

## 5. Notifications

`NotificationService.enqueue(event, recipients, params)` inside the business
transaction → `notifications` + `notification_deliveries` rows (outbox, in a
savepoint so a template error cannot abort the business action). The worker
delivers EMAIL rows, retries with exponential backoff (1, 5, 15, 60 min; then
`DEAD`), and records the result. IN_APP rows are delivered on insert.
Channels SMS and WhatsApp are adapter slots.

## 6. Security events

| Event | Raised when | Severity |
|---|---|---|
| `EARLY_OPEN_ATTEMPT` | opening requested before opening time | critical |
| `UNAUTHORIZED_NETWORK_ATTEMPT` | NetworkPolicy fails | critical |
| `UNAUTHORIZED_DEVICE_ATTEMPT` | DevicePolicy fails | critical |
| `FAILED_MULTI_APPROVAL` | approval rejected, or duplicate / undesignated approver | warning |
| `SEALED_ACCESS_DENIED` | content endpoint called while sealed | critical |
| `FILE_INTEGRITY_FAILURE` | hash or GCM verification fails | critical |
| `VAULT_OPENED`, `PROPOSAL_VIEWED`, `PROPOSAL_DOWNLOADED` | normal but audited | info |

Critical events notify every holder of `security_alert.receive`.
