# V2.5.90 — SINGLE-WINDOW ROLE TRANSFER

## Final account model

Every authenticated user has exactly ONE visible account interface.
There is no Resident profile / Seniūnė profile switch.

Every user has:
- Paprastas
- Išplėstinis

### R.S. — Rosita Steponavičiūtė
Operational Seniūnė / leader.
Single Seniūnė-capable interface.
Has the former senior operational capabilities:
- senior dashboard
- generation / publish
- full summary / audit
- backups / swaps / emergency operations
- proof / senior guide
- rules administration in Advanced mode

Workload role:
- resident_directory.role = senior
- target_adjustment = -2

### R.Š. — Rapolas Šalaševičius
Single resident-facing account interface.
No profile selector.
Workload status remains ordinary resident:
- resident_directory.role = resident
- target_adjustment = 0

But the same R.Š. account embeds:
- researcher capabilities
- operational senior/admin capabilities
- operational generation
- full audit / rules controls
- isolated research-shadow generator
- AVAILABLE GPT + HUMAN vs MY ENGINE research comparison

Research-only tools remain mainly in Išplėstinis to keep Paprastas uncluttered.

### G.M. — Gabrielė Maleckaitė
Normal resident only.
No senior dashboard, generation/publish control, senior guide or senior rule administration.

Workload role:
- resident_directory.role = resident
- target_adjustment = 0

Historical G.M. research/comparator records are not rewritten.

## Research senior handoff

Prospective scheduler-workload checkpoints now follow the CURRENT operational Seniūnė (R.S.).
Historical G.M./L.V. retrospective questionnaire labels/data remain historical and unchanged.

## Identity safety

All V2.5.89 auth.uid() identity locks remain unchanged.
Role transfer does not weaken one-auth-user <-> one-resident binding.

## Live database

Migration `v2590_single_window_role_transfer` applied successfully:
- G.M. resident / 0
- R.S. senior / -2
- R.Š. resident / 0

No solver fairness constitution changed except the intended transfer of the senior -2 workload entitlement from G.M. to R.S.
