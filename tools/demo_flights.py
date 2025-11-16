import asyncio
from datetime import date

from models.flights import FlightSearchRequest, FlightsAgent
from services.amadeus_client import AmadeusClient
from services.amadeus_flights import AmadeusFlightProvider


async def main() -> None:
    client = AmadeusClient()
    provider = AmadeusFlightProvider(client, currency="INR")  # or "USD", etc.
    agent = FlightsAgent([provider])

    request = FlightSearchRequest(
        origin="DEL",
        destination="BOM",
        departure_date=date(2025, 12, 1),
        user_preference="cheapest",  # "non-stop", "comfort", etc.
        non_stop_only=False,
    )

    # Optional: partial callback, here just prints tentative results sizes
    async def on_partial(resp):
        print(f"[PARTIAL] status={resp.status}, options={len(resp.options)}")

    options = await agent.search(request, on_partial=on_partial)

    print("\n[FINAL RESULTS]")
    for i, opt in enumerate(options, start=1):
        print(
            f"{i}. {opt.origin}->{opt.destination} {opt.departure_date} "
            f"{opt.carrier_code}{opt.flight_number} "
            f"{opt.duration}, stops={opt.stops}, "
            f"{opt.price.amount} {opt.price.currency}, fare={opt.fare_class}"
        )

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
