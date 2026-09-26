# Security model

This document states what the platform protects, from whom, how, and — just as
important — where the protection currently ends.

## 1. Assets

| Asset | Why it matters |
|---|---|
| Sealed submission content (prices, proposals, files) | Premature disclosure destroys competition and is the core integrity promise. |
| Scholarship applications and documents | Sensitive personal data (identity, finances, welfare). |
| Distribution records | Proof that no supplier was excluded by hand. |
| Opening and decision records, protocols | Legal record of the process. |
| Audit trail | Evidence that everything above is true. |

## 2. Adversaries

| Actor | Capability assumed | Must not be able to |
|---|---|---|
| Competing supplier | Own account, network access | See other submissions; learn who submitted before opening. |
| Procurement employee | Staff account with process permissions | Read sealed content early; exclude a matched supplier; open without the policy being satisfied. |
| System administrator | Manages users, categories, configuration via the application | Read sealed content or applications; grant themselves business roles; bypass the opening policy. |
| Database administrator | Full read/write to PostgreSQL | Read sealed content (ciphertext only); silently alter the audit trail. |
| Application developer / host operator | Server shell, source code, `.env` | See §7 — the honest limit. |

## 3. Principles

1. **Server-side enforcement only.** Hiding a button is presentation. Every
   rule is enforced in the API/service layer and covered by tests that call the
   API directly.
2. **Infrastructure access ≠ business access.** `system_admin` has no
   permission to read submissions, applications or applicant documents, and the
   role → permission map is code, not data an administrator can edit.
3. **Least privilege and need-to-know.** A permission is necessary but not
   sufficient; content access also requires participation in that specific
   process (owner, assigned committee member, or an explicit, reasoned, audited
   grant).
4. **Cryptography, not flags, for sealing.** A sealed submission is
   ciphertext. Its key is only unwrapped by `SecureVaultService` after an
   `OpeningService` decision that re-evaluates the full policy at that moment.
5. **Everything important is audited, in the same transaction.** If the audit
   record cannot be written, the action does not happen. Denied security-relevant
   attempts are recorded in their own transaction so the denial is not lost.
6. **Separation of technical enforcement from municipal policy.** The software
   enforces whatever opening policy, retention period and approval count the
   council configures. It does not claim to decide legal compliance.

## 4. Sealing: envelope encryption

```
payload JSON ─┐
file 1 ───────┼── AES-256-GCM with DEK (fresh 256-bit key per submission version,
file n ───────┘   unique 96-bit nonce per part, AAD = version id + part name)
                     │
DEK ─── RSA-OAEP-SHA256 with the vault PUBLIC key (3072-bit, one key pair per process)
                     │
vault PRIVATE key ── wrapped by the Key Management Service (context = vault id)
```

* **Per-submission DEK** — compromise of one does not expose another.
* **Per-process vault key pair.** Sealing needs only the public key, which is
  stored in the clear. The private key is generated at publication, wrapped by
  the KMS immediately, and the plaintext is discarded. From then until the
  opening, **no code path holds the private key** — accepting a submission does
  not require it. Opening is one KMS unwrap; the private key is also the value a
  future threshold scheme would split.
* **KMS abstraction** (`adapters/kms.py`, `KeyManagementService` protocol:
  `wrap(plaintext, context)`, `unwrap(ciphertext, context)`):
  * `LocalKms` — development and demonstration only; AES-GCM with a master key
    from `VAULT_MASTER_KEY` (or a generated key file). Refuses to start when
    `ENVIRONMENT=production`.
  * Production adapters (AWS KMS `Encrypt/Decrypt` with `EncryptionContext`,
    Azure Key Vault `wrapKey/unwrapKey`, PKCS#11 HSM) implement the same two
    methods. The KMS key policy should allow `Decrypt` only to the API's
    workload identity, and every unwrap is logged by the KMS itself — an
    out-of-band unwrap is therefore visible outside this system.
* **No plaintext at rest.** The private key is never stored unwrapped. After
  opening, each authorized view unwraps again; nothing is cached to disk.
* **Low-entropy payloads are salted.** The submission payload (e.g. a price) is
  hashed together with a random 128-bit salt before its hash appears on a
  receipt or in the audit log, so the hash cannot be brute-forced back to a
  price.
* **What staff see before opening:** the number of sealed submissions. Not
  names, not prices, not file names, and not who has submitted (the fairness
  dashboard shows per-supplier submission flags only after opening; counts
  before).
* **What the supplier sees before opening:** their own receipt — submission
  id, timestamp, file names, sizes and hashes. They can replace their
  submission until the deadline by submitting a new version; the server never
  decrypts their earlier version back to them.

### Opening all together

There is one vault per process. The vault is either `SEALED` or `OPENED`;
content endpoints check the vault state before unwrapping any key. There is no
per-submission open operation, so "open supplier A while B stays sealed" is not
expressible.

### Integrity

Every file has a SHA-256 of its plaintext recorded at upload (plus GCM's
authentication tag over the ciphertext). At opening and at every download the
plaintext is re-hashed after decryption. A mismatch or a GCM failure blocks
access to that file, marks it `INTEGRITY_FAILED`, records
`FILE_INTEGRITY_FAILURE` as a critical audit event and notifies oversight.

## 5. Opening policy

`OpeningPolicy` is a list of independent rules, each returning
`PASS | FAIL | PENDING` with a reason. The vault opens only when every rule
passes at the moment of opening (they are re-evaluated, not trusted from the
approval stage).

| Rule | Checks | Dev adapter | Production adapter |
|---|---|---|---|
| `TimePolicy` | server `now() >= opening_time` (default: deadline) | — | — |
| `NetworkPolicy` | client IP inside configured CIDR ranges | `X-Real-IP` from nginx, `TRUSTED_PROXIES` | same; VLAN ranges configured as CIDRs |
| `DevicePolicy` | managed/compliant device | `MockDevicePosture` (configurable) | Intune compliance via Entra device claim / Graph |
| `IdentityPolicy` | active account, MFA satisfied if required | local TOTP step-up | Entra ID `amr` contains `mfa` |
| `RolePolicy` | actor holds the opening permission and participates in the process | — | — |
| `MultiApprovalPolicy` | M distinct approvers of N designated officials | — | — |

A failure produces a typed security event: `EARLY_OPEN_ATTEMPT`,
`UNAUTHORIZED_NETWORK_ATTEMPT`, `UNAUTHORIZED_DEVICE_ATTEMPT`,
`FAILED_MULTI_APPROVAL`. Critical events notify users holding
`security_alert.receive`.

Each approval stores approver, time, authentication context (methods, MFA),
client IP, device-posture result, and the decision. An approver cannot approve
twice; the initiator counts as one approver only if the policy says so.

## 6. Identity, sessions, request security

* Sessions are opaque random tokens, stored hashed in `sessions`, sent as
  `HttpOnly; Secure; SameSite=Lax` cookies. Idle and absolute expiry.
* CSRF: double-submit token (`csrf_token` cookie + `X-CSRF-Token` header) on
  every unsafe method.
* Passwords (local accounts only): `scrypt` with per-user salt. Production
  staff sign in through Entra ID (OIDC); local passwords remain for suppliers
  and applicants.
* MFA is carried in the `AuthContext` (`amr`). Step-up is required for
  opening when the policy says so.
* Rate limiting in nginx (auth, uploads, API) and an in-process limiter on
  login.
* Security headers (CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`,
  `Permissions-Policy`, frame denial) from the API and nginx.
* All SQL through SQLAlchemy with bound parameters. Pydantic models with
  `extra="forbid"` at every boundary — an unexpected field (for instance an
  attempt to pass an exclusion list at publication) is rejected, not ignored.
* Uploads: size limit, extension allow-list, magic-byte check, malware scanner
  hook (`MalwareScanner` protocol; `NoopScanner` in dev, ClamAV adapter point in
  production). Files are stored under random keys, never under user names.

## 7. Role-escalation controls

`system_admin` can assign roles — so the design must stop "assign myself
procurement manager, then open the tender":

* An administrator cannot grant a role to their own account.
* Granting any business role (procurement, committee, scholarship, auditor)
  is audited as `ROLE_GRANTED` and notifies oversight.
* Tender opening requires M distinct approvers from the designated officials
  of that specific process; one escalated account is not enough.
* The role → permission map is in code; no UI or API edits it.

## 8. Audit trail

Every event: `event_id, sequence, event_type, occurred_at, actor_id,
actor_role, process_id, submission_id, metadata, previous_hash, event_hash`.

`event_hash = SHA-256(canonical_json(all fields except event_hash))`, where the
canonical form includes `previous_hash`. `verify_audit_chain()` recomputes every
hash in sequence order and reports the first broken link.

Appends are serialised (`pg_advisory_xact_lock` on PostgreSQL) so the chain has
no forks. A database trigger rejects `UPDATE` and `DELETE` on `audit_events`;
a superuser can drop the trigger, which is exactly the case the hash chain
exists to expose. For stronger guarantees the head hash can be periodically
anchored outside the database (e-mailed to oversight, written to WORM storage);
the `audit anchor` CLI command prints the current head for that purpose.

Sensitive values (prices, personal data, file contents) never go into audit
metadata or logs — only identifiers and salted hashes.

## 9. Where protection ends (honest limits)

* **A host operator with both the application secrets and database access**
  can, in principle, run code that calls the KMS to unwrap a vault private key early.
  The production mitigations are external: the KMS key policy restricts who can
  call `Decrypt`, the KMS logs every call in a system this platform does not
  control, and the audit chain records every legitimate open — so an early
  decrypt leaves evidence that does not match an opening event.
  Eliminating this trust entirely needs **threshold cryptography**: split the
  vault private key with Shamir's secret sharing (M-of-N) at publication, and
  wrap each share to an official's personal key (WebAuthn PRF or a smart card)
  so the server alone never holds enough shares. `SecureVaultService` isolates
  the private key behind `_wrap_private_key / _unwrap_private_key`, so that
  change is local and sealing (public key only) is unaffected.
* `LocalKms` stores its master key beside the application. It is suitable for
  development and demonstrations only, and refuses to run in production.
* Network and device checks trust the reverse proxy's client IP and the device
  provider's claim; they are only as strong as that infrastructure.

## 10. Scholarship privacy (phase 8)

Applications are sensitive personal data: need-to-know access, committee
members see a minimised view after a conflict-of-interest declaration, every
application view / document view / download is audited, administrators have no
document access, and retention periods are configurable per program with a
deletion job that records what was removed.
