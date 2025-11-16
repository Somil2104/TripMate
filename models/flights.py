from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Awaitable, Callable, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, validator
from enum import Enum

# ---------------------------------------------------------------------------
# Constants (PRD-aligned)
# ---------------------------------------------------------------------------

MAX_RESULTS_PER_AGENT = 5
PROVIDER_MAX_RETRIES = 2          # 1–2 retries per provider
PROVIDER_TIMEOUT_SECONDS = 5      # single provider timeout
AGENT_TIMEOUT_SECONDS = 20        # overall agent timeout


# ---------------------------------------------------------------------------
# Core Models
# ---------------------------------------------------------------------------


class Money(BaseModel):
    amount: float
    currency: str


class FlightUserPreference(str, Enum):
    """
    Simple string enum for user hints. We keep it as plain strings to avoid
    serialization headaches across services.
    """
    CHEAPEST = "cheapest"
    NON_STOP = "non-stop"
    COMFORT = "comfort"
    BALANCED = "balanced"


class FlightSearchRequest(BaseModel):
    """
    Inputs to the Flights agent.

    NOTE: This is an internal contract between Supervisor/Planner and this agent.
    """
    origin: str
    destination: str
    departure_date: date

    # Optional return date – you can ignore it in MVP if you only do one-way.
    return_date: Optional[date] = None

    # Cabin class / service class – e.g. "economy", "business".
    cabin_class: Optional[str] = None

    # A single dominant user hint from: cheapest, non-stop, comfort, balanced.
    user_preference: Optional[str] = None

    # Filter hints
    non_stop_only: bool = False

    # Allow caller to override default limit (but never exceed MAX_RESULTS_PER_AGENT)
    limit: int = MAX_RESULTS_PER_AGENT

    @validator("limit")
    def clamp_limit(cls, v: int) -> int:
        return min(max(v, 1), MAX_RESULTS_PER_AGENT)


class FlightOption(BaseModel):
    """
    Normalized flight option as per PRD.

    Required external contract fields:
    - id
    - provider
    - price
    - fare_class
    - duration
    - stops

    We also add a few optional fields needed for real-world deduping and ranking.
    """
    id: str
    provider: str
    price: Money
    fare_class: str
    duration: str
    stops: int

    # Optional fields used for dedupe & ranking (not strictly required by PRD)
    carrier_code: Optional[str] = None           # e.g. "AI"
    flight_number: Optional[str] = None          # e.g. "302"
    origin: Optional[str] = None                 # IATA code
    destination: Optional[str] = None            # IATA code
    departure_date: Optional[date] = None        # local date at origin

    # Internal scoring field – excluded from JSON by default
    score: Optional[float] = Field(default=None, exclude=True)


class FlightResultStatus(str, Enum):
    TENTATIVE = "tentative"
    FINAL = "final"


class FlightSearchResponse(BaseModel):
    """
    Wrapper returned to Supervisor/Planner.

    status:
      - tentative: fast, possibly partial or lightly processed
      - final: deduped + ranked results
    """
    status: FlightResultStatus
    options: List[FlightOption]


# ---------------------------------------------------------------------------
# Provider Interface
# ---------------------------------------------------------------------------


class FlightProvider(ABC):
    """
    Abstract base class for a flight data provider (e.g., Amadeus).

    Implementations live in services/ (e.g., services/amadeus_flights.py) and
    should convert provider responses directly into FlightOption objects.
    """

    name: str

    def __init__(self, name: Optional[str] = None) -> None:
        if name:
            self.name = name

    @abstractmethod
    async def search_flights(self, request: FlightSearchRequest) -> List[FlightOption]:
        """
        Perform a flight search and return normalized FlightOption objects.

        Implementations MUST:
          - Respect request.origin, destination, dates, cabin_class, etc.
          - Map provider-specific fields into FlightOption, including
            dedupe-relevant fields where possible:
              carrier_code, flight_number, origin, destination, departure_date.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Deduping & Ranking
# ---------------------------------------------------------------------------


def _dedupe_key(option: FlightOption) -> Tuple[Any, ...]:
    """
    Build a key that represents real-world flight identity:
      (carrier_code, flight_number, departure_date, origin, destination)

    If some fields are missing, we still attempt a best-effort key.
    """
    return (
        option.carrier_code,
        option.flight_number,
        option.departure_date,
        option.origin,
        option.destination,
    )


def dedupe_flights(options: Sequence[FlightOption]) -> List[FlightOption]:
    """
    Deduplicate flight options by real-world identity.

    If duplicates are found, we keep the one with:
      - lower price, or
      - higher score if price is equal or unknown.
    """
    best_by_key: dict[Tuple[Any, ...], FlightOption] = {}

    for opt in options:
        key = _dedupe_key(opt)

        if key not in best_by_key:
            best_by_key[key] = opt
            continue

        current = best_by_key[key]
        # Prefer cheaper flights if both prices are known
        if opt.price and current.price:
            if opt.price.amount < current.price.amount:
                best_by_key[key] = opt
                continue

        # Tie-breaker: higher score wins
        if (opt.score or 0.0) > (current.score or 0.0):
            best_by_key[key] = opt

    return list(best_by_key.values())


def _base_score(option: FlightOption) -> float:
    """
    Compute a neutral composite score based on price, stops, and (if possible)
    a rough duration estimate.

    Higher score = better.
    """
    # Normalize price: cheaper is better; avoid divide-by-zero
    price_component = 0.0
    if option.price and option.price.amount > 0:
        price_component = 1.0 / option.price.amount

    # Fewer stops is better, with non-stop strongly favored
    stops_component = 1.0 if option.stops == 0 else 0.5 / max(option.stops, 1)

    # Duration heuristic: we don't parse the string strictly; you can extend this
    duration_component = 0.0
    # Simple guess: if duration contains "h", treat it as "<hours> h"
    try:
        if "h" in option.duration.lower():
            hours_part = option.duration.lower().split("h")[0]
            hours = float("".join(ch for ch in hours_part if (ch.isdigit() or ch == ".")))
            if hours > 0:
                duration_component = 1.0 / hours
    except Exception:
        duration_component = 0.0

    # Weighted sum; tweak as you like
    return 0.6 * price_component + 0.25 * stops_component + 0.15 * duration_component


def _apply_preference_bias(
    score: float,
    option: FlightOption,
    preference: Optional[str],
) -> float:
    """
    Adjust score based on user preference.

    - cheapest: heavier weight on price
    - non-stop: strong bonus for non-stop flights
    - comfort: bias against many stops and extremely cheap options
    """
    if not preference:
        return score

    pref = preference.lower()

    if pref == FlightUserPreference.CHEAPEST:
        # Extra bonus for cheap options
        if option.price and option.price.amount > 0:
            score += 0.5 / option.price.amount

    elif pref == FlightUserPreference.NON_STOP:
        if option.stops == 0:
            score += 0.3

    elif pref == FlightUserPreference.COMFORT:
        # Penalize too many stops; assume higher price ~ more comfort
        score += 0.2 * max(0, 2 - option.stops)
        if option.price and option.price.amount > 0:
            score += 0.2 * (1.0 / (option.price.amount ** 0.3))

    # BALANCED or unknown => no change
    return score


def rank_flights(
    options: Sequence[FlightOption],
    preference: Optional[str],
) -> List[FlightOption]:
    """
    Compute composite scores with user bias, then return flights ordered
    from best to worst.
    """
    ranked: List[FlightOption] = []

    for opt in options:
        base = _base_score(opt)
        biased = _apply_preference_bias(base, opt, preference)
        opt.score = biased
        ranked.append(opt)

    ranked.sort(key=lambda o: o.score or 0.0, reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


async def _with_retries(
    func: Callable[[], Awaitable[List[FlightOption]]],
    retries: int = PROVIDER_MAX_RETRIES,
) -> List[FlightOption]:
    """
    Simple async retry with exponential backoff.
    """
    delay = 0.5
    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            return await func()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == retries:
                break
            await asyncio.sleep(delay)
            delay *= 2

    # If we reach here, all retries failed
    # In a real app, log `last_exc` here
    return []


# ---------------------------------------------------------------------------
# Flights Agent
# ---------------------------------------------------------------------------

PartialCallback = Callable[[FlightSearchResponse], Awaitable[None]]


class FlightsAgent:
    """
    Flights Agent responsible for:
      - querying multiple providers in parallel
      - deduping and ranking results
      - returning up to 5 normalized FlightOption objects
      - optionally emitting a fast, tentative partial response

    Streaming contract:
      - If on_partial is provided, we send an early "tentative" response
        as soon as we have some options (1–3).
      - The final return value is always the final, deduped + ranked list.
    """

    def __init__(self, providers: Iterable[FlightProvider]) -> None:
        self.providers: List[FlightProvider] = list(providers)

    async def search(
        self,
        request: FlightSearchRequest,
        on_partial: Optional[PartialCallback] = None,
    ) -> List[FlightOption]:
        """
        Main entrypoint for Supervisor/Planner.

        - Executes all provider calls in parallel with retries and per-call timeout.
        - Optionally emits a fast tentative response via `on_partial`.
        - Returns final, deduped + ranked list (up to request.limit).
        """

        async def run_all_providers() -> List[FlightOption]:
            tasks: List[Awaitable[List[FlightOption]]] = []

            for provider in self.providers:
                async def _call_provider(p: FlightProvider = provider) -> List[FlightOption]:
                    async def call() -> List[FlightOption]:
                        return await asyncio.wait_for(
                            p.search_flights(request),
                            timeout=PROVIDER_TIMEOUT_SECONDS,
                        )

                    return await _with_retries(call, retries=PROVIDER_MAX_RETRIES)

                tasks.append(_call_provider())

            results: List[FlightOption] = []
            partial_emitted = False

            # as_completed lets us emit early partials
            for coro in asyncio.as_completed(tasks):
                provider_results = await coro
                results.extend(provider_results)

                if on_partial and not partial_emitted and len(results) > 0:
                    # Produce a quick tentative shortlist
                    tentative = self._postprocess(
                        options=results,
                        preference=request.user_preference,
                        limit=min(3, request.limit),
                    )
                    if tentative:
                        partial_emitted = True
                        await on_partial(
                            FlightSearchResponse(
                                status=FlightResultStatus.TENTATIVE,
                                options=tentative,
                            )
                        )

            return results

        try:
            all_results = await asyncio.wait_for(
                run_all_providers(),
                timeout=AGENT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            # Hard timeout: return whatever we have, deduped + ranked
            all_results = []

        final_options = self._postprocess(
            options=all_results,
            preference=request.user_preference,
            limit=request.limit,
        )

        # If we never emitted a tentative response but we *do* have results
        # and a callback, we can emit them now as final.
        if on_partial and final_options:
            await on_partial(
                FlightSearchResponse(
                    status=FlightResultStatus.FINAL,
                    options=final_options,
                )
            )

        return final_options

    @staticmethod
    def _postprocess(
        options: Sequence[FlightOption],
        preference: Optional[str],
        limit: int,
    ) -> List[FlightOption]:
        if not options:
            return []

        deduped = dedupe_flights(options)
        ranked = rank_flights(deduped, preference=preference)
        return ranked[:limit]
