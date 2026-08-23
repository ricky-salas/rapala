# V2.5.73 — ONKO EVEN ABSOLUTE + WORKSTYLE

## Non-negotiable invariant

Onko RO is a 9 h FULL day and equals **1.5 standard 6 h workload units**.
Therefore each resident's Onko count must always be **even**:

`0, 2, 4, 6, ...`

Counts `1, 3, 5, ...` are ABSOLUTE HARD errors in both SYSTEM and ACTUAL.

## Exact workload

The calculated monthly target is exact in all modes. Examples:

- target 28 -> exactly 28.0
- target 26 -> exactly 26.0

`27.5`, `28.5`, etc. are invalid and cannot be accepted by a voluntary swap.

## Monthly Onko supply parity

Only active, non-blocked Onko rows count toward monthly supply.

- even active supply -> fill all active Onko rows;
- odd active supply -> leave exactly one active Onko row unfilled;
- distribute the remaining filled Onko rows in resident pairs.

Example regression:

- August 2026: 21 active Onko rows -> 20 filled + 1 parity gap;
- September 2026: 22 active Onko rows -> all 22 filled.

## Voluntary swaps

V2.5.73 removes the old loophole that allowed ACTUAL swaps to break target equality or Onko parity.
A voluntary swap is blocked if it would create:

- odd Onko for either resident;
- half-unit monthly workload;
- any other true ABSOLUTE HARD violation.

The V2.5.69 consecutive-Onko rule remains a narrow ACK exception after publication: consecutive Onko may be acknowledged bilaterally when all true ABSOLUTE HARD constraints remain satisfied. This does not permit odd Onko or workload deviation.

## Fail-closed guard

The fast generation path now refuses to return an OK schedule unless the validator explicitly confirms:

- exact workload targets passed;
- even Onko pairs passed;
- actual filled Onko count equals expected even filled count.

## Preserved

- V2.5.71 double fairness + shift-length allocation;
- Shift Happens v3.0 display;
- V2.5.72 Workstyle UI/settings schema compatibility fix;
- hidden internal `_weekday` helper column;
- existing fairness, research, backup and operational architecture.
