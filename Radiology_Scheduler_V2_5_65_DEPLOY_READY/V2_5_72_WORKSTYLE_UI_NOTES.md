# V2.5.72 — WORKSTYLE UI CLEANUP

- Built directly on V2.5.71 double-fairness + shift-length workstyle.
- Resident-facing workday-length selector now talks only about desired hours, not backend double-shift allocation.
- Display order: Mostly 6h → Mostly 12h → Mixed → No preference.
- Values and solver semantics are unchanged: 1=6h, 3=12h, 2=mixed, 0=neutral.
- The preference remains private account settings data.
- Backend double total, double spread <=2, critical-double targeting, exact workload, Onko pair/recovery, and V2.5.69 voluntary-swap behavior are unchanged.
