# Migration Business Rules

## Transaction Transformation Rules

1. **Savings Deposits**
   - Split total amount: 50% savings, K20 social fund, K30 admin fund
   - Post to: Bank Cash (debit), Member Savings + Social Fund + Admin Fund (credits)

2. **Loan Disbursements**
   - Post to: Loans Receivable (debit), Bank Cash (credit)

3. **Repayments**
   - Split principal and interest based on loan terms
   - Post to: Bank Cash (debit), Loans Receivable (principal credit), Interest Income (interest credit)

4. **Penalties**
   - Post to: Member Savings (debit), Penalty Income (credit)

## Validation Rules

- All journal entries must balance (debits = credits)
- Member totals must match between old and new systems
- Group totals (bank cash, loans receivable, social/admin funds) must match
