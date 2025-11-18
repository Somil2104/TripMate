
"""OCR Agent - Handles receipt processing, expense categorization, and ledger management"""
from typing import Optional
from datetime import datetime
from models.expense import Expense, ExpenseCategory, ReceiptData, ExpenseLedger
from tools.ocr import extract_text_from_receipt, parse_receipt_data
from tools.currency import convert_currency


async def process_receipt(receipt_path: str = None, receipt_bytes: bytes = None) -> Expense:
    """Process receipt image and extract expense data"""
    if receipt_bytes:
        text = extract_text_from_receipt(receipt_bytes, is_bytes=True)
    elif receipt_path:
        text = extract_text_from_receipt(receipt_path, is_bytes=False)
    else:
        raise ValueError("Must provide either receipt_path or receipt_bytes")
    
    receipt_data = parse_receipt_data(text)
    
    # Auto-categorize
    category = await categorize_expense(receipt_data.merchant_name or "", receipt_data.items)
    receipt_data.category = category
    
    # expense record
    expense = Expense(
        id=f"exp_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        date=receipt_data.date or datetime.now(),
        merchant=receipt_data.merchant_name or "Unknown",
        category=category,
        amount=receipt_data.total_amount or 0.0,
        currency=receipt_data.currency or "USD",
        original_amount=receipt_data.total_amount,
        original_currency=receipt_data.currency,
        items=receipt_data.items,
        tax=receipt_data.tax,
        tip=receipt_data.tip,
        receipt_image_path=receipt_path,
        verified=False,
        created_at=datetime.now()
    )
    
    return expense


async def categorize_expense(merchant: str, items: list = None) -> ExpenseCategory:
    """Auto-categorize expense based on merchant and items"""
    merchant_lower = merchant.lower()
    items_str = " ".join(items or []).lower()
    
    # Hotel keywords
    if any(kw in merchant_lower for kw in ["hotel", "resort", "inn", "lodge", "hostel", "airbnb"]):
        return ExpenseCategory.ACCOMMODATION
    
    # Food keywords
    if any(kw in merchant_lower for kw in ["restaurant", "cafe", "coffee", "bar", "bistro", "grill"]):
        return ExpenseCategory.FOOD
    if any(kw in items_str for kw in ["food", "meal", "coffee", "sandwich"]):
        return ExpenseCategory.FOOD
    
    # Transport keywords
    if any(kw in merchant_lower for kw in ["uber", "lyft", "taxi", "transit", "airline", "rental"]):
        return ExpenseCategory.TRANSPORT
    
    # Activity keywords
    if any(kw in merchant_lower for kw in ["museum", "tour", "ticket", "attraction", "park"]):
        return ExpenseCategory.ACTIVITIES
    
    # Shopping keywords
    if any(kw in merchant_lower for kw in ["store", "shop", "market", "mall"]):
        return ExpenseCategory.SHOPPING
    
    return ExpenseCategory.OTHER


async def categorize_manual_expense(merchant: str, amount: float, currency: str,
                                   description: str = None) -> ExpenseCategory:
    """Categorize a manually entered expense"""
    return await categorize_expense(merchant, [description] if description else [])


async def create_expense_ledger(trip_id: str, user_id: str, budget: float,
                               currency: str = "USD") -> ExpenseLedger:
    """Create new expense ledger for a trip"""
    return ExpenseLedger(
        trip_id=trip_id,
        user_id=user_id,
        budget=budget,
        currency=currency,
        remaining=budget,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


# Main OCR agent interface for Supervisor
class OCRAgent:
    """OCR Agent for receipt processing and expense tracking"""
    
    async def process_receipt_image(self, receipt_path: str = None,
                                   receipt_bytes: bytes = None) -> Expense:
        """Process receipt and return expense"""
        return await process_receipt(receipt_path, receipt_bytes)
    
    async def categorize(self, merchant: str, amount: float,
                        currency: str, description: str = None) -> ExpenseCategory:
        """Categorize manual expense"""
        return await categorize_manual_expense(merchant, amount, currency, description)
    
    async def create_ledger(self, trip_id: str, user_id: str,
                          budget: float, currency: str = "USD") -> ExpenseLedger:
        """Create new expense ledger"""
        return await create_expense_ledger(trip_id, user_id, budget, currency)


# Singleton instance
ocr_agent = OCRAgent()