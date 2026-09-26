# API design

Base path `/api/v1`. JSON everywhere except uploads (`multipart/form-data`)
and protocols (`text/html`). OpenAPI at `/api/v1/docs` (disabled in
production unless `EXPOSE_DOCS=true`).

## Conventions

* **Auth**: session cookie `bdp_session` (HttpOnly). Unsafe methods require
  `X-CSRF-Token` equal to the `bdp_csrf` cookie.
* **Errors**: `{"error": {"code": "deadline_passed", "message": "…", "details": {…}}}`.
  Codes are stable and translated by the frontend. `401 not_authenticated`,
  `403 forbidden`, `403 vault_sealed`, `403 opening_policy_failed`,
  `404 not_found`, `409 invalid_transition`, `409 deadline_passed`,
  `422 validation_error`.
* **Validation**: request models forbid unknown fields.
* **Lists**: `?limit=&offset=`; response `{items, total}`; stable ordering.
* **Money**: integer agorot in the API (`price_before_vat_agorot`).
* **Time**: ISO-8601 UTC.
* **Language**: `Accept-Language` or the user's `locale` selects notification
  and protocol language; API error messages are English, codes are canonical.

## Endpoints

### Health and meta
| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness + DB check |
| GET | `/meta` | environment name, enabled process types, VAT rate, demo mode flag |

### Auth and identity
| Method | Path | Permission |
|---|---|---|
| POST | `/auth/login` | public — `{email, password}` |
| POST | `/auth/logout` | session |
| GET | `/auth/me` | session — user, roles, permissions, supplier profile id |
| GET | `/auth/demo-users` | public, only when `DEMO_MODE=true` and not production |
| POST | `/auth/demo-login` | same condition — `{user_id}` |
| PATCH | `/me` | session — locale, name, phone |

### Administration
| Method | Path | Permission |
|---|---|---|
| GET | `/admin/users` | `user.manage` |
| POST | `/admin/users` | `user.manage` |
| PATCH | `/admin/users/{id}` | `user.manage` (activate/deactivate) |
| POST | `/admin/users/{id}/roles` | `role.assign` — `{role_key, reason}`; never self |
| DELETE | `/admin/users/{id}/roles/{role_key}` | `role.assign` |
| GET | `/admin/roles` | `role.assign` — roles with permissions (read-only) |

### Categories
| Method | Path | Permission |
|---|---|---|
| GET | `/categories` | public — full active tree, three languages |
| POST | `/categories` | `category.manage` |
| PATCH | `/categories/{id}` | `category.manage` (rename, reorder, deactivate) |

### Suppliers
| Method | Path | Permission |
|---|---|---|
| POST | `/suppliers/register` | public — company + contact user + password + category ids |
| GET | `/suppliers/me` | `supplier.self` |
| PATCH | `/suppliers/me` | `supplier.self` |
| PUT | `/suppliers/me/categories` | `supplier.self` — `{category_ids}`; triggers supplemental distribution |
| POST | `/suppliers/me/documents` | `supplier.self` — multipart certificate + expiry |
| GET | `/suppliers/me/opportunities` | `supplier.self` — processes this supplier was invited to |
| GET | `/suppliers` | `supplier.registry.read` — filter by category, status, q |
| GET | `/suppliers/{id}` | `supplier.registry.read` |
| PATCH | `/suppliers/{id}/status` | `supplier.registry.manage` |

### Processes
| Method | Path | Permission |
|---|---|---|
| GET | `/process-types` | session |
| GET | `/processes` | `process.read` — filters: type, status, phase, q |
| POST | `/processes` | `process.create.<type>` — `{process_type, …}` |
| GET | `/processes/{id}` | `process.read`, or an invited supplier (public view) |
| PATCH | `/processes/{id}` | `process.manage` + participant, DRAFT only |
| POST | `/processes/{id}/documents` | `process.manage` + participant, DRAFT only |
| GET | `/processes/{id}/documents/{doc_id}` | staff with `process.read`, or invited supplier |
| POST | `/distribution/preview` | `process.create.rfq` — `{category_ids, service_regions?}` → count + supplier names |
| POST | `/processes/{id}/publish` | `process.manage` + participant — body `{}` only |
| POST | `/processes/{id}/cancel` | `process.manage` + participant — `{reason}` |
| GET | `/processes/{id}/distribution` | `process.monitor` — fairness report |
| GET | `/processes/{id}/timeline` | `process.read` or invited supplier |

### Invitations and submissions (supplier)
| Method | Path | Permission |
|---|---|---|
| GET | `/invitations/{token}` | public — records `opened_at`; returns process id + reference |
| POST | `/processes/{id}/submission/start` | `submission.create` + recipient |
| GET | `/processes/{id}/submission` | `submission.create` — own receipt(s) only |
| POST | `/processes/{id}/submission` | `submission.create` + recipient + before deadline — multipart: `payload` (JSON), `files[]`, `kinds[]` |

### Opening, content, decisions
| Method | Path | Permission |
|---|---|---|
| GET | `/processes/{id}/opening` | `process.read` — policy, per-rule evaluation for the caller, approvals, vault state, sealed count |
| POST | `/processes/{id}/opening/requests` | `opening.initiate` + participant |
| POST | `/opening-requests/{id}/approve` | `opening.approve` + designated |
| POST | `/opening-requests/{id}/reject` | `opening.approve` + designated — `{reason}` |
| GET | `/processes/{id}/comparison` | `submission.read_opened` + participant + vault OPENED |
| GET | `/submissions/{id}/documents/{doc_id}` | same — verifies hash, streams plaintext |
| POST | `/processes/{id}/decision` | `decision.record` + participant + OPENED — `{decision_type, selected_submission_id?, reason}` |
| POST | `/processes/{id}/close` | `process.manage` + participant — requires decision + protocol |
| POST | `/processes/{id}/participants` | `process.manage` + owner — `{user_id, participation, reason}` |

### Protocols
| Method | Path | Permission |
|---|---|---|
| POST | `/processes/{id}/protocols` | `protocol.generate` + participant — `{protocol_type, locale}` |
| GET | `/processes/{id}/protocols` | `protocol.read` |
| GET | `/protocols/{id}/html` | `protocol.read` — printable HTML |

### Notifications
| Method | Path | Permission |
|---|---|---|
| GET | `/notifications` | session — own in-app messages |
| POST | `/notifications/{id}/read` | session |
| POST | `/notifications/read-all` | session |

### Audit and dashboards
| Method | Path | Permission |
|---|---|---|
| GET | `/audit/events` | `audit.read` — filters: process_id, event_type, severity |
| POST | `/audit/verify` | `audit.verify` — `{valid, checked, first_broken_sequence, head_hash}` |
| GET | `/dashboard/staff` | `process.read` — cards + recent activity |
| GET | `/dashboard/supplier` | `supplier.self` |

## Example: publish

```http
POST /api/v1/processes/7c2…/publish
X-CSRF-Token: …
Content-Type: application/json

{}
```

```json
{
  "id": "7c2…",
  "status": "PUBLISHED",
  "published_at": "2026-09-20T07:00:00Z",
  "version": {"version_no": 1, "content_hash": "9f1…"},
  "distribution": {"snapshot_id": "…", "recipient_count": 27, "snapshot_hash": "44a…"}
}
```

Sending `{"exclude_supplier_ids": ["…"]}` returns `422 validation_error`.
