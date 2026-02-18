"""AI chat service - LLM integration with function calling."""
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, List, Optional
from groq import Groq
import json
import re
from app.core.config import settings
from app.ai.tool_registry import get_tool_schemas, execute_tool
from app.models.ai import AIAuditLog


def process_ai_query(
    db: Session,
    user_id: UUID,
    member_id: UUID,
    query: str,
    user_first_name: Optional[str] = None
) -> Dict:
    """
    Process AI query with function calling - LLM dynamically selects which tools to use.
    Enforces constraints: rules/policies only + member's own account status.
    """
    client = Groq(api_key=settings.GROQ_API_KEY)
    tool_calls = []
    citations = []
    max_iterations = 3  # Prevent infinite loops
    iteration = 0
    
    # Get available tools
    tools = get_tool_schemas()
    
    # Personalized system prompt
    first_name_part = f" (the member's first name is {user_first_name})" if user_first_name else ""
    system_prompt = f"""You are the Luboss VB Finance Assistant, a helpful and knowledgeable assistant for the Luboss Village Banking system{first_name_part}.

Your role is to assist members with:

1. **App Usage and Navigation**: Help members understand how to use the app, navigate features, make declarations, apply for loans, upload documents, and access their information.

2. **Constitution and Policy Interpretation**: 
   - Answer questions about the uploaded constitution document
   - Provide clarity and interpretation on constitutional clauses, rules, and policies
   - Help members understand what they may be in doubt about regarding the constitution
   - Cite specific sections, pages, and versions when referencing the constitution

3. **Account and Transaction Information**:
   - Provide information about the member's own account (savings balance, loan balance, etc.)
   - Explain transactions, declarations, loans, penalties, and deposits
   - Help members understand their financial status and history
   - Only access the current member's own account information - never access other members' data

4. **Credit Rating Information**:
   - Provide information about the member's credit rating and tier
   - Explain borrowing limits and maximum loan amounts based on credit rating
   - Show available interest rates for different loan terms based on credit rating
   - Help members understand how their credit rating affects loan eligibility

5. **Member Information** (Non-Financial):
   - Help members find information about other members (name, email, phone, status)
   - Answer questions like "Who is [name]?", "What is [name]'s email?", "Is [name] an active member?"
   - Answer questions like "Who is the chairman?", "Who is the treasurer?", "Who is the compliance officer?"
   - Answer questions like "How many active members are in the group?", "How many members do we have?"
   - Answer questions like "What credit tier is [name] in?" — return tier name only, never financial amounts
   - List members by status (active, inactive)
   - Show member contact information, join dates, roles, and credit tier names
   - Use `get_group_info` for group-level questions (total members, committee, current cycle)
   - Use `get_member_info` for individual member lookups
   - **IMPORTANT**: NEVER provide savings, loan amounts, penalties, or financial transaction data about other members
   - Only provide: name, email, phone, status, join date, role/committee position, credit tier name (not multiplier/limit), and whether they have an active loan (yes/no)

6. **Penalty Information**:
   - Explain penalty types and their fee amounts
   - Inform members about when penalties are applied (outside date ranges)
   - Explain automatic vs manual penalty application
   - Help members understand penalty rules for declarations, loan applications, and deposits
   - Answer questions about what happens if they miss deadlines or make transactions outside allowed date ranges
   - Use the get_penalty_information tool to get current penalty rules and configurations

7. **General Village Banking Information**:
   - Explain village banking rules, policies, and procedures
   - Help with interest rate calculations and loan terms
   - Provide guidance on compliance and requirements

**Important Guidelines**:
- Always be friendly, professional, and helpful
- When answering questions about the constitution or policies, always cite your sources (document name, version, page number)
- For account queries, provide clear and accurate information based on the member's actual data
- For credit rating queries, explain the tier name, borrowing limits, and available loan terms clearly
- For penalty queries, use get_penalty_information to get current penalty types and rules, then explain clearly when penalties apply and whether they are automatic
- For member information queries, you can provide basic member details (name, email, phone, status, join date, roles, credit tier name, has_active_loan) but NEVER provide financial information about other members (savings, loan amounts, penalty amounts)
- For group-level questions (total members, committee roles, current cycle), use `get_group_info`
- If you don't have enough information, use the available tools to get it
- Never access or discuss other members' financial accounts, savings, loans, penalties, or credit ratings
- You can help members find contact information and basic profile details of other members
- If a question is outside your scope, politely redirect to relevant topics you can help with

**Penalty Rules**:
- Penalties may be configured for Declaration Period, Loan Application Period, and Deposits Period
- Each period has specific start and end days of the month when transactions are allowed
- If a penalty type is configured for a period, it may be automatically applied when transactions occur outside the allowed date range
- Penalty types have specific names, descriptions, and fee amounts
- Members should be informed about penalty rules to avoid unnecessary penalties
- Always check the current cycle's penalty configuration using get_penalty_information when answering penalty-related questions

**Currency and Formatting**:
- ALWAYS use K (Kwacha) as the currency symbol, NOT ₦ or any other currency
- Format all monetary amounts as: K1,234.56 (with comma thousands separator and two decimal places)
- Format responses using Markdown for web display:
  - Use **bold** for important numbers and labels
  - Use bullet points (-) or numbered lists for structured information
  - Use line breaks (double newline) to separate sections
  - Format account summaries clearly with proper spacing
  - Example format for account balance:
    ```
    Your current account summary:
    
    - **Savings balance:** **K2,000.00**
    - **Outstanding loan balance:** **K5,000.00**
    ```
- Keep responses concise but informative
- Use proper spacing and formatting for readability on web

**Tool Usage**:
- When tools are available, use them to get information when needed
- Call tools based on what the user is asking about
- You can call multiple tools if needed to answer a question completely
- If tools are not available, provide answers based on your training knowledge and the context provided"""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]
    
    # Enable function calling for models that support it
    tool_use_models = ["tool-use", "3.3", "3-groq"]
    use_function_calling = any(m in settings.LLM_MODEL.lower() for m in tool_use_models)
    
    # Update system prompt to explicitly disable tool usage when function calling is disabled
    if not use_function_calling:
        system_prompt += "\n\n**IMPORTANT: You do NOT have access to any tools or function calling. Answer questions directly based on the context provided and your knowledge. Do NOT attempt to call any tools, functions, or APIs.**"
    
    try:
        if use_function_calling and tools:
            # Try function calling approach
            # Iterative function calling - LLM can call tools and we respond with results
            while iteration < max_iterations:
                iteration += 1
                
                # Call LLM with tools
                api_params = {
                    "model": settings.LLM_MODEL,
                    "messages": messages,
                    "temperature": 0.7
                }
                
                # Add tools only on first iteration
                if iteration == 1 and tools:
                    api_params["tools"] = tools
                    api_params["tool_choice"] = "auto"
                
                try:
                    response = client.chat.completions.create(**api_params)
                except Exception as api_error:
                    # If function calling fails, fall back to keyword-based
                    if "tool" in str(api_error).lower() or "400" in str(api_error):
                        use_function_calling = False
                        break
                    raise
                
                message = response.choices[0].message
                assistant_msg = {
                    "role": message.role,
                    "content": message.content
                }
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]
                messages.append(assistant_msg)
                
                # Check if LLM wants to call a tool
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    # Execute tool calls
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            arguments = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                        except:
                            arguments = {}
                        
                        # Execute the tool
                        try:
                            result = execute_tool(tool_name, arguments, db, user_id)
                            tool_calls.append({
                                "tool": tool_name,
                                "arguments": arguments,
                                "result": result
                            })
                            
                            # Handle special cases
                            if tool_name == "get_policy_answer" and isinstance(result, dict):
                                citations = result.get("citations", [])
                            
                            # Add tool result to conversation
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result)
                            })
                        except Exception as e:
                            # Rollback on error
                            try:
                                db.rollback()
                            except:
                                pass
                            error_result = {"error": str(e)}
                            tool_calls.append({
                                "tool": tool_name,
                                "arguments": arguments,
                                "result": error_result
                            })
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(error_result)
                            })
                else:
                    # LLM has finished - return the response
                    ai_response = message.content
                    break
            else:
                # Max iterations reached
                if messages and messages[-1].get("content"):
                    ai_response = messages[-1]["content"]
                else:
                    ai_response = "I apologize, but I'm having trouble processing your request. Please try rephrasing your question."
        
        # Fallback to keyword-based approach if function calling not supported or failed
        if not use_function_calling or 'ai_response' not in locals():
            # Use the old keyword-based approach as fallback
            from app.ai.tools import (
                get_my_account_summary,
                get_my_loans,
                get_my_penalties,
                get_my_declarations,
                get_my_credit_rating,
                get_policy_answer,
                get_member_info
            )
            
            query_lower = query.lower()
            is_account_query = any(keyword in query_lower for keyword in [
                "my", "account", "balance", "loan", "savings", "penalty", "declaration", "status",
                "transaction", "deposit", "withdrawal", "repayment", "interest", "fund"
            ])
            is_credit_rating_query = any(keyword in query_lower for keyword in [
                "credit rating", "credit", "rating", "tier", "credit tier", "borrowing limit", "max loan"
            ])
            is_policy_query = any(keyword in query_lower for keyword in [
                "rule", "policy", "constitution", "interest", "rate", "collateral", "how", "what", "explain",
                "app", "use", "help", "documentation", "guide", "interpret", "clarify", "meaning"
            ])
            is_member_info_query = any(keyword in query_lower for keyword in [
                "member", "who is", "who are", "find member", "member list", "active member", "pending member",
                "suspended member", "member email", "member contact", "member phone", "member status",
                "list members", "show members", "all members", "members", "who are the members",
                "members of the group", "group members", "village banking members", "luboss members",
                "who are all", "show all", "list all", "everyone", "people in", "who belongs"
            ])
            
            if not (is_account_query or is_credit_rating_query or is_policy_query or is_member_info_query):
                is_policy_query = True
            
            context = ""
            
            # Handle account status queries
            if is_account_query:
                try:
                    if "loan" in query_lower:
                        loans = get_my_loans(db, user_id)
                        tool_calls.append({"tool": "get_my_loans", "result": loans})
                        context += f"Member's loans: {loans}\n"
                except Exception as e:
                    try:
                        db.rollback()
                    except:
                        pass
                    tool_calls.append({"tool": "get_my_loans", "result": {"error": str(e)}})
                
                try:
                    if "penalty" in query_lower:
                        penalties = get_my_penalties(db, user_id)
                        tool_calls.append({"tool": "get_my_penalties", "result": penalties})
                        context += f"Member's penalties: {penalties}\n"
                except Exception as e:
                    try:
                        db.rollback()
                    except:
                        pass
                    tool_calls.append({"tool": "get_my_penalties", "result": {"error": str(e)}})
                
                try:
                    if "declaration" in query_lower:
                        declarations = get_my_declarations(db, user_id)
                        tool_calls.append({"tool": "get_my_declarations", "result": declarations})
                        context += f"Member's declarations: {declarations}\n"
                except Exception as e:
                    try:
                        db.rollback()
                    except:
                        pass
                    tool_calls.append({"tool": "get_my_declarations", "result": {"error": str(e)}})
                
                try:
                    summary = get_my_account_summary(db, user_id)
                    tool_calls.append({"tool": "get_my_account_summary", "result": summary})
                    context += f"Account summary: {summary}\n"
                except Exception as e:
                    try:
                        db.rollback()
                    except:
                        pass
                    tool_calls.append({"tool": "get_my_account_summary", "result": {"error": str(e)}})
            
            # Handle credit rating queries
            if is_credit_rating_query:
                try:
                    credit_rating = get_my_credit_rating(db, user_id)
                    tool_calls.append({"tool": "get_my_credit_rating", "result": credit_rating})
                    context += f"Member's credit rating: {credit_rating}\n"
                except Exception as e:
                    try:
                        db.rollback()
                    except:
                        pass
                    tool_calls.append({"tool": "get_my_credit_rating", "result": {"error": str(e)}})
            
            # Handle member information queries (non-financial)
            if is_member_info_query:
                try:
                    # Extract search term and status from query
                    search_term = None
                    status_filter = None
                    
                    # Check for status filters first (before name extraction)
                    if "active member" in query_lower or "active members" in query_lower or "who are active" in query_lower:
                        status_filter = "active"
                    elif "pending member" in query_lower or "pending members" in query_lower or "who are pending" in query_lower:
                        status_filter = "pending"
                    elif "suspended member" in query_lower or "suspended members" in query_lower or "who are suspended" in query_lower:
                        status_filter = "suspended"
                    
                    # Try to extract member name or email from query
                    # Look for patterns like "who is [name]", "find [name]", "[name]'s email"
                    # Only extract if it's not a general "list all" type query
                    if not any(phrase in query_lower for phrase in [
                        "who are the members", "members of the group", "all members", "list members",
                        "show members", "everyone", "group members", "who are all"
                    ]):
                        name_patterns = [
                            r"who is (.+?)(?:\?|$)",
                            r"find (.+?)(?:\?|$)",
                            r"(.+?)'s (?:email|phone|contact|status)",
                            r"member (.+?)(?:\?|$)",
                            r"(.+?) member",
                            r"email of (.+?)(?:\?|$)",
                            r"phone of (.+?)(?:\?|$)",
                            r"contact (.+?)(?:\?|$)"
                        ]
                        for pattern in name_patterns:
                            match = re.search(pattern, query_lower, re.IGNORECASE)
                            if match:
                                potential_name = match.group(1).strip()
                                # Filter out common words
                                if potential_name and potential_name not in ["the", "a", "an", "all", "active", "pending", "suspended", "list", "show", "group", "village", "banking", "luboss"]:
                                    search_term = potential_name
                                    break
                    
                    # If no specific search term and no status filter, get all members
                    # (search_term=None and status=None will return all members)
                    member_info = get_member_info(db, search_term=search_term, status=status_filter)
                    tool_calls.append({"tool": "get_member_info", "result": member_info})
                    context += f"Member information: {member_info}\n"
                except Exception as e:
                    try:
                        db.rollback()
                    except:
                        pass
                    tool_calls.append({"tool": "get_member_info", "result": {"error": str(e)}})
            
            # Handle policy queries
            if is_policy_query:
                try:
                    policy_result = get_policy_answer(db, query)
                    context += f"Policy context: {policy_result.get('context', '')}\n"
                    citations = policy_result.get("citations", [])
                    tool_calls.append({"tool": "get_policy_answer", "result": policy_result})
                except Exception as e:
                    try:
                        db.rollback()
                    except:
                        pass
                    tool_calls.append({"tool": "get_policy_answer", "result": {"error": str(e)}})
            
            # Call LLM with context (explicitly disable tool calling)
            # Note: Some models may not support tool_choice parameter, so we catch errors
            try:
                response = client.chat.completions.create(
                    model=settings.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Context: {context}\n\nUser question: {query}"}
                    ],
                    temperature=0.7,
                    tool_choice="none"  # Explicitly disable tool calling
                )
            except Exception as tool_error:
                # If tool_choice parameter causes issues, retry without it
                if "tool" in str(tool_error).lower() or "400" in str(tool_error):
                    response = client.chat.completions.create(
                        model=settings.LLM_MODEL,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": f"Context: {context}\n\nUser question: {query}"}
                        ],
                        temperature=0.7
                    )
                else:
                    raise
            
            ai_response = response.choices[0].message.content
        
        # Ensure we have a response
        if 'ai_response' not in locals() or not ai_response:
            ai_response = "I apologize, but I couldn't generate a response. Please try again."
        
        # Log to audit in a separate try-except to avoid failing the whole request
        # Rollback any previous transaction state to ensure clean state for audit log
        try:
            # Rollback to clear any failed transaction state from tool calls
            # (Tool calls are read-only, so this won't lose any data)
            db.rollback()
            
            # Now save audit log in a fresh transaction
            audit_log = AIAuditLog(
                user_id=user_id,
                query_text=query,
                tool_calls=tool_calls,
                response=ai_response,
                citations=citations
            )
            db.add(audit_log)
            db.commit()
        except Exception as audit_error:
            # If audit log fails, rollback and continue without failing the request
            try:
                db.rollback()
            except:
                pass
            # Log the error but don't fail the request
            import logging
            logging.error(f"Failed to save AI audit log: {str(audit_error)}")
        
        return {
            "response": ai_response,
            "citations": citations,
            "tool_calls": tool_calls
        }
    except Exception as e:
        # Rollback any failed transaction
        try:
            db.rollback()
        except:
            pass  # Ignore rollback errors
        
        # Check if error is related to tool calling and provide a clearer message
        error_message = str(e)
        if "tool" in error_message.lower() and ("400" in error_message or "invalid_request" in error_message.lower()):
            # Model tried to use tools when they're disabled
            return {
                "response": "I apologize, but I encountered an issue while processing your request. Please try rephrasing your question, and I'll answer based on the information available.",
                "citations": None,
                "tool_calls": tool_calls
            }
        
        return {
            "response": f"Error processing query: {error_message}",
            "citations": None,
            "tool_calls": tool_calls
        }
