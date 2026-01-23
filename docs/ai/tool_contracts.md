# AI Tool Contracts

## Tool Specifications

### get_my_account_summary
- **Input**: user_id, cycle_id (optional)
- **Output**: Account summary (savings, loans, status)
- **Access**: User-scoped (only own account)

### get_my_loans
- **Input**: user_id
- **Output**: List of member's loans
- **Access**: User-scoped

### get_my_penalties
- **Input**: user_id, cycle_id (optional)
- **Output**: List of member's penalties
- **Access**: User-scoped

### get_my_declarations
- **Input**: user_id, month (optional)
- **Output**: List of member's declarations
- **Access**: User-scoped

### explain_interest_rate
- **Input**: loan_amount, months, borrow_count, credit_tier
- **Output**: Interest rate calculation and explanation
- **Access**: Policy calculation (no user data)

### get_policy_answer
- **Input**: query (text)
- **Output**: Relevant policy chunks with citations
- **Access**: RAG retrieval (public policies)

## Audit Logging

All tool calls and AI responses are logged to `ai_audit_log` table for compliance and debugging.
