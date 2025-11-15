# Orchestration Overview

- Supervisor (LLM-driven policy) delegates to specialist agents via a tool_handoff node.
- Invariants ensure: if dates are set, itinerary must include flights and lodging; if budget provided, bundles must exist; booking requires approval.
- State shape defined in models/state.py (AppState). The graph operates on a dict mirroring AppState fields.

## Graph (v1)
START -> supervisor_llm -> (tool_handoff | respond)
tool_handoff -> supervisor_llm
respond -> END

## Next
- Replace tool_handoff stubs with real subgraph delegates (planner, flights, hotels).
- Add checkpointer persistence and session storage.
- Add conditional edges based on real tool_calls detection.

