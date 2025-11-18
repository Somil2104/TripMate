
"""In-Trip Agent - Handles weather, navigation, translation, and re-planning triggers"""
from typing import List
from datetime import datetime
from models.intrip import WeatherAlert, NavigationResult, TranslationResult, RePlanTrigger, Severity
from tools.weather import get_weather_forecast, check_severe_weather
from tools.maps import get_directions, calculate_eta
from tools.translate import translate_text, detect_language


async def get_weather_alert(location: str, dates: List[datetime]) -> List[WeatherAlert]:
    """Get weather alerts for location and date range"""
    forecast = get_weather_forecast(location, days=len(dates))
    alerts = []
    
    for day_forecast in forecast.get("daily", []):
        severe = check_severe_weather(day_forecast)
        if severe:
            alert = WeatherAlert(
                location=location,
                alert_type=severe["type"],
                severity=Severity(severe["severity"]),
                description=severe["description"],
                start_time=day_forecast["date"],
                end_time=day_forecast["date"],
                recommendations=severe["recommendations"],
                temperature_celsius=day_forecast.get("temp_max")
            )
            alerts.append(alert)
    
    return alerts


async def get_navigation(origin: str, destination: str, mode: str = "driving") -> NavigationResult:
    """Get navigation directions and ETA"""
    directions = get_directions(origin, destination, mode)
    eta = calculate_eta(origin, destination)
    
    from models.intrip import NavigationMode
    return NavigationResult(
        origin=origin,
        destination=destination,
        distance_km=directions["distance_km"],
        duration_minutes=int(directions["duration_minutes"]),
        eta=eta,
        mode=NavigationMode(mode),
        steps=directions["steps"],
        traffic_conditions=directions.get("traffic", "unknown")
    )


async def translate_phrase(text: str, target_language: str) -> TranslationResult:
    """Translate text to target language"""
    translation = translate_text(text, target_language, "auto")
    
    return TranslationResult(
        original_text=text,
        translated_text=translation["text"],
        source_language=translation["source_lang"],
        target_language=target_language,
        confidence=translation.get("confidence", 1.0)
    )


async def check_replan_triggers(location: str, dates: List[datetime],
                               navigation_duration: int = 0) -> List[RePlanTrigger]:
    """Check if re-planning is needed based on conditions"""
    triggers = []
    
    # Check weather
    weather_alerts = await get_weather_alert(location, dates)
    for alert in weather_alerts:
        if alert.severity in [Severity.HIGH, Severity.EXTREME]:
            triggers.append(RePlanTrigger(
                trigger_type="severe_weather",
                severity=alert.severity,
                description=alert.description,
                affected_items=[],
                recommended_action="Consider indoor activities or postpone outdoor plans",
                timestamp=datetime.now()
            ))
    
    # Check long travel times
    if navigation_duration > 180:  # 3+ hours
        triggers.append(RePlanTrigger(
            trigger_type="long_travel_time",
            severity=Severity.MEDIUM,
            description=f"Travel time is {navigation_duration} minutes",
            affected_items=[],
            recommended_action="Consider closer alternatives or split into multiple days",
            timestamp=datetime.now()
        ))
    
    return triggers


# Main in-trip agent interface for Supervisor
class InTripAgent:
    """In-Trip Agent for travel assistance"""
    
    async def get_weather(self, location: str, dates: List[datetime]) -> List[WeatherAlert]:
        """Get weather alerts"""
        return await get_weather_alert(location, dates)
    
    async def get_directions(self, origin: str, destination: str, mode: str = "driving") -> NavigationResult:
        """Get navigation directions"""
        return await get_navigation(origin, destination, mode)
    
    async def translate(self, text: str, target_lang: str) -> TranslationResult:
        """Translate text"""
        return await translate_phrase(text, target_lang)
    
    async def check_replan_needed(self, location: str, dates: List[datetime],
                                 nav_duration: int = 0) -> List[RePlanTrigger]:
        """Check if re-planning is needed"""
        return await check_replan_triggers(location, dates, nav_duration)


# Singleton instance
intrip_agent = InTripAgent()