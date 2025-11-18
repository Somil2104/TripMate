
"""
Data models for OCR Agent and Expense Tracking
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class ExpenseCategory(str, Enum):
    """Expense categories"""
    ACCOMMODATION = "accommodation"
    FOOD = "food"
    TRANSPORT = "transport"
    ACTIVITIES = "activities"
    SHOPPING = "shopping"
    OTHER = "other"


class ReceiptItem(BaseModel):
    """Individual item on a receipt"""
    name: str = Field(..., description="Item name")
    quantity: int = Field(default=1, description="Quantity")
    unit_price: Optional[float] = Field(None, description="Price per unit")
    total_price: Optional[float] = Field(None, description="Total price for this item")


class ReceiptData(BaseModel):
    """Parsed receipt data from OCR"""
    merchant_name: Optional[str] = Field(None, description="Merchant/business name")
    merchant_address: Optional[str] = Field(None, description="Merchant address")
    date: Optional[datetime] = Field(None, description="Transaction date")
    time: Optional[str] = Field(None, description="Transaction time")
    items: List[str] = Field(default_factory=list, description="List of items purchased")
    detailed_items: List[ReceiptItem] = Field(
        default_factory=list,
        description="Detailed item breakdown"
    )
    subtotal: Optional[float] = Field(None, description="Subtotal before tax/tip")
    tax: Optional[float] = Field(None, description="Tax amount")
    tip: Optional[float] = Field(None, description="Tip amount")
    total_amount: Optional[float] = Field(None, description="Total amount paid")
    currency: Optional[str] = Field(None, description="Currency code")
    payment_method: Optional[str] = Field(None, description="Payment method used")
    receipt_number: Optional[str] = Field(None, description="Receipt/transaction number")
    category: ExpenseCategory = Field(
        default=ExpenseCategory.OTHER,
        description="Auto-categorized expense type"
    )
    converted_amount: Optional[float] = Field(
        None,
        description="Amount converted to user's currency"
    )
    converted_currency: Optional[str] = Field(
        None,
        description="User's preferred currency"
    )
    confidence_score: float = Field(
        default=0.0,
        description="OCR confidence score (0-1)"
    )


class Expense(BaseModel):
    """Expense record for ledger"""
    id: str = Field(..., description="Unique expense ID")
    date: datetime = Field(..., description="Expense date")
    merchant: str = Field(..., description="Merchant name")
    category: ExpenseCategory = Field(..., description="Expense category")
    amount: float = Field(..., description="Amount in user's currency")
    currency: str = Field(..., description="User's currency")
    original_amount: Optional[float] = Field(
        None,
        description="Original amount if different currency"
    )
    original_currency: Optional[str] = Field(
        None,
        description="Original currency if converted"
    )
    description: Optional[str] = Field(None, description="Expense description")
    receipt_image_path: Optional[str] = Field(None, description="Path to receipt image")
    items: List[str] = Field(default_factory=list, description="Items purchased")
    tax: Optional[float] = Field(None, description="Tax amount")
    tip: Optional[float] = Field(None, description="Tip amount")
    payment_method: Optional[str] = Field(None, description="Payment method")
    notes: Optional[str] = Field(None, description="User notes")
    tags: List[str] = Field(default_factory=list, description="User tags")
    verified: bool = Field(default=False, description="Whether expense is verified")
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="When record was created"
    )
    updated_at: Optional[datetime] = Field(None, description="Last update time")


class ExpenseSummary(BaseModel):
    """Summary of expenses by category"""
    category: ExpenseCategory = Field(..., description="Expense category")
    total_amount: float = Field(..., description="Total spent in this category")
    count: int = Field(..., description="Number of expenses")
    percentage: float = Field(..., description="Percentage of total budget")


class ExpenseLedger(BaseModel):
    """Complete expense ledger for trip"""
    trip_id: str = Field(..., description="Associated trip ID")
    user_id: str = Field(..., description="User ID")
    budget: float = Field(..., description="Total trip budget")
    currency: str = Field(..., description="Currency code")
    expenses: List[Expense] = Field(default_factory=list, description="All expenses")
    total_spent: float = Field(default=0.0, description="Total amount spent")
    remaining: float = Field(..., description="Remaining budget")
    by_category: List[ExpenseSummary] = Field(
        default_factory=list,
        description="Expenses grouped by category"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Ledger creation time"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="Last update time"
    )