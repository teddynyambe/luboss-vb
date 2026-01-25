# Monthly Cycle Rules Documentation

## Overview

The Village Banking system operates on **annual cycles** with **monthly recurring phases**. Each cycle contains multiple phases that repeat monthly throughout the year. This document codifies the rules governing monthly cycle operations as implemented in the system.

## Cycle Structure

### Annual Cycles

- Each cycle represents a **financial year** (e.g., 2024, 2025, 2026)
- Cycles have a `start_date` and `end_date` (typically one year apart)
- Only **one cycle can be ACTIVE** at any given time
- Cycle statuses: `DRAFT`, `ACTIVE`, `CLOSED`

### Cycle Phases

Each cycle contains multiple phases that define when specific activities can occur:

1. **DECLARATION** - Period for members to submit monthly declarations
2. **LOAN_APPLICATION** - Period for members to apply for loans
3. **DEPOSITS** - Period for members to submit deposit proofs
4. **PAYOUT** - Period for payouts (future implementation)
5. **SHAREOUT** - Period for shareouts (future implementation)

## Monthly Phase Configuration

### Phase Properties

Each phase can be configured with the following properties:

- **`monthly_start_day`**: Day of month (1-31) when the phase starts each month
- **`monthly_end_day`**: Day of month (1-31) when the phase ends each month
- **`penalty_type_id`**: Optional penalty type to apply for late submissions
- **`auto_apply_penalty`**: Boolean flag indicating if penalties should be automatically applied
- **`is_open`**: Boolean flag indicating if the phase is currently open (can be manually toggled)

### Phase Order

Phases have a predefined order within a cycle:
1. DECLARATION (order: "1")
2. LOAN_APPLICATION (order: "2")
3. DEPOSITS (order: "3")

## Monthly Cycle Rules

### 1. Declaration Phase Rules

#### Declaration Period
- **Start**: Day 1 of each month (implicit - declarations can be made from the start of the month)
- **End**: `monthly_end_day` of the effective month (e.g., day 20)
- **Effective Month**: The month for which the declaration is being made

#### Declaration Submission Rules

1. **Timing**:
   - Declarations can be submitted for the **current month** or **future months**
   - Declarations cannot be submitted for **past months** (unless editing a rejected declaration). This also accounts for profit allocation. Such a declaratioin will not benefit from profit sharing in that month because funds where not available for borrowing.
   - Only **one declaration per member per month per cycle** is allowed

2. **Late Declaration Penalties**:
   - If `auto_apply_penalty` is enabled and `monthly_end_day` is set:
     - Declaration is considered **late** if submitted **after** `monthly_end_day` of the effective month
     - Example: If `monthly_end_day = 20` and effective month is January 2026:
       - Declaration submitted on or before January 20, 2026 → **On time** (no penalty)
       - Declaration submitted after January 20, 2026 → **Late** (penalty applied)
   - Late penalties are **automatically created** with `APPROVED` status
   - Penalty notes include: "Late Declaration - Declaration made after day {monthly_end_day} of {month} {year}"

3. **Declaration Status Workflow**:
   - **PENDING**: Initial status when declaration is created
   - **PROOF**: Status when member uploads deposit proof
   - **APPROVED**: Status when treasurer approves the deposit proof
   - **REJECTED**: Status when treasurer rejects the deposit proof (resets to PENDING for editing)

4. **Declaration Editing Rules**:
   - Declarations can only be edited if:
     - Status is `PENDING` (or `APPROVED` if `allow_rejected_edit=True`)
     - Current date is within the **effective month** (cannot edit previous months)
     - No restriction on day of month (can edit current month declarations anytime)

5. **Rejected Declaration Editing**:
   - When a deposit proof is rejected, declaration status resets to `PENDING`
   - Member can then edit and resubmit the declaration
   - Editing is allowed even if past the `monthly_end_day` for rejected declarations

### 2. Loan Application Phase Rules

#### Loan Application Period
- **Start**: Day 1 of each month (implicit)
- **End**: `monthly_end_day` of the current month (e.g., day 15)

#### Loan Application Submission Rules

1. **Timing**:
   - Loan applications can be submitted during the loan application phase
   - Applications are tied to the **current cycle** and **current month**

2. **Late Application Penalties**:
   - If `auto_apply_penalty` is enabled and `monthly_end_day` is set:
     - Application is considered **late** if submitted **after** `monthly_end_day` of the current month
     - Example: If `monthly_end_day = 15`:
       - Application submitted on or before day 15 → **On time** (no penalty)
       - Application submitted after day 15 → **Late** (penalty applied)
   - Late penalties are **automatically created** with `APPROVED` status
   - Penalty notes include: "Late Loan Application - Application made after day {monthly_end_day} of {month} {year}"

### 3. Deposits Phase Rules

#### Deposit Period
- **Start**: `monthly_start_day` of the **effective month** (e.g., day 26 of January)
- **End**: `monthly_end_day` of the **next month** (e.g., day 5 of February)
- **Example**: If `monthly_start_day = 26` and `monthly_end_day = 5`:
  - Deposit period for January 2026: January 26, 2026 to February 5, 2026
  - Deposit period for February 2026: February 26, 2026 to March 5, 2026

#### Deposit Proof Submission Rules

1. **Timing**:
   - Deposit proofs can be uploaded during the deposit period
   - Deposit period spans from the `monthly_start_day` of the effective month to the `monthly_end_day` of the next month
   - Deposit proofs are linked to a specific declaration

2. **Late Deposit Penalties**:
   - If `auto_apply_penalty` is enabled and `monthly_end_day` is set:
     - Deposit is considered **late** if submitted **after** `monthly_end_day` of the **next month**
     - Example: For January 2026 declaration with `monthly_start_day = 26` and `monthly_end_day = 5`:
       - Deposit period: January 26, 2026 to February 5, 2026
       - Deposit submitted on or before February 5, 2026 → **On time** (no penalty)
       - Deposit submitted after February 5, 2026 → **Late** (penalty applied)
   - Late penalties are **automatically created** with `APPROVED` status
   - Penalty notes include: "Late Deposits - Deposit submitted after day {monthly_end_day} of {next_month} (Deposit period: {start_day} of {effective_month} to {end_day} of {next_month})"

3. **Deposit Status Workflow**:
   - **SUBMITTED**: Initial status when deposit proof is uploaded
   - **APPROVED**: Status when treasurer approves the deposit
   - **REJECTED**: Status when treasurer rejects the deposit

4. **Declaration Status Update**:
   - When deposit proof is uploaded → Declaration status changes to `PROOF`
   - When deposit proof is approved → Declaration status changes to `APPROVED` and journal entries are posted
   - When deposit proof is rejected → Declaration status resets to `PENDING` (member can edit and resubmit)

## Automatic Penalty Application

### Penalty Creation Rules

1. **Automatic Application**:
   - Penalties are **automatically created** when:
     - `auto_apply_penalty = True` for the phase
     - `monthly_end_day` is configured
     - `penalty_type_id` is set
     - The submission is late (after the deadline)

2. **Penalty Status**:
   - Cycle-defined penalties are created with `APPROVED` status (auto-approved)
   - No manual approval required for cycle-defined penalties

3. **Duplicate Prevention**:
   - System checks for existing penalties before creating new ones
   - Checks are based on:
     - Member ID
     - Penalty type ID
     - Effective month/year (for declarations)
     - Notes containing the month/year (for deposits and loan applications)

4. **Penalty Notes Format**:
   - **Late Declaration**: "Late Declaration - Declaration made after day {monthly_end_day} of {month} {year} (Declaration period ends on day {monthly_end_day})"
   - **Late Loan Application**: "Late Loan Application - Application made after day {monthly_end_day} of {month} {year}"
   - **Late Deposit**: "Late Deposits - Deposit submitted after day {monthly_end_day} of {next_month} (Deposit period: {start_day} of {effective_month} to {end_day} of {next_month})"

## Phase Opening/Closing

### Manual Phase Control

- Phases can be manually opened/closed via API endpoints:
  - `POST /api/chairman/cycles/{cycle_id}/phases/{phase_id}/open` - Open a phase
  - `POST /api/chairman/cycles/{cycle_id}/phases/{phase_id}/close` - Close a phase
- When a phase is closed, activities for that phase are restricted
- When a phase is open, activities can occur within the monthly date ranges

### Automatic Phase Control (Future)

- Currently, phases are controlled manually
- Future enhancement: Automatic phase opening/closing based on `monthly_start_day` and `monthly_end_day`

## Examples

### Example 1: Declaration Phase Configuration

**Configuration**:
- `monthly_end_day = 20`
- `auto_apply_penalty = True`
- `penalty_type_id = "late-declaration-penalty"`

**Scenario**: Member submits declaration for January 2026
- **On time**: Submitted on or before January 20, 2026 → No penalty
- **Late**: Submitted after January 20, 2026 → Penalty automatically created

### Example 2: Deposit Phase Configuration

**Configuration**:
- `monthly_start_day = 26`
- `monthly_end_day = 5`
- `auto_apply_penalty = True`
- `penalty_type_id = "late-deposit-penalty"`

**Scenario**: Member uploads deposit proof for January 2026 declaration
- **Deposit period**: January 26, 2026 to February 5, 2026
- **On time**: Submitted on or before February 5, 2026 → No penalty
- **Late**: Submitted after February 5, 2026 → Penalty automatically created

### Example 3: Loan Application Phase Configuration

**Configuration**:
- `monthly_end_day = 15`
- `auto_apply_penalty = True`
- `penalty_type_id = "late-loan-application-penalty"`

**Scenario**: Member submits loan application in January 2026
- **On time**: Submitted on or before January 15, 2026 → No penalty
- **Late**: Submitted after January 15, 2026 → Penalty automatically created

## Implementation Details

### Code Locations

1. **Cycle Model**: `app/models/cycle.py`
   - Defines `Cycle`, `CyclePhase`, `PhaseType`, `CycleStatus`

2. **Declaration Creation**: `app/services/transaction.py::create_declaration()`
   - Checks for late declarations and creates penalties

3. **Deposit Proof Upload**: `app/api/member.py::upload_deposit_proof()`
   - Checks for late deposits and creates penalties

4. **Loan Application**: `app/api/member.py::create_loan_application()`
   - Checks for late loan applications and creates penalties

5. **Penalty Calculation**: `app/api/member.py::get_applicable_penalties()`
   - Calculates applicable penalties for declarations

### Database Schema

**cycle_phase table**:
- `monthly_start_day` (Integer, nullable) - Day of month when phase starts
- `monthly_end_day` (Integer, nullable) - Day of month when phase ends
- `penalty_type_id` (UUID, nullable) - Reference to penalty type
- `auto_apply_penalty` (Boolean, default=False) - Whether to auto-apply penalties
- `is_open` (Boolean, default=False) - Whether phase is currently open

## Best Practices

1. **Configuration**:
   - Set `monthly_start_day` and `monthly_end_day` for all recurring phases
   - Configure penalty types before enabling `auto_apply_penalty`
   - Test penalty logic with sample data before going live

2. **Monitoring**:
   - Monitor penalty creation to ensure rules are working as expected
   - Review late submissions to identify patterns
   - Adjust phase dates if needed based on member behavior

3. **Communication**:
   - Clearly communicate phase dates to members
   - Provide reminders before phase deadlines
   - Explain penalty rules in member documentation

## API Endpoints

### Cycle Management
- `POST /api/chairman/cycles` - Create cycle with phase configurations
- `PUT /api/chairman/cycles/{cycle_id}` - Update cycle and phase configurations
- `GET /api/chairman/cycles/{cycle_id}` - Get cycle details with phases
- `GET /api/chairman/cycles/{cycle_id}/phases` - Get cycle phases

### Phase Control
- `POST /api/chairman/cycles/{cycle_id}/phases/{phase_id}/open` - Open a phase
- `POST /api/chairman/cycles/{cycle_id}/phases/{phase_id}/close` - Close a phase

### Member Activities
- `POST /api/member/declarations` - Create declaration (checks for late submission)
- `PUT /api/member/declarations/{declaration_id}` - Update declaration (editing rules apply)
- `POST /api/member/deposits/proof` - Upload deposit proof (checks for late submission)
- `POST /api/member/loans/apply` - Submit loan application (checks for late submission)
- `GET /api/member/penalties/applicable` - Get applicable penalties for declaration

## Summary

The monthly cycle rules ensure:

1. **Structured Timeline**: Clear start and end dates for each phase type
2. **Automatic Enforcement**: Late penalties are automatically applied when configured
3. **Flexibility**: Phases can be manually controlled and configured per cycle
4. **Consistency**: Rules are consistently applied across all members
5. **Transparency**: Penalty reasons are clearly documented in penalty records

These rules are codified in the system code and enforced automatically when members interact with the system.
