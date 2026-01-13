import chromadb
import json
import traceback
from src.model.embeddings import MergenEmbedder
from src.model.llm_wrapper import MergenLLM

class MergenSearchEngine:
    def __init__(self, db_path: str = "./data/chroma_db"):
        self.db_path = db_path
        self.error_message = None
        
        try:
            self.client = chromadb.PersistentClient(path=db_path)
            self.collection = self.client.get_collection(name="hotels")
            
            # Collection'ın kaç hotel içerdiğini kontrol et
            collection_count = self.collection.count()
            print(f"[INFO] ChromaDB: {collection_count} otel yüklü")
            
            if collection_count == 0:
                self.error_message = "ChromaDB boş! Lütfen veri yüklemek için şu komutu çalıştırın: python -m src.data_generation.vector_store"
                print(f"[WARNING] {self.error_message}")
            
            self.embedder = MergenEmbedder()
            self.llm = MergenLLM()
            
        except Exception as e:
            self.error_message = f"Arama Motoru Başlatma Hatası: {str(e)}"
            print(f"[ERROR] {self.error_message}")
            traceback.print_exc()

    def _prepare_simplified_hotels(self, matched_hotels):
        """
        Otel bilgisini LLM icin sadeleştirir.
        Sadece isim, konum, fiyat ve kritik 3 ozelligi içerir.
        """
        simplified = []
        for hotel in matched_hotels:
            # Amenities'i parse et
            try:
                amenities = json.loads(hotel.get("amenities", "[]"))
                if not isinstance(amenities, list):
                    amenities = [amenities]
            except:
                amenities = []
            
            # Kritik 3 ozelliği al
            critical_amenities = amenities[:3]
            
            simplified.append({
                "name": hotel["name"],
                "city": hotel["city"],
                "price": hotel["price"],
                "amenities": critical_amenities
            })
        
        return simplified

    def search(self, query: str, top_k: int = 3):
        """
        Semantik arama yapar ve LLM ile otel özelinde 'neden' cümlelerini döner.
        Hata detaylarını tuple ile döndürür: (results, error_message)
        """
        # Initialization hatası kontrolü
        if self.error_message:
            print(f"[ERROR] Initialization Error: {self.error_message}")
            return ([], self.error_message)
        
        try:
            # 1. Sorguyu vektore cevir
            try:
                query_vector = self.embedder.create_embeddings([query])[0].tolist()
            except Exception as e:
                error_msg = f"Embedding Hatası: {str(e)}"
                print(f"[ERROR] {error_msg}")
                return ([], error_msg)

            # 2. Vektor veritabaninda ara
            try:
                results = self.collection.query(
                    query_embeddings=[query_vector],
                    n_results=top_k
                )
            except Exception as e:
                error_msg = f"ChromaDB Sorgusu Hatası: {str(e)}"
                print(f"[ERROR] {error_msg}")
                return ([], error_msg)

            # 3. Sonuclari duzenle
            matched_hotels = []
            try:
                for i in range(len(results['ids'][0])):
                    amenities_data = results['metadatas'][0][i].get('amenities', '[]')
                    try:
                        amenities_list = json.loads(amenities_data) if isinstance(amenities_data, str) else amenities_data
                    except:
                        amenities_list = []
                    
                    matched_hotels.append({
                        "name": results['metadatas'][0][i]['name'],
                        "city": results['metadatas'][0][i]['city'],
                        "concept": results['metadatas'][0][i]['concept'],
                        "price": results['metadatas'][0][i]['price'],
                        "description": results['documents'][0][i],
                        "amenities": amenities_list
                    })
            except Exception as e:
                error_msg = f"Sonuç İşleme Hatası: {str(e)}"
                print(f"[ERROR] {error_msg}")
                return ([], error_msg)

            # 4. LLM'den otel özelinde 'neden' cümlelerini al
            try:
                reasons_dict = self.llm.generate_reasons(query, matched_hotels)
            except Exception as e:
                error_msg = f"LLM Hatası: {str(e)}"
                print(f"[ERROR] {error_msg}")
                return ([], error_msg)
            
            # 5. Nedenleri otel objelerine ekle
            for hotel in matched_hotels:
                hotel['reason'] = reasons_dict.get(hotel['name'], "Kriterlerinizle tam uyumlu harika bir tesis.")

            return (matched_hotels, None)
            
        except Exception as e:
            error_msg = f"Beklenmedik Hata: {str(e)}\n{traceback.format_exc()}"
            print(f"[ERROR] {error_msg}")
            return ([], error_msg)

if __name__ == "__main__":
    # Test amacli arama
    engine = MergenSearchEngine()
    test_query = "Antalya'da denize yakın, ailemle gidebileceğim uygun fiyatlı bir otel"
    results, error_msg = engine.search(test_query)
    
    if error_msg:
        print(f"\n❌ HATA: {error_msg}\n")
    else:
        print("\n--- MergenX Arama Sonuçları ---\n")
        if results:
            for hotel in results:
                print(f"🏨 {hotel['name']} ({hotel['city']})")
                print(f"   Neden: {hotel.get('reason', 'N/A')}")
                print()
        else:
            print("Sonuç bulunamadı.")
