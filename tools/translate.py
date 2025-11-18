
"""
Translation tools
"""
import requests
from typing import Dict
import os

GOOGLE_TRANSLATE_API_KEY = os.getenv("GOOGLE_TRANSLATE_API_KEY", "demo_key")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "demo_key")

LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "it": "Italian", "pt": "Portuguese", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese", "ar": "Arabic", "hi": "Hindi", "nl": "Dutch"
}


def translate_text(text: str, target_language: str, source_language: str = "auto") -> Dict:
    """Translate text to target language"""
    if DEEPL_API_KEY != "demo_key":
        try:
            return _translate_with_deepl(text, target_language, source_language)
        except Exception as e:
            print(f"DeepL failed: {e}")
    
    if GOOGLE_TRANSLATE_API_KEY != "demo_key":
        try:
            return _translate_with_google(text, target_language, source_language)
        except Exception as e:
            print(f"Google Translate failed: {e}")
    
    return _mock_translate(text, target_language, source_language)


def _translate_with_deepl(text: str, target_language: str, source_language: str) -> Dict:
    """Translate using DeepL API"""
    url = "https://api-free.deepl.com/v2/translate"
    target_lang = target_language.upper()
    
    data = {"auth_key": DEEPL_API_KEY, "text": text, "target_lang": target_lang}
    
    if source_language != "auto":
        data["source_lang"] = source_language.upper()
    
    response = requests.post(url, data=data, timeout=10)
    response.raise_for_status()
    
    result = response.json()
    translation = result["translations"][0]
    
    return {
        "text": translation["text"],
        "source_lang": translation["detected_source_language"].lower(),
        "target_lang": target_language.lower(),
        "confidence": 1.0,
        "provider": "deepl"
    }


def _translate_with_google(text: str, target_language: str, source_language: str) -> Dict:
    """Translate using Google Translate API"""
    url = "https://translation.googleapis.com/language/translate/v2"
    params = {"key": GOOGLE_TRANSLATE_API_KEY, "q": text, "target": target_language}
    
    if source_language != "auto":
        params["source"] = source_language
    
    response = requests.post(url, params=params, timeout=10)
    response.raise_for_status()
    
    result = response.json()
    translation = result["data"]["translations"][0]
    
    return {
        "text": translation["translatedText"],
        "source_lang": translation.get("detectedSourceLanguage", source_language),
        "target_lang": target_language,
        "confidence": 0.95,
        "provider": "google"
    }


def _mock_translate(text: str, target_language: str, source_language: str) -> Dict:
    """Mock translation for demo"""
    mock_translations = {
        ("en", "fr"): {
            "hello": "bonjour", "goodbye": "au revoir", "thank you": "merci",
            "please": "s'il vous plaît", "yes": "oui", "no": "non",
            "where is": "où est", "bathroom": "toilettes"
        },
        ("en", "es"): {
            "hello": "hola", "goodbye": "adiós", "thank you": "gracias",
            "please": "por favor", "yes": "sí", "no": "no",
            "where is": "dónde está", "bathroom": "baño"
        }
    }
    
    text_lower = text.lower().strip()
    key = (source_language if source_language != "auto" else "en", target_language)
    
    if key in mock_translations:
        translations = mock_translations[key]
        for phrase, translation in translations.items():
            if phrase in text_lower:
                return {
                    "text": translation,
                    "source_lang": key[0],
                    "target_lang": target_language,
                    "confidence": 0.85,
                    "provider": "mock"
                }
    
    return {
        "text": f"[{target_language}] {text}",
        "source_lang": source_language if source_language != "auto" else "en",
        "target_lang": target_language,
        "confidence": 0.7,
        "provider": "mock"
    }


def detect_language(text: str) -> Dict:
    """Detect the language of text"""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ["the", "is", "are", "hello", "where"]):
        return {"language": "en", "language_name": "English", "confidence": 0.8}
    elif any(word in text_lower for word in ["bonjour", "merci", "où"]):
        return {"language": "fr", "language_name": "French", "confidence": 0.8}
    elif any(word in text_lower for word in ["hola", "gracias", "dónde"]):
        return {"language": "es", "language_name": "Spanish", "confidence": 0.8}
    else:
        return {"language": "unknown", "language_name": "Unknown", "confidence": 0.3}


def get_supported_languages() -> Dict[str, str]:
    """Get list of supported languages"""
    return LANGUAGE_NAMES.copy()