import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class MergenLLM:
    def __init__(self):
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.model = "llama-3.3-70b-versatile"

    def generate_reasons(self, query: str, hotels: list):
        """Her otel için kullanıcı sorgusuna özel bir 'neden' cümlesi üretir."""
        hotel_list_text = "\n".join([f"- {h['name']}: {h['description']}" for h in hotels])
        
        prompt = f"""
        Kullanıcı Sorgusu: "{query}"
        Bulunan Oteller:
        {hotel_list_text}

        GÖREV:
        Her otel için, kullanıcının kriterleriyle neden eşleştiğini anlatan 15 kelimelik, çok vurucu bir cümle yaz.
        Yanıtı SADECE şu JSON formatında ver:
        {{
            "Otel Adı": "Neden cümlesi...",
            "Otel Adı 2": "Neden cümlesi..."
        }}
        Asla giriş/sonuç yazma, sadece JSON dön. Türkçe konuş.
        """

        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                response_format={"type": "json_object"}
            )
            return json.loads(completion.choices[0].message.content)
        except Exception as e:
            print(f"LLM Hatası: {e}")
            return {}