from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str


class TripSlots(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    start_date: Optional[str] = None  # ISO date
    end_date: Optional[str] = None    # ISO date
    budget: Optional[str] = None      # accept as string for LLM friendliness
    party: Optional[str] = None
    interests: Optional[List[str]] = None


class BundleQuote(BaseModel):
    name: Literal["Cheapest", "Balanced", "Comfort"]
    total_cost: Optional[float] = None
    currency: Optional[str] = None
    breakdown: Dict[str, float] = Field(default_factory=dict)  # flights, lodging, transport, meals, activities, buffer
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)


class ItineraryDay(BaseModel):
    date: Optional[str] = None  # ISO date
    items: List[Dict[str, Any]] = Field(default_factory=list)  # activities/segments with times and notes


class AppState(BaseModel):
    # Session-scoped state for orchestration
    session_id: str
    messages: List[Message] = Field(default_factory=list)

    # Inputs/slots and user profile
    user_profile: Dict[str, Any] = Field(default_factory=dict)
    trip_slots: TripSlots = Field(default_factory=TripSlots)

    # Candidates and composed outputs
    candidates: Dict[str, Any] = Field(default_factory=dict)  # flights/hotels/activities raw results
    itinerary_draft: Dict[str, Any] = Field(default_factory=dict)  # { days: List[ItineraryDay] }
    bundles: List[BundleQuote] = Field(default_factory=list)

    # Approvals and booking handoff
    approvals: Dict[str, Any] = Field(default_factory=dict)  # { approved_bundle: str, timestamp: str, ... }

    # Control and errors
    errors: List[str] = Field(default_factory=list)
    next_action: Optional[str] = None  # internal routing hint (e.g., "tool_handoff", "respond")
