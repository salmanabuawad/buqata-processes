# Database schema

PostgreSQL 16 in deployed environments; SQLite for local development and tests.
All primary keys are UUIDs (`sqlalchemy.Uuid`). All timestamps are UTC
(`timestamptz`; a `UTCDateTime` type restores the zone on SQLite). Money is
stored as integer agorot. JSON columns are `jsonb` on PostgreSQL.

Migrations are Alembic (`backend/alembic/versions`). The phase column says when
a table lands; tables for later phases are designed here so earlier ones do not
have to change shape.

## Identity and access (phase 3)

| Table | Key columns | Notes |
|---|---|---|
| `organizations` | `id, slug UNIQUE, name_he, name_ar, name_en` | One row today (Buq'ata); multi-tenant ready. |
| `users` | `id, organization_id FK, email UNIQUE, full_name, phone, kind (staff/supplier/applicant), password_hash NULL, locale, is_active, totp_secret NULL, created_at, last_login_at` | `password_hash` null for OIDC-only staff. |
| `roles` | `id, key UNIQUE, name_he, name_ar, name_en, is_business_role` | Seeded from code. |
| `permissions` | `key PK, description` | Seeded from code; documentation and reporting only. |
| `role_permissions` | `role_id FK, permission_key FK` PK both | Synchronised from `app/core/rbac.py` on every migrate/seed; not editable through the API. |
| `user_roles` | `id, user_id FK, role_id FK, organization_id FK, granted_by FK NULL, granted_at, reason, revoked_at NULL` | Active = `revoked_at IS NULL`. Partial unique index on active (user, role, org). |
| `sessions` | `id, user_id FK, token_hash UNIQUE, csrf_token, amr jsonb, ip, user_agent, created_at, last_seen_at, expires_at, revoked_at` | Token stored as SHA-256 only. |

## Catalogue and supplier registry (phase 4)

| Table | Key columns | Notes |
|---|---|---|
| `categories` | `id, parent_id FK NULL, key UNIQUE, name_he, name_ar, name_en, path, depth, sort_order, is_active` | `path` = `/id/id/.../` materialised path for ancestor/descendant queries. |
| `stored_files` | `id, storage_key UNIQUE, original_filename, mime_type, size_bytes, sha256, encrypted bool, integrity_status (OK/FAILED/UNVERIFIED), uploaded_by FK, uploaded_at` | Every file in the system. For encrypted files `sha256` is of the plaintext and `storage_key` holds ciphertext. |
| `suppliers` | `id, organization_id FK, company_name, company_number UNIQUE, contact_name, email, phone, address, city, website, description, service_regions jsonb, status (ACTIVE/INACTIVE/SUSPENDED), notify_email, notify_in_app, preferred_locale, registered_at, updated_at` | |
| `supplier_contacts` | `id, supplier_id FK, user_id FK UNIQUE, is_primary, title` | Links login accounts to companies. |
| `supplier_categories` | `supplier_id FK, category_id FK` PK both, `added_at` | Changes audited as `SUPPLIER_CATEGORY_CHANGED`. |
| `supplier_documents` | `id, supplier_id FK, doc_type, title, stored_file_id FK, issued_on, expires_on NULL, uploaded_at` | Certificates; drives "expiring documents". |

## Processes (phase 5)

| Table | Key columns | Notes |
|---|---|---|
| `process_types` | `key PK, name_he, name_ar, name_en, is_enabled, default_config jsonb` | rfq, tender, scholarship, call_for_proposals (disabled). |
| `processes` | `id, organization_id FK, process_type FK, reference_number UNIQUE, title, description, status, details jsonb, submission_deadline, opening_time, published_at NULL, deadline_recorded_at NULL, contact_name, contact_email, contact_phone, created_by FK, created_at, updated_at, current_version_id NULL` | `details` is validated by the type's Pydantic model (quantity, delivery date, technical spec…). Status: DRAFT → PUBLISHED → OPENED → DECIDED → CLOSED; CANCELLED from DRAFT/PUBLISHED. |
| `process_versions` | `id, process_id FK, version_no, snapshot jsonb, content_hash, frozen_at, frozen_by FK` | Immutable; UNIQUE (process_id, version_no). |
| `process_categories` | `process_id FK, category_id FK` PK both | Target categories for automatic matching. |
| `process_documents` | `id, process_id FK, stored_file_id FK, kind (specification/attachment), title` | Public to recipients after publication. |
| `process_participants` | `id, process_id FK, user_id FK, participation (OWNER/TEAM/COMMITTEE/OPENING_OFFICIAL/CONTENT_ACCESS), granted_by, granted_at, reason, revoked_at` | Need-to-know. `CONTENT_ACCESS` is the explicit grant for auditors/legal. |
| `distribution_snapshots` | `id, process_id FK, kind (INITIAL/SUPPLEMENTAL), rule jsonb, recipient_count, snapshot_hash, created_at, created_by FK` | Immutable. `rule` records the category ids and matching rule used. |
| `distribution_recipients` | `id, snapshot_id FK, process_id FK, supplier_id FK, match_reason jsonb, invitation_token_hash UNIQUE, notification_id FK NULL, notified_at, opened_at NULL, submission_started_at NULL` | UNIQUE (process_id, supplier_id). No API deletes or updates the recipient set; tracking columns only move forward. |

## Submissions and vault (phase 5–6)

| Table | Key columns | Notes |
|---|---|---|
| `vaults` | `id, process_id FK UNIQUE, status (SEALED/OPENED), kms_provider, kms_key_ref, public_key_pem, wrapped_private_key, created_at, opened_at NULL, opening_request_id FK NULL` | Sealing uses the public key; `wrapped_private_key` is KMS ciphertext. |
| `submissions` | `id, process_id FK, supplier_id FK NULL, applicant_user_id FK NULL, receipt_number UNIQUE, status (STARTED/SUBMITTED/OPENED/WITHDRAWN), started_at, submitted_at NULL, current_version_id NULL, opened_at NULL` | UNIQUE (process_id, supplier_id). |
| `submission_versions` | `id, submission_id FK, version_no, submitted_by FK, submitted_at, wrapped_dek, payload_ciphertext, payload_nonce, payload_hash, receipt_hash, is_current, superseded_at NULL` | Immutable once written except `is_current/superseded_at`. `payload_hash` is salted (see SECURITY_MODEL §4). |
| `submission_documents` | `id, submission_version_id FK, stored_file_id FK, kind, nonce` | Ciphertext in storage; plaintext hash on `stored_files`. |

## Opening (phase 6–7)

| Table | Key columns | Notes |
|---|---|---|
| `opening_policies` | `id, process_id FK UNIQUE, rules jsonb, required_approvals, designated_official_ids jsonb, frozen` | `rules` = ordered `[{type, params}]`. Copied from the type default at creation; frozen at publication. |
| `opening_requests` | `id, process_id FK, requested_by FK, requested_at, status (PENDING/EXECUTED/REJECTED/CANCELLED), last_evaluation jsonb, executed_at NULL` | At most one PENDING per process. |
| `opening_approvals` | `id, opening_request_id FK, approver_id FK, decision (APPROVE/REJECT), decided_at, auth_context jsonb, client_ip, device jsonb` | UNIQUE (request, approver). |

## Decisions, protocols, notifications, audit (phase 5)

| Table | Key columns | Notes |
|---|---|---|
| `decisions` | `id, process_id FK, subject_submission_id FK NULL, decision_type (AWARD/NO_AWARD/APPROVE/REJECT), reason, decided_by FK, decided_at, metadata jsonb` | Never written by a scheduler or a scoring engine. |
| `protocols` | `id, process_id FK, protocol_type, locale, html, content_hash, audit_head_hash, generated_by FK, generated_at` | `audit_head_hash` pins the protocol to the audit chain position. |
| `notifications` | `id, recipient_user_id FK NULL, recipient_supplier_id FK NULL, recipient_email NULL, event_type, locale, subject, body, link, process_id NULL, created_at, read_at NULL` | The row is also the in-app message. |
| `notification_deliveries` | `id, notification_id FK, channel (EMAIL/IN_APP/SMS/WHATSAPP), status (PENDING/SENT/FAILED/DEAD), attempts, next_attempt_at, last_error, sent_at` | Outbox. Worker picks `PENDING` / `FAILED` due for retry. |
| `audit_events` | `id, sequence UNIQUE, event_type, severity (INFO/WARNING/CRITICAL), occurred_at, actor_id NULL, actor_role NULL, process_id NULL, submission_id NULL, ip NULL, metadata jsonb, previous_hash, event_hash UNIQUE` | Append-only (trigger). Deliberately **no foreign keys**, so the log never blocks and never cascades. |

## Committees and scholarships (phase 7–8, designed)

| Table | Key columns |
|---|---|
| `committees` | `id, organization_id, kind (TENDER/SCHOLARSHIP), name, created_at` |
| `committee_members` | `id, committee_id, user_id, role (CHAIR/MEMBER), active` |
| `scholarship_programs` | `id, process_id FK UNIQUE, academic_year, amount_agorot, budget_agorot, max_recipients, privacy_notice_*, declarations jsonb, retention_days` |
| `scholarship_applications` | `id, process_id, applicant_user_id, application_number UNIQUE, status (DRAFT…REJECTED), form jsonb (encrypted fields), completeness_pct, submitted_at, locked_at` |
| `application_documents` | `id, application_id, requirement_key, stored_file_id, status` |
| `eligibility_rules` | `id, process_id, rule_type, params jsonb, severity (REQUIRED/ADVISORY), order` |
| `eligibility_results` | `id, application_id, overall (ELIGIBLE/POTENTIALLY_ELIGIBLE/MISSING_INFORMATION/NOT_ELIGIBLE), rule_results jsonb, evaluated_at` |
| `scoring_criteria` | `id, process_id, key, name_*, description_*, weight, max_score, required_evidence` |
| `review_assignments` | `id, application_id, reviewer_id, assigned_at` |
| `conflict_declarations` | `id, application_id, reviewer_id, declaration (NO_CONFLICT/CONFLICT), statement, declared_at` |
| `review_scores` | `id, application_id, reviewer_id, criterion_id, score, comment, scored_at` |
| `deadline_exceptions` | `id, process_id, subject_id, reason, allowed_change, approved_by, approved_at, expires_at` |
| `kpi_baselines` | `id, key, value, unit, source_note, basis (MEASURED/CALCULATED/ESTIMATED)` |

## Indexes worth naming

* `distribution_recipients (process_id, supplier_id)` unique — one invitation
  per supplier per process, even across supplemental snapshots.
* `submissions (process_id, supplier_id)` unique.
* `audit_events (sequence)` unique, `(process_id, sequence)`.
* `notification_deliveries (status, next_attempt_at)` for the worker.
* `categories (path)` for prefix matching.
* `supplier_documents (expires_on)`.
