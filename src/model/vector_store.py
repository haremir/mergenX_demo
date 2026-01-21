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

    def process_and_save(self, json_path: str):
        """
        JSON verisini okur, embedding olusturur ve ChromaDB'ye kaydeder.
        UUID-based ID'ler, reset ve batch control ile duplicate ID hatasını önler.
        """
        try:
            if not os.path.exists(json_path):
                print(f"Hata: {json_path} dosyasi bulunamadi!")
                return

            with open(json_path, "r", encoding="utf-8") as f:
                hotels = json.load(f)

            # Veri yapısını kontrol et
            if isinstance(hotels, dict) and "hotels" in hotels:
                hotels_list = hotels["hotels"]
            elif isinstance(hotels, list):
                hotels_list = hotels
            else:
                raise ValueError(f"Beklenmeyen veri yapısı: {type(hotels)}")

            print(f"[INFO] {len(hotels_list)} otel işleniyor...")

            # STEP 1: Koleksiyonu sıfırla
            try:
                self.client.delete_collection(name="hotels")
                print("[INFO] Eski koleksiyon silindi")
            except Exception as e:
                print(f"[INFO] Koleksiyon sıfırlama (ilk kez normal): {e}")

            # Yeni koleksiyon oluştur
            self.collection = self.client.get_or_create_collection(
                name="hotels",
                metadata={"hnsw:space": "cosine"}
            )
            print("[INFO] Yeni koleksiyon oluşturuldu")

            ids = []
            documents = []
            metadatas = []

            # STEP 2: UUID-based unique ID'ler ile veri hazırla
            for idx, hotel in enumerate(hotels_list):
                # Tamamen eşsiz UUID oluştur
                unique_id = str(uuid.uuid4())
                
                # Arama motorunun anlam çıkaracağı metni oluşturuyoruz
                hotel_name = hotel.get('hotel_name', hotel.get('name', 'Unknown'))
                location = hotel.get('location', {})
                city = location.get('city', '') if isinstance(location, dict) else ''
                district = location.get('district', '') if isinstance(location, dict) else ''
                concept = hotel.get('concept', '')
                desc = hotel.get('description', '')
                amenities = hotel.get('amenities', [])
                amenities_str = ' '.join(amenities) if amenities else ''
                
                searchable_text = f"{hotel_name} {city} {district} {concept} {desc} {amenities_str}"
                
                ids.append(unique_id)
                documents.append(searchable_text)
                
                # Filtreleme için metadata ekliyoruz
                metadatas.append({
                    "uuid": unique_id,
                    "name": hotel_name,
                    "city": city.lower() if city else "",
                    "concept": concept,
                    "price": str(hotel.get("price_per_night", 0)),
                    "amenities": json.dumps(amenities) if amenities else "[]"
                })

            print(f"[INFO] {len(documents)} otel için embedding oluşturuluyor...")
            # Vektorleri oluştur (Embeddings)
            embeddings = self.embedder.create_embeddings(documents)

            # STEP 3: Batch control - mevcut ID'leri kontrol et
            existing_ids = set()
            try:
                existing_data = self.collection.get()
                if existing_data and 'ids' in existing_data:
                    existing_ids = set(existing_data['ids'])
                    print(f"[INFO] Koleksiyonda {len(existing_ids)} mevcut ID bulundu")
            except Exception as e:
                print(f"[INFO] Mevcut ID kontrolü: {e}")

            # Yalnızca yeni ID'leri ekle
            new_ids = []
            new_documents = []
            new_metadatas = []
            new_embeddings = []
            
            for idx, (id_, doc, meta, emb) in enumerate(zip(ids, documents, metadatas, embeddings)):
                if id_ not in existing_ids:
                    new_ids.append(id_)
                    new_documents.append(doc)
                    new_metadatas.append(meta)
                    new_embeddings.append(emb.tolist() if hasattr(emb, 'tolist') else emb)
            
            if new_ids:
                print(f"[INFO] {len(new_ids)} yeni otel ekleniyor...")
                # ChromaDB'ye ekle
                self.collection.add(
                    ids=new_ids,
                    embeddings=new_embeddings,
                    documents=new_documents,
                    metadatas=new_metadatas
                )
            else:
                print("[INFO] Eklenecek yeni otel yok (tümü zaten mevcut)")
            
            final_count = self.collection.count()
            print(f"[SUCCESS] Koleksiyon başarıyla güncellendi: {final_count} otel")

        except Exception as e:
            print(f"[ERROR] Veri kaydetme hatası: {e}")
            # Hata oluşursa koleksiyonu sil ve yeniden oluştur
            try:
                self.client.delete_collection(name="hotels")
                self.collection = self.client.get_or_create_collection(
                    name="hotels",
                    metadata={"hnsw:space": "cosine"}
                )
                print("[WARNING] Koleksiyon hatası nedeniyle sıfırlandı")
            except Exception as reset_error:
                print(f"[ERROR] Koleksiyon sıfırlama başarısız: {reset_error}")
            raise

if __name__ == "__main__":
    store = MergenVectorStore()
    store.process_and_save("data/hotels.json")