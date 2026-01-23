# Migration Validation Checklist

## Per-Member Validation

- [ ] Total deposits match
- [ ] Loan principal outstanding matches
- [ ] Interest paid matches
- [ ] Penalties posted match

## Group-Level Validation

- [ ] Bank cash balance matches
- [ ] Total loans receivable matches
- [ ] Social fund total matches
- [ ] Admin fund total matches

## Data Integrity

- [ ] All journal entries balance
- [ ] All ID mappings are complete
- [ ] No orphaned records
- [ ] All source references are valid

## Run Validation

```bash
python scripts/migrate_validate.py
```
