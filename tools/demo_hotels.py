import asyncio
from datetime import date
import traceback

from models.hotels import HotelSearchRequest, HotelsAgent
from services.amadeus_client import AmadeusClient
from services.amadeus_hotels import AmadeusHotelProvider


async def main() -> None:
    # Make sure your AMADEUS_CLIENT_ID / AMADEUS_CLIENT_SECRET env vars are set
    client = AmadeusClient()
    provider = AmadeusHotelProvider(client, currency="INR")  # or "USD"
    providers = [provider]  # list expected by HotelsAgent
    agent = HotelsAgent(providers)

    # NOTE: destination here is the Amadeus cityCode, e.g. "BOM" for Mumbai.
    request = HotelSearchRequest(
        destination="LON",
        checkin_date=date(2025, 12, 1),
        checkout_date=date(2025, 12, 3),
        user_preference="balanced",  # "cheapest", "luxury", "high-rating", etc.
        min_rating=3.5,              # optional
        star_rating_only=None,       # e.g. 4 for 4-star only
        amenities_must_have=[],      # e.g. ["Free WiFi", "Air conditioning"]
        pets_allowed_only=False,
    )

    async def on_partial(resp):
        print(f"[PARTIAL] status={resp.status}, options={len(resp.options)}")

    # --- FIXED: provider is a single object, providers is the list ---
    print("Providers count:", len(providers))
    print("Providers:", [getattr(p, "name", repr(p)) for p in providers])

    try:
        options = await agent.search(request, on_partial=on_partial)
    except Exception as exc:
        print("agent.search() raised an exception:")
        traceback.print_exc()
        options = []

    print("\n[FINAL RESULTS]")
    if not options:
        print("No hotels returned. See logs above for provider errors or timeouts.")
    for i, opt in enumerate(options, start=1):
        # Safe price formatting
        if opt.price:
            price_str = f"{opt.price.amount} {opt.price.currency}"
        else:
            price_str = "N/A"

        rating_str = f"{opt.rating}" if opt.rating is not None else "N/A"

        print(f"{i}. {opt.name or 'Unknown name'} (rating={rating_str}, price={price_str})")

        print(
            f"   Location: {opt.location.lat}, {opt.location.lon} | "
            f"Address: {opt.address or 'N/A'}"
        )

        print(
            f"   Check-in: {opt.checkin_checkout_times.checkin or 'N/A'} | "
            f"Check-out: {opt.checkin_checkout_times.checkout or 'N/A'}"
        )

        print(f"   Amenities sample: {', '.join(opt.amenities[:5]) if opt.amenities else 'N/A'}")
        print()


    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
