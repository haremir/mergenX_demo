import chromadb
import json
import os
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
        """
        if not os.path.exists(json_path):
            print(f"Hata: {json_path} dosyasi bulunamadi!")
            return

        with open(json_path, "r", encoding="utf-8") as f:
            hotels = json.load(f)

        ids = []
        documents = []
        metadatas = []

        for idx, hotel in enumerate(hotels):
            # Arama motorunun anlam cikaracagi metni olusturuyoruz
            searchable_text = f"{hotel['hotel_name']} {hotel['location']['city']} {hotel['location']['district']} {hotel['concept']} {hotel['description']} {' '.join(hotel['amenities'])}"
            
            ids.append(str(idx))
            documents.append(searchable_text)
            
            # Filtreleme icin metadata ekliyoruz
            metadatas.append({
                "name": hotel["hotel_name"],
                "city": hotel["location"]["city"],
                "concept": hotel["concept"],
                "price": hotel["price_per_night"],
                "amenities": json.dumps(hotel["amenities"])  # JSON string olarak sakla
            })

        print(f"MergenX: {len(documents)} otel icin embedding olusturuluyor...")
        # Vektorleri olustur (Embeddings)
        embeddings = self.embedder.create_embeddings(documents)

        # ChromaDB'ye ekle
        self.collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=documents,
            metadatas=metadatas
        )
        print("Basarili! Oteller semantik hafizaya kaydedildi.")

if __name__ == "__main__":
    store = MergenVectorStore()
    store.process_and_save("data/hotels.json")