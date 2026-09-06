# V2.5.122 — Weekend backup source fix

Fixes PostgreSQL `23514` on FCFS weekend backup selection.

Cause: the new FCFS RPC writes `source='self_fcfs'`, while the legacy table CHECK constraint still allowed only `self`, `auto`, and `senior`. The same mismatch would later have broken automatic random fill (`auto_random`) and operator corrections (`operator_manual`, `operator_manual_swap`).

The migration expands the constraint while preserving all legacy values. No schedule, preferences, claims, or audit rows are modified.

The app also now shows a readable schema-upgrade message if this exact mismatch is encountered on another environment.
