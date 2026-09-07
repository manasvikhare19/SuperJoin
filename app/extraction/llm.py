import os
import json
import logging
import requests
from typing import Optional, Dict, Any
from app.config import (
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL
)

logger = logging.getLogger(__name__)

class LLMProvider:
    def generate(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = True) -> str:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError

class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = True) -> str:
        url = f"{self.base_url}/api/generate"
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }
        if system_prompt:
            payload["system"] = system_prompt
        if json_mode:
            payload["format"] = "json"

        try:
            response = requests.post(url, json=payload, timeout=90)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except Exception as e:
            logger.error(f"Ollama generation error: {e}")
            raise

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = GEMINI_MODEL):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "") or GEMINI_API_KEY
        self.model = model
        self.client = None
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize google-genai Client: {e}")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = True) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        
        # Use google-genai SDK if available
        if self.client:
            from google.genai import types
            config = types.GenerateContentConfig()
            if system_prompt:
                config.system_instruction = system_prompt
            if json_mode:
                config.response_mime_type = "application/json"
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config
            )
            return response.text.strip()
        else:
            # Fallback direct REST API call if client init had an issue
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
            contents = []
            if system_prompt:
                contents.append({"role": "user", "parts": [{"text": f"System Instruction: {system_prompt}"}]})
            contents.append({"role": "user", "parts": [{"text": prompt}]})
            
            body = {"contents": contents}
            if json_mode:
                body["generationConfig"] = {"responseMimeType": "application/json"}
            
            r = requests.post(url, json=body, timeout=60)
            r.raise_for_status()
            res = r.json()
            return res["candidates"][0]["content"]["parts"][0]["text"].strip()

class UnifiedLLM:
    """
    Unified LLM Client providing:
    - Ollama + Qwen2.5 (Primary, local, ₹0 cost)
    - Gemini API (Fallback or user selectable)
    """
    def __init__(
        self,
        preferred_provider: Optional[str] = None,
        ollama_url: str = OLLAMA_BASE_URL,
        ollama_model: str = OLLAMA_MODEL,
        gemini_key: Optional[str] = None,
        gemini_model: str = GEMINI_MODEL
    ):
        self.preferred = (preferred_provider or LLM_PROVIDER).lower()
        self.ollama = OllamaProvider(base_url=ollama_url, model=ollama_model)
        self.gemini = GeminiProvider(api_key=gemini_key, model=gemini_model)

    def get_active_provider_name(self) -> str:
        if self.preferred == "ollama" and self.ollama.is_available():
            return f"Ollama ({self.ollama.model})"
        if self.gemini.is_available():
            return f"Gemini ({self.gemini.model})"
        if self.ollama.is_available():
            return f"Ollama ({self.ollama.model})"
        return "No LLM Provider Available (Start Ollama or set GEMINI_API_KEY)"

    def is_any_available(self) -> bool:
        return self.ollama.is_available() or self.gemini.is_available()

    def generate(self, prompt: str, system_prompt: Optional[str] = None, json_mode: bool = True) -> str:
        # Check preference
        if self.preferred == "ollama" and self.ollama.is_available():
            try:
                return self.ollama.generate(prompt, system_prompt=system_prompt, json_mode=json_mode)
            except Exception as e:
                logger.warning(f"Ollama failed, attempting fallback to Gemini: {e}")
                if self.gemini.is_available():
                    return self.gemini.generate(prompt, system_prompt=system_prompt, json_mode=json_mode)
                raise

        # Check Gemini
        if self.gemini.is_available():
            try:
                return self.gemini.generate(prompt, system_prompt=system_prompt, json_mode=json_mode)
            except Exception as e:
                logger.warning(f"Gemini failed, checking Ollama: {e}")
                if self.ollama.is_available():
                    return self.ollama.generate(prompt, system_prompt=system_prompt, json_mode=json_mode)
                raise

        if self.ollama.is_available():
            return self.ollama.generate(prompt, system_prompt=system_prompt, json_mode=json_mode)

        # Neither is available
        raise ConnectionError(
            "No LLM provider is currently reachable. Please either run Ollama locally ('ollama run qwen2.5:7b') "
            "or enter your GEMINI_API_KEY in the sidebar / .env."
        )

def clean_json_response(raw_text: str) -> str:
    """Strips markdown ```json ... ``` blocks and extracts parseable JSON string."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
