"""AI chat service - LLM integration with function calling."""
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, List, Optional
import json
import re
from app.core.config import settings
from app.ai.tool_registry import get_tool_schemas, execute_tool
from app.models.ai import AIAuditLog


def _get_llm_client():
    """Create an LLM client based on the configured provider."""
    provider = (settings.LLM_PROVIDER or "groq").lower()

    if provider == "local" and settings.LLM_BASE_URL:
        from openai import OpenAI
        return OpenAI(
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY or "not-needed",
        )
    elif provider == "openai":
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY)
    else:
        from groq import Groq
        return Groq(api_key=settings.GROQ_API_KEY)


def process_ai_query(
    db: Session,
    user_id: UUID,
    member_id: UUID,
    query: str,
    user_first_name: Optional[str] = None,
    user_role: Optional[str] = None,
) -> Dict:
    """
    Process AI query with function calling - LLM dynamically selects which tools to use.
    Enforces constraints: rules/policies only + member's own account status.
    """
    client = _get_llm_client()
    tool_calls = []
    citations = []
    max_iterations = 3  # Prevent infinite loops
    iteration = 0
    
    # Get available tools
    tools = get_tool_schemas()
    
    # Personalized system prompt — kept concise to stay within token limits
    first_name_part = f" The member's name is {user_first_name}." if user_first_name else ""
    system_prompt = f"""You are the Luboss VB Finance Assistant.{first_name_part}

You help members with: app usage, constitution/policy questions, their account info (savings, loans, declarations, penalties), credit ratings, member lookups, penalty rules, and general village banking questions.

RULES:
- Currency: always use K (Kwacha), format as K1,234.56
- Constitution questions: cite document name, version, and page number
- Member lookups: provide name, email, phone, status, join date, roles, credit tier name, has_active_loan. NEVER reveal other members' financial data (savings, loans, penalties)
- Use get_group_info for group-level questions (total members, committee, cycle)
- Use get_member_info for individual member lookups
- Use get_penalty_information for penalty rules
- Use get_policy_answer for constitution/policy questions
- Format responses in Markdown with bold for key numbers and bullet points
- Be concise and helpful"""

    # Role-specific addendum
    admin_roles = {"chairman", "treasurer"}
    if user_role and user_role.lower() in admin_roles:
        system_prompt += f"""

ADMIN ACCESS ({user_role.title()}): Use get_member_personal_details for NRC/bank/address/next-of-kin. Use get_member_account_details for a member's financial details. Both require a search term (name or email). Confirm the member name in your response."""
    
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
                            result = execute_tool(tool_name, arguments, db, user_id, user_role=user_role)
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
                get_member_info,
                get_member_personal_details,
                get_member_account_details,
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
            is_personal_details_query = any(keyword in query_lower for keyword in [
                "bank account", "bank details", "account number", "account details",
                "nrc", "nrc number", "national registration",
                "physical address", "home address", "address",
                "next of kin", "next-of-kin", "kin",
                "bank name", "bank branch",
            ])
            is_member_info_query = any(keyword in query_lower for keyword in [
                "member", "who is", "who are", "find member", "member list", "active member", "pending member",
                "suspended member", "member email", "member contact", "member phone", "member status",
                "list members", "show members", "all members", "members", "who are the members",
                "members of the group", "group members", "village banking members", "luboss members",
                "who are all", "show all", "list all", "everyone", "people in", "who belongs"
            ])

            # Detect when chairman/treasurer asks about another member's financial data
            is_member_account_query = False
            if user_role and user_role.lower() in {"chairman", "treasurer"}:
                # Check if query mentions a person's name along with financial keywords
                financial_keywords = ["account", "savings", "loan", "balance", "penalties", "declaration", "status", "financial", "owe", "owing"]
                name_indicators = ["for ", "of ", "'s ", "about "]
                has_financial = any(kw in query_lower for kw in financial_keywords)
                has_name_ref = any(ni in query_lower for ni in name_indicators)
                if has_financial and has_name_ref:
                    is_member_account_query = True

            if not (is_account_query or is_credit_rating_query or is_policy_query or is_member_info_query or is_personal_details_query or is_member_account_query):
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
            
            # Handle personal details queries (chairman/treasurer only)
            if is_personal_details_query:
                try:
                    # Extract member name from the query
                    personal_search_term = None
                    personal_patterns = [
                        r"(?:bank account|bank details|account details|account number|nrc|address|next of kin|bank name|bank branch)\s+(?:for|of)\s+(?:member\s+)?(.+?)(?:\?|$)",
                        r"(?:for|of)\s+(?:member\s+)?(.+?)\s+(?:bank account|bank details|account details|nrc|address|next of kin)",
                        r"member\s+(.+?)'s\s+(?:bank|nrc|address|next of kin|account)",
                        r"(.+?)'s\s+(?:bank account|bank details|nrc|address|next of kin|account number|account details)",
                        r"(?:what is|what are|get|find|show)\s+(?:the\s+)?(?:bank account|bank details|nrc|address|next of kin)\s+(?:for|of)\s+(?:member\s+)?(.+?)(?:\?|$)",
                    ]
                    for pattern in personal_patterns:
                        match = re.search(pattern, query_lower, re.IGNORECASE)
                        if match:
                            candidate = match.group(1).strip()
                            if candidate and candidate not in ["the", "a", "an", "member", "this", "that"]:
                                personal_search_term = candidate
                                break

                    personal_details = get_member_personal_details(
                        db, search_term=personal_search_term, user_role=user_role
                    )
                    tool_calls.append({"tool": "get_member_personal_details", "result": personal_details})
                    context += f"Member personal details: {personal_details}\n"
                except Exception as e:
                    try:
                        db.rollback()
                    except:
                        pass
                    tool_calls.append({"tool": "get_member_personal_details", "result": {"error": str(e)}})

            # Handle member account/financial queries (chairman/treasurer only)
            if is_member_account_query:
                try:
                    # Extract member name from the query
                    acct_search_term = None
                    acct_patterns = [
                        r"(?:account|savings|loan|balance|penalties|declaration|status|financial)\s+(?:for|of|about)\s+(?:member\s+)?(.+?)(?:\?|$)",
                        r"(?:for|of|about)\s+(?:member\s+)?(.+?)(?:'s)?\s+(?:account|savings|loan|balance|penalties|declaration|status|financial)",
                        r"(.+?)'s\s+(?:account|savings|loan|balance|penalties|declaration|status|financial)",
                        r"(?:what is|what are|get|find|show|check)\s+(?:the\s+)?(?:account|savings|loan|balance|status)\s+(?:for|of)\s+(?:member\s+)?(.+?)(?:\?|$)",
                    ]
                    for pattern in acct_patterns:
                        match = re.search(pattern, query_lower, re.IGNORECASE)
                        if match:
                            candidate = match.group(1).strip()
                            if candidate and candidate not in ["the", "a", "an", "member", "this", "that", "my"]:
                                acct_search_term = candidate
                                break

                    if acct_search_term:
                        member_account = get_member_account_details(
                            db, search_term=acct_search_term, user_role=user_role
                        )
                        tool_calls.append({"tool": "get_member_account_details", "result": member_account})
                        context += f"Member account details: {member_account}\n"
                except Exception as e:
                    try:
                        db.rollback()
                    except:
                        pass
                    tool_calls.append({"tool": "get_member_account_details", "result": {"error": str(e)}})

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
        
        # Return user-friendly messages instead of raw API errors
        error_message = str(e)
        error_lower = error_message.lower()

        if "rate_limit" in error_lower or "413" in error_message or "429" in error_message or "too large" in error_lower or "tokens per minute" in error_lower:
            friendly = "I'm currently experiencing high demand. Please try again in a moment, or try a shorter question."
        elif "tool" in error_lower and ("400" in error_message or "invalid_request" in error_lower):
            friendly = "I apologize, but I encountered an issue while processing your request. Please try rephrasing your question."
        else:
            friendly = "I'm sorry, I'm having trouble processing your request right now. Please try again shortly."
            import logging
            logging.error(f"AI chat error: {error_message}")

        return {
            "response": friendly,
            "citations": None,
            "tool_calls": tool_calls
        }
