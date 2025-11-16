
"""Currency conversion and FX rate tools"""
import requests
from typing import Dict
from datetime import datetime, timedelta
from models.budget import FXConversion

_fx_rate_cache: Dict[str, Dict] = {}
_cache_duration = timedelta(hours=1)

def get_fx_rates(base_currency: str = "USD") -> Dict[str, float]:
    cache_key = f"rates_{base_currency}"
    if cache_key in _fx_rate_cache:
        cached = _fx_rate_cache[cache_key]
        if datetime.now() - cached["timestamp"] < _cache_duration:
            return cached["rates"]
    
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        rates = data.get("rates", {})
        _fx_rate_cache[cache_key] = {"rates": rates, "timestamp": datetime.now()}
        return rates
    except:
        usd_rates = {"USD": 1.0, "EUR": 0.92, "GBP": 0.79, "JPY": 149.0, "CAD": 1.38, "AUD": 1.52, "INR": 83.2}
        if base_currency == "USD":
            return usd_rates
        base_to_usd = 1.0 / usd_rates.get(base_currency, 1.0)
        return {currency: rate * base_to_usd for currency, rate in usd_rates.items()}

def convert_currency(amount: float, from_currency: str, to_currency: str) -> FXConversion:
    if from_currency == to_currency:
        return FXConversion(amount=amount, from_currency=from_currency, to_currency=to_currency,
                          converted_amount=amount, exchange_rate=1.0, timestamp=datetime.now())
    
    rates = get_fx_rates(from_currency)
    if to_currency not in rates:
        raise ValueError(f"Unsupported currency: {to_currency}")
    
    exchange_rate = rates[to_currency]
    converted_amount = amount * exchange_rate
    
    return FXConversion(amount=amount, from_currency=from_currency, to_currency=to_currency,
                       converted_amount=round(converted_amount, 2), exchange_rate=round(exchange_rate, 4),
                       timestamp=datetime.now())