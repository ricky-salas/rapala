# V2.5.107 — HARD WISHES + EXPLICIT AUDIT

V2.5.107 changes the SYSTEM-generation constitution around resident-entered `Negaliu dirbti` / Unavailable blocks.

## Core rule

- Every `Negaliu dirbti` whole-day / AM / PM / recurring block is mandatory during SYSTEM generation.
- It is encoded as a real assignment prohibition and separately audited at zero violations.
- It is **not** a weighted penalty and cannot be traded for structural fairness or SOFT satisfaction.
- If mandatory availability cannot coexist with safety, coverage, exact workload and Onko parity, no SYSTEM draft is returned.

## Resilient zero-HARD fallback

The strict structural 0–1 work-pattern pass is still attempted first. If that strict structure is infeasible, the fallback preserves zero Resident-HARD and uses bounded feasibility tiers rather than a long weighted-optimum solve:

1. zero HARD + all exact date/block SOFT wishes + work-style targets;
2. if needed, zero HARD + all exact date/block SOFT wishes;
3. if needed, mandatory zero-HARD baseline only.

Anything relaxed remains visible in the wish audit. This keeps the hierarchy `mandatory availability -> fairness -> SOFT`, while avoiding the V2.5.105/V2.5.106 no-incumbent stall pattern.

## Generation-screen audit

After a successful draft, the senior sees:

- Active wishes
- Honored
- Missed
- Cannot-work violations

If `Missed = 0`, the UI shows **ALL ACTIVE WISHES MET**. If anything is missed, an **UNMET WISHES** table shows the exact resident/request/result. Any Cannot-work violation is treated as a critical invalid-draft condition.

## September 2026 regression

The real September request snapshot used for the production failure now returns a verified draft in about 28 seconds in the clean runner test:

- HARD errors: 0
- Resident-HARD violations: 0
- Exact workload targets: True
- Onko parity: True (22/22 slots)
- Active scored wishes: 77
- Honored wishes: 77
- Missed wishes: 0
- Cannot-work misses: 0
- Mean preference score: 100.0%
- Zero-HARD fallback wish mode: ALL_EXACT_PLUS_WORKSTYLE_FEASIBLE
- MG is fully off on 2026-09-11.
- VL receives requested Sundays 6, 13, 20 and 27.

Structural fairness is allowed to widen before any `Negaliu dirbti` block is violated, and the resulting spreads remain explicitly visible in diagnostics.
