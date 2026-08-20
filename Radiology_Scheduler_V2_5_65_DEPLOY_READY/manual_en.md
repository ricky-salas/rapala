# Schedule rules

This document defines the resident monthly scheduling, publication, backup-cover, notification, and change workflow. The system aims to apply hard rules consistently, distribute burden transparently, and satisfy individual preferences whenever possible.

## 1. User roles

In V2.5 beta, every person has an individual email/password account. On first registration the account is linked to one resident identity using a one-time invite code. G.M. has the senior role, so the same login can switch between the **Resident profile** and the **Senior scheduler profile**.

### Resident profile

A resident can edit only their own monthly preferences and personal settings, view the published schedule and fairness information, view their backup-cover duties, export their own calendar, propose or accept voluntary swaps, and use the personal proof page to check how the schedule matched their requests.

A resident cannot generate, regenerate, publish, or directly edit the official schedule.

### Senior scheduler profile

The senior scheduler has all resident functions and can additionally review every resident's submitted preferences, see missing submissions and missing email addresses, generate/regenerate the draft, publish and lock the official baseline, edit the rules, manage backup-cover assignments, record the actual backup person when reality differs from the plan, and trigger reminder emails when email delivery is configured.

## 2. Preference deadline

Preferences for the next month are due **by the 13th day of the current month, inclusive**.

Every profile shows the exact deadline and the number of days remaining, or clearly states that the deadline has passed.

## 3. Account email and notifications

Every account should contain an email address.

Notifications are **on by default**. In Settings, each resident can turn them off or select the day of the month from which reminder emails should begin. While next month's preferences are still missing, reminders state how many days remain until the 13th-day deadline.

When the senior scheduler publishes and locks the schedule, the system prepares a publication message for every resident. When email delivery is configured, each resident receives a personalized `.ics` attachment that can be added to their calendar.

## 4. Settings, short-term, and long-term preferences

Persistent Settings contain the resident's normal work-style choices, notifications, reminder start day, and email.

### Short-term monthly preferences

For a specific month a resident can enter whole-day / AM / PM hard unavailability, requested days off, preferred work dates, an optional note, and how many accumulated backup bonuses to use for that month.

### Long-term recurring preferences

A recurring preference is linked to a **weekday name** rather than a date in one month. For example, a resident can prefer to work every Tuesday, prefer every Thursday off, or be hard-unavailable every Monday morning. The rule is automatically expanded into each future month until the resident changes or removes it.

A month-specific soft preference overrides an opposite recurring soft preference for that month. A recurring **hard** unavailability remains hard and cannot be overridden by a monthly soft request.

## 5. Priority order

1. **Hard rules** – may never be violated.
2. **Fairness** – burden and undesirable shifts are distributed as evenly as possible.
3. **Soft preferences** – optimized within the first two levels.
4. **Cosmetic optimization** – improves convenience and variety.

If the hard rules cannot be satisfied simultaneously, the system does not create a schedule.

## 6. Monthly workload

Base target:

**number of weekdays × 7.6 / 6**

The result is rounded to the nearest whole number. Official role adjustments are applied afterward. In the current configuration the senior scheduler receives a 2-shift reduction.

One Onko RO centre assignment is worth 1.5 workload units and each person's Onko count must be even.

## 7. Hard rules

Hard rules are never sacrificed for preference satisfaction or fairness.

### Hard unavailability

A resident may mark:

- **whole day** – no normal assignment and no backup duty that day;
- **morning only (08:00–14:00)** – no morning or full-day assignment and no backup duty for an overlapping morning/full-day shift;
- **afternoon only (14:00–20:00)** – no afternoon or full-day assignment and no backup duty for an overlapping afternoon/full-day shift.

If only one half-day is unavailable, the resident may still work or provide backup cover during the non-overlapping half-day.

Other hard rules include time-overlap limits, mandatory coverage, weekend uniqueness, the blocked Friday-afternoon mammography slot, exact workload targets, even Onko counts, and the requirement that **every filled normal shift has one eligible named backup**.


## 8. Double shifts and fatigue

A **double shift** means two compatible normal schedule assignments on the same day. It is not the same as backup cover.

The system penalizes long work streaks and undesirable double shifts and prefers a fresher alternative when feasible.

## 9. Backup cover

A **backup** is a specific resident assigned to cover **one specific normal-schedule shift** if needed.

Backups are generated **per shift by default**, not for an entire calendar day.

If a resident works a morning shift and an afternoon shift on the same day, the two shifts may have different backup residents. One person may cover both only if they are eligible during both time blocks.

### Eligibility for a specific shift

A resident can be a backup when:

1. they have no overlapping normal assignment during the covered shift;
2. they are not hard-unavailable during that time block;
3. they are not the resident who owns the covered shift.

Therefore a resident working only in the afternoon may still back up a morning shift, and vice versa. A full-day shift requires a backup who is free throughout the overlapping time.

### Complete coverage

Every filled normal-schedule shift must have **one planned backup**. If any filled shift has no eligible candidate, the schedule is not fully ready and publication is blocked.

When eligible capacity is limited, the same resident may cover several shifts. The system first minimizes simultaneous reuse, then balances total monthly backup burden and repeated resident pairings.

### Display and calendar

The Backup view and personal `.ics` calendar show the exact date, time block, covered resident, and department/shift. Backup calendar events use the same start and end time as the covered shift.

### Actual cover

If someone else actually provides cover, the senior scheduler may record an **actual backup**. The actual resident must also be eligible for that specific time block. Effective backup statistics then use the actual resident.

After an approved voluntary swap, the shift-level backup plan is recalculated from the new current schedule.


### Actual completed cover

Simply being scheduled or activated as a backup creates no credit. V2.5.5 uses a reciprocal typed ledger: the covering resident first settles oldest same-type WORK debt or earns a REST credit; the covered resident first consumes a free same-type REST credit or incurs same-type WORK debt. MORNING, AFTERNOON and NIGHT are separate and non-interchangeable. Full rules are described in the V2.5.5 reciprocal-ledger section below.

## 10. Fairness: how to read it

Fairness is **never above hard-rule validity**. V2.5.6 uses this hierarchy:

| Level | What is evaluated | Interpretation |
|---|---|---|
| **1. HARD validity** | Legal/rest, physical, availability and coverage hard constraints | **Must be 0 HARD errors.** A schedule with any HARD error cannot be published even if fairness is 100%. |
| **2. Cumulative fairness** | Equality of burden accumulated across all published months | This is the **primary long-term fairness objective**. One month may intentionally look less even if it repairs earlier imbalance. |
| **3. Monthly fairness** | Equality inside the selected month only | Secondary diagnostic showing how even that specific month is. |
| **4. Soft preferences / cosmetics** | Individual wishes and work-style preferences | Optimized only inside the feasible/fair envelope. |

### Why there are two fairness percentages

**Monthly fairness** asks: “Was this particular month distributed evenly?”

**Cumulative fairness** asks the more important question: “Across all months, is the system preventing the same residents from repeatedly carrying more inconvenient burden?”

A month can therefore have lower Monthly fairness while improving Cumulative fairness by compensating for prior imbalance.

### Formula

Both use:

**Fairness = 100 − 18 × weekend spread − 7 × Friday spread − 4 × double-shift spread − 2 × weekday-day spread**

Spread means `maximum − minimum` across residents. Scores are floored at 0%.

| Component | Penalty per spread unit |
|---|---:|
| Weekends | **−18** |
| Fridays | **−7** |
| Double shifts | **−4** |
| Distinct weekday-days | **−2** |

Monthly fairness uses counts from the selected month only.

Cumulative fairness first sums each resident's weekends, Fridays, doubles and weekday-days across all prior published months plus the selected month, then calculates the spreads.

In V2.5.6 all four components are truly cumulative. Earlier beta logic carried only weekend history forward.

### What does 92% mean?

It is a technical equality indicator, not “92% good / 8% bad.” For example, if all spreads are zero except double-shift spread = 2:

**100 − 4 × 2 = 92%**

### Why 100% may be impossible

100% requires spread 0 in all four components. A single month often cannot achieve this because shift counts may not divide evenly among 16 residents, the number of weekends/Fridays varies, HARD availability constrains options, targets can differ, and the system may deliberately repair earlier cumulative imbalance.

Read the result in this order:

**0 HARD errors → highest possible Cumulative fairness → Monthly fairness → soft preferences.**

### Fairness history graph

The Transparency page plots both values over time:

- **Cumulative fairness** shows long-term group equality;
- **Monthly fairness** shows equality inside each individual month.

### SYSTEM FAIRNESS vs ACTUAL work

V2.5.7 keeps two separate ledgers:

- **SYSTEM FAIRNESS ledger** — what the algorithm assigned at publication;
- **ACTUAL work ledger** — what the resident actually works after voluntary swaps.

A swap that is **bilaterally and voluntarily accepted** is fairness-neutral.

Example: the system assigned Friday to A and Tuesday to B. A and B voluntarily trade. In the actual schedule B now works Friday, but the fairness ledger still attributes the Friday burden to A because that was the system's assignment. B must not receive a future cumulative penalty for a duty B voluntarily chose to accept.

Therefore a bilateral voluntary swap:
- does **not change Monthly fairness**;
- does **not change Cumulative fairness**;
- does not alter future algorithmic compensation;
- but does change the ACTUAL schedule, calendars, rest/HARD validation and actual-work audit.

This prevents artificial fairness spread caused purely by resident preference trades.

A non-voluntary administrative reassignment is different and should be recorded as a separate event type that may update the fairness ledger.

The publication-time SYSTEM FAIRNESS ledger remains auditable and is used for future cumulative balancing.

## 11. Individual preference fulfillment

Each resident receives a preference-fulfillment percentage calculated only from categories in which they expressed an active preference. Neutral categories are excluded.

The transparency page shows the group cumulative-fairness percentage, the person's preference-fulfillment percentage at publication, the current personal percentage after voluntary changes, and the personal-vs-cumulative-fairness balance ratio. The balance ratio is the smaller percentage divided by the larger one. **1.00** means the two percentages are at the same level. It is an alignment measure, not an absolute quality measure, so both percentages must also be considered.

## 12. Personal proof page

After publication, every resident receives a Proof page showing point by point whether hard-unavailable dates were respected, which requested days off were honored or missed, which preferred work dates were hit or missed, whether the chosen weekday/weekend/distribution/double-shift style was achieved, and whether the exact workload target was maintained.

Soft-preference mismatches are shown clearly and can be addressed through voluntary swap requests when a safe alternative exists.

## 13. Publication

The senior scheduler first generates a draft. Only the senior scheduler can publish and lock it. Publication preserves the original baseline and its fairness statistics.

## 14. Swaps

In the shared V2.5 beta, both residents must still voluntarily accept the swap. Because final hard-rule validation uses private availability data from the whole group, the senior scheduler performs the final apply step after mutual acceptance. The senior cannot create mutual consent on behalf of the two residents; the senior only runs final validation and, if it passes, the system applies the swap and recalculates backups.


A resident proposes a specific assignment-for-assignment swap, the other resident accepts or rejects it, and an accepted request takes effect only after all hard rules are revalidated. The locked baseline remains preserved and voluntary swaps do not reduce the baseline fairness score.

## 15. Transparency

Every resident can view hard-rule validation, the frozen publication fairness score, component spreads, individual preference fulfillment, the personal-versus-group balance ratio, requested days-off fulfillment, and maximum consecutive workdays.

## 16. Permanent colors

Each resident keeps one fixed color across months, schedule views, summaries, swaps, backup-cover views, and exports.

## 17. Export

Residents can download a personal `.ics` file containing normal shifts and backup-cover events, and the group can export a formatted colored `.xlsx` month-grid schedule with a summary sheet.

## 18. Language

The interface has separate LT and EN modes. Languages are not mixed within a mode.


## Labour-law and rest-safety rules — V2.5.2

This is a hard safety layer, not a substitute for an individual employment contract or formal institutional working-time accounting.

- Morning 08:00–14:00 + Afternoon 14:00–20:00 may be assigned to the same resident on the same day: this is a 12-hour workday. The 11-hour rule applies between separate workdays/shifts, not between the two 6-hour parts of the same workday.
- Known scheduled work may not exceed 12 hours in one workday.
- At least 11 consecutive hours of rest must remain between separate workdays. With current hours, 20:00 → next-day 08:00 leaves 12 hours.
- No more than 6 working days may occur in any 7 consecutive calendar days.
- Known work in this scheduler may not exceed **48 hours in any rolling 7-day period**. The generator additionally aims for about **40h/7d** and water-fills weekly workload across residents.
- With current 08:00–20:00 limits, one whole calendar day off creates at least 36 consecutive hours of rest, conservatively protecting the ≥35-hour weekly-rest minimum.
- Entering the **start date** of a real >12–24h or 24h duty blocks the entire following calendar day from ordinary shifts as a conservative ≥24h post-duty rest safeguard.
- `Justified absence` is a hard no-work date and proportionally reduces the internal monthly target so approved absence is not automatically worked back.
- A 38-hour/week contractual norm is deliberately not hard-coded in V2.5.2.
- The 48-hour provision is not converted into a simple hard 48h/rolling-7-days cap because it is an average-working-time requirement tied to the applicable accounting/reference period.
- The system can validate only work it knows about; unentered work for other employers prevents complete cross-employer legal validation.

Legal basis: Lithuanian Labour Code Articles 114 and 122 and official State Labour Inspectorate guidance on maximum working time and minimum rest. Institution-specific rules must be reviewed before using the software as a complete legal-compliance determination.

## Backups — V2.5.2 LOCKED

**Backups are assigned only on weekends.**

- Every filled Saturday/Sunday SPS RO duty shift must have a named backup.
- Monday–Friday shifts receive no backups and reserve no backup capacity.
- Missing weekday backup never blocks publication; missing weekend backup does.
- A weekend backup must be free during the covered time block and hard-available then.
- Weekend backup events remain optional in the personal `.ics`.
- The senior may activate a concrete weekend backup when cover is actually needed; email alerting follows the resident's settings.
- Credits are awarded only after actual cover is marked completed: 6h = +1, 12h = +2.
- The `weekends only` rule is **LOCKED** in this version and must not be changed silently.


## Weekend backup self-selection — V2.5.3 LOCKED

- Target: **one weekend backup duty per resident per month** when there are 16 weekend shifts and 16 residents.
- Each resident selects one free weekend backup slot before the preference deadline.
- Slots are **first come, first served**. One self-reservation per resident/month and one resident per slot.
- A claimed backup time block becomes a hard planning reservation against overlapping normal work.
- Residents who do not choose by the deadline lose selection priority and enter the first-priority automatic-assignment pool for remaining unclaimed weekend duties.
- Months with more than 16 weekend slots may require a second backup duty for some residents; overflow is balanced as eligibility allows.
- A separate reminder is sent when the deadline approaches and no backup slot has been selected.
- After publication, backup-day changes use the Swaps tab.
- Backup swaps are bilateral, eligibility-checked, and unavailable after activation/completion.
- Cover credits remain tied only to actual completed cover.


## Reciprocal cover ledger — V2.5.5 LOCKED

A planned or merely activated backup duty creates no credit. Balances change only after the senior marks a concrete backup as **actual completed cover**.

Three types are tracked separately:

- **MORNING** = 08:00–14:00, 6h;
- **AFTERNOON** = 14:00–20:00, 6h;
- **NIGHT** = 20:00–08:00, 12h.

When resident A actually covers resident B:

1. For A, the system first checks same-type WORK debt. If A has one, the oldest same-type debt is settled. Only if no such debt exists does A receive a new REST credit.
2. For B, the system first checks for a free, unredeemed and unreserved same-type REST credit. If one exists, it is consumed as an offset and no new debt is created. Otherwise B receives a new same-type WORK debt.

A rest credit already reserved for a future month is protected and is not automatically consumed by a later cover event.

### Rest credits

- Rest credits are valid for **12 months from the actual cover date**.
- MORNING and AFTERNOON credits each reduce the current daytime workload target by one shift when redeemed.
- A resident may redeem at most **2 daytime rest credits in total per month**. This prevents accumulated credits from making a future schedule infeasible.
- Credits may be banked and used in a chosen future month, allowing short rest periods / “mini holidays” within the monthly cap.
- The current PGY1 engine has no normal NIGHT slots. NIGHT credits are therefore bank-only and cannot reduce daytime workload.
- MORNING and AFTERNOON balances remain separately tracked even though both currently reduce the unified daytime target 1:1.

### Work debts

A work debt means the resident was actually covered and owes future same-type cover work.

Repayment is not forced in the immediately following month:

- **0–2 months:** banked, no extra priority;
- **3–5 months:** soft priority for same-type automatic backup opportunities;
- **6–11 months:** strong priority;
- **12+ months:** OVERDUE, highest priority, and the debt remains active until actually settled.

The 12-month date is an operational obligation. Because actual need for cover cannot be mathematically guaranteed, an overdue debt does not disappear; it remains visible and receives highest assignment priority.

A debt is settled only by **actual completed same-type cover**, not by merely being scheduled as standby.

### Interaction with first-come selection

Resident self-selection remains **first come, first served**. Debt priority never takes away a self-reserved slot. Debt age affects only automatic assignment of remaining unclaimed weekend backup slots. A 6+ month debt may outrank the ordinary non-selector penalty queue; 12+ month overdue debt has highest automatic priority.

If an actual-cover event was recorded by mistake, the senior may undo it only while the resulting credit/debt effects have not already been used downstream.


## Department Observer read-only account — V2.5.8 LOCKED

A separate **Department Observer** role is provided for departmental administration. It is not a Senior Scheduler account and has no schedule-management powers.

The observer can see:

- the **SYSTEM baseline** schedule at publication;
- the **ACTUAL** current schedule after bilateral voluntary swaps;
- a direct table of normal assignments that changed from baseline to actual;
- normal-shift swap history and statuses;
- weekend-backup swap history and statuses;
- weekend backup overview: planned backup, actual backup, activation and actual-cover status;
- HARD validity, Monthly fairness, Cumulative fairness and component breakdown;
- the fairness history chart across months;
- the current Manual / rules.

The observer **cannot** generate or publish schedules, approve/reject/finalize swaps, edit assignments or backups, activate/complete cover, edit fairness history, edit the Manual, or change account roles.

Private resident preference data are deliberately excluded: HARD-unavailable dates, personal preference notes, absence details, emails/notification settings and individual rest-credit/work-debt balances are not displayed.

The observer sees only operational scheduling information required for oversight: resident names/initials, assigned/current shifts, swap records and backup status.

The two schedule views have different purposes:

1. **SYSTEM baseline** = what the algorithm assigned and what the fairness ledger records.
2. **ACTUAL** = what is operationally valid now after approved voluntary swaps.

A bilateral voluntary swap remains fairness-neutral: ACTUAL work changes while SYSTEM FAIRNESS does not. This lets department administration understand both the original allocation and the real current staffing situation.

Observer access is activated using a separate one-time invite code and is always visibly marked **READ ONLY**.

## Research window (V2.5.9 RESEARCH BETA)

All residents have a **Research** tab where they can complete a short baseline (“Before use”) or follow-up (“After use”) survey. The same core 1–5 items are repeated so paired change can later be calculated.

R.Š. and G.M. have an additional research dashboard showing operational metrics for the selected month (HARD errors, monthly/cumulative fairness, preference fulfilment, normal swaps, backup swaps, actual cover events and SYSTEM→ACTUAL changes) together with group survey summaries.

Privacy: G.M. sees aggregated group survey results and anonymous comments only. The R.Š. researcher view may additionally inspect de-identified individual records using a pseudonymous code; resident names/initials are not displayed next to responses. Research responses are stored separately from scheduling preferences.

The current survey is a project-specific v0.1 instrument, not a finalized validated psychometric scale. Before formal publication, the questionnaire/protocol should undergo methodology and ethics/IRB review as applicable.


## LOCKED FAIRNESS RULE — WORKPLACE / MODALITY DIVERSITY

Each month the system should expose every resident to as many different workplaces as feasible:
CENTRO RO, Onko RO, SPS RO, Centro UG, SPS UG, ADC 144, ADC 145, Pediatric US, and Mammography.

This is a core longitudinal fairness principle, but not an absolute feasibility constraint. HARD safety,
legal-rest rules, unavailability, and workload targets remain higher priority. If equal exposure cannot be
achieved in a month because of those constraints or real slot supply, the schedule is not invalid. The
published SYSTEM exposure history is carried forward and the solver preferentially reduces the imbalance
during the next feasible shifts and following months.

Each workplace is balanced across residents separately. The solver also maximizes the number of distinct
workplaces experienced by each resident within the month and avoids unnecessary repeated placement in the
same workplace when an equivalent valid allocation exists.



## LOCKED V2.5.32 — BACKUP COVERAGE SCOPE

Named backup is mandatory for:
- every weekend shift;
- every weekday **SPS RO d.d.** shift;
- every weekday **SPS UG 1035** AM and PM shift.

Before the selection deadline, a resident may reserve multiple concrete backup slots from these groups. A reserved backup slot is a real generator input: the resident cannot receive overlapping normal work in the same time block. Each covered slot can have only one self-claim. Remaining required backups are auto-assigned subject to HARD availability, non-overlapping normal work and balanced backup load.

This rule is implemented in the engine, DB reservation layer, publication validation and Backup UI.


## V2.5.50 — two-dimensional preference fairness

Preferences are optimized on two axes. **Vertically**, strict priority is: ABSOLUTE HARD → RESIDENT HARD → SOFT-1 → SOFT-2 → SOFT-3. A higher rank is locked before the solver moves downward.

| Rank | Includes | Principle |
|---|---|---|
| ABSOLUTE HARD | Labour/rest safety, approved sickness/leave, physical impossibility | 100% mandatory; never relaxed |
| RESIDENT HARD | Unavailable — date, AM, PM, recurring | Zero losses first; if impossible, minimum total loss plus horizontal water-filling |
| SOFT-1 | Want time off; structured double/recovery avoidance | Protect personal time and recovery first |
| SOFT-2 | Want to work — exact date / AM / PM | Positive placement into desired work time |
| SOFT-3 | Dispersed or clustered month | Overall month shape; generic weekend/weekday direction is no longer scored as SOFT in V2.5.52+ |

**Horizontally**, progressive filling / water-filling is used inside each rank. For request counts `2,2,2,4`, the engine first aims for `2,2,2,2`, then attempts the remaining two requests of the fourth resident. For `2,2,3,4`, it protects `2,2,2,2` first and only then optimizes the remaining `0,0,1,2`. Raw request volume therefore does not buy extra priority.

## V2.5.52 — critical exposure, golden-middle guardrails and POST DEBT

V2.5.52 defines three co-equal critical structural categories: **SPS RO, SPS UG and weekends**. They sit immediately below TRUE ABSOLUTE HARD. Each uses layered water-filling: every eligible resident receives the first exposure unit before anyone receives a second, then the second before a third, and so on. The constitutional raw max–min target/ceiling is **0–1 whenever mathematically feasible**. Ordinary SOFT preferences cannot widen this critical corridor to 2.

This protects both educational exposure and fatigue. Among schedules with equal critical counts, the engine also minimizes clustered exposure: consecutive weekends (including across the previous-month boundary) and unnecessary consecutive SPS RO / SPS UG days are penalized.

The remaining posts — CENTRO RO, Onko RO, Centro UG, ADC 144, ADC 145, Paediatric UG and Mammography — also use water-filling. Ideal spread is 0–1 and the normal monthly guardrail is **≤2**. **≤3** is allowed only as an explicitly diagnosed exceptional last resort when ≤2 is infeasible inside higher-rank locks. Legitimate SOFT may use flexibility within 0–2 but cannot break the critical SPS/weekend 0–1 corridor.

Temporary ordinary-post imbalance is recorded as **POST DEBT**. Positive debt means a resident is owed future exposure to that post and receives catch-up priority; negative debt means overexposure and later extra units are deferred. POST DEBT is a compensation mechanism, not permission to create poor current-month balance.

SOFT input is whitelist-based. Accepted signals are exact personal-time/work-date requests (`Want free`, `Prefer to work`), structured recovery/double avoidance, and the dispersed-versus-concentrated month-shape signal. Broad “no weekends”, “fewer weekdays”, or station-selection requests (“only SPS RO”, “no Mammography”, “more CENTRO RO”) are not ordinary SOFT. A genuine physical/legal restriction must be recorded through the appropriate HARD class.

SOFT retains two-dimensional fairness: vertical SOFT-1 → SOFT-2 → SOFT-3 ranking and horizontal resident water-filling within each rank, so raw request volume cannot buy extra priority.


## V2.5.53 — weekly load and recovery water-filling

V2.5.53 adds a separate **temporal workload** matrix: resident × calendar week / rolling 7-day window. The monthly target must not be front-loaded into a 60-hour week for one resident while peers are comparatively light.

| Layer | Rule | Status |
|---|---|---|
| Rolling 7 days | Maximum **48 known scheduled hours** | TRUE ABSOLUTE HARD; Rule Profile may only tighten |
| Rolling 7 days | Maximum **6 worked days** — at least one fully free day | TRUE ABSOLUTE HARD |
| Weekly target | First minimize the worst excess above **~40h/7d**, then total excess and the calendar-week hour spread across residents | STRUCTURAL WATER-FILL |
| After one 12h double day | A second double on the next day is strongly discouraged; one shift or rest is preferred | STRUCTURAL RECOVERY |
| After two consecutive 12h double days | The next day may be **PM-only or fully free**; fully free is preferred | HARD RECOVERY + structural preference |
| Three consecutive double days | Prevented by the preceding rule | HARD |

The weekly-load frontier is locked before lower-priority ordinary-post and SOFT optimization. A later preference therefore cannot recreate a 60h week, remove the required free day, or create a three-double sequence.


## V2.5.54 — voluntary normal-shift swap >48h acknowledgement

- Generation/regeneration still never plans more than 48 known hours in a rolling 7-day window and continues to target about 40h/7d.
- After publication, only a bilateral voluntary **normal-shift swap** may exceed the 48h ceiling.
- The platform previews the ACTUAL post-swap schedule. If that swap increases an affected resident's rolling-7 maximum above 48h, the resident sees the projected maximum and the affected rolling-7 windows and must explicitly acknowledge the exceedance.
- If both residents newly exceed 48h because of the swap, both must acknowledge separately.
- The acknowledgement is stored in the ACTUAL swap audit with the swap ID, resident and accepted rolling-7 cap.
- This is an exception to the 48h ceiling only. Daily-hour limits, minimum rest, the rolling workday/free-day rule, post-double recovery, approved absence, overlap/coverage/eligibility and protection against new Resident-HARD conflicts remain mandatory.
- The exception does not apply to forced/admin repairs.
- SYSTEM fairness remains frozen; ACTUAL satisfaction and workload diagnostics are recalculated after the swap.

## V2.5.56 — unplanned absence and critical SPS rescue

After publication, sickness, leave, another approved absence or force majeure changes only the **ACTUAL** schedule. The published SYSTEM schedule and fairness history remain frozen.

If the absent resident was assigned to **SPS RO or SPS UG**, critical coverage must remain filled. The operational hierarchy is:

1. First find a resident already working the same day / overlapping time block in a **lower-priority non-mandatory post** (e.g. CENTRO RO, Centro UG, ADC, Paediatric UG, Mammography).
2. Move that resident into the critical SPS post; their optional donor post may remain vacant.
3. A critical SPS post is never sacrificed as a donor for a lower-priority station.
4. Onko is not used automatically as a donor because it has a separate monthly coverage rule.
5. Only if no safe same-block optional-post transfer exists may a target-block-free resident fallback be used.
6. Among feasible choices, avoid new Resident-HARD losses first, then minimize structural spread damage and additional repair burden.

The emergency pull-down may create an extra optional gap in the ACTUAL schedule. This is accepted because mandatory SPS coverage has higher operational priority; the original SYSTEM gap plan and fairness baseline remain frozen for audit/research.

## V2.5.57 — fairness-neutral post-publication repair exposure

A justified post-publication repair (sickness, approved leave, force majeure) changes the **ACTUAL** operational schedule, not the algorithmic fairness allocation.

If a resident originally scheduled in SPS RO / SPS UG becomes unavailable, the system first pulls a resident who is already working the same overlapping block in a lower-priority optional post. Because that donor resident was already scheduled to work that time block, the station change is treated as **fairness-neutral**.

Therefore:

- SYSTEM fairness remains tied to the publication baseline;
- SYSTEM workplace spread remains tied to the publication baseline;
- post debt / future catch-up is not changed by the repair;
- weekend/double/fairness-history burden is not changed by the repair;
- actual workplace exposure may be displayed separately for operational/audit purposes, but it is explicitly **NOT FAIRNESS**;
- donor ranking for same-block SPS pull-down does not use workplace spread or post debt as a fairness criterion; first avoid new Resident-HARD losses, then use deterministic operational selection.

The SYSTEM matrix answers “what did the algorithm allocate?”, while the ACTUAL matrix answers “where did residents actually work after swaps/repairs?”. Longitudinal fairness and research fairness use the SYSTEM matrix.


## V2.5.58 — Public-holiday allocation

Settings now include one persistent normalized SOFT signal: **prefer holiday work**, **neutral**, or **prefer holiday rest**. This is not a right to claim or avoid every holiday.

Official Lithuanian public holidays use a dedicated preference-cohort water-fill layer after ABSOLUTE HARD, critical SPS/weekend equality, Resident-HARD and weekly-recovery locks. Holiday duty goes to holiday-work volunteers first, neutral residents next, and holiday-rest residents only when coverage requires it. Within each cohort, one holiday unit is distributed across peers before a second unit is given to the same person, and prior published SYSTEM holiday burden is used for longitudinal rotation.

A statutory holiday falling on a weekday uses the non-working-day SPS RO AM/PM duty pattern rather than ordinary outpatient rows. The holiday preference enters the frozen ORIGINAL request ledger only in months that actually contain public holidays. Post-publication swaps/repairs do not rewrite SYSTEM holiday burden.

## SENIOR USABILITY AND AUDIT WORKFLOW — V2.5.59

The senior workflow is **Generate → Audit claims → Correct only exceptions → Publish**. Before publication, inspect HARD diagnostics, critical SPS RO / SPS UG / weekend 0–1 spread, worst weekly load and a spot-check of concrete preference/post claims for 3–5 residents. The aim is exception-focused human oversight rather than manually recounting the entire schedule. See the **Senior guide** tab and `SENIOR_USABILITY_GUIDE_EN.md`.

## V2.5.61 — voluntary backup takeover with explicit acknowledgement

When a backup is actually needed, planning-comfort thresholds alone should not automatically block a volunteer. A new 12-hour day, >40/>48-hour rolling load, a six-day work streak, consecutive 12-hour days, or a voluntary self-override of Resident-HARD is shown in a concrete consequence table and may be accepted explicitly.

This is not an “ignore all rules” control. ABSOLUTE blockers remain non-overrideable: justified absence / mandatory post-duty rest, overlapping work, >12 hours in one workday, <11 hours of uninterrupted daily rest, >6 workdays in 7 consecutive days, or the active Rule Profile maximum 7-day swap/backup cap. The 48-hour threshold is shown as a warning signal; the employer remains responsible for the exact legal work-time regime.


## Emergency swap — recording an already occurred change

When an urgent operational change has already happened, either the senior scheduler or one of the involved residents can record it in Swaps → Emergency. The two original assignments are selected, ACTUAL is updated immediately, and the published SYSTEM fairness baseline remains unchanged.

If the senior records the event, both residents see a 🔔 until they mark the record as seen/correct. If a resident records it, that resident is marked as seen immediately and the other participant receives the acknowledgement prompt. The end-of-month final operational schedule is reconstructed from ACTUAL, so urgent changes are not lost in messages or memory.

The Emergency subsection is not for a future planned swap; use the standard voluntary-swap workflow for that.

## V2.5.63 — fairness corridor failsafe
Before returning a SYSTEM draft, the scheduler must verify an acceptably even workplace distribution. SPS RO, SPS UG and weekends normally differ by at most one assignment between the most- and least-exposed resident; other main workplaces normally differ by at most two. A timeout is not treated as proof that a wider imbalance is necessary. Concrete SPS dates remain flexible so personal requests can still be honored whenever the same overall equality can be preserved safely.

## V2.5.65 — sparse-post first exposure, approved vacation, and automatic calendar subscription

### First exposure in a sparse educational post

When a post has relatively few monthly slots but enough for at least one assignment per eligible resident, the scheduler first tries to give **everyone one exposure** before giving another resident an avoidable second exposure. This is especially relevant to Onko RO, Centro UG, and pediatric US. SPS RO, SPS UG, and weekends remain as equal as mathematically feasible. A particular date is not locked to a resident merely to protect monthly post balance: if the same total can be preserved on another date while better honoring a request, the scheduler should use the better placement.

### Approved vacation / leave

`Preferences` contains a separate **Approved vacation / leave days** field. This is not a soft wish. No normal assignment or backup may be scheduled on those dates, and the resident's monthly workload target is reduced proportionally so approved leave does not create an artificial fairness deficit.

### Preference-deadline reminders

The notification setting explicitly refers to reminders about the **preference submission deadline**. The concrete deadline date for the selected schedule month is shown next to the setting.

### My calendar schedule

A resident can:
- download a one-time `.ics` snapshot;
- subscribe once to a private iCalendar URL;
- use the Google Calendar, Apple Calendar, or Outlook Calendar handoff/instructions;
- use the standard `.ics` file or iCalendar URL for another compatible calendar app.

The subscription contains all published ACTUAL months and is refreshed after a new publication and important ACTUAL changes (normal swaps, emergency changes, repairs, and actual backup changes). Changing the setting that includes backups in the personal calendar refreshes the feed as well.

The private calendar URL contains a long random bearer token and must be treated like a password. Resident initials and the account UUID are not exposed in the public feed path.
