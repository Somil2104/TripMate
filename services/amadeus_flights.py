from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from models.flights import (
    FlightOption,
    FlightProvider,
    FlightSearchRequest,
    Money,
)
from services.amadeus_client import AmadeusClient


class AmadeusFlightProvider(FlightProvider):
    """
    Amadeus implementation of FlightProvider using the
    Flight Offers Search API (GET /v2/shopping/flight-offers).
    """

    def __init__(self, client: AmadeusClient, currency: str = "USD") -> None:
        super().__init__(name="amadeus")
        self.client = client
        self.currency = currency

    async def search_flights(self, request: FlightSearchRequest) -> List[FlightOption]:
        params: Dict[str, Any] = {
            "originLocationCode": request.origin,
            "destinationLocationCode": request.destination,
            "departureDate": request.departure_date.isoformat(),
            "adults": 1,  # MVP: assume 1 adult; extend later as needed
            "max": 20,    # get more, we'll rank & trim to 5
        }

        if request.return_date:
            params["returnDate"] = request.return_date.isoformat()

        if request.cabin_class:
            # Amadeus expects: ECONOMY, PREMIUM_ECONOMY, BUSINESS, FIRST
            params["travelClass"] = request.cabin_class.upper()

        if request.non_stop_only:
            params["nonStop"] = "true"

        if self.currency:
            params["currencyCode"] = self.currency

        try:
            json_data = await self.client.get(
                "/v2/shopping/flight-offers", params=params
            )
        except Exception:
            # In a real app, log this error properly; agent will handle empty list gracefully
            return []

        data = json_data.get("data") or []
        results: List[FlightOption] = []

        for raw_offer in data:
            try:
                opt = self._parse_offer(raw_offer, request.departure_date)
                if opt is not None:
                    results.append(opt)
            except Exception:
                # Skip malformed offers
                continue

        return results

    def _parse_offer(
        self, offer: Dict[str, Any], requested_departure_date: date
    ) -> Optional[FlightOption]:
        """
        Map Amadeus flight offer JSON into our FlightOption model.

        We only look at the *first* itinerary (outbound) for scoring & display
        in this MVP.
        """
        price_info = offer.get("price") or {}
        total_price_str = price_info.get("total")
        currency = price_info.get("currency", self.currency)

        if total_price_str is None:
            return None

        try:
            total_amount = float(total_price_str)
        except ValueError:
            return None

        itineraries = offer.get("itineraries") or []
        if not itineraries:
            return None

        outbound = itineraries[0]
        duration = outbound.get("duration", "")
        segments = outbound.get("segments") or []
        if not segments:
            return None

        # Stops = number of segments minus 1
        stops = max(len(segments) - 1, 0)

        first_seg = segments[0]
        last_seg = segments[-1]

        carrier_code = first_seg.get("carrierCode")
        flight_number = first_seg.get("number")

        origin_code = first_seg.get("departure", {}).get("iataCode")
        dest_code = last_seg.get("arrival", {}).get("iataCode")

        # Departure date: parse YYYY-MM-DD from the 'at' field, fallback to requested date
        departure_at = first_seg.get("departure", {}).get("at")
        dep_date: Optional[date] = None
        if departure_at:
            try:
                dep_date = datetime.fromisoformat(departure_at).date()
            except ValueError:
                dep_date = requested_departure_date
        else:
            dep_date = requested_departure_date

        # Fare class: use travelerPricings[0].fareDetailsBySegment[0].cabin as a proxy
        fare_class = "UNKNOWN"
        traveler_pricings = offer.get("travelerPricings") or []
        if traveler_pricings:
            first_tp = traveler_pricings[0]
            fdbs = first_tp.get("fareDetailsBySegment") or []
            if fdbs:
                cabin = fdbs[0].get("cabin")
                if cabin:
                    fare_class = cabin

        return FlightOption(
            id=str(offer.get("id")),
            provider="amadeus",
            price=Money(amount=total_amount, currency=currency),
            fare_class=fare_class,
            duration=duration,
            stops=stops,
            carrier_code=carrier_code,
            flight_number=flight_number,
            origin=origin_code,
            destination=dest_code,
            departure_date=dep_date,
        )
