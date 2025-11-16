
"""
OCR tools for receipt processing
"""
import re
from typing import Optional, Union
from datetime import datetime
import os

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    print("Tesseract not available, using mock OCR")

from models.expense import ReceiptData, ExpenseCategory

GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY", "demo_key")


def extract_text_from_receipt(receipt_input: Union[str, bytes], is_bytes: bool = False) -> str:
    """Extract text from receipt image using OCR"""
    if GOOGLE_VISION_API_KEY != "demo_key" and is_bytes:
        try:
            return _extract_with_vision_api(receipt_input)
        except Exception as e:
            print(f"Vision API failed: {e}")
    
    if TESSERACT_AVAILABLE:
        try:
            if is_bytes:
                from io import BytesIO
                image = Image.open(BytesIO(receipt_input))
            else:
                image = Image.open(receipt_input)
            
            text = pytesseract.image_to_string(image)
            return text
        except Exception as e:
            print(f"Tesseract OCR failed: {e}")
    
    return _mock_ocr_extract()


def parse_receipt_data(text: str) -> ReceiptData:
    """Parse structured data from OCR text"""
    receipt = ReceiptData()
    
    lines = text.split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    
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
    
    receipt.currency = _extract_currency(text)
    receipt.items = _extract_items(text)
    receipt.payment_method = _extract_payment_method(text)
    receipt.confidence_score = _calculate_confidence(receipt)
    
    return receipt


def _extract_date(text: str) -> Optional[datetime]:
    """Extract date from text"""
    patterns = [
        r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b',
        r'\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            try:
                for fmt in ['%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d', '%m-%d-%Y']:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except:
                        continue
            except:
                pass
    
    return None


def _extract_amounts(text: str) -> list:
    """Extract monetary amounts from text"""
    pattern = r'[\$€£¥]?\s*(\d+[,.]?\d*\.?\d{2})'
    matches = re.findall(pattern, text)
    amounts = []
    
    for match in matches:
        try:
            amount_str = match.replace(',', '')
            amount = float(amount_str)
            if amount > 0:
                amounts.append(amount)
        except:
            continue
    
    return sorted(amounts)


def _extract_currency(text: str) -> Optional[str]:
    """Extract currency code from text"""
    text_upper = text.upper()
    currency_map = {
        '$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY',
        'USD': 'USD', 'EUR': 'EUR', 'GBP': 'GBP', 'JPY': 'JPY'
    }
    
    for symbol, code in currency_map.items():
        if symbol in text or symbol in text_upper:
            return code
    
    return 'USD'


def _extract_items(text: str) -> list:
    """Extract item names from text"""
    lines = text.split('\n')
    items = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if any(keyword in line.lower() for keyword in ['total', 'subtotal', 'tax', 'tip']):
            continue
        
        if re.search(r'\d+\.?\d{2}', line):
            item_match = re.match(r'^(.+?)\s+[\$€£¥]?\s*\d', line)
            if item_match:
                item_name = item_match.group(1).strip()
                if len(item_name) > 2:
                    items.append(item_name)
    
    return items[:10]


def _extract_payment_method(text: str) -> Optional[str]:
    """Extract payment method from text"""
    text_lower = text.lower()
    payment_methods = {
        'visa': 'Visa', 'mastercard': 'Mastercard', 'amex': 'American Express',
        'cash': 'Cash', 'debit': 'Debit Card', 'credit': 'Credit Card'
    }
    
    for keyword, method in payment_methods.items():
        if keyword in text_lower:
            return method
    
    return None


def _calculate_confidence(receipt: ReceiptData) -> float:
    """Calculate confidence score"""
    score = 0.0
    if receipt.merchant_name:
        score += 0.2
    if receipt.date:
        score += 0.2
    if receipt.total_amount:
        score += 0.3
    if receipt.currency:
        score += 0.1
    if receipt.items:
        score += 0.1
    if receipt.payment_method:
        score += 0.1
    
    return min(score, 1.0)


def _extract_with_vision_api(image_bytes: bytes) -> str:
    """Extract text using Google Cloud Vision API"""
    import requests
    import base64
    
    url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
    encoded_image = base64.b64encode(image_bytes).decode('utf-8')
    
    request_body = {
        "requests": [{
            "image": {"content": encoded_image},
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }
    
    response = requests.post(url, json=request_body, timeout=15)
    response.raise_for_status()
    result = response.json()
    
    if "textAnnotations" in result["responses"][0]:
        return result["responses"][0]["textAnnotations"][0]["description"]
    
    return ""


def _mock_ocr_extract() -> str:
    """Generate mock OCR text"""
    return """
    Le Cafe Parisien
    123 Rue de Rivoli
    Paris, France
    
    Date: 11/15/2025
    Time: 12:30 PM
    
    Espresso          €3.50
    Croissant         €2.80
    Sandwich          €8.90
    
    Subtotal         €15.20
    Tax (20%)         €3.04
    
    Total            €18.24
    
    Visa Card ****1234
    
    Thank you!
    """