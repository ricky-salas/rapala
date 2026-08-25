# V2.5.77 — FRIDAY + ALL-POST STRUCTURAL WATER-FILL

## New SYSTEM HARD rule
Friday exposure is now structural water-filling.

For every generated SYSTEM schedule:
- count all filled Friday assignments;
- divide by the resident count;
- every resident must fall inside floor(total/N)..ceil(total/N);
- raw Friday max-min spread must therefore be 0–1.

Preferred Friday dates still count as Friday exposure. They are SOFT and cannot
break the structural Friday corridor.

Example from September 2026:
- 72 Friday assignments / 16 residents = 4.5;
- correct water-fill = 8 residents x4 + 8 residents x5;
- observed regression result: raw Friday spread = 1.

## Interaction with all-post water-fill
Phase 1 now chooses exact workload/date/block patterns while enforcing:
- exact monthly workload;
- even Onko 0/2/4...;
- weekend structural fairness;
- double structural fairness;
- Friday floor/ceil raw spread 0–1.

Phase 2 then jointly assigns every non-Onko post label under the V2.5.74
all-post structural water-fill. Thus Friday reallocation and post-label
reallocation cooperate rather than treating workplace balance as an afterthought.

## ACTUAL voluntary swaps
Post-publication mutually accepted swaps may make Friday distribution uneven.
Friday fairness is NOT a voluntary-swap blocker, matching the existing rule for
workplace/post exposure.

True safety/work-time HARD rules still apply.
V2.5.73 exact monthly workload equality and even Onko parity remain non-relaxable.

## September 2026 regression
PASS:
- HARD errors: 0
- Friday counts: only 4 or 5
- Friday total: 72
- Friday raw spread: 1
- CENTRO RO spread: 1
- SPS RO spread: 1
- SPS UG spread: 1
- Centro UG spread: 1
- ADC 144 spread: 1
- ADC 145 spread: 1
- Vaikų UG spread: 1
- Mamografijos spread: 1
- Onko counts: only 0 or 2
- Onko spread: 2
- solve time in regression environment: ~33.5 s

## SYSTEM vs ACTUAL regression
A same-workload ordinary swap was tested that increased Friday spread from 1 to 3:
- validation_mode=SYSTEM/generation: REJECTED with Friday structural HARD error;
- validation_mode=voluntary_swap: ALLOWED with 0 hard errors.

No Supabase schema migration required.
