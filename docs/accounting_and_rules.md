# Chart of Accounts and System Rules

This document explains how the accounting system is structured and all the business rules enforced in the LUBOSS 95 Village Banking system.

## Table of Contents
1. [Chart of Accounts](#chart-of-accounts)
2. [Account Creation Process](#account-creation-process)
3. [System Rules and Validations](#system-rules-and-validations)

---

## Chart of Accounts

The system uses a double-entry bookkeeping approach with a hierarchical chart of accounts. Accounts are organized by type and can be either organization-level (shared) or member-specific (individual).

### Account Types

The system uses five standard accounting account types:

1. **ASSET** - Resources owned by the organization or receivables
2. **LIABILITY** - Obligations owed by the organization
3. **INCOME** - Revenue earned by the organization
4. **EXPENSE** - Costs incurred by the organization
5. **EQUITY** - Net worth of the organization

### Organization-Level Accounts (Core Accounts)

These accounts are created during initial system setup and are shared across all members:

#### Asset Accounts
- **`BANK_CASH`** - Main bank account where all cash deposits are recorded
- **`SOC_FUND_REC`** - Social Fund Receivable (organization's receivable from all members for social fund contributions)
- **`ADM_FUND_REC`** - Admin Fund Receivable (organization's receivable from all members for admin fund contributions)

#### Liability Accounts
- **`SOCIAL_FUND`** - Social Fund Payable (legacy account, maintained for compatibility)
- **`ADMIN_FUND`** - Admin Fund Payable (legacy account, maintained for compatibility)

#### Income Accounts
- **`INTEREST_INCOME`** - Interest income earned from loans
- **`PENALTY_INCOME`** - Penalty income from late payments and compliance violations

#### Equity Accounts
- **`CARRY_FORWARD`** - Carry-forward reserve for end-of-cycle distributions

### Member-Specific Accounts

These accounts are created automatically for each member when needed. Each member has their own set of accounts:

#### Member Savings Account
- **Account Code**: `MEM_SAV_{member_short_id}`
- **Account Type**: LIABILITY
- **Purpose**: Tracks member's accumulated savings
- **When Created**: Automatically created when member makes their first deposit or when running `setup_ledger_accounts.py`

#### Member Social Fund Account
- **Account Code**: `MEM_SOC_{member_short_id}`
- **Account Type**: ASSET (for receivable tracking)
- **Purpose**: Tracks member's social fund contributions and outstanding balance
- **When Created**: 
  - Automatically created when member makes their first declaration for a cycle
  - Or when running `setup_ledger_accounts.py`

#### Member Admin Fund Account
- **Account Code**: `MEM_ADM_{member_short_id}`
- **Account Type**: ASSET (for receivable tracking)
- **Purpose**: Tracks member's admin fund contributions and outstanding balance
- **When Created**: 
  - Automatically created when member makes their first declaration for a cycle
  - Or when running `setup_ledger_accounts.py`

#### Member Penalties Payable Account
- **Account Code**: `PEN_PAY_{member_short_id}`
- **Account Type**: LIABILITY
- **Purpose**: Tracks penalties owed by the member
- **When Created**: 
  - Automatically created when a penalty is approved for the member
  - Or when running `setup_ledger_accounts.py`

#### Member Loans Receivable Account
- **Account Code**: `LOAN_REC_{member_short_id}`
- **Account Type**: ASSET
- **Purpose**: Tracks loans issued to the member (principal amount)
- **When Created**: 
  - Automatically created when a loan is approved and disbursed
  - Or when running `setup_ledger_accounts.py`

### Account Naming Convention

- **Organization accounts**: Use descriptive codes (e.g., `BANK_CASH`, `INTEREST_INCOME`)
- **Member accounts**: Use prefix + member short ID pattern:
  - `MEM_SAV_` - Member Savings
  - `MEM_SOC_` - Member Social Fund
  - `MEM_ADM_` - Member Admin Fund
  - `PEN_PAY_` - Penalties Payable
  - `LOAN_REC_` - Loans Receivable

The `member_short_id` is the first 8 characters of the member's UUID (without hyphens).

---

## Account Creation Process

### Initial Setup

When the system is first set up, run the following script to create all core accounts:

```bash
python scripts/setup_ledger_accounts.py
```

This script:
1. Creates all organization-level accounts if they don't exist
2. Creates member-specific accounts for all existing members
3. Prevents duplicate account creation

### Dynamic Account Creation During Operation

The system automatically creates member accounts as needed during normal operations:

#### 1. First Declaration for a Cycle
When a member makes their **first declaration** for a cycle:
- **Social Fund Account** is created (if it doesn't exist)
- **Admin Fund Account** is created (if it doesn't exist)
- **Organization receivable accounts** (`SOC_FUND_REC`, `ADM_FUND_REC`) are created if missing
- **Initial required amounts** are posted:
  - Debit: Member's Social Fund account (annual required amount)
  - Credit: Organization's `SOC_FUND_REC` account
  - Debit: Member's Admin Fund account (annual required amount)
  - Credit: Organization's `ADM_FUND_REC` account

#### 2. Deposit Approval
When the Treasurer approves a deposit:
- **Member Savings Account** is created if missing
- **Member Social Fund Account** is created if missing (for social fund payments)
- **Member Admin Fund Account** is created if missing (for admin fund payments)
- **Member Penalties Payable Account** is created if missing (for penalty payments)
- **Organization receivable accounts** are created if missing

#### 3. Loan Disbursement
When a loan is approved and disbursed:
- **Member Loans Receivable Account** is created if missing
- Journal entries are posted to record the loan

#### 4. Penalty Approval
When the Treasurer approves a penalty:
- **Member Savings Account** is created if missing (penalties are deducted from savings)
- **Member Penalties Payable Account** is created if missing
- Journal entries are posted to record the penalty

### Account Lifecycle

- **Creation**: Accounts are created on-demand when first needed
- **Status**: All accounts are marked as `is_active = True` by default
- **Deactivation**: Accounts can be deactivated but are never deleted (for audit trail)
- **Uniqueness**: Account codes must be unique across the system

---

## System Rules and Validations

The system enforces numerous business rules to ensure data integrity and compliance with village banking policies. These rules are categorized below:

### 1. Declaration Rules

#### Declaration Creation
- ✅ **One Declaration Per Month**: A member cannot create multiple declarations for the same month and cycle
- ✅ **Active Member Required**: Only members with `ACTIVE` status can create declarations
- ✅ **Active Cycle Required**: Declarations can only be created for active cycles

#### Declaration Editing
- ✅ **Current Month Only**: Declarations can only be edited for the current month (cannot edit previous months)
- ✅ **Status Restriction**: Only `PENDING` declarations can be edited (unless explicitly allowed after rejection)
- ✅ **No 20th Day Restriction**: Current month declarations can be edited anytime (previous restriction removed)

#### First Declaration Special Handling
- ✅ **Initial Posting**: On the first declaration for a cycle, the system automatically posts:
  - Annual Social Fund required amount as a **debit** to member's Social Fund account
  - Annual Admin Fund required amount as a **debit** to member's Admin Fund account
  - Corresponding **credits** to organization receivable accounts
- ✅ **Duplicate Prevention**: Initial postings are only made once per cycle (checked before posting)

### 2. Deposit Approval Rules

#### Deposit Proof Validation
- ✅ **Status Check**: Only `SUBMITTED` deposit proofs can be approved
- ✅ **Declaration Required**: Deposit proof must be linked to a valid declaration
- ✅ **Amount Validation**: All declared amounts must be non-negative

#### Journal Entry Posting
When a deposit is approved, the system creates a balanced journal entry:

**For Savings:**
- Debit: `BANK_CASH` (full deposit amount)
- Credit: Member Savings Account (declared savings amount)

**For Social Fund Payment:**
- Debit: Member Social Fund Account (payment amount - shown as debit per user requirement)
- Credit: `SOC_FUND_REC` (organization receivable - reduces receivable)

**For Admin Fund Payment:**
- Debit: Member Admin Fund Account (payment amount - shown as debit per user requirement)
- Credit: `ADM_FUND_REC` (organization receivable - reduces receivable)

**For Penalties:**
- Credit: Member Penalties Payable Account (reduces liability)

**For Interest on Loan:**
- Credit: `INTEREST_INCOME` (income earned)

**For Loan Repayment:**
- Credit: Member Loans Receivable Account (reduces asset/loan balance)

- ✅ **Balance Validation**: All journal entries must balance (total debits = total credits)
- ✅ **Account Creation**: Missing member accounts are automatically created during approval

### 3. Loan Rules

#### Loan Application
- ✅ **Active Member**: Only active members can apply for loans
- ✅ **Active Cycle**: Loans can only be applied for in active cycles
- ✅ **Eligibility Check**: Loan amount must not exceed borrowing limit based on:
  - Member's savings balance
  - Credit rating tier multiplier
  - Cycle-specific borrowing limit policy
- ✅ **Single Active Loan**: Members can only have one active loan at a time
- ✅ **Pending Application Edit**: Pending loan applications can be edited or withdrawn

#### Loan Approval and Disbursement
- ✅ **Status Check**: Only `PENDING` loan applications can be approved
- ✅ **Approval Required**: Loan must be approved before disbursement
- ✅ **Journal Entry**: On disbursement:
  - Debit: Member Loans Receivable Account
  - Credit: `BANK_CASH`
- ✅ **Account Creation**: Member Loans Receivable account is created if missing

#### Loan Repayment
- ✅ **Declaration-Based**: Loan repayments are declared in monthly declarations
- ✅ **Principal vs Interest**: Repayments are split into principal and interest based on loan terms
- ✅ **Balance Reduction**: Principal portion reduces the loan receivable balance

### 4. Penalty Rules

#### Penalty Creation
- ✅ **Penalty Type Required**: Penalty record must have a valid penalty type
- ✅ **Fee Amount Validation**: Penalty type must have a valid fee amount (> 0)

#### Penalty Approval
- ✅ **Status Check**: Only `PENDING` penalties can be approved
- ✅ **No Duplicate Posting**: Penalties that are already `POSTED` cannot be approved again
- ✅ **Account Creation**: Member Savings and Penalties Payable accounts are created if missing
- ✅ **Journal Entry**: On approval:
  - Debit: Member Savings Account (penalty deducted from savings)
  - Credit: Member Penalties Payable Account (reduces liability)
  - Credit: `PENALTY_INCOME` (income earned)

### 5. Accounting Rules

#### Journal Entry Validation
- ✅ **Double-Entry Balance**: Every journal entry must balance (total debits = total credits)
- ✅ **Account Existence**: All accounts referenced in journal entries must exist
- ✅ **Account Type Consistency**: Debits and credits must align with account types:
  - **ASSET accounts**: Debits increase, Credits decrease
  - **LIABILITY accounts**: Credits increase, Debits decrease
  - **INCOME accounts**: Credits increase (income), Debits decrease
  - **EXPENSE accounts**: Debits increase (expenses), Credits decrease

#### Balance Calculations

**Savings Balance:**
- Sum of all credits to member savings account (deposits)
- Minus any debits (penalties, withdrawals)

**Loan Balance:**
- Sum of all debits to member loans receivable account (loan disbursements)
- Minus all credits (loan repayments)

**Social Fund Balance:**
- Shows accumulated payments made (sum of payment debits/credits)
- Initial required amount is posted as debit on first declaration
- Payments are posted as debits to member account

**Admin Fund Balance:**
- Shows accumulated payments made (sum of payment debits/credits)
- Initial required amount is posted as debit on first declaration
- Payments are posted as debits to member account

**Penalties Balance:**
- Sum of all credits to penalties payable account (penalties assessed)
- Minus all debits (penalties paid)

### 6. Member Status Rules

#### Member Activation
- ✅ **Approval Required**: Members must be approved by Chairman before activation
- ✅ **Status Transition**: Members move from `PENDING` → `ACTIVE` upon approval
- ✅ **Suspension**: Active members can be suspended (status: `SUSPENDED`)
- ✅ **Reactivation**: Suspended members can be reactivated by Chairman

#### Member Access
- ✅ **Active Status Required**: Only `ACTIVE` members can:
  - Create declarations
  - Apply for loans
  - Upload deposit proofs
  - Access member dashboard features
- ✅ **Suspended Members**: Suspended members cannot perform transactions but can view their account history

### 7. Cycle Management Rules

#### Cycle Creation
- ✅ **Unique Year**: Each cycle must have a unique year
- ✅ **Date Validation**: Start date must be before end date (if end date is set)
- ✅ **Required Amounts**: Social Fund and Admin Fund required amounts can be set per cycle

#### Cycle Activation
- ✅ **Single Active Cycle**: Only one cycle can be active at a time
- ✅ **Status Transition**: Cycles move from `DRAFT` → `ACTIVE` upon activation

#### Cycle Closure
- ✅ **Active Status Required**: Only `ACTIVE` cycles can be closed
- ✅ **Status Transition**: Cycles move from `ACTIVE` → `CLOSED` upon closure
- ✅ **Reopening Restriction**: Only closed cycles can be reopened
- ✅ **Year Restriction**: Cycles from previous years cannot be reopened

### 8. Credit Rating Rules

#### Credit Rating Assignment
- ✅ **Cycle-Specific**: Credit ratings are assigned per cycle
- ✅ **Tier Validation**: Credit rating must belong to a valid tier in the cycle's credit rating scheme
- ✅ **Borrowing Limit**: Borrowing limit is calculated as:
  - `Savings Balance × Credit Rating Multiplier`
  - Subject to cycle-specific borrowing limit policy maximum

#### Interest Rate Calculation
- ✅ **Tier-Based**: Interest rates are determined by credit rating tier
- ✅ **Term-Based**: Different interest rates apply to different loan terms
- ✅ **Range Validation**: Interest rates must fall within the tier's allowed range
- ✅ **Special Rule**: LOW RISK tier starts at 8% in new cycles

### 9. User Registration and Authentication Rules

#### Registration
- ✅ **Email Uniqueness**: Email addresses must be unique across all users
- ✅ **NRC Uniqueness**: National Registration Card (NRC) numbers must be unique (if provided)
- ✅ **Admin Approval**: New registrations require admin approval before access
- ✅ **Password Requirements**: Passwords are hashed using bcrypt

#### Authentication
- ✅ **Active Status Check**: Suspended members cannot log in
- ✅ **JWT Tokens**: Authentication uses JWT tokens with expiration
- ✅ **Role-Based Access**: Access to endpoints is controlled by user roles

### 10. File Upload Rules

#### Deposit Proof Upload
- ✅ **File Size Limit**: Deposit proof files must be within size limits
- ✅ **File Type Validation**: Only allowed file types can be uploaded
- ✅ **One Proof Per Declaration**: Each declaration can have one deposit proof
- ✅ **Storage**: Files are stored in `uploads/deposit_proofs/` directory

### 11. Data Integrity Rules

#### Transaction Integrity
- ✅ **No Orphaned Records**: All journal entries must reference valid accounts
- ✅ **Reversal Tracking**: Reversed journal entries are tracked (not deleted)
- ✅ **Audit Trail**: All transactions include:
  - Creation timestamp
  - Creator user ID (if applicable)
  - Source type and reference
  - Cycle association

#### Referential Integrity
- ✅ **Foreign Key Constraints**: All foreign key relationships are enforced
- ✅ **Cascade Rules**: Appropriate cascade behaviors for related records
- ✅ **Unique Constraints**: Account codes, email addresses, and NRC numbers must be unique

### 12. Display and Calculation Rules

#### Balance Display
- ✅ **Social/Admin Fund**: Cards show accumulated payments (not outstanding balance)
- ✅ **Non-Negative Balances**: All balances are displayed as non-negative values
- ✅ **Currency Formatting**: All amounts are displayed in Kwacha (K) with proper formatting

#### Transaction History
- ✅ **Initial Requirements**: Marked with "Required Amount" badge (orange background)
- ✅ **Payments**: Marked with "Payment" badge (purple background)
- ✅ **Chronological Order**: Transactions displayed in reverse chronological order (newest first)
- ✅ **Source Tracking**: Each transaction shows its source type (declaration, deposit approval, etc.)

---

## Summary

The LUBOSS 95 system implements a comprehensive set of business rules to ensure:

1. **Financial Accuracy**: Double-entry bookkeeping with automatic balance validation
2. **Data Integrity**: Comprehensive validation at every step
3. **Audit Trail**: Complete transaction history with source tracking
4. **Flexibility**: Automatic account creation as needed
5. **Compliance**: Enforcement of village banking policies and procedures

All rules are enforced at the service layer, ensuring consistent behavior across all API endpoints and preventing invalid data from entering the system.
