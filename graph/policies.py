from typing import Dict, Any
from models.state import AppState


def should_call_tools(state: Dict[str, Any]) -> bool:
    # In v1 we look for a supervisor hint; later you can inspect tool_calls in messages
    return state.get("next_action") == "tool_handoff"


def invariants_pass(state: Dict[str, Any]) -> bool:
    """
    Guardrails before ending:
    - If dates are set, require flights + lodging present in candidates or itinerary_draft.
    - If budget provided, ensure bundles computed (non-empty).
    - If booking handoff requested, ensure approvals present.
    """
    try:
        st = AppState(**state)
    except Exception:
        return False

    slots = st.trip_slots
    has_dates = bool(slots.start_date and slots.end_date)
    has_flights = bool(st.candidates.get("flights")) or "flights" in st.itinerary_draft
    has_hotels = bool(st.candidates.get("hotels")) or "lodging" in st.itinerary_draft
    has_bundles_if_budget = (not slots.budget) or (slots.budget and len(st.bundles) > 0)
    booking_needs_approval = st.approvals.get("required") is not True or st.approvals.get("granted") is True

    if has_dates and not (has_flights and has_hotels):
        return False
    if not has_bundles_if_budget:
        return False
    if not booking_needs_approval:
        return False
    return True
