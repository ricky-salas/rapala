# V2.5.99 — ROSTER INITIALS MIGRATION

## Current roster identifiers
- MG — Maleckaitė Gabrielė
- SA — Sveboda Arminas
- PV — Pileckienė Aistė
- SK — Stašinskas Kipras
- MŽ — Mažonavičius Ignas
- KE — Khatskeleva Elena
- VL — Volkovskaja Laura
- GB — Grumblys Justinas
- ŠR — Šalaševičius Rapolas
- SR — Steponavičiūtė Rosita
- SE — Stanišauskytė Eglė
- GD — Giedrimas Deivydas
- MR — Montvilaitė Reda
- GE — Gertas Ernestas
- SN — Stankevičiūtė Vytautė
- DU — Dulkė Sofija Ana

## Identity migration
The change is an identity-key migration, not a new resident roster. Existing person colors, role/target adjustment, linked accounts, settings, preferences, recurring rules, schedules, swaps, backup records, audit history and research data are moved to the new initials.

SR remains the operational Senior Scheduler with the -2 target adjustment. ŠR remains the researcher / contingency lifecycle operator. MG and the remaining residents remain resident-only.

Exact old initials are also rewritten inside stored schedule/research JSON payloads so an already published schedule does not retain mixed old/new identifiers.

## Solver regression protection
Only identity labels changed in the scheduling engine. Rule Profile and generated slot definitions are unchanged from V2.5.98. The V2.5.98 position-based backup, credit-only cover, Saturday/Sunday water-fill, Centro 120 PM, Mammography-last, workstyle preference and V2.5.96 SYSTEM/ACTUAL no-catch-up behavior remain in force.
