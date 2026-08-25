# V2.5.85 — FROZEN WORKLOAD CREDIT + ATOMIC EMERGENCY RESCUE

Monthly workload credit is fixed when SYSTEM is published.

After publication, normal swaps, backup/double swaps and Emergency Rescue never
add, subtract or transfer target units. ACTUAL may change placement and may contain
a vacancy, but target fulfillment remains the published SYSTEM ledger.

Example:
- SYSTEM A.P. = 28/28.
- A.P. is RESCUED from one 6 h critical slot.
- ACTUAL placement weight may become 27.0.
- workload credit remains 28/28.
- target delta remains 0.
- no work debt is created and no extra shift is generated.

The reason the rescued person did not work (sick leave, justified absence,
unexcused absence, etc.) is outside scheduler target accounting.

The engine keeps both concepts:
- workload_credit = frozen SYSTEM target credit;
- actual_assignment_workload = physical ACTUAL slot weight.

Emergency Rescue is now one SECURITY DEFINER transaction:
ACTUAL update + backup-plan sync + Rescue audit. If anything fails, the whole
transaction rolls back. The resident no longer directly upserts backup_assignments.

The RPC is idempotent, so a lost HTTP response and retry cannot apply Rescue twice.

Live migration `v2585_atomic_emergency_rescue` was applied to production Supabase.
