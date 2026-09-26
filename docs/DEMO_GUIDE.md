# Demo guide

The demo data is created through the real services (`python -m app.cli seed-demo`),
so everything shown — sealing, distribution, opening, audit — is the production
code path. Names, companies and addresses are fictional; demo e-mail addresses
use the reserved `.test` domain.

**Signing in.** In demo mode the sign-in page lists users for one-click entry.
Password sign-in also works for every demo account with the password in
`DEMO_PASSWORD` (default set in `backend/app/seed/demo.py`). Demo sign-in
never claims MFA.

| Account | Role |
|---|---|
| סועאד אבו ג'בל (`procurement@buqata.test`) | Procurement manager — owns the demo RFQ |
| וליד חלבי (`procurement2@buqata.test`) | Procurement manager — not on the demo RFQ |
| רמי עמאר (`admin@buqata.test`) | System administrator |
| עו"ד ג'מיל ספדי (`auditor@buqata.test`) | Auditor / legal — receives security alerts |
| Five tender-committee members | For phase 7 |
| `office@<company>.test` | 45 supplier contacts |

## What is seeded

* 45 suppliers across 14 top-level categories (IT, electricity, maintenance …).
* **RFQ-2026-0184 "רכישת 20 מחשבים נייחים"** — category מחשוב → מחשבים →
  מחשבים נייחים. 27 suppliers matched (5 registered at "מחשוב", 8 at
  "מחשבים", 14 at "מחשבים נייחים"); 4 IT suppliers in sibling branches
  (networking, cyber, software, printers) correctly *not* invited. 27 notified,
  11 opened the invitation, 8 started, 6 submitted. Deadline two hours before
  seeding — **awaiting opening**.
* Two open RFQs (laptops, air-conditioning maintenance), two completed and
  closed RFQs with decisions and protocols, one draft.

## Walkthrough (≈10 minutes)

1. **Landing page** — the four principles; switch עברית / العربية / English and
   watch the layout flip between RTL and LTR.
2. **Supplier registers** — "הרשמה כספק": choose categories; note the fairness
   notice. After registration, the supplier is automatically added (through a
   supplemental snapshot) to any open RFQ it matches.
3. **Procurement manager** (סועאד) → *פתיחת הליך חדש* → *הצעת מחיר*. Pick
   "מחשבים נייחים": the side panel shows **"27 registered suppliers match
   this request"**. Open the list: read-only, no remove button (and the API
   rejects any attempt).
4. Open **RFQ-2026-0184** → *הפצה והוגנות*: 27 eligible · 27 notified ·
   delivered · 11 opened · 8 started · 6 submitted. The per-supplier
   "submitted" column shows a lock — who submitted is hidden until opening.
   Snapshot hash shown.
5. *כספת ופתיחה*: **6 SEALED PROPOSALS**, no prices. The policy panel shows
   each rule evaluated for the current user.
6. Sign in as the **system administrator** and try the same process: no
   access to the comparison, no opening, and granting yourself a role is
   refused (`SELF_GRANT_BLOCKED` in the audit trail).
7. Back as procurement → **פתיחת הכספת**. All six open at the same instant,
   every file hash is verified, and every submitter gets a `VAULT_OPENED`
   notification (sign in as one of the suppliers to see it).
8. *השוואה והחלטה*: sortable comparison, no winner highlighted. Record a
   decision with a reason.
9. *פרוטוקולים*: generate in Hebrew, Arabic or English; open for printing;
   close the process.
10. **Auditor** → *יומן ביקורת* → verify the chain; inspect `EARLY_OPEN_ATTEMPT`
    or `SEALED_ACCESS_DENIED` events if you triggered them.

To show an early-opening attempt, open one of the RFQs still accepting
submissions and press "פתיחת הכספת": it is refused and recorded as a critical
security event, and the auditor is alerted.
