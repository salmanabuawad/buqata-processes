# Administrator guide

## Users and roles

*משתמשים והרשאות* lists staff and suppliers. Staff roles are defined in
`backend/app/core/rbac.py` (see `RBAC.md`) and cannot be edited in the UI.

* Granting requires a reason, is audited (`ROLE_GRANTED`) and — for business
  roles — alerts the auditors.
* You cannot grant roles to, or deactivate, your own account.
* In production, staff sign in with Entra ID; create them without a password.
* First administrator on a new host:
  `python -m app.cli create-admin --email … --name … --password …`.

## Categories

*תחומי פעילות* edits the tree used for supplier registration and automatic
distribution. Every category has Hebrew, Arabic and English names. Keys are
permanent. Deactivating a category hides it from new registrations and stops
it matching; existing distribution snapshots are unchanged.

## Suppliers

The registry is read-only for staff, except status: activating a supplier
invites it to open processes it matches (supplemental snapshot); suspending it
stops future invitations. Staff never choose recipients.

## Opening policies

Each process copies its type's default opening policy at creation, editable
until publication and frozen afterwards. RFQ default: after the deadline, by a
participating procurement manager, one approval. Tender (phase 7) adds
municipal network CIDRs, managed device, MFA and M-of-N designated officials.
The approval count, network ranges and committee structure are municipal and
legal policy — the software enforces whatever is configured.

## Audit

*יומן ביקורת* → *אימות שרשרת היומן* recomputes every hash. A broken chain names
the first damaged record. For external anchoring, record the output of
`python -m app.cli audit-anchor` periodically outside this system.

## Notifications

E-mail is delivered by the worker with retries (1, 5, 15, 60 minutes, then
marked failed). The fairness report shows delivery per supplier. A failed
e-mail never undoes a publication or a submission; the in-app notification is
always created.
