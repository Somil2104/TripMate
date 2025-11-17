from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field, validator
from enum import Enum


# ---------------------------------------------------------------------------
# Constants (PRD-aligned)
# ---------------------------------------------------------------------------

MAX_RESULTS_PER_AGENT = 5
PROVIDER_MAX_RETRIES = 2          # 1–2 retries per provider
PROVIDER_TIMEOUT_SECONDS = 15      # single provider timeout
AGENT_TIMEOUT_SECONDS = 60        # overall agent timeout
HOTEL_CACHE_TTL_SECONDS = 300     # ~5 minutes


# ---------------------------------------------------------------------------
# Core Models
# ---------------------------------------------------------------------------


class Money(BaseModel):
    amount: float
    currency: str


class GeoPoint(BaseModel):
    lat: float
    lon: float


class CheckinCheckoutTimes(BaseModel):
    checkin: Optional[str] = None   # e.g. "15:00"
    checkout: Optional[str] = None  # e.g. "11:00"


class HotelUserPreference(str, Enum):
    CHEAPEST = "cheapest"
    LUXURY = "luxury"
    BALANCED = "balanced"
    HIGH_RATING = "high-rating"


class HotelSearchRequest(BaseModel):
    """
    Inputs to the Hotels agent.

    Destination can be:
      - city_name (e.g., "New York")
      - or lat/lon (e.g., map bounding box)
    We keep it simple for MVP: city_name OR coordinates.
    """

    # Option 1: human-readable city / area
    destination: Optional[str] = None

    # Option 2: coordinates (e.g., user says "near this point")
    lat: Optional[float] = None
    lon: Optional[float] = None

    checkin_date: date
    checkout_date: date

    # User preference / bias: cheapest, luxury, balanced, high-rating
    user_preference: Optional[str] = None

    # Filter hints – only applied if present
    min_rating: Optional[float] = None          # e.g. 4.0
    star_rating_only: Optional[int] = None      # e.g. 4 => 4-star only
    amenities_must_have: List[str] = Field(default_factory=list)
    pets_allowed_only: bool = False

    # Allow caller to override default limit (but never exceed MAX_RESULTS_PER_AGENT)
    limit: int = MAX_RESULTS_PER_AGENT

    @validator("limit")
    def clamp_limit(cls, v: int) -> int:
        return min(max(v, 1), MAX_RESULTS_PER_AGENT)

    @validator("destination")
    def require_destination_or_coords(cls, v: Optional[str], values: dict) -> Optional[str]:
        lat = values.get("lat")
        lon = values.get("lon")
        if not v and (lat is None or lon is None):
            raise ValueError("Either destination or (lat, lon) must be provided")
        return v


class HotelOption(BaseModel):
    """
    Normalized hotel option as per PRD.

    NOTE: made several fields optional / defaulted to be tolerant of provider
    responses that miss fields (so provider parsing errors don't raise).
    """
    id: str
    provider: str

    # price may be absent for some provider responses; allow None
    price: Optional[Money] = None

    # rating may be missing; default to 0.0
    rating: Optional[float] = Field(default=0.0)

    # allow empty amenities by default
    amenities: List[str] = Field(default_factory=list)

    # location may be missing; default to a neutral point (0.0, 0.0)
    location: GeoPoint = Field(default_factory=lambda: GeoPoint(lat=0.0, lon=0.0))

    # allow checkin/checkout info to be absent
    checkin_checkout_times: Optional[CheckinCheckoutTimes] = Field(default_factory=CheckinCheckoutTimes)

    # For dedupe
    name: Optional[str] = None
    address: Optional[str] = None

    # Optional scoring helpers
    distance_from_center_km: Optional[float] = None

    # Internal scoring field – excluded from JSON by default
    score: Optional[float] = Field(default=None, exclude=True)


class HotelResultStatus(str, Enum):
    TENTATIVE = "tentative"
    FINAL = "final"


class HotelSearchResponse(BaseModel):
    """
    Wrapper returned to Supervisor/Planner.

    status:
      - tentative: fast, possibly partial
      - final: deduped + ranked
    """
    status: HotelResultStatus
    options: List[HotelOption]


# ---------------------------------------------------------------------------
# Provider Interface
# ---------------------------------------------------------------------------


class HotelProvider(ABC):
    """
    Abstract base class for a hotel data provider (e.g., Booking.com).

    Implementations live in services/ (e.g., services/booking_hotels.py) and
    should convert provider responses directly into HotelOption objects.
    """

    name: str

    def __init__(self, name: Optional[str] = None) -> None:
        if name:
            self.name = name

    @abstractmethod
    async def search_hotels(self, request: HotelSearchRequest) -> List[HotelOption]:
        """
        Perform a hotel search and return normalized HotelOption objects.

        Implementations MUST:
          - Respect location, dates, and any relevant filters.
          - Map provider-specific fields into HotelOption, including:
              name, address, amenities, rating, price, location, etc.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Deduping & Ranking
# ---------------------------------------------------------------------------


def _dedupe_key(option: HotelOption) -> Tuple[Any, ...]:
    """
    Real-world identity key for a hotel.

    Prefer name + address; if address is missing, fall back to location,
    with coarse rounding on lat/lon to group near-identical POIs.
    """
    name = (option.name or "").strip().lower()
    address = (option.address or "").strip().lower()

    if name and address:
        return (name, address)

    # Fallback: coarse geo bucket
    lat_bucket = round(option.location.lat, 3)
    lon_bucket = round(option.location.lon, 3)
    return (name, lat_bucket, lon_bucket)


def dedupe_hotels(options: Sequence[HotelOption]) -> List[HotelOption]:
    """
    Deduplicate hotel options by real-world identity.

    If duplicates are found, we keep the one with:
      - higher rating, then
      - lower price.
    """
    best_by_key: dict[Tuple[Any, ...], HotelOption] = {}

    for opt in options:
        key = _dedupe_key(opt)

        if key not in best_by_key:
            best_by_key[key] = opt
            continue

        current = best_by_key[key]

        # Prefer higher rating
        if opt.rating > current.rating:
            best_by_key[key] = opt
            continue

        # If rating is equal, prefer cheaper
        if opt.rating == current.rating:
            if opt.price and current.price and opt.price.amount < current.price.amount:
                best_by_key[key] = opt
                continue

        # Tie-breaker: higher score wins
        if (opt.score or 0.0) > (current.score or 0.0):
            best_by_key[key] = opt

    return list(best_by_key.values())


def _base_score(option: HotelOption) -> float:
    """
    Neutral composite score:
      - rating (higher is better)
      - price (lower is better)
      - distance_from_center_km (closer is better, if provided)
    """
    rating_component = option.rating / 5.0 if option.rating else 0.0

    price_component = 0.0
    if option.price and option.price.amount > 0:
        price_component = 1.0 / option.price.amount

    distance_component = 0.0
    if option.distance_from_center_km is not None:
        # Closer gets more points; beyond ~10km the effect diminishes
        distance_component = max(0.0, 1.0 - (option.distance_from_center_km / 10.0))

    # Weighted sum; tweak as needed
    return 0.5 * rating_component + 0.3 * price_component + 0.2 * distance_component


def _apply_preference_bias(
    score: float,
    option: HotelOption,
    preference: Optional[str],
) -> float:
    """
    Adjust score based on user preference.

    - cheapest: heavier weight on low price
    - luxury: favor higher rating & higher price
    - high-rating: strong boost for rating
    """
    if not preference:
        return score

    pref = preference.lower()

    if pref == HotelUserPreference.CHEAPEST:
        if option.price and option.price.amount > 0:
            score += 0.6 * (1.0 / option.price.amount)

    elif pref == HotelUserPreference.LUXURY:
        # Reward high rating and NOT extremely low price
        score += 0.3 * (option.rating / 5.0)
        if option.price and option.price.amount > 0:
            score += 0.2 * (option.price.amount ** 0.3)  # lightly reward higher price

    elif pref == HotelUserPreference.HIGH_RATING:
        score += 0.4 * (option.rating / 5.0)

    # BALANCED or unknown => no extra bias
    return score


def rank_hotels(
    options: Sequence[HotelOption],
    preference: Optional[str],
) -> List[HotelOption]:
    """
    Compute composite scores with user bias, then return hotels ordered
    from best to worst.
    """
    ranked: List[HotelOption] = []

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
    func: Callable[[], Awaitable[List[HotelOption]]],
    retries: int = PROVIDER_MAX_RETRIES,
    tolerate_error_texts: Sequence[str] = ("NO ROOMS", "NO ROOMS AVAILABLE", "INVALID PROPERTY", "INVALID PROPERTY CODE", "INVALID OR MISSING DATA"),
) -> List[HotelOption]:
    """
    Simple async retry with exponential backoff.

    - If an exception message contains any string in `tolerate_error_texts`,
      we treat that as a non-retriable provider-specific 'business' error and
      return an empty list immediately (don't propagate).
    - For other exceptions, we retry up to `retries`.
    """
    delay = 0.5
    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            return await func()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            text = str(exc).upper()

            # If exception clearly indicates no inventory / invalid property,
            # log and return empty result rather than retrying.
            if any(tok in text for tok in (t.upper() for t in tolerate_error_texts)):
                try:
                    provider_name = getattr(func.__self__, "name", None)
                except Exception:
                    provider_name = None
                print(f"[tolerate] provider={provider_name} non-retriable error (treated as empty): {exc!r}")
                return []

            # Otherwise treat as transient and maybe retry
            try:
                provider_name = getattr(func.__self__, "name", None)
            except Exception:
                provider_name = None
            print(f"[retry] attempt {attempt+1} failed for provider={provider_name}: {exc!r}")

            if attempt == retries:
                break
            await asyncio.sleep(delay)
            delay *= 2

    # All retries exhausted — log and return empty list
    print(f"[retry] exhausted retries; returning empty results. last_exc={last_exc!r}")
    return []


# ---------------------------------------------------------------------------
# Hotels Agent (with simple in-memory cache)
# ---------------------------------------------------------------------------

PartialCallback = Callable[[HotelSearchResponse], Awaitable[None]]


@dataclass
class _CacheEntry:
    expires_at: float
    options: List[HotelOption]


class HotelsAgent:
    """
    Hotels Agent responsible for:
      - querying multiple providers in parallel
      - deduping and ranking results
      - returning up to 5 normalized HotelOption objects
      - optionally emitting a fast, tentative partial response
      - simple in-memory caching with ~5 minute TTL
    """

    def __init__(self, providers: Iterable[HotelProvider]) -> None:
        self.providers: List[HotelProvider] = list(providers)
        self._cache: dict[str, _CacheEntry] = {}

    # ------------- public API -------------

    async def search(
        self,
        request: HotelSearchRequest,
        on_partial: Optional[PartialCallback] = None,
        use_cache: bool = True,
    ) -> List[HotelOption]:
        """
        Main entrypoint for Supervisor/Planner.

        - Caches results for HOTEL_CACHE_TTL_SECONDS if use_cache=True.
        - Executes provider calls in parallel with retries & per-call timeout.
        - Optionally emits a fast tentative response via `on_partial`.
        - Returns final, deduped + ranked list (up to request.limit).
        """
        import time
        cache_key = self._cache_key(request)

        # Try cache first
        now = time.time()
        if use_cache and cache_key in self._cache:
            entry = self._cache[cache_key]
            if entry.expires_at > now:
                cached = entry.options[: request.limit]
                if on_partial and cached:
                    await on_partial(
                        HotelSearchResponse(
                            status=HotelResultStatus.FINAL,
                            options=cached,
                        )
                    )
                return cached
            else:
                self._cache.pop(cache_key, None)

        async def run_all_providers() -> List[HotelOption]:
            # Build tasks for each provider (each task returns List[HotelOption])
            tasks: List[Awaitable[List[HotelOption]]] = []

            for provider in self.providers:
                async def _call_provider(p: HotelProvider = provider) -> List[HotelOption]:
                    async def call() -> List[HotelOption]:
                        return await asyncio.wait_for(
                            p.search_hotels(request),
                            timeout=PROVIDER_TIMEOUT_SECONDS,
                        )

                    return await _with_retries(call, retries=PROVIDER_MAX_RETRIES)

                tasks.append(_call_provider())

            # Run providers concurrently, but don't let one provider exception stop others.
            # Using gather(return_exceptions=True) and coerce exceptions to empty lists.
            results: List[HotelOption] = []
            partial_emitted = False

            # gather with return_exceptions so we can log failures and continue
            gathered = await asyncio.gather(*tasks, return_exceptions=True)

            for idx, provider_result in enumerate(gathered):
                # get provider name if possible
                try:
                    provider_name = getattr(self.providers[idx], "name", None)
                except Exception:
                    provider_name = None

                # If the task returned an exception object (including CancelledError),
                # log and skip it. `return_exceptions=True` causes exceptions to be
                # returned rather than raised.
                if isinstance(provider_result, Exception):
                    # Distinguish CancelledError for more informative logs if desired
                    if isinstance(provider_result, asyncio.CancelledError):
                        print(f"[provider done] provider index={idx} name={provider_name} was cancelled.")
                    else:
                        print(f"[provider done] provider index={idx} name={provider_name} raised: {provider_result!r}")
                    continue

                # Normal case: provider_result should be a list of HotelOption
                got = len(provider_result or [])
                print(f"[provider done] got {got} options from provider name={provider_name} (task index={idx})")
                results.extend(provider_result or [])

                # Trigger one tentative partial emission when we have something useful
                if on_partial and not partial_emitted and len(results) > 0:
                    tentative = self._postprocess(
                        options=results,
                        preference=request.user_preference,
                        limit=min(3, request.limit),
                    )
                    if tentative:
                        partial_emitted = True
                        await on_partial(
                            HotelSearchResponse(
                                status=HotelResultStatus.TENTATIVE,
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
            all_results = []

        final_options = self._postprocess(
            options=all_results,
            preference=request.user_preference,
            limit=request.limit,
        )

        # Update cache
        if use_cache and final_options:
            import time
            self._cache[cache_key] = _CacheEntry(
                expires_at=time.time() + HOTEL_CACHE_TTL_SECONDS,
                options=final_options,
            )

        if on_partial and final_options:
            await on_partial(
                HotelSearchResponse(
                    status=HotelResultStatus.FINAL,
                    options=final_options,
                )
            )

        print(f"[FINAL RESULTS] count={len(final_options)}")
        for o in final_options:
            if o.price:
                price_str = f"{o.price.amount} {o.price.currency}"
            else:
                price_str = "N/A"
            # rating may also be optional/None; coerce to numeric default
            rating_str = f"{o.rating}" if o.rating is not None else "N/A"
            print(f"- {o.id} provider={o.provider} price={price_str} rating={rating_str}")



        return final_options

    # ------------- internal helpers -------------

    @staticmethod
    def _postprocess(
        options: Sequence[HotelOption],
        preference: Optional[str],
        limit: int,
    ) -> List[HotelOption]:
        if not options:
            return []

        deduped = dedupe_hotels(options)
        ranked = rank_hotels(deduped, preference=preference)
        return ranked[:limit]

    @staticmethod
    def _cache_key(request: HotelSearchRequest) -> str:
        """
        Build a simple cache key based on location + dates + main filters.
        """
        dest = (request.destination or "").lower()
        lat = request.lat or 0.0
        lon = request.lon or 0.0

        # Round coords to avoid exploding cache keys
        lat = round(lat, 3)
        lon = round(lon, 3)

        parts = [
            f"dest:{dest}",
            f"lat:{lat}",
            f"lon:{lon}",
            f"checkin:{request.checkin_date.isoformat()}",
            f"checkout:{request.checkout_date.isoformat()}",
            f"min_rating:{request.min_rating or ''}",
            f"stars:{request.star_rating_only or ''}",
            f"pets:{int(request.pets_allowed_only)}",
            f"amenities:{','.join(sorted([a.lower() for a in request.amenities_must_have]))}",
        ]
        return "|".join(parts)
