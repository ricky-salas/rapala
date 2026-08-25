# V2.5.91 — COLORED FINALIZATION + CONTROLLED SWAP WINDOW

## Locked monthly lifecycle

DRAFT → SWAP OPEN → SWAP CLOSED / R.S. OVERSIGHT → FINAL FOR ADMINISTRATION.

- SYSTEM is frozen when R.S. first confirms the month.
- ACTUAL starts equal to SYSTEM and changes only through approved operational actions.
- FINAL is an immutable snapshot of ACTUAL at R.S.'s final confirmation.
- FINAL also freezes the effective backup rows used by the administration Excel.
- Later Emergency/force-majeure ACTUAL changes do not rewrite SYSTEM or FINAL.

## R.S. control center

R.S. operates the lifecycle in **Grafikas → Grafiko tvirtinimas**. No new top-level profile/window was added.

The panel uses the same colored visual language as Apsikeitimai:
- blue = draft / not opened;
- orange = swap window open;
- red = deadline expired / new swaps blocked;
- amber = swap window closed / R.S. oversight / late-access stage;
- green = FINAL for administration.

R.Š. retains embedded senior/admin capabilities from V2.5.90 but is NOT allowed to open/close/finalize this administration lifecycle. R.S. alone is the operational lifecycle owner.

## First confirmation

R.S. chooses:
- swap-window length in days (1–14);
- exact deadline time (default 20:00 Lithuania time).

The first confirmation is fail-closed for real email readiness:
- SMTP must be configured;
- every active resident must have an email in account settings.

Then the app:
1. revalidates draft + exact targets + frozen requests + HARD;
2. plans and freezes SYSTEM backups;
3. publishes SYSTEM baseline and initializes ACTUAL;
4. persists fairness history;
5. opens the server-side swap window;
6. sends real email to every resident with exact deadline and personal ICS.

## Real email integration

Existing SMTP delivery is reused. Required Streamlit/environment secrets:
- SCHEDULER_SMTP_HOST
- SCHEDULER_SMTP_PORT (default 587)
- SCHEDULER_SMTP_USER (if provider requires auth)
- SCHEDULER_SMTP_PASSWORD (if provider requires auth)
- SCHEDULER_SMTP_USE_TLS (default 1)
- SCHEDULER_EMAIL_FROM
- SCHEDULER_PUBLIC_URL (recommended)

Opening the normal swap window is blocked if SMTP is not configured or any resident email is missing. Failed sends are logged and R.S. gets a resend button.

## Swap deadline enforcement

New normal and backup swap requests no longer rely only on UI visibility. They are created through SECURITY DEFINER V2.5.91 RPCs.

After the deadline:
- new requests are server-rejected;
- existing requests may still be accepted/rejected;
- a resident-accepted normal swap still requires R.S. final apply;
- R.S. alone performs the normal-swap senior apply step.

Direct INSERT policies for new normal/backup swap requests are removed, preventing client-side bypass.

## Late resident access

After R.S. closes the normal swap window she can grant an individual exception:
- resident;
- duration (1–168 h in UI);
- number of new requests (1–5 in UI);
- audit reason.

The grant is server stored, can be revoked, and sends a real email. Only that resident receives the temporary ability to create new swaps. Everyone else remains closed.

## Final gate

R.S. can create FINAL only when:
- lifecycle state is SWAP CLOSED;
- current ACTUAL passes HARD validation;
- no pending normal requests;
- no resident-accepted normal swaps await R.S. apply;
- no pending backup swap requests;
- no active unconsumed late-access grants.

R.S. must explicitly check a final confirmation box and press **PATVIRTINTI GALUTINĮ GRAFIKĄ ADMINISTRACIJAI**.

The server verifies that the submitted snapshot exactly equals authoritative ACTUAL, then freezes:
- final_json;
- final_backups;
- finalized_at;
- finalized_by.

## FINAL Excel

Only after FINAL does R.S. receive the primary:
**ATSISIŲSTI FINAL EXCEL ADMINISTRACIJAI**.

The workbook is visibly labeled `FINAL — ADMINISTRACIJAI` and uses the frozen FINAL backup snapshot, not later live backup rows.

Before FINAL, the Schedule tab may provide clearly labeled ACTUAL exports, but they are not the administration FINAL.

## Reset

Month reset clears lifecycle + late-access state while the month is not FINAL. Once FINAL exists, reset is blocked by the database (`RESET_BLOCKED_FINAL_SCHEDULE`).


## FINAL cohort email
After R.S. successfully confirms the immutable FINAL schedule, the app automatically sends the final cohort email using the same real SMTP path.

Lithuanian subject:
`FINAL — <month> grafikas paskelbtas. Crack on, radistai!`

The body first states clearly that the FINAL schedule has been published and submitted to administration, confirms that ordinary and late swaps are closed, attaches each resident's final `.ics`, and ends with the light closing:
`Viskas. Crack on, radistai — gero mėnesio ir kuo mažiau netikėtų „gal gali mane pakeist?“ žinučių.`

The existing FINAL-email resend control uses the same template.
