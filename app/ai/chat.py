"""AI chat service - LLM integration."""
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, List
from groq import Groq
from app.core.config import settings
from app.ai.tools import (
    get_my_account_summary,
    get_my_loans,
    get_my_penalties,
    get_my_declarations,
    explain_interest_rate,
    get_policy_answer
)
from app.models.ai import AIAuditLog


def process_ai_query(
    db: Session,
    user_id: UUID,
    member_id: UUID,
    query: str
) -> Dict:
    """
    Process AI query with RAG and tool calls.
    Enforces constraints: rules/policies only + member's own account status.
    """
    # Classify query type
    query_lower = query.lower()
    is_account_query = any(keyword in query_lower for keyword in [
        "my", "account", "balance", "loan", "savings", "penalty", "declaration", "status"
    ])
    is_policy_query = any(keyword in query_lower for keyword in [
        "rule", "policy", "constitution", "interest", "rate", "collateral", "how", "what", "explain"
    ])
    
    if not (is_account_query or is_policy_query):
        return {
            "response": "I can only answer questions about village banking rules/policies or your own account status. Please rephrase your question.",
            "citations": None,
            "tool_calls": None
        }
    
    tool_calls = []
    context = ""
    citations = []
    
    # Handle account status queries
    if is_account_query:
        if "loan" in query_lower:
            loans = get_my_loans(db, user_id)
            tool_calls.append({"tool": "get_my_loans", "result": loans})
            context += f"Member's loans: {loans}\n"
        
        if "penalty" in query_lower:
            penalties = get_my_penalties(db, user_id)
            tool_calls.append({"tool": "get_my_penalties", "result": penalties})
            context += f"Member's penalties: {penalties}\n"
        
        if "declaration" in query_lower:
            declarations = get_my_declarations(db, user_id)
            tool_calls.append({"tool": "get_my_declarations", "result": declarations})
            context += f"Member's declarations: {declarations}\n"
        
        # Always get account summary for account queries
        summary = get_my_account_summary(db, user_id)
        tool_calls.append({"tool": "get_my_account_summary", "result": summary})
        context += f"Account summary: {summary}\n"
    
    # Handle policy/rules queries
    if is_policy_query:
        policy_result = get_policy_answer(db, query)
        context += f"Policy context: {policy_result.get('context', '')}\n"
        citations = policy_result.get("citations", [])
        tool_calls.append({"tool": "get_policy_answer", "result": policy_result})
    
    # Call LLM with context
    client = Groq(api_key=settings.GROQ_API_KEY)
    
    system_prompt = """You are a helpful assistant for a Village Banking system. 
    You can only answer questions about:
    1. Village banking rules, policies, and constitution
    2. The member's own account status (savings, loans, penalties, declarations)
    
    You cannot access other members' information or answer unrelated questions.
    Always cite sources when answering policy questions."""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context: {context}\n\nUser question: {query}"}
    ]
    
    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        # Log to audit
        audit_log = AIAuditLog(
            user_id=user_id,
            query_text=query,
            tool_calls=tool_calls,
            response=ai_response,
            citations=citations
        )
        db.add(audit_log)
        db.commit()
        
        return {
            "response": ai_response,
            "citations": citations,
            "tool_calls": tool_calls
        }
    except Exception as e:
        return {
            "response": f"Error processing query: {str(e)}",
            "citations": None,
            "tool_calls": tool_calls
        }
