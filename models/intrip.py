
"""
Data models for In-Trip Agent
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class Severity(str, Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


class WeatherAlert(BaseModel):
    """Weather alert information"""
    location: str = Field(..., description="Location for this alert")
    alert_type: str = Field(..., description="Type of weather alert")
    severity: Severity = Field(..., description="Severity level")
    description: str = Field(..., description="Human-readable description")
    start_time: datetime = Field(..., description="When alert starts")
    end_time: datetime = Field(..., description="When alert ends")
    recommendations: List[str] = Field(default_factory=list, description="Recommended actions")
    temperature_celsius: Optional[float] = Field(None, description="Temperature if relevant")


class NavigationMode(str, Enum):
    """Transportation modes"""
    DRIVING = "driving"
    WALKING = "walking"
    TRANSIT = "transit"
    BICYCLING = "bicycling"


class NavigationStep(BaseModel):
    """Individual navigation step"""
    instruction: str = Field(..., description="Turn-by-turn instruction")
    distance_meters: float = Field(..., description="Distance for this step")
    duration_seconds: int = Field(..., description="Time for this step")


class NavigationResult(BaseModel):
    """Navigation directions and ETA"""
    origin: str = Field(..., description="Starting location")
    destination: str = Field(..., description="Destination location")
    distance_km: float = Field(..., description="Total distance in kilometers")
    duration_minutes: int = Field(..., description="Estimated duration in minutes")
    eta: datetime = Field(..., description="Estimated time of arrival")
    mode: NavigationMode = Field(default=NavigationMode.DRIVING, description="Transportation mode")
    steps: List[NavigationStep] = Field(default_factory=list, description="Turn-by-turn directions")
    traffic_conditions: str = Field(default="unknown", description="Current traffic conditions")


class TranslationResult(BaseModel):
    """Translation result"""
    original_text: str = Field(..., description="Original text")
    translated_text: str = Field(..., description="Translated text")
    source_language: str = Field(..., description="Detected source language code")
    target_language: str = Field(..., description="Target language code")
    confidence: float = Field(default=1.0, description="Translation confidence (0-1)")


class RePlanTrigger(BaseModel):
    """Trigger for re-planning itinerary"""
    trigger_type: str = Field(..., description="Type: severe_weather, long_travel_time, etc.")
    severity: Severity = Field(..., description="Severity of the trigger")
    description: str = Field(..., description="Description of the issue")
    affected_items: List[str] = Field(default_factory=list, description="Affected activities or bookings")
    recommended_action: str = Field(..., description="Recommended action to take")
    timestamp: datetime = Field(default_factory=datetime.now, description="When trigger was detected")