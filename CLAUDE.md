# Working in this repository

Municipal digital-process platform for Buq'ata Local Council. Read
`docs/ARCHITECTURE.md` and `docs/SECURITY_MODEL.md` before changing anything
in services, and `docs/DEPLOYMENT.md` before touching deployment.

## Invariants — do not break these

**Staff never choose recipients.** Distribution is computed from categories
and written as an immutable snapshot. No API accepts inclusion/exclusion
lists; request models forbid unknown fields. Late matches go into a new
SUPPLEMENTAL snapshot — never edit an existing one.

**Sealing is cryptographic.** Offers are encrypted with per-version DEKs
wrapped by the vault's RSA public key. Only `vault.open_vault` (called by the
opening service after the policy passes) and reads on an OPENED vault unwrap
the private key. Never add a per-submission open, a cache of plaintext, or a
bypass for any role.

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
