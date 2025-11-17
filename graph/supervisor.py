from typing import TypedDict, Any, Dict
from langgraph.graph import StateGraph, START, END
from models.state import AppState, Message, BundleQuote
from graph.policies import should_call_tools, invariants_pass


def build_planner_subgraph():
    planner_graph = StateGraph(AppState)
    # 2. Add Nodes
    planner_graph.add_node("extract_slots", extract_slots)
    planner_graph.add_node("validate_slots", validate_slots)
    planner_graph.add_node("generate_itinerary", generate_itinerary)
    planner_graph.add_node("respond_clarification", respond_clarification)

    # 3. Define Edges (Transitions)
    planner_graph.set_entry_point("extract_slots")

    # Conditional Edge after Slot Validation
    planner_graph.add_conditional_edges(
        "validate_slots", 
        lambda state: state.get("next_action"), # Uses the next_action hint from the node
        {
            "generate_itinerary": "generate_itinerary",
            "respond_clarification": "respond_clarification",
        }
    )

    # Fixed Edges
    planner_graph.add_edge("extract_slots", "validate_slots")


    planner_graph.add_edge("generate_itinerary", END) # End of Planner's task, goes back to Supervisor
    planner_graph.add_edge("respond_clarification", END) # Handoff to Supervisor for user response

    return planner_graph.compile()

# 4. Compile the Subgraph
PLANNER_SUBGRAPH = build_planner_subgraph.compile()

class GraphState(TypedDict, total=False):
    # Stored as plain dict for LangGraph; validated via AppState when needed
    session_id: str
    messages: list
    user_profile: dict
    trip_slots: dict
    candidates: dict
    itinerary_draft: dict
    bundles: list
    approvals: dict
    errors: list
    next_action: str


def _ensure_defaults(state: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure keys exist so nodes can rely on structure
    state.setdefault("messages", [])
    state.setdefault("user_profile", {})
    state.setdefault("trip_slots", {})
    state.setdefault("candidates", {})
    state.setdefault("itinerary_draft", {})
    state.setdefault("bundles", [])
    state.setdefault("approvals", {})
    state.setdefault("errors", [])
    return state


def supervisor_llm(state: GraphState) -> Dict[str, Any]:
    """
    This is a placeholder decision node.
    In Step 3+, replace with an LLM call that decides the next action and composes tool calls.
    """
    s = _ensure_defaults(dict(state))
    # Echo and set a reasonable next step for demo flow
    msgs = s.get("messages", [])
    user_last = next((m for m in reversed(msgs) if m.get("role") == "user"), None)
    if user_last:
        content = user_last.get("content", "")
    else:
        content = ""

    # Simple routing heuristic for the skeleton
    if any(k in content.lower() for k in ["flight", "hotel", "trip", "plan"]):
        s["next_action"] = "tool_handoff"
        s["messages"].append({"role": "assistant", "content": "Delegating to specialists (stub)..."})
    else:
        s["next_action"] = "respond"
        s["messages"].append({"role": "assistant", "content": "How can I help plan your trip? (stub)"})

    return s


def tool_handoff(state: GraphState) -> Dict[str, Any]:
    """
    In the real system, this node would call specialist agent subgraphs as tools.
    For now, we stub in minimal candidates so invariants can pass and we can exercise the loop.
    """
    s = _ensure_defaults(dict(state))
    # Stub candidates to satisfy invariants for dated trips
    s["candidates"].setdefault("flights", [{"route": "DEL→CDG", "price": 550.0, "currency": "EUR"}])
    s["candidates"].setdefault("hotels", [{"name": "Hotel Demo", "nightly": 120.0, "currency": "EUR"}])

    # Stub bundles when budget present
    budget = s.get("trip_slots", {}).get("budget")
    if budget and not s.get("bundles"):
        s["bundles"] = [
            {"name": "Cheapest", "total_cost": 900.0, "currency": "EUR", "breakdown": {"flights": 500, "lodging": 300, "buffer": 100}, "pros": ["Saves money"], "cons": ["Basic comfort"]},
            {"name": "Balanced", "total_cost": 1200.0, "currency": "EUR", "breakdown": {"flights": 550, "lodging": 500, "buffer": 150}, "pros": ["Good value"], "cons": ["Fewer luxuries"]},
            {"name": "Comfort", "total_cost": 1600.0, "currency": "EUR", "breakdown": {"flights": 700, "lodging": 800, "buffer": 100}, "pros": ["More comfort"], "cons": ["Higher cost"]},
        ]

    # After tools, route back to supervisor for another decision
    s["next_action"] = "respond"
    return s


def respond(state: GraphState) -> Dict[str, Any]:
    """
    Terminal response node that enforces invariants before ending.
    If invariants fail, push a remediation message and loop back to supervisor.
    """
    s = _ensure_defaults(dict(state))

    if not invariants_pass(s):
        s["messages"].append({"role": "assistant", "content": "Need more info or steps before finishing. Let’s clarify your dates, flights, and lodging (stub)."})
        # Loop back
        s["next_action"] = ""
        return s  # Edge defined to go back to supervisor
    # If OK, finalize
    s["messages"].append({"role": "assistant", "content": "Itinerary draft and bundles ready (stub)."})
    return s


def build_supervisor():
    graph = StateGraph(GraphState)
    
    graph.add_node("planner_agent", PLANNER_SUBGRAPH)
    graph.add_node("supervisor_llm", supervisor_llm)
    graph.add_node("tool_handoff", tool_handoff)
    graph.add_node("respond", respond)

    # Edges: START -> supervisor
    graph.add_edge(START, "supervisor_llm")

    # Conditional routing: supervisor -> tools or respond
    def route_from_supervisor(state: GraphState) -> str:
        s = AppState(**state)

        if not s.trip_slots.destination and any(k in s.messages[-1].content.lower() for k in ["plan", "trip", "go to"]):
            return "planner_agent"
        
        if s.itinerary_draft and should_call_tools(state):
            return "tool_handoff"

        return "respond"

    graph.add_conditional_edges("supervisor_llm", route_from_supervisor, {
        "planner_agent": "planner_agent",
        "tool_handoff": "tool_handoff",
        "respond": "respond",
    })

    # After tools, go back to supervisor for another decision
    graph.add_edge("planner_agent", "tool_handoff", "supervisor_llm")

    # Respond either ends or loops (handled inside node; we route to END here)
    graph.add_edge("respond", END)

    return graph.compile()


if __name__ == "__main__":
    app = build_supervisor()
    out = app.invoke({
        "session_id": "demo-1",
        "messages": [{"role": "user", "content": "Plan flights and hotels to Paris, budget 1200 EUR"}],
        "trip_slots": {"destination": "Paris", "budget": "1200 EUR", "start_date": "2025-11-10", "end_date": "2025-11-14"},
    })
    print(out)
