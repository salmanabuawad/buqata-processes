# Roles and permissions

The role → permission map is defined in `backend/app/core/rbac.py` and is the
only source of truth. It is synchronised to the `roles`, `permissions` and
`role_permissions` tables for reporting, but no API edits it.

Authorization is two-layered:

1. **Permission** — does any of the user's active roles grant it?
2. **Scope** — for process content, is the user a participant of *this*
   process (owner, team, committee, designated opening official, or holder of an
   explicit `CONTENT_ACCESS` grant)?

Content endpoints additionally require the vault to be `OPENED`. No role
satisfies that condition — only the opening workflow does.

## Permissions

| Permission | Meaning |
|---|---|
| `system.configure` | Settings, integrations, process-type configuration |
| `user.manage` | Create, deactivate users |
| `role.assign` | Grant / revoke roles (never to oneself) |
| `category.manage` | Create and edit the category tree |
| `template.manage` | Notification templates |
| `system_log.read` | Technical logs, notification delivery errors |
| `supplier.registry.read` | Browse the supplier registry |
| `supplier.registry.manage` | Add, edit, suspend and archive suppliers |
| `supplier.self` | Maintain one's own supplier profile, categories, certificates |
| `process.read` | See metadata of all processes (title, status, counts, timeline) |
| `process.read.own` | The same, only for processes one participates in |
| `process.create.rfq` / `.tender` / `.scholarship` | Create a process of that type |
| `process.manage` | Edit drafts, publish, cancel (processes one participates in) |
| `process.monitor` | Distribution and fairness data |
| `opening.initiate` | Start an opening request |
| `opening.approve` | Approve an opening request (when designated) |
| `submission.create` | Submit to a process one is invited to (supplier) |
| `submission.read_opened` | Read opened submission content (with scope) |
| `decision.record` | Record a decision (with scope) |
| `protocol.generate` / `protocol.read` | Protocols |
| `audit.read` / `audit.verify` | Audit trail and chain verification |
| `committee.review` | Review assigned items after a conflict declaration |
| `scholarship.manage` | Programs, requirements, eligibility and scoring configuration |
| `application.create` | Apply to scholarships |
| `security_alert.receive` | Receive critical security notifications |

## Roles

| Permission | system_admin | procurement_manager | requester | tender_committee | scholarship_admin | scholarship_committee | auditor | supplier | applicant |
|---|---|---|---|---|---|---|---|---|---|
| system.configure | ✓ | | | | | | | | |
| user.manage | ✓ | | | | | | | | |
| role.assign | ✓ | | | | | | | | |
| category.manage | ✓ | ✓ | | | | | | | |
| template.manage | ✓ | | | | | | | | |
| system_log.read | ✓ | | | | | | | | |
| supplier.registry.read | ✓ | ✓ | | | | | ✓ | | |
| supplier.registry.manage | ✓ | | | | | | | | |
| supplier.self | | | | | | | | ✓ | |
| process.read | | ✓ | | ✓ | ✓ | | ✓ | | |
| process.read.own | | | ✓ | | | | | | |
| process.create.rfq | | ✓ | ✓ | | | | | | |
| process.create.tender | | ✓ | | | | | | | |
| process.create.scholarship | | | | | ✓ | | | | |
| process.manage | | ✓ | ✓ | | ✓ | | | | |
| process.monitor | | ✓ | | ✓ | ✓ | | ✓ | | |
| opening.initiate | | ✓ | | | | | | | |
| opening.approve | | ✓ | | ✓ | | | | | |
| submission.create | | | | | | | | ✓ | |
| submission.read_opened | | ✓ | | ✓ | | | | | |
| decision.record | | ✓ | | ✓ | ✓ | | | | |
| protocol.generate | | ✓ | | ✓ | ✓ | | | | |
| protocol.read | | ✓ | | ✓ | ✓ | | ✓ | | |
| audit.read | | | | | | | ✓ | | |
| audit.verify | ✓ | | | | | | ✓ | | |
| committee.review | | | | ✓ | | ✓ | | | |
| scholarship.manage | | | | | ✓ | | | | |
| application.create | | | | | | | | | ✓ |
| security_alert.receive | | | | | | | ✓ | | |

Notes:

* **`system_admin` has no content permission and no process permission.** It
  can verify the audit chain (an integrity check that reveals nothing) but not
  read the trail's business contents.
* `auditor` reads process metadata, distribution, openings, decisions,
  protocols and the audit trail. Proposal content requires an explicit
  `CONTENT_ACCESS` participation granted by the process owner with a reason —
  audited as `CONTENT_ACCESS_GRANTED`.
* A procurement manager reads content only for processes they participate in
  (as owner or team). The creator is added as `OWNER` automatically.
* `requester` is department staff: they create quotation requests, publish them
  and see only the requests they take part in. They cannot open offers, read
  them or decide; the owner adds procurement staff as participants (with a
  reason, audited as `PARTICIPANT_ADDED`) and those staff open and decide.
* Only `system_admin` manages the supplier registry: adding a supplier (with an
  initial password handed to the supplier), editing its details and categories,
  and archiving it. Archiving is the removal: the row stays for distribution
  records and submissions, the supplier leaves the registry and matching, and
  its sign-in is disabled until restored. Procurement reads the registry.
* A user may hold several roles; permissions are the union, scope rules still
  apply.

## Separation of duties

* No self-grant: `role.assign` cannot target the caller's own account.
* Business-role grants notify `security_alert.receive` holders.
* For tenders, `MultiApprovalPolicy` requires M distinct designated officials;
  the initiator's approval counts once at most.
* The person who records a decision is recorded; the protocol lists everyone
  who opened, viewed and decided.
