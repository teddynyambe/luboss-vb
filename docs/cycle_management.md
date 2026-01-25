# Cycle Management Documentation

## Overview

The Village Banking system operates on annual cycles. Each cycle represents a financial year during which members can make declarations, apply for loans, and make deposits.

## Cycle Lifecycle

### Cycle Statuses

1. **DRAFT**: Newly created cycle, not yet active
2. **ACTIVE**: Currently active cycle - members can make declarations and apply for loans
3. **CLOSED**: Completed cycle - no new activities allowed

### Creating a New Cycle

When a new cycle is created via `/api/chairman/cycles`:
- Status is set to **DRAFT** by default
- Cycle phases are configured (Declaration, Loan Application, Deposits)
- Credit rating scheme can be configured
- The cycle is NOT automatically activated

### Activating a Cycle

When a cycle is activated via `/api/chairman/cycles/{cycle_id}/activate`:

1. **Automatic Deactivation**: All other ACTIVE cycles are automatically set to DRAFT
   - This ensures only ONE cycle is active at a time
   - Prevents conflicts and confusion

2. **Cycle Activation**: The selected cycle status is set to ACTIVE

3. **Account Continuity**: 
   - Account balances (savings, loans, funds) are preserved via the ledger
   - Balances carry forward from previous cycles
   - No account reset occurs

4. **Member Access**: 
   - Members can now see the active cycle in their dashboard
   - Members can make declarations for the new cycle
   - Members can apply for loans in the new cycle

### Closing a Cycle

When a cycle is closed via `/api/chairman/cycles/{cycle_id}/close`:

1. **Cycle Status**: Set to CLOSED
2. **Phase Closure**: All phases in the cycle are closed
3. **Activity Restriction**: 
   - No new declarations can be made
   - No new loan applications can be submitted
   - Historical data remains accessible

4. **Account Preservation**:
   - Account balances remain in the ledger
   - Balances carry forward to the next cycle
   - No account reset or closing entries are created

## Account Handling Between Cycles

### Key Principle: **Accounts Never Close**

The system uses a **double-entry ledger** where:
- All transactions are recorded as journal entries
- Account balances are calculated from the ledger
- Balances persist across cycles

### What Happens to Accounts?

1. **Savings Accounts**: 
   - Balance carries forward
   - New savings in the new cycle are added to existing balance

2. **Loan Accounts**:
   - Outstanding loan balances carry forward
   - New loans in the new cycle are added
   - Repayments reduce the balance regardless of cycle

3. **Fund Accounts** (Social Fund, Admin Fund):
   - Balances carry forward
   - New contributions are added to existing balance

4. **Penalty Accounts**:
   - Outstanding penalties carry forward
   - New penalties are added to existing balance

### Cycle-Specific Data

The following data is tied to specific cycles:
- **Declarations**: Each declaration is tied to a cycle and effective month
- **Loan Applications**: Each application is tied to a cycle
- **Loans**: Each loan is tied to a cycle
- **Journal Entries**: Can optionally reference a cycle for reporting

## Workflow Example

### End of Year 2025, Starting Year 2026

1. **Before Cycle End**:
   - 2025 cycle is ACTIVE
   - Members making declarations and applying for loans
   - All transactions recorded in ledger

2. **Closing 2025 Cycle** (Manual action by Chairman):
   ```
   PUT /api/chairman/cycles/{2025_cycle_id}/close
   ```
   - 2025 cycle status → CLOSED
   - All phases closed
   - No new activities allowed for 2025

3. **Creating 2026 Cycle** (Manual action by Chairman):
   ```
   POST /api/chairman/cycles
   ```
   - 2026 cycle created with status DRAFT
   - Phases configured
   - Credit rating scheme configured

4. **Activating 2026 Cycle** (Manual action by Chairman):
   ```
   PUT /api/chairman/cycles/{2026_cycle_id}/activate
   ```
   - 2025 cycle (if still ACTIVE) → DRAFT
   - 2026 cycle → ACTIVE
   - Members can now see 2026 cycle
   - Account balances carry forward automatically

5. **Member Experience**:
   - Member dashboard shows 2026 as active cycle
   - Savings balance from 2025 is still visible
   - Member can make new declarations for 2026
   - Member can apply for new loans in 2026

## Important Notes

1. **No Automatic Cycle Closing**: Cycles must be manually closed by the Chairman
2. **No Automatic Cycle Activation**: New cycles must be manually activated
3. **Account Balances Never Reset**: All balances persist across cycles
4. **Historical Data Preserved**: All declarations, loans, and transactions remain accessible
5. **Only One Active Cycle**: The system enforces that only one cycle can be ACTIVE at a time

## API Endpoints

- `POST /api/chairman/cycles` - Create a new cycle (status: DRAFT)
- `PUT /api/chairman/cycles/{cycle_id}/activate` - Activate a cycle (deactivates others)
- `PUT /api/chairman/cycles/{cycle_id}/close` - Close a cycle
- `GET /api/chairman/cycles` - List all cycles
- `GET /api/member/cycles` - Get active cycles (for members)

## Monthly Cycle Rules

For detailed documentation on monthly cycle rules, phase configurations, deadlines, and automatic penalty application, see:

**[Monthly Cycle Rules Documentation](./monthly_cycle_rules.md)**

This document covers:
- Monthly phase configuration (start/end days)
- Declaration phase rules and deadlines
- Deposit phase rules and deadlines
- Loan application phase rules and deadlines
- Automatic penalty application rules
- Phase opening/closing controls

## Future Enhancements

Potential improvements:
1. **Automated Cycle Closing**: Scheduled task to close cycles on end_date
2. **Cycle Transition Reports**: Generate reports when closing a cycle
3. **Balance Verification**: Verify ledger balances match cycle totals
4. **Cycle Opening Balances**: Optional opening balance entries for new cycles
5. **Automatic Phase Control**: Automatic phase opening/closing based on monthly_start_day and monthly_end_day
