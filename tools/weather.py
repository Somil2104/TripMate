
"""Weather forecast and alert tools"""
import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import os

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "demo_key")

def get_weather_forecast(location: str, days: int = 3) -> Dict:
    try:
        base_date = datetime.now()
        daily_forecast = []
        for i in range(days):
            date = base_date + timedelta(days=i)
            daily_forecast.append({
                "date": date,
                "temp_min": 10 + i * 2,
                "temp_max": 20 + i * 2,
                "condition": "Clear" if i % 2 == 0 else "Clouds",
                "description": "clear sky" if i % 2 == 0 else "few clouds",
                "humidity": 60,
                "wind_speed": 15,
                "precipitation_probability": 20 if i % 3 == 0 else 5,
                "uvi": 5
            })
        return {"location": location, "daily": daily_forecast, "timezone": "UTC"}
    except Exception as e:
        print(f"Weather API error: {e}")
        return {"location": location, "daily": [], "timezone": "UTC"}

def check_severe_weather(day_forecast: Dict) -> Optional[Dict]:
    condition = day_forecast.get("condition", "").lower()
    temp_max = day_forecast.get("temp_max", 20)
    temp_min = day_forecast.get("temp_min", 20)
    precip_prob = day_forecast.get("precipitation_probability", 0)
    
    if condition in ["thunderstorm", "storm"]:
        return {"type": "Thunderstorm", "severity": "high", "description": "Severe thunderstorms expected",
                "recommendations": ["Stay indoors", "Avoid outdoor activities"]}
    if precip_prob > 80:
        return {"type": "Heavy Rain", "severity": "medium", "description": f"High chance of rain ({precip_prob:.0f}%)",
                "recommendations": ["Bring umbrella", "Consider indoor activities"]}
    if temp_max > 38:
        return {"type": "Extreme Heat", "severity": "high", "description": f"Extreme heat warning ({temp_max:.1f}°C)",
                "recommendations": ["Stay hydrated", "Avoid midday sun"]}
    if temp_min < -10:
        return {"type": "Extreme Cold", "severity": "high", "description": f"Extreme cold warning ({temp_min:.1f}°C)",
                "recommendations": ["Dress in layers", "Limit outdoor exposure"]}
    return None