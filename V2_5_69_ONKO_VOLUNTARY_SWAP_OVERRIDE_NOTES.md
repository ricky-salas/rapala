# V2.5.69 — ONKO VOLUNTARY SWAP OVERRIDE

- SYSTEM generator still forbids consecutive Onko RO days, including month-boundary carry-over.
- Bilateral voluntary swaps may create consecutive Onko RO days.
- Consecutive Onko becomes an ACK consequence row, not a swap hard block.
- Both affected participants must satisfy the normal consequence-ACK flow.
- True ABSOLUTE HARD swap blockers remain unchanged: justified absence, overlap, >12 h/day, <11 h rest, active hard rolling caps, mandatory rest and operational feasibility.
- SYSTEM fairness/post debt remains frozen; ACTUAL schedule changes.
