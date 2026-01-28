import os
from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm
from google.adk.models import Gemini
from pydantic import PrivateAttr

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

class GroqFallbackClient(LiteLlm):
    """
    Wrapper for Groq models.
    Implements automatic fallback if a model is busy.
    """
    _model_names: list = PrivateAttr(default=[
        "groq/meta-llama/llama-4-maverick-17b-128e-instruct",       
        "groq/meta-llama/llama-4-scout-17b-16e-instruct",       
        "groq/llama-3.3-70b-versatile"      
    ])
    _clients: list = PrivateAttr(default=[])

    def __init__(self):
        super().__init__(model=self._model_names[0], api_key=GROQ_API_KEY)
        
        self._clients = [
            LiteLlm(model=name, api_key=GROQ_API_KEY) 
            for name in self._model_names
        ]

    async def generate_content_async(self, contents, **kwargs):
        if 'model' in kwargs:
            del kwargs['model']
            
        last_error = None
        for i, client in enumerate(self._clients):
            try:
                async for chunk in client.generate_content_async(contents, **kwargs):
                    yield chunk
                return # Success
            except Exception as e:
                print(f"[Bridge] ⚠️ Groq Model {self._model_names[i]} failed: {e}")
                last_error = e
                continue
        
        raise last_error or Exception("All Groq models exhausted.")

class GeminiFallbackClient(Gemini):
    """
    Wrapper for Gemini models.
    """
    _model_names: list = PrivateAttr(default=[
        "gemini-3-flash",          
        "gemini-2.5-flash",        
        "gemini-2.5-flash-lite"    
    ])
    
    def __init__(self):
        super().__init__(model=self._model_names[0], api_key=GEMINI_API_KEY)

    async def generate_content_async(self, contents, **kwargs):
        if 'model' in kwargs:
            del kwargs['model']
            
        try:
            async for chunk in super().generate_content_async(contents, **kwargs):
                yield chunk
        except Exception as e:
            print(f"[Bridge] ❌ Gemini Error: {e}")
            raise e