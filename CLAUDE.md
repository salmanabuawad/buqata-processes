# Working in this repository

Municipal digital-process platform for Buq'ata Local Council. Read
`docs/ARCHITECTURE.md` and `docs/SECURITY_MODEL.md` before changing anything
in services, and `DEPLOY_SERVER.md` before touching deployment.

## Invariants — do not break these

**Distribution is computed, edits are policy.** Recipients come from
categories and are written as immutable snapshots. Whether staff may then add
or remove suppliers is the process type's `distribution_editable` flag —
municipal policy: yes for quotation requests, never for tenders. Every edit
needs a reason and is audited; additions go into a MANUAL snapshot, removals
mark the recipient row (`removed_at`), nothing is deleted or rewritten.

**Sealing is cryptographic and chosen per process.** Offers are always
encrypted with per-version DEKs wrapped by the vault's RSA public key. A
quotation request picks an `opening_mode` at creation: `visible` (readable by
the process team as offers arrive), `sealed_anytime` (sealed; may open before
the deadline, which closes submissions) or `sealed_after_deadline`. Tenders
are always sealed until the deadline. Only `vault.open_vault` and content
reads permitted by `definition.content_sealed()` unwrap the private key. Never
add a per-submission open, a cache of plaintext, or a bypass for any role.

**Every opening re-evaluates the policy** at the moment of opening. Policy
failures raise typed security events in their own transaction.

**Audit in the same transaction.** Business actions call `audit.record` inside
their transaction; denials use `record_independent`. Never update or delete
audit rows; never log prices, personal data or file contents.

**No automatic decisions.** Comparison, eligibility and scoring advise; a
person records the decision with a reason.

**Process types are definitions, not branches.** Add a type in
`app/processes/` + registry; shared services must not switch on type keys.

## Things that are easy to get wrong

- No Docker. Development runs natively (SQLite, local storage); the host runs
  PostgreSQL, nginx and systemd units directly.
- Business time comes from `app.core.clock.now()`; tests freeze it. Sessions
  expire when tests jump the clock — sign in again after a jump.
- SQLite is for dev/tests only; run the suite against PostgreSQL
  (`TEST_DATABASE_URL`) after schema or locking changes. Audit appends take a
  PostgreSQL advisory lock; don't hold a read transaction on `audit_events`
  while doing DDL in tests.
- Frontend is a static export: no dynamic routes, no rewrites in production,
  detail pages use `?id=` query parameters, links end with `/`.
- All UI text lives in `frontend/src/i18n/messages/{he,ar,en}.json`; the three
  files must keep identical keys. Use logical CSS (`ms-`, `pe-`, `start`).
- Keep the backend compatible with Python 3.10 (the deploy host).
- Line endings: LF for anything that runs on the Linux host (`.gitattributes`).
