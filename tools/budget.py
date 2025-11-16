
"""
Budget helper functions
"""
from models.budget import BudgetCheck, CategoryBreakdown
from tools.currency import convert_currency


async def check_budget_feasibility(
    user_budget: float,
    currency: str,
    flight_cost: float,
    hotel_cost: float,
    activities_cost: float,
    transport_cost: float = 0.0,
    meals_estimate: float = 0.0
) -> BudgetCheck:
    """Check if proposed costs fit within user budget"""
    total_cost = (flight_cost + hotel_cost + activities_cost + 
                  transport_cost + meals_estimate)
    
    buffer = total_cost * 0.10
    total_with_buffer = total_cost + buffer
    
    within_budget = total_with_buffer <= user_budget
    remaining = user_budget - total_with_buffer
    
    recommendations = []
    if not within_budget:
        recommendations.append("Consider cheaper flight options")
        recommendations.append("Look for budget-friendly hotels")
        recommendations.append("Reduce number of paid activities")
    elif remaining < user_budget * 0.1:
        recommendations.append("Budget is tight - minimal flexibility")
    else:
        recommendations.append(f"Within budget with {currency} {remaining:.2f} remaining")
    
    breakdown = CategoryBreakdown(
        flights=flight_cost,
        hotels=hotel_cost,
        activities=activities_cost,
        transport=transport_cost,
        meals=meals_estimate,
        buffer=buffer,
        total=total_with_buffer,
        currency=currency
    )
    
    return BudgetCheck(
        within_budget=within_budget,
        total_cost=total_with_buffer,
        remaining_budget=remaining,
        currency=currency,
        recommendations=recommendations,
        breakdown=breakdown
    )