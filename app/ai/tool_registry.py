"""Tool registry for AI function calling."""
from typing import Dict, List, Callable, Any
from sqlalchemy.orm import Session
from uuid import UUID
import inspect


# Registry of available tools
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    function: Callable
):
    """Register a tool for function calling."""
    TOOL_REGISTRY[name] = {
        "name": name,
        "description": description,
        "parameters": parameters,
        "function": function
    }


def get_tool_schemas() -> List[Dict[str, Any]]:
    """Get all registered tools as OpenAI-compatible function schemas."""
    schemas = []
    for tool_name, tool_info in TOOL_REGISTRY.items():
        # Build parameters schema
        params_schema = {
            "type": "object",
            "properties": tool_info["parameters"].get("properties", {})
        }
        
        # Only include required if there are required parameters
        required = tool_info["parameters"].get("required", [])
        if required:
            params_schema["required"] = required
        
        schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_info["description"],
                "parameters": params_schema
            }
        }
        schemas.append(schema)
    return schemas


def execute_tool(tool_name: str, arguments: Dict[str, Any], db: Session, user_id: UUID, user_role: str = None) -> Any:
    """Execute a tool by name with given arguments."""
    if tool_name not in TOOL_REGISTRY:
        return {"error": f"Tool '{tool_name}' not found"}

    tool_info = TOOL_REGISTRY[tool_name]
    func = tool_info["function"]

    # Get function signature to determine which parameters to pass
    sig = inspect.signature(func)
    params = {}

    # Always pass db and user_id if function accepts them; pass user_role if accepted
    for param_name in sig.parameters:
        if param_name == "db":
            params["db"] = db
        elif param_name == "user_id":
            params["user_id"] = user_id
        elif param_name == "user_role":
            params["user_role"] = user_role
        elif param_name in arguments:
            params[param_name] = arguments[param_name]

    try:
        result = func(**params)
        return result
    except Exception as e:
        return {"error": str(e)}


# Register all available tools
def initialize_tools():
    """Initialize and register all available tools."""
    from app.ai.tools import (
        get_my_account_summary,
        get_my_loans,
        get_my_penalties,
        get_my_declarations,
        get_my_credit_rating,
        get_policy_answer,
        get_member_info,
        get_member_personal_details,
        get_penalty_information,
        get_group_info
    )
    
    register_tool(
        name="get_my_account_summary",
        description="Get the member's account summary including savings balance, loan balance, and account status. Use this when the user asks about their balance, account, savings, or overall financial status.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        function=get_my_account_summary
    )
    
    register_tool(
        name="get_my_loans",
        description="Get the member's loan information including loan amounts, interest rates, status, and disbursement dates. Use this when the user asks about their loans, loan details, or loan status.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        function=get_my_loans
    )
    
    register_tool(
        name="get_my_penalties",
        description="Get the member's penalty records including dates and status. Use this when the user asks about penalties, fines, or penalty records.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        function=get_my_penalties
    )
    
    register_tool(
        name="get_my_declarations",
        description="Get the member's declaration records including effective months and status. Use this when the user asks about declarations, monthly declarations, or declaration history.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        function=get_my_declarations
    )
    
    register_tool(
        name="get_my_credit_rating",
        description="Get the member's credit rating information including tier name, borrowing limits, maximum loan amount, and available interest rates for different loan terms. Use this when the user asks about credit rating, credit tier, borrowing limit, maximum loan amount, or loan eligibility.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        function=get_my_credit_rating
    )
    
    register_tool(
        name="get_policy_answer",
        description="Search the constitution and policy documents to answer questions about rules, policies, constitution, procedures, or how to use the app. Use this for questions about what something means, how something works, or explanations of policies.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The question or query to search for in policy documents"
                }
            },
            "required": ["query"]
        },
        function=get_policy_answer
    )
    
    register_tool(
        name="get_member_info",
        description="Get information about other members (non-financial). Use this when users ask about other members, member lists, member status, member contact information, who is a member, or to find members by name or email. Returns member name, email, phone, status, and join date. Does NOT return savings, loans, penalties, or any financial information.",
        parameters={
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": "Optional search term to find members by name or email. Leave empty to get all members."
                },
                "status": {
                    "type": "string",
                    "description": "Optional filter by member status: 'pending', 'active', or 'suspended'. Leave empty to get all statuses.",
                    "enum": ["pending", "active", "suspended"]
                }
            },
            "required": []
        },
        function=get_member_info
    )
    
    register_tool(
        name="get_penalty_information",
        description="Get information about penalty types and penalty rules for the current cycle. Returns all available penalty types (name, description, fee amount) and penalty configurations for Declaration Period, Loan Application Period, and Deposits Period (including date ranges, penalty types, and whether penalties are automatically applied). Use this when users ask about: penalties, penalty types, when penalties are applied, automatic penalties, penalty amounts, what happens if they miss deadlines, penalty rules for declarations/loan applications/deposits, what penalties exist, or how to avoid penalties.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        function=get_penalty_information
    )

    register_tool(
        name="get_group_info",
        description="Get group-level information: total members, active member count, committee members and their roles, and current cycle. Use when users ask about the group, how many members, who leads the group, or who holds specific roles.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        },
        function=get_group_info
    )

    register_tool(
        name="get_member_personal_details",
        description=(
            "Get a member's full personal details including NRC number, bank account, bank name, "
            "bank branch, physical address, and next-of-kin information. "
            "Only available to chairman and treasurer. "
            "Use this when a chairman or treasurer asks for a member's NRC, bank details, address, "
            "next of kin, or other personal/sensitive information."
        ),
        parameters={
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": "Member name, email, or NRC number to search for."
                }
            },
            "required": ["search_term"]
        },
        function=get_member_personal_details
    )


# Initialize tools on module import
initialize_tools()
