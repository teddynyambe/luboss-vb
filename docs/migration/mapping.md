# Migration Mapping

## Field Mappings

### User Table
- `id` (char(36)) → `id` (UUID)
- All other fields preserved as-is

### Transactions → Journal Entries
- Savings deposits → Debit Bank Cash, Credit Member Savings + Social + Admin
- Loan disbursements → Debit Loans Receivable, Credit Bank Cash
- Repayments → Debit Bank Cash, Credit Loans Receivable (principal) + Interest Income
- Penalties → Debit Member Savings, Credit Penalty Income

## ID Mapping Tables

- `id_map_user`: Maps old user IDs to new user IDs
- `id_map_member`: Maps old member IDs to new member_profile IDs
- `id_map_loan`: Maps old loan IDs to new loan IDs

## Source References

All journal entries include `source_ref` field linking to original old system record IDs for traceability.
