import os
import json
import time
from typing import List, Dict
from groq import Groq
from dotenv import load_dotenv

# Validator importu
from src.data_generation.data_validator import MergenDataValidator

load_dotenv()

class MergenDataGenerator:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY bulunamadi! .env dosyasini kontrol edin.")
        
        self.client = Groq(api_key=self.api_key)
        # Guncel Groq modeli
        self.model = "llama-3.3-70b-versatile" 
        self.validator = MergenDataValidator()
        
        # Referans veri 
        self.seed_example = {
            "hotel_name": "Verde Otel Icmeler",
            "location": {"city": "Mugla", "district": "Marmaris", "area": "Icmeler"},
            "concept": "Her Sey Dahil",
            "price_per_night": 4500,
            "amenities": ["Acik Havuz", "Cocuk Havuzu", "Plaj", "Animasyon", "Otopark"],
            "description": "Modern odalari ve merkezi konumuyla konforlu bir tatil sunan tesis.",
            "source": "bitur.com.tr"
        }

    def generate_batch(self, region: str, count: int) -> List[Dict]:
        """Groq API kullanarak sentetik veri uretir."""
        prompt = f"""
        Sen bir turizm veri uzmanisin. 
        Asagidaki ornegi baz alarak {region} bolgesi icin {count} adet benzersiz otel verisi uret.
        
        Ornek:
        {json.dumps(self.seed_example)}
        
        Kurallar:
        1. Sadece JSON don. 'hotels' anahtari altinda bir liste olsun.
        2. price_per_night: 3000-25000 arasi.
        3. amenities: En az 5 adet ozellik[cite: 69].
        4. description: Semantik arama icin zengin metin[cite: 71].
        """

        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                response_format={"type": "json_object"},
                temperature=0.7
            )
            
            response_data = json.loads(completion.choices[0].message.content)
            raw_hotels = response_data.get("hotels", [])
            return self.validator.validate_batch(raw_hotels)
        except Exception as e:
            print(f"Hata ({region}): {str(e)}")
            return []

    def run(self, total_count: int = 500):
        """Veri uretim surecini yonetir[cite: 100]."""
        regions = ["Antalya", "Mugla", "Izmir", "Aydin", "Balikesir"]
        hotels_per_region = total_count // len(regions)
        all_hotels = []

        print(f"MergenX Veri Uretimi Basladi. Hedef: {total_count}")

        for region in regions:
            print(f"-> {region} bolgesi isleniyor...")
            count_for_region = 0
            while count_for_region < hotels_per_region:
                batch = self.generate_batch(region, 10)
                all_hotels.extend(batch)
                count_for_region += len(batch)
                time.sleep(1)

        os.makedirs("data", exist_ok=True)
        with open("data/hotels.json", "w", encoding="utf-8") as f:
            json.dump(all_hotels, f, ensure_ascii=False, indent=4)
        
        print(f"Islem Tamam! data/hotels.json dosyasina {len(all_hotels)} otel yazildi.")

if __name__ == "__main__":
    generator = MergenDataGenerator()
    generator.run(total_count=500)