
"""Maps and navigation tools"""
import requests
from typing import Dict
from datetime import datetime, timedelta
import os
from models.intrip import NavigationStep

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "demo_key")

def get_directions(origin: str, destination: str, mode: str = "driving") -> Dict:
    distances = {"driving": 15.0, "walking": 2.0, "transit": 10.0, "bicycling": 5.0}
    speeds = {"driving": 50, "walking": 5, "transit": 30, "bicycling": 15}
    
    distance_km = distances.get(mode, 10.0)
    speed = speeds.get(mode, 30)
    duration_minutes = (distance_km / speed) * 60
    
    return {
        "distance_km": distance_km,
        "duration_minutes": duration_minutes,
        "steps": [NavigationStep(instruction=f"Head toward {destination}",
                                distance_meters=distance_km * 1000,
                                duration_seconds=int(duration_minutes * 60))],
        "traffic": "moderate",
        "start_address": origin,
        "end_address": destination
    }

def calculate_eta(origin: str, destination: str, departure_time: datetime = None) -> datetime:
    if departure_time is None:
        departure_time = datetime.now()
    directions = get_directions(origin, destination, "driving")
    duration_minutes = directions["duration_minutes"]
    return departure_time + timedelta(minutes=duration_minutes)