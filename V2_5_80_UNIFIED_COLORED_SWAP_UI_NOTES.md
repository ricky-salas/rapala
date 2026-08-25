# V2.5.80 — UNIFIED COLORED SWAP + BACKUP + RESCUE UI

All three operational tools now use the same visual language while preserving
their different workflows.

## Normal swaps
Selection remains:
- MY SHIFT dropdown
- OTHER RESIDENT'S SHIFT dropdown

Immediately below the selectors the chosen pair is rendered as:
- colored resident badges;
- MY SHIFT colored card;
- OTHER RESIDENT'S SHIFT colored card;
- date / weekday / department / block;
- bilateral arrow.

The normal swap functionality itself is unchanged:
request -> target accept/reject -> senior apply.

## Backup swaps
Selection remains:
- MY BACKUP DUTY
- OTHER RESIDENT'S BACKUP DUTY

The selected pair now renders using the same card system:
- colored backup-holder badges;
- MY BACKUP DUTY colored card;
- OTHER RESIDENT'S BACKUP DUTY colored card;
- date / department / block;
- covered resident displayed with their own resident color badge.

Backup-swap functionality is unchanged.

## Emergency Rescue
The one-way rescue continues to use:
CURRENT LOCATION -> MOVING TO -> RESCUED PERSON

The heading previously shown as `Vizualus emergency rescue` is now simply:
`Emergency Rescue`.

Functionality remains one-way:
- CURRENT LOCATION becomes vacant;
- mover goes to critical MOVING TO;
- RESCUED PERSON is released and is not swapped back.

## Design rule
Normal Swap, Backup Swap and Emergency Rescue share:
- resident color palette;
- rounded structured cards;
- consistent labels;
- date / block / workplace formatting;
- colored person identity badges.

They do NOT share business logic. Each workflow remains independent.

## Preservation
No scheduler-engine change.
No database migration.
V2.5.79 email notifications, one-way rescue, V2.5.78 atomic swap state,
V2.5.77 Friday water-fill and all earlier fairness rules are preserved.
