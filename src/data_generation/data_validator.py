import json
from typing import List, Dict

class MergenDataValidator:
    def __init__(self):
        # Proje kapsamındaki zorunlu alanlar [cite: 67, 70]
        self.required_fields = ["hotel_name", "location", "concept", "price_per_night", "amenities", "description"]
        self.required_location_fields = ["city", "district"]

    def validate_hotel(self, hotel: Dict) -> bool:
        """Tek bir otel verisinin doğruluğunu kontrol eder."""
        try:
            for field in self.required_fields:
                if field not in hotel or hotel[field] is None:
                    return False
            
            for loc_field in self.required_location_fields:
                if loc_field not in hotel["location"]:
                    return False
            
            if not isinstance(hotel["price_per_night"], (int, float)):
                return False
            
            if not isinstance(hotel["amenities"], list) or len(hotel["amenities"]) < 3:
                return False
                
            return True
        except Exception:
            return False

    def validate_batch(self, hotels: List[Dict]) -> List[Dict]:
        """Üretilen listedeki geçerli otelleri ayıklar."""
        valid_hotels = [h for h in hotels if self.validate_hotel(h)]
        print(f"--- Dogrulama Raporu: {len(hotels)} otelden {len(valid_hotels)} tanesi gecerli. ---")
        return valid_hotels