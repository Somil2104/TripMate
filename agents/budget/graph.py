
"""Budget Agent - Handles FX conversion, budget checking, and bundle generation"""
from typing import Dict, List, Optional
from datetime import datetime
from models.budget import BudgetCheck, CategoryBreakdown, BundleCost, FXConversion
from tools.currency import convert_currency, get_fx_rates
from tools.budget import check_budget_feasibility


async def check_budget(
    user_budget: float,
    currency: str,
    flight_cost: float = 0.0,
    hotel_cost: float = 0.0,
    activities_cost: float = 0.0,
    transport_cost: float = 0.0,
    meals_estimate: float = 0.0
) -> BudgetCheck:
    """Check if proposed costs fit within user budget"""
    return await check_budget_feasibility(
        user_budget=user_budget,
        currency=currency,
        flight_cost=flight_cost,
        hotel_cost=hotel_cost,
        activities_cost=activities_cost,
        transport_cost=transport_cost,
        meals_estimate=meals_estimate
    )


async def convert_budget(amount: float, from_currency: str, to_currency: str) -> FXConversion:
    """Convert budget between currencies"""
    return convert_currency(amount, from_currency, to_currency)


async def generate_bundles(
    flight_cost: float,
    hotel_cost: float,
    activities_cost: float,
    transport_cost: float,
    meals_estimate: float,
    currency: str = "USD"
) -> List[BundleCost]:
    """Generate Cheapest, Balanced, and Comfort bundle options"""
    base_costs = {
        "flight": flight_cost,
        "hotel": hotel_cost,
        "activities": activities_cost,
        "transport": transport_cost,
        "meals": meals_estimate
    }
    
    bundles = []
    multipliers = {
        "cheapest": (1.0, ["Lowest cost", "More budget for other activities", "Economical choice"],
                     ["Basic amenities", "Possible inconveniences", "Limited flexibility"]),
        "balanced": (1.3, ["Good value", "Comfortable options", "Balanced trade-offs"],
                    ["Moderate cost", "Some compromises"]),
        "comfort": (1.7, ["Premium experience", "Best amenities", "Maximum comfort"],
                   ["Higher cost", "May exceed budget", "Less flexibility"])
    }
    
    for bundle_type, (multiplier, pros, cons) in multipliers.items():
        bundle = BundleCost(
            bundle_type=bundle_type,
            flight_cost=base_costs["flight"] * multiplier,
            hotel_cost=base_costs["hotel"] * multiplier,
            activities_cost=base_costs["activities"] * multiplier,
            transport_cost=base_costs["transport"] * multiplier,
            meals_estimate=base_costs["meals"] * multiplier,
            total_cost=sum(base_costs.values()) * multiplier,
            currency=currency,
            pros=pros,
            cons=cons
        )
        bundles.append(bundle)
    
    return bundles


async def calculate_category_breakdown(
    flight_cost: float,
    hotel_cost: float,
    activities_cost: float,
    transport_cost: float,
    meals_estimate: float,
    currency: str = "USD"
) -> CategoryBreakdown:
    """Calculate detailed budget breakdown by category"""
    subtotal = flight_cost + hotel_cost + activities_cost + transport_cost + meals_estimate
    buffer = subtotal * 0.10
    
    return CategoryBreakdown(
        flights=flight_cost,
        hotels=hotel_cost,
        activities=activities_cost,
        transport=transport_cost,
        meals=meals_estimate,
        buffer=buffer,
        total=subtotal + buffer,
        currency=currency
    )


# Main budget agent interface for Supervisor
class BudgetAgent:
    """Budget Agent for travel planning system"""
    
    async def check_feasibility(self, user_budget: float, currency: str, 
                               flight_cost: float, hotel_cost: float,
                               activities_cost: float, transport_cost: float = 0.0,
                               meals_estimate: float = 0.0) -> BudgetCheck:
        """Check if costs are within budget"""
        return await check_budget(user_budget, currency, flight_cost, hotel_cost,
                                 activities_cost, transport_cost, meals_estimate)
    
    async def convert_currency(self, amount: float, from_curr: str, to_curr: str) -> FXConversion:
        """Convert between currencies"""
        return await convert_budget(amount, from_curr, to_curr)
    
    async def generate_bundle_options(self, flight_cost: float, hotel_cost: float,
                                     activities_cost: float, transport_cost: float,
                                     meals_estimate: float, currency: str = "USD") -> List[BundleCost]:
        """Generate bundle options"""
        return await generate_bundles(flight_cost, hotel_cost, activities_cost,
                                     transport_cost, meals_estimate, currency)
    
    async def get_breakdown(self, flight_cost: float, hotel_cost: float,
                          activities_cost: float, transport_cost: float,
                          meals_estimate: float, currency: str = "USD") -> CategoryBreakdown:
        """Get category breakdown"""
        return await calculate_category_breakdown(flight_cost, hotel_cost, activities_cost,
                                                 transport_cost, meals_estimate, currency)


# Singleton instance
budget_agent = BudgetAgent()