import chromadb
import json
import os
import uuid
from src.model.embeddings import MergenEmbedder

class MergenVectorStore:
    def __init__(self, db_path: str = "./data/chroma_db"):
        self.db_path = db_path
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.embedder = MergenEmbedder()
        # Koleksiyonu olustur veya var olani al
        self.collection = self.client.get_or_create_collection(name="hotels")

    def _validate_hotel_data(self, hotel: dict) -> dict:
        """
        Otel verisini doğrula ve eksik alanları varsayılan değerlerle doldur.
        Tüm alanları explicit type casting ile döndür.
        """
        validated = {}
        
        # Hotel name - Zorunlu
        validated['name'] = str(hotel.get('hotel_name', hotel.get('name', 'Unknown'))).strip()
        if not validated['name']:
            validated['name'] = 'Unknown'
        
        # Location bilgilerini ekstrak et
        location = hotel.get('location', {})
        if isinstance(location, dict):
            city_raw = location.get('city', '')
            district_raw = location.get('district', '')
        else:
            city_raw = ''
            district_raw = ''
        
        # City - Zorunlu, varsayılan "Not Specified"
        validated['city'] = str(city_raw).strip()
        if not validated['city']:
            validated['city'] = 'Not Specified'
        
        # District - Zorunlu, varsayılan "Not Specified"
        validated['district'] = str(district_raw).strip()
        if not validated['district']:
            validated['district'] = 'Not Specified'
        
        # Location - Kombinasyon
        validated['location'] = f"{validated['city']}, {validated['district']}"
        
        # Price - Zorunlu ve numeric
        price_raw = hotel.get('price_per_night', hotel.get('price', 0))
        try:
            validated['price'] = float(price_raw) if price_raw is not None else 0.0
        except (ValueError, TypeError):
            print(f"[WARNING] Price için invalid değer '{price_raw}' found for {validated['name']}. Using 0.0")
            validated['price'] = 0.0
        
        # Concept
        validated['concept'] = str(hotel.get('concept', '')).strip()
        if not validated['concept']:
            validated['concept'] = 'Standard'
        
        # Description
        validated['description'] = str(hotel.get('description', '')).strip()[:200]
        if not validated['description']:
            validated['description'] = 'No description available'
        
        # Amenities - JSON string olarak
        amenities_raw = hotel.get('amenities', [])
        if isinstance(amenities_raw, list):
            validated['amenities'] = json.dumps(amenities_raw)
        else:
            validated['amenities'] = json.dumps([])
        
        return validated

    def process_and_save(self, json_path: str):
        """
        ChromaDB metadata kaybı sorununu çözmek için katı validation ile veri yükleme.
        - Data Validation: Her alan kontrol ve cast
        - Explicit Metadata: str()/float() type casting
        - Collection Wipe: Başında delete_collection
        - ID Fix: UUID kullanımı
        """
        try:
            if not os.path.exists(json_path):
                print(f"Hata: {json_path} dosyasi bulunamadi!")
                return

            print(f"[STEP 1] JSON dosyası okunuyor: {json_path}")
            with open(json_path, "r", encoding="utf-8") as f:
                hotels_data = json.load(f)

            # Veri yapısını kontrol et
            if isinstance(hotels_data, dict) and "hotels" in hotels_data:
                hotels_list = hotels_data["hotels"]
            elif isinstance(hotels_data, list):
                hotels_list = hotels_data
            else:
                raise ValueError(f"Beklenmeyen veri yapısı: {type(hotels_data)}")

            print(f"[STEP 2] {len(hotels_list)} otel bulundu. Validation başlıyor...")

            # COLLECTION WIPE: Eski bozuk verileri sil
            print("[STEP 3] Collection wiping...")
            try:
                self.client.delete_collection(name="hotels")
                print("[SUCCESS] Eski koleksiyon tamamen silindi")
            except Exception as e:
                print(f"[INFO] Koleksiyon sil (first time normal): {e}")

            # Yeni temiz koleksiyon oluştur
            self.collection = self.client.get_or_create_collection(
                name="hotels",
                metadata={"hnsw:space": "cosine"}
            )
            print("[SUCCESS] Yeni koleksiyon oluşturuldu")

            # Veri hazırlama
            ids = []
            documents = []
            metadatas = []
            
            print("[STEP 4] Data validation ve preparation...")
            for idx, hotel in enumerate(hotels_list):
                # Data Validation: Her otel için eksik alanları kontrol et
                validated = self._validate_hotel_data(hotel)
                
                # ID Fix: UUID kullanımı
                unique_id = str(uuid.uuid4())
                
                # Searchable text
                searchable_text = f"{validated['name']} {validated['city']} {validated['district']} {validated['concept']} {validated['description']}"
                
                ids.append(unique_id)
                documents.append(searchable_text)
                
                # Explicit Metadata: Tüm değerleri type cast ile oluştur
                metadata = {
                    "uuid": str(unique_id),
                    "name": str(validated['name']),
                    "city": str(validated['city']).lower(),
                    "district": str(validated['district']).lower(),
                    "location": str(validated['location']),
                    "concept": str(validated['concept']),
                    "price": float(validated['price']),  # EXPLICIT FLOAT
                    "description": str(validated['description']),
                    "amenities": str(validated['amenities'])  # JSON string
                }
                
                metadatas.append(metadata)
                
                if (idx + 1) % 100 == 0:
                    print(f"[PROGRESS] {idx + 1}/{len(hotels_list)} hotels validated")

            print(f"[STEP 5] Embedding creation for {len(documents)} hotels...")
            # Vektorleri oluştur
            embeddings = self.embedder.create_embeddings(documents)
            print(f"[SUCCESS] {len(embeddings)} embeddings created")

            # ChromaDB'ye ekle
            print(f"[STEP 6] Adding {len(ids)} hotels to ChromaDB...")
            self.collection.add(
                ids=ids,
                embeddings=[emb.tolist() if hasattr(emb, 'tolist') else emb for emb in embeddings],
                documents=documents,
                metadatas=metadatas
            )
            
            final_count = self.collection.count()
            print(f"[SUCCESS] ChromaDB başarıyla güncellendiI: {final_count} hotels stored")
            
            # Verification: Birkaç otel'in metadata'sını kontrol et
            print(f"[VERIFICATION] Checking stored metadata integrity...")
            try:
                sample_data = self.collection.get(limit=3, include=['metadatas'])
                for i, meta in enumerate(sample_data['metadatas']):
                    print(f"  Sample {i+1}: {meta.get('name')} - Price type: {type(meta.get('price'))} = {meta.get('price')}")
            except Exception as verify_error:
                print(f"[WARNING] Verification check failed: {verify_error}")

        except Exception as e:
            print(f"[ERROR] Data save error: {e}")
            import traceback
            traceback.print_exc()
            # Hata durumunda koleksiyonu sil ve yeniden oluştur
            try:
                print("[RECOVERY] Attempting collection recovery...")
                self.client.delete_collection(name="hotels")
                self.collection = self.client.get_or_create_collection(
                    name="hotels",
                    metadata={"hnsw:space": "cosine"}
                )
                print("[RECOVERY] Collection recovered (empty)")
            except Exception as recovery_error:
                print(f"[ERROR] Recovery failed: {recovery_error}")
            raise

if __name__ == "__main__":
    store = MergenVectorStore()
    store.process_and_save("data/hotels.json")