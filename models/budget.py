
"""
Data models for Budget Agent
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class Currency(str, Enum):
    """Supported currencies"""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CAD = "CAD"
    AUD = "AUD"
    CHF = "CHF"
    CNY = "CNY"
    INR = "INR"


class CategoryBreakdown(BaseModel):
    """Budget breakdown by category"""
    flights: float = Field(default=0.0, description="Flight costs")
    hotels: float = Field(default=0.0, description="Hotel costs")
    transport: float = Field(default=0.0, description="Local transport costs")
    meals: float = Field(default=0.0, description="Estimated meal costs")
    activities: float = Field(default=0.0, description="Activity and attraction costs")
    buffer: float = Field(default=0.0, description="Buffer for unexpected costs (10%)")
    total: float = Field(default=0.0, description="Total cost including buffer")
    currency: str = Field(default="USD", description="Currency code")


class BundleCost(BaseModel):
    """Cost breakdown for a bundle option"""
    bundle_type: str = Field(..., description="Type: cheapest, balanced, or comfort")
    flight_cost: float = Field(..., description="Flight cost for this bundle")
    hotel_cost: float = Field(..., description="Hotel cost for this bundle")
    activities_cost: float = Field(..., description="Activities cost for this bundle")
    transport_cost: float = Field(..., description="Transport cost estimate")
    meals_estimate: float = Field(..., description="Meals cost estimate")
    total_cost: float = Field(..., description="Total bundle cost")
    currency: str = Field(default="USD", description="Currency code")
    pros: List[str] = Field(default_factory=list, description="Advantages")
    cons: List[str] = Field(default_factory=list, description="Disadvantages")


class BudgetCheck(BaseModel):
    """Result of budget feasibility check"""
    within_budget: bool = Field(..., description="Whether costs fit within budget")
    total_cost: float = Field(..., description="Total estimated cost")
    remaining_budget: float = Field(..., description="Remaining budget")
    currency: str = Field(default="USD", description="Currency code")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations")
    breakdown: Optional[CategoryBreakdown] = None


class FXConversion(BaseModel):
    """Foreign exchange conversion result"""
    amount: float = Field(..., description="Original amount")
    from_currency: str = Field(..., description="Source currency code")
    to_currency: str = Field(..., description="Target currency code")
    converted_amount: float = Field(..., description="Converted amount")
    exchange_rate: float = Field(..., description="Exchange rate used")
    timestamp: datetime = Field(default_factory=datetime.now, description="When rate was fetched")


class BudgetState(BaseModel):
    """Complete budget state for session"""
    user_budget: float = Field(..., description="User's total budget")
    currency: str = Field(default="USD", description="User's preferred currency")
    spent_to_date: float = Field(default=0.0, description="Amount spent so far")
    allocated: CategoryBreakdown = Field(default_factory=CategoryBreakdown, description="Allocated budget")
    remaining: float = Field(..., description="Remaining available budget")
    bundles: List[BundleCost] = Field(default_factory=list, description="Available bundle options")
    warnings: List[str] = Field(default_factory=list, description="Budget warnings")