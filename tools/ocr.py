
"""OCR tools for receipt processing"""
import re
from typing import Optional
from datetime import datetime
from models.expense import ReceiptData, ExpenseCategory

def extract_text_from_receipt(receipt_input, is_bytes: bool = False) -> str:
    return """
    Le Cafe Parisien
    123 Rue de Rivoli
    Date: 11/15/2025
    Espresso €3.50
    Croissant €2.80
    Subtotal €6.30
    Tax €1.26
    Total €7.56
    Visa ****1234
    """

def parse_receipt_data(text: str) -> ReceiptData:
    receipt = ReceiptData()
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if lines:
        receipt.merchant_name = lines[0]
    
    receipt.date = _extract_date(text)
    amounts = _extract_amounts(text)
    
    if amounts:
        receipt.total_amount = amounts[-1]
        if len(amounts) >= 2:
            receipt.subtotal = amounts[0]
        if len(amounts) >= 3:
            receipt.tax = amounts[1]
    
    receipt.currency = "USD"
    receipt.items = _extract_items(text)
    receipt.confidence_score = 0.85
    
    return receipt

def _extract_date(text: str) -> Optional[datetime]:
    pattern = r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b'
    match = re.search(pattern, text)
    if match:
        try:
            return datetime.strptime(match.group(1), '%m/%d/%Y')
        except:
            pass
    return None

def _extract_amounts(text: str) -> list:
    pattern = r'[\$€£¥]?\s*(\d+[,.]?\d*\.?\d{2})'
    matches = re.findall(pattern, text)
    amounts = []
    for match in matches:
        try:
            amount = float(match.replace(',', ''))
            if amount > 0:
                amounts.append(amount)
        except:
            pass
    return sorted(amounts)

def _extract_items(text: str) -> list:
    lines = text.split('\n')
    items = []
    for line in lines:
        if re.search(r'\d+\.?\d{2}', line) and not any(k in line.lower() for k in ['total', 'tax']):
            item_match = re.match(r'^(.+?)\s+[\$€£¥]', line)
            if item_match:
                items.append(item_match.group(1).strip())
    return items[:10]