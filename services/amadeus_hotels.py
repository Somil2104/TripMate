from __future__ import annotations

import asyncio
import random
from datetime import date
from typing import Any, Dict, List, Optional

from httpx import HTTPStatusError

from models.hotels import (
    CheckinCheckoutTimes,
    GeoPoint,
    HotelOption,
    HotelProvider,
    HotelSearchRequest,
    Money,
)
from services.amadeus_client import AmadeusClient


class AmadeusHotelProvider(HotelProvider):
    """
    Amadeus implementation of HotelProvider using the Hotel List (v1)
    to get hotelIds, then v3 /shopping/hotel-offers to fetch offers.

    This version is resilient to 400/429 responses and rate limits.
    """

    def __init__(self, client: AmadeusClient, currency: str = "USD") -> None:
        super().__init__(name="amadeus_hotels")
        self.client = client
        self.currency = currency

    async def search_hotels(self, request: HotelSearchRequest) -> List[HotelOption]:
        if not request.destination:
            return []

        # 1) Resolve city -> hotel IDs using Hotel List API (v1)
        try:
            list_params = {"cityCode": request.destination}
            print("[amadeus] Looking up hotels for city:", request.destination)
            list_payload = await self.client.get(
                "/v1/reference-data/locations/hotels/by-city", params=list_params
            )
        except Exception as exc:
            print("[amadeus] hotel-list API failed:", repr(exc))
            return []

        hotels_data = list_payload.get("data") or []
        if not hotels_data:
            print("[amadeus] no hotels found for city:", request.destination)
            return []

        # Extract hotel IDs safely
        hotel_ids: List[str] = []
        for h in hotels_data:
            hid = h.get("hotelId") or h.get("id") or (h.get("hotel") or {}).get("hotelId")
            if hid:
                hotel_ids.append(str(hid))

        if not hotel_ids:
            print("[amadeus] could not extract any hotelIds from hotel-list response")
            return []

        # Tune limits for stability
        MAX_HOTEL_IDS = 6         # limit total hotels we'll query (keep small to avoid 429)
        CHUNK_SIZE = 1            # how many hotelIds per offers request (1 = safest)
        MAX_HOTEL_IDS = min(MAX_HOTEL_IDS, len(hotel_ids))
        hotel_ids = hotel_ids[:MAX_HOTEL_IDS]
        print(
            f"[amadeus] found {len(hotel_ids)} hotelIds, querying offers in chunks of {CHUNK_SIZE}"
        )

        # Build common offer query params
        base_offer_params = {
            "checkInDate": request.checkin_date.isoformat(),
            "checkOutDate": request.checkout_date.isoformat(),
            "adults": 1,
            "roomQuantity": 1,
        }
        if self.currency:
            base_offer_params["currencyCode"] = self.currency

        # --- inner helper: fetch single chunk with retries & backoff ---
                # --- Replacement: tolerant fetch + per-hotel fallback that returns HotelOption(s) ---
        # Build a lookup map from hotelId -> hotel metadata (from hotel-list response),
        # so we can produce partial HotelOption objects when offers are missing.
        metadata_map: Dict[str, Dict[str, Any]] = {}
        for h in hotels_data:
            hid = h.get("hotelId") or h.get("id") or (h.get("hotel") or {}).get("hotelId")
            if not hid:
                continue
            metadata_map[str(hid)] = h

        async def _call_offers(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            # Single HTTP call wrapper that returns parsed JSON or raises HTTPStatusError
            return await self.client.get("/v3/shopping/hotel-offers", params=params)

        async def fetch_offers_for_hotel_ids(
            client,
            ids: List[str],
            base_params: Dict[str, Any],
            chunk_size: int = 1,
        ) -> List[HotelOption]:
            """
            Robust fetcher that:
              - queries ids in chunks
              - on chunk 400 will try per-hotel calls and create partial HotelOption entries for
                business errors like NO ROOMS or RATE NOT AVAILABLE while skipping INVALID PROPERTY.
              - on 429 respects Retry-After or performs exponential backoff.
              - always returns a list of HotelOption (price may be None for partials).
            """
            out: List[HotelOption] = []

            async def try_chunk(chunk: List[str]) -> Optional[List[Dict[str, Any]]]:
                params = dict(base_params)
                params["hotelIds"] = ",".join(chunk)
                MAX_ATTEMPTS = 3
                backoff = 0.5

                for attempt in range(1, MAX_ATTEMPTS + 1):
                    try:
                        print(f"[amadeus] chunk request (attempt {attempt}) hotelIds={params['hotelIds']}")
                        payload = await _call_offers(params)
                        return payload.get("data") or []
                    except HTTPStatusError as http_err:
                        resp = getattr(http_err, "response", None)
                        status = getattr(resp, "status_code", None)
                        # attempt to read body text safely
                        text_snip = ""
                        try:
                            text_snip = (getattr(resp, "text", "") or str(http_err))[:2000].replace("\n", " ")
                        except Exception:
                            text_snip = str(http_err)[:2000]
                        print(f"[amadeus] HTTPStatusError {status} for chunk {params['hotelIds']}: {text_snip}")

                        # Rate limiting -> follow Retry-After or backoff
                        if status == 429:
                            ra = None
                            try:
                                ra = resp.headers.get("Retry-After") if resp is not None else None
                            except Exception:
                                ra = None
                            if ra:
                                try:
                                    wait = float(ra)
                                except Exception:
                                    wait = None
                                if wait:
                                    print(f"[amadeus] rate limited, server asked to wait {wait}s")
                                    await asyncio.sleep(wait + 0.1)
                                    continue
                            jitter = random.uniform(0.1, 0.6)
                            sleep_for = backoff + jitter
                            print(f"[amadeus] rate limited, sleeping {sleep_for:.2f}s before retry")
                            await asyncio.sleep(sleep_for)
                            backoff *= 2
                            continue

                        # 400-level business responses -> trigger per-hotel fallback (caller will handle)
                        if status == 400:
                            return None

                        # other status codes: log + don't retry
                        print(f"[amadeus] non-retryable HTTP error {status} for chunk; skipping chunk")
                        return []

                    except Exception as exc:
                        jitter = random.uniform(0.1, 0.5)
                        sleep_for = backoff + jitter
                        print(f"[amadeus] network/error for chunk (attempt {attempt}): {repr(exc)}; sleeping {sleep_for:.2f}s")
                        await asyncio.sleep(sleep_for)
                        backoff *= 2
                        continue

                print(f"[amadeus] exhausted retries for chunk {params['hotelIds']}")
                return []

            def _make_partial_option_from_metadata(hid: str) -> HotelOption:
                meta = metadata_map.get(hid, {}) or {}
                # try to pluck fields from meta in several common shapes
                hotel_obj = meta.get("hotel") or meta
                name = hotel_obj.get("name") or hotel_obj.get("hotelName") or None
                address_info = hotel_obj.get("address") or {}
                address_lines = address_info.get("lines") or []
                full_address = ", ".join(
                    address_lines + [address_info.get("city", "") or "", address_info.get("countryCode", "") or ""]
                ).strip(", ") or None

                geo = hotel_obj.get("geoCode") or {}
                lat = geo.get("latitude") or geo.get("lat") or 0.0
                lon = geo.get("longitude") or geo.get("lon") or 0.0

                rating_raw = hotel_obj.get("rating")
                try:
                    rating = float(rating_raw) if rating_raw is not None else 0.0
                except Exception:
                    rating = 0.0

                amenities = hotel_obj.get("amenities") or []

                return HotelOption(
                    id=str(hid),
                    provider="amadeus",
                    price=None,
                    rating=rating,
                    amenities=amenities,
                    location=GeoPoint(lat=float(lat), lon=float(lon)),
                    checkin_checkout_times=CheckinCheckoutTimes(),
                    name=name,
                    address=full_address,
                )

            # Process in chunks
            for i in range(0, len(ids), chunk_size):
                chunk = ids[i : i + chunk_size]
                chunk_resp = await try_chunk(chunk)

                # If chunk_resp is None → 400 occurred for chunk, fall back to single-id calls
                if chunk_resp is None:
                    print(f"[amadeus] chunk-level 400 for {chunk}, falling back to per-id attempts")
                    for hid in chunk:
                        single_params = dict(base_params)
                        single_params["hotelIds"] = hid
                        try:
                            payload = await _call_offers(single_params)
                            offers = payload.get("data") or []
                            if not offers:
                                # 200 but no offers → treat as no rooms: produce partial
                                print(f"[amadeus] individual call returned no offers for {hid}; creating partial option")
                                out.append(_make_partial_option_from_metadata(hid))
                                await asyncio.sleep(0.12)
                                continue

                            # Map each returned offer item into HotelOption (use existing parser)
                            for item in offers:
                                try:
                                    parsed = self._parse_hotel_item(item, request)
                                    if parsed:
                                        out.append(parsed)
                                except Exception as e:
                                    print(f"[amadeus] parser failed for single-id response {hid}: {repr(e)}")
                            await asyncio.sleep(0.12)
                        except HTTPStatusError as http_err_single:
                            resp_single = getattr(http_err_single, "response", None)
                            text_snip_single = ""
                            try:
                                text_snip_single = (getattr(resp_single, "text", "") or str(http_err_single))[:2000]
                            except Exception:
                                text_snip_single = str(http_err_single)[:2000]
                            print(f"[amadeus] single-id HTTP error for {hid}: {text_snip_single}")

                            status_single = getattr(resp_single, "status_code", None)
                            txt = (text_snip_single or "").upper()

                            # Skip invalid property codes
                            if status_single == 400 and ("INVALID PROPERTY" in txt or "INVALID PROPERTY CODE" in txt):
                                print(f"[amadeus] hotelId {hid} invalid; skipping.")
                                continue

                            # No rooms / rate restricted -> create partial HotelOption
                            if status_single == 400 and (
                                "NO ROOMS" in txt
                                or "ROOM OR RATE NOT AVAILABLE" in txt
                                or "RATE NOT AVAILABLE" in txt
                                or "RESTRICTED" in txt
                                or "UNABLE TO PROCESS" in txt
                            ):
                                print(f"[amadeus] hotelId {hid} no rooms/rate restricted -> returning partial hotel (no price).")
                                out.append(_make_partial_option_from_metadata(hid))
                                continue

                            # 429 handling (honor Retry-After header if present here too)
                            if status_single == 429:
                                try:
                                    ra = resp_single.headers.get("Retry-After") if resp_single is not None else None
                                except Exception:
                                    ra = None
                                if ra:
                                    try:
                                        wait = float(ra)
                                    except Exception:
                                        wait = None
                                    if wait:
                                        print(f"[amadeus] single-id 429; sleeping {wait}s before retry")
                                        await asyncio.sleep(wait + 0.1)
                                        # attempt retry once
                                        try:
                                            payload = await _call_offers(single_params)
                                            offers = payload.get("data") or []
                                            if not offers:
                                                out.append(_make_partial_option_from_metadata(hid))
                                            else:
                                                for item in offers:
                                                    parsed = self._parse_hotel_item(item, request)
                                                    if parsed:
                                                        out.append(parsed)
                                            await asyncio.sleep(0.12)
                                            continue
                                        except Exception:
                                            print(f"[amadeus] retry after 429 failed for {hid}; skipping.")
                                            continue

                            # Other errors -> skip
                            print(f"[amadeus] skipping hotelId {hid} due to error.")
                            continue

                else:
                    # chunk_resp is a list (possibly empty) of returned items
                    offers = chunk_resp
                    if not offers:
                        # chunk call returned 200 but no items -> produce partials for each id
                        for hid in chunk:
                            print(f"[amadeus] chunk returned empty offers for {hid}; creating partial option")
                            out.append(_make_partial_option_from_metadata(hid))
                        await asyncio.sleep(0.12)
                    else:
                        for item in offers:
                            try:
                                parsed = self._parse_hotel_item(item, request)
                                if parsed:
                                    out.append(parsed)
                            except Exception as e:
                                print("[amadeus] mapping failed for offer:", repr(e))
                                continue

            return out

        # Use the tolerant fetcher to get HotelOption objects (may have price=None)
        results: List[HotelOption] = await fetch_offers_for_hotel_ids(
            client=self.client,
            ids=hotel_ids,
            base_params=base_offer_params,
            chunk_size=CHUNK_SIZE,
        )

        print(f"[amadeus] mapped total {len(results)} HotelOption(s)")
        return results


    # ------------------------------------------------------------------ #
    # Parsing helpers (unchanged)
    # ------------------------------------------------------------------ #

    def _parse_hotel_item(
        self,
        item: Dict[str, Any],
        request: HotelSearchRequest,
    ) -> Optional[HotelOption]:
        hotel = item.get("hotel") or {}
        offers = item.get("offers") or []
        if not offers:
            return None

        # Pick the cheapest offer for this hotel
        cheapest_offer = self._get_cheapest_offer(offers)
        price_info = cheapest_offer.get("price") or {}
        total_str = price_info.get("total")
        currency = price_info.get("currency", self.currency)

        if total_str is None:
            return None

        try:
            total_amount = float(total_str)
        except Exception:
            return None

        # Basic hotel info
        name = hotel.get("name")
        address_info = hotel.get("address") or {}
        address_lines = address_info.get("lines") or []
        full_address = ", ".join(
            address_lines
            + [
                address_info.get("postalCode", "") or "",
                address_info.get("city", "") or "",
                address_info.get("countryCode", "") or "",
            ]
        ).strip(", ")

        geo = hotel.get("geoCode") or {}
        lat = geo.get("latitude")
        lon = geo.get("longitude")
        if lat is None or lon is None:
            return None

        # Rating
        rating_raw = hotel.get("rating")
        try:
            rating = float(rating_raw) if rating_raw is not None else 0.0
        except Exception:
            rating = 0.0

        amenities = hotel.get("amenities") or []
        distance_info = hotel.get("distance") or {}
        distance_from_center_km = distance_info.get("value")

        cheapest_offer = cheapest_offer or {}
        checkin_date_str = cheapest_offer.get("checkInDate")
        checkout_date_str = cheapest_offer.get("checkOutDate")

        checkin_checkout = CheckinCheckoutTimes(
            checkin=checkin_date_str,
            checkout=checkout_date_str,
        )

        return HotelOption(
            id=str(item.get("id") or item.get("hotel", {}).get("hotelId") or ""),
            provider="amadeus",
            price=Money(amount=total_amount, currency=currency),
            rating=rating,
            amenities=amenities,
            location=GeoPoint(lat=lat, lon=lon),
            checkin_checkout_times=checkin_checkout,
            name=name,
            address=full_address or None,
            distance_from_center_km=distance_from_center_km,
        )

    @staticmethod
    def _get_cheapest_offer(offers: List[Dict[str, Any]]) -> Dict[str, Any]:
        def get_price(o: Dict[str, Any]) -> float:
            try:
                return float(o.get("price", {}).get("total", "inf"))
            except Exception:
                return float("inf")

        return min(offers, key=get_price)

    @staticmethod
    def _is_pets_allowed(amenities: List[str]) -> bool:
        lowered = {a.lower() for a in amenities}
        keywords = ["pet friendly", "pets allowed", "pet-friendly"]
        return any(k in lowered_elem for lowered_elem in lowered for k in keywords)
