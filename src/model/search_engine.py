import chromadb
import json
import traceback
import os
import uuid
import logging
from pathlib import Path
from difflib import SequenceMatcher
from src.model.embeddings import MergenEmbedder
from src.model.llm_wrapper import MergenLLM

# Logger ayarla
logger = logging.getLogger(__name__)

class TravelPlanner:
    """
    Revize Seyahat Planlayıcı:
    1. Niyeti Analiz: extract_travel_params() ile kullanıcı isteğini anla
    2. Otel Arama: Preferences'ı kullanarak vektör araması yap
    3. Uçuş Filtreleme: Teknik filtreleme ile uygun uçuşları bul
    4. Transfer Filtreleme: Havalimanı + bölge bazlı transfer ara
    5. Paketleme: Tüm verileri bir pakette sun
    6. Akıllı Özet: LLM'e paketi göndererek kişiselleştirilmiş özet oluştur
    """
    
    def __init__(self, db_path: str = None):
        self.error_message = None
        
        try:
            # Absolute path logic for cloud compatibility
            if db_path is None:
                db_path = "./data/chroma_db_v2"
            
            # Convert to absolute path (Linux/Streamlit Cloud uyumlu)
            if not os.path.isabs(db_path):
                db_path = os.path.join(os.getcwd(), db_path)
            
            self.db_path = db_path
            self.hotels_json_path = os.path.join(os.getcwd(), "data", "hotels.json")
            
            pass  # Production ready
            
            # ChromaDB client'ı oluştur
            self.client = chromadb.PersistentClient(path=self.db_path)
            
            # SMART RE-INIT: Check Streamlit Cloud environment
            is_streamlit_cloud = "STREAMLIT_CLOUD" in os.environ
            
            # Koleksiyon var mı kontrol et
            try:
                self.collection = self.client.get_collection(name="hotels")
                collection_count = self.collection.count()
                
                # METADATA INTEGRITY CHECK (özellikle Cloud'da önemli)
                if collection_count > 0:
                    try:
                        sample = self.collection.get(limit=1, include=['metadatas'])
                        if sample and sample['metadatas']:
                            meta = sample['metadatas'][0]
                            # Kritik alanları kontrol et
                            city = meta.get('city')
                            price = meta.get('price')
                            
                            if not city or city == 'bilinmiyor' or city == '':
                                raise ValueError("Metadata integrity check failed: empty city")
                            
                            if price is None or (isinstance(price, (int, float)) and price <= 0):
                                raise ValueError("Metadata integrity check failed: invalid price")
                    except Exception as integrity_error:
                        import shutil
                        import time
                        
                        # Close and wipe
                        try:
                            del self.collection
                            del self.client
                        except:
                            pass
                        
                        # Physical wipe
                        if os.path.exists(self.db_path):
                            shutil.rmtree(self.db_path)
                            time.sleep(1)
                        
                        # Recreate
                        self.client = chromadb.PersistentClient(path=self.db_path)
                        raise ValueError("Database reset due to metadata corruption")
                
                if collection_count == 0:
                    self._initialize_db_from_hotels_json()
            
            except Exception as collection_error:
                self._initialize_db_from_hotels_json()
            
            self.embedder = MergenEmbedder()
            self.llm = MergenLLM()
            
            # Veri yükleme
            self._load_flight_data()
            self._load_transfer_data()
            
        except Exception as e:
            self.error_message = f"Seyahat Planlayıcı Başlatma Hatası: {str(e)}"
            traceback.print_exc()

    def _initialize_db_from_hotels_json(self):
        """
        hotels.json dosyasından ChromaDB'yi on-the-fly oluştur
        UUID-based IDs, koleksiyon reset ve batch control ile duplicate ID hatasını önler
        """
        try:
            import streamlit as st
            has_streamlit = True
        except ImportError:
            has_streamlit = False
        
        try:
            # Dosya var mı kontrol et
            if not os.path.exists(self.hotels_json_path):
                raise FileNotFoundError(f"hotels.json bulunamadı: {self.hotels_json_path}")
            
            if has_streamlit:
                spinner_context = __import__('streamlit').spinner("🏨 Vektör veritabanı oluşturuluyor... Bu ilk sefer biraz zaman alabilir.")
            else:
                # Non-Streamlit ortamda dummy context
                from contextlib import contextmanager
                @contextmanager
                def dummy_spinner(msg):
                    yield
                spinner_context = dummy_spinner("")
            
            with spinner_context:
                # hotels.json'ı oku
                with open(self.hotels_json_path, 'r', encoding='utf-8') as f:
                    hotels_data = json.load(f)
                
                # Veri yapısını kontrol et
                if isinstance(hotels_data, dict) and "hotels" in hotels_data:
                    hotels_list = hotels_data["hotels"]
                elif isinstance(hotels_data, list):
                    hotels_list = hotels_data
                else:
                    raise ValueError(f"Beklenmeyen hotels.json yapısı: {type(hotels_data)}")
                
                # STEP 1: Eski koleksiyonu sil
                try:
                    self.client.delete_collection(name="hotels")
                except Exception as e:
                    pass  # Normal - collection doesn't exist yet
                
                # Yeni koleksiyon oluştur
                self.collection = self.client.get_or_create_collection(
                    name="hotels",
                    metadata={"hnsw:space": "cosine"}
                )
                
                # Embedder'ı oluştur
                embedder = MergenEmbedder()
                
                # STEP 2 & 3: UUID-based IDs ile otelleri vektör DB'ye ekle ve batch control
                batch_size = 50
                total_added = 0
                
                for i in range(0, len(hotels_list), batch_size):
                    batch = hotels_list[i:i+batch_size]
                    
                    ids = []
                    documents = []
                    metadatas = []
                    
                    for hotel in batch:
                        # Tamamen eşsiz UUID oluştur
                        unique_id = str(uuid.uuid4())
                        
                        hotel_name = hotel.get("name", hotel.get("hotel_name", "Unknown"))
                        hotel_desc = hotel.get("description", "")
                        
                        # ============================================================
                        # NESTED DICT EXTRACTION: City ve District
                        # ============================================================
                        city_value = None
                        district_value = None
                        area_value = None
                        
                        # Try direct 'city' field first
                        if 'city' in hotel and hotel['city']:
                            city_value = hotel['city']
                        # Try nested location.city structure
                        elif 'location' in hotel and isinstance(hotel['location'], dict):
                            if 'city' in hotel['location'] and hotel['location']['city']:
                                city_value = hotel['location']['city']
                        
                        # Try direct 'district' field first
                        if 'district' in hotel and hotel['district']:
                            district_value = hotel['district']
                        # Try nested location.district structure
                        elif 'location' in hotel and isinstance(hotel['location'], dict):
                            if 'district' in hotel['location'] and hotel['location']['district']:
                                district_value = hotel['location']['district']
                        
                        # Try direct 'area' field first (✅ YENİ)
                        if 'area' in hotel and hotel['area']:
                            area_value = hotel['area']
                        # Try nested location.area structure (✅ YENİ)
                        elif 'location' in hotel and isinstance(hotel['location'], dict):
                            if 'area' in hotel['location'] and hotel['location']['area']:
                                area_value = hotel['location']['area']
                        
                        # Set defaults if not found
                        city_clean = str(city_value).strip().lower() if city_value else 'bilinmiyor'
                        district_clean = str(district_value).strip().lower() if district_value else 'merkez'
                        area_clean = str(area_value).strip().lower() if area_value else 'merkez'  # ✅ YENİ
                        
                        # Validate non-empty
                        if not city_clean or city_clean == 'unknown city' or city_clean == 'unknown':
                            city_clean = 'bilinmiyor'
                        if not district_clean or district_clean == 'unknown district' or district_clean == 'unknown':
                            district_clean = 'merkez'
                        if not area_clean or area_clean == 'unknown area' or area_clean == 'unknown':  # ✅ YENİ
                            area_clean = 'merkez'
                        
                        # Metadata hazırla
                        amenities_list = hotel.get("amenities", [])
                        amenities_str = json.dumps(amenities_list) if amenities_list else "[]"
                        
                        # Extract price safely and convert to float
                        price_raw = hotel.get("price_per_night", hotel.get("price", 0))
                        try:
                            price_float = float(price_raw) if price_raw else 0.0
                        except (ValueError, TypeError):
                            price_float = 0.0
                        
                        ids.append(unique_id)
                        documents.append(hotel_desc)
                        metadatas.append({
                            "uuid": unique_id,
                            "name": hotel_name,
                            "city": city_clean,  # NESTED DICT READY
                            "district": district_clean,  # NESTED DICT READY
                            "area": area_clean,  # ✅ YENİ: Belek, Alanya, vb.
                            "location": f"{city_clean}, {district_clean}",
                            "concept": hotel.get("concept", ""),
                            "price": price_float,  # FLOAT not STRING
                            "amenities": amenities_str
                        })
                    
                    # STEP 3: Batch control - mevcut ID'leri kontrol et
                    existing_ids = set()
                    try:
                        existing_data = self.collection.get()
                        if existing_data and 'ids' in existing_data:
                            existing_ids = set(existing_data['ids'])
                    except Exception as e:
                        print(f"[DEBUG] Mevcut ID kontrolü: {e}")
                    
                    # Yalnızca yeni ID'leri ekle
                    new_ids = []
                    new_documents = []
                    new_metadatas = []
                    
                    for id_, doc, meta in zip(ids, documents, metadatas):
                        if id_ not in existing_ids:
                            new_ids.append(id_)
                            new_documents.append(doc)
                            new_metadatas.append(meta)
                    
                    if new_ids:
                        # Embeddings oluştur
                        emb_vectors = embedder.create_embeddings(new_documents)
                        embeddings = [emb.tolist() for emb in emb_vectors]
                        
                        # DB'ye ekle
                        self.collection.add(
                            ids=new_ids,
                            documents=new_documents,
                            metadatas=new_metadatas,
                            embeddings=embeddings
                        )
                        total_added += len(new_ids)
                        print(f"[INFO] Batch: {len(new_ids)} yeni otel eklendi (Toplam: {total_added}/{len(hotels_list)})")
                        
                        # ============================================================
                        # DEBUG OUTPUT: Every 100 hotels
                        # ============================================================
                        if total_added % 100 == 0 or total_added == len(hotels_list):
                            if new_metadatas:
                                sample_meta = new_metadatas[-1]  # Last hotel in batch
                                debug_name = sample_meta.get('name', 'N/A')
                                debug_city = sample_meta.get('city', 'N/A')
                                debug_price = sample_meta.get('price', 'N/A')
                                print(f"[DEBUG] {total_added}/{len(hotels_list)} - Örnek Otel: {debug_name} - {debug_city} ({debug_price} TRY)")
                    else:
                        print(f"[INFO] Batch: Eklenecek yeni otel yok")
                
                final_count = self.collection.count()
                print(f"[SUCCESS] Vektör veritabanı başarıyla oluşturuldu: {final_count} otel")
                
                if has_streamlit:
                    __import__('streamlit').success(f"✅ Vektör veritabanı hazırlandı! {final_count} otel yüklendi.")
        
        except Exception as e:
            print(f"[ERROR] ChromaDB başlatma hatası: {str(e)}")
            # STEP 4: Try-Catch - Hata oluşursa koleksiyonu sil ve yeniden oluştur
            try:
                print("[WARNING] Hata nedeniyle koleksiyon sıfırlanıyor...")
                self.client.delete_collection(name="hotels")
                self.collection = self.client.get_or_create_collection(
                    name="hotels",
                    metadata={"hnsw:space": "cosine"}
                )
                print("[WARNING] Koleksiyon sıfırlandı ve yeniden oluşturuldu")
            except Exception as reset_error:
                print(f"[ERROR] Koleksiyon sıfırlama başarısız: {reset_error}")
            raise Exception(f"ChromaDB başlatma hatası: {str(e)}")

    def _load_flight_data(self):
        """flights.json dosyasını yükle (OS-bağımsız dosya yolları)"""
        try:
            flights_path = os.path.join("data", "flights.json")
            if os.path.exists(flights_path):
                with open(flights_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # flights.json bir obje, "flights" anahtarı altında liste var
                    if isinstance(data, dict) and "flights" in data:
                        self.flights = data.get("flights", [])
                    else:
                        self.flights = data if isinstance(data, list) else []
            else:
                self.flights = []
        except Exception as e:
            self.flights = []

    def _load_transfer_data(self):
        """transfers.json dosyasını yükle (OS-bağımsız dosya yolları)"""
        try:
            transfers_path = os.path.join("data", "transfers.json")
            if os.path.exists(transfers_path):
                with open(transfers_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # transfers.json bir obje, "transfer_routes" anahtarı altında liste var
                    self.transfers = data  # Tüm veriyi tut, sonra filter_transfers'ta extract et
            else:
                self.transfers = {"transfer_routes": []}
        except Exception as e:
            self.transfers = {"transfer_routes": []}

    def plan_travel(self, user_query: str, top_k: int = 3) -> tuple:
        """
        ANA SEYAHATTRAFİK PLANLAMA FONKSİYONU - Tamamen Revize

        Adımlar:
        1. extract_travel_params() ile niyeti anla
        2. Preferences'ı kullanarak otel ara
        3. Uçuş ve transfer filtrele
        4. Paketleme yap
        5. Akıllı özet oluştur

        Returns: (packages_list, error_message)
        """
        
        # Initialization hatası kontrolü
        if self.error_message:
            return ([], self.error_message)
        
        # ✅ CONTEXT ISOLATION: Her arama başında TravelParams sıfırla
        # Eski sorgulardan kalabilecek niyetler (bebek koltuğu vb) temizlenir
        
        # ✅ MAKSIMUM 3 PAKET: top_k'ı kesinlikle 3'ü geçme
        if top_k > 3:
            top_k = 3
        
        try:
            # ============================================================
            # ADIM 1: NİYET ANALİZİ
            # ============================================================
            travel_params = self.llm.extract_travel_params(user_query)
            
            intent = travel_params.get("intent", {})
            destination_city = travel_params.get("destination_city", "")
            destination_iata = travel_params.get("destination_iata", "ADB")
            origin_iata = travel_params.get("origin_iata", "IST")
            travel_style = travel_params.get("travel_style", "aile")
            preferences = travel_params.get("preferences", [])
            
            # ============================================================
            # ADIM 2: OTEL ARAMA (Preferences'ı Kullanarak)
            # ============================================================
            
            # Preferences'tan irrelevant kelimeleri temizle (uçuş, transfer vb.)
            clean_preferences = self._clean_preferences(preferences)
            
            # Temizlenmiş preferences'ı sorgu olarak kullan (destination_city'yi ayrı parameter olarak geç)
            search_query = f"{' '.join(clean_preferences)}" if clean_preferences else destination_city
            hotels = self._search_hotels_by_preferences(search_query, destination_city, top_k)
            
            if not hotels:
                return ([], f"{destination_city} için uygun otel bulunamadı")
            
            # ============================================================
            # ADIM 3: PAKETLEME VE FİLTRELEME
            # ============================================================
            packages = []
            
            for idx, hotel in enumerate(hotels, 1):
                
                try:
                    # Uçuş filtrele
                    flight = None
                    flight_reason = ""
                    if intent.get("flight"):
                        flight, flight_reason = self._filter_flights(
                            origin_iata=origin_iata,
                            destination_iata=destination_iata,
                            travel_style=travel_style
                        )
                    
                    # Transfer filtrele
                    transfer = None
                    transfer_reason = ""
                    if intent.get("transfer"):
                        transfer, transfer_reason = self._filter_transfers(
                            airport_code=destination_iata,
                            hotel=hotel,  # ✅ Otel objesinin tamamını geç (district bilgisini içeriyor)
                            travel_style=travel_style
                        )
                    
                    # Paketi oluştur
                    package = {
                        "hotel": {
                            "id": hotel.get("id"),
                            "name": hotel.get("name"),
                            "city": hotel.get("city"),
                            "concept": hotel.get("concept"),
                            "price": hotel.get("price"),
                            "description": hotel.get("description"),
                            "amenities": hotel.get("amenities", [])
                        },
                        "flight": flight,
                        "transfer": transfer,
                        "metadata": {
                            "travel_style": travel_style,
                            "preferences": preferences,
                            "destination_iata": destination_iata,
                            "origin_iata": origin_iata
                        }
                    }
                    
                    # ============================================================
                    # TOPLAM FİYAT HESAPLAMASI (TİP GÜVENLI)
                    # ============================================================
                    try:
                        # Hotel fiyatı
                        hotel_price = hotel.get("price", 0)
                        if hotel_price is not None:
                            hotel_price = float(hotel_price)
                        else:
                            hotel_price = 0
                        
                        # Flight fiyatı - flight bir dict mi liste mi kontrol et
                        flight_price = 0
                        if flight is not None:
                            # Eğer flight bir liste ise [0]'ı kullan, değilse doğrudan kullan
                            if isinstance(flight, list) and len(flight) > 0:
                                flight_obj = flight[0]
                            elif isinstance(flight, dict):
                                flight_obj = flight
                            else:
                                flight_obj = None
                            
                            if flight_obj:
                                price_value = flight_obj.get("price", 0)
                                if price_value is not None:
                                    flight_price = float(price_value)
                                else:
                                    flight_price = 0
                        
                        # Transfer fiyatı - transfer bir dict mi liste mi kontrol et
                        transfer_price = 0
                        if transfer is not None:
                            # Eğer transfer bir liste ise [0]'ı kullan, değilse doğrudan kullan
                            if isinstance(transfer, list) and len(transfer) > 0:
                                transfer_obj = transfer[0]
                            elif isinstance(transfer, dict):
                                transfer_obj = transfer
                            else:
                                transfer_obj = None
                            
                            if transfer_obj:
                                price_value = transfer_obj.get("price", 0)
                                if price_value is not None:
                                    transfer_price = float(price_value)
                                else:
                                    transfer_price = 0
                        
                        total_price = hotel_price + flight_price + transfer_price
                        
                        package["price_breakdown"] = {
                            "hotel": hotel_price,
                            "flight": flight_price,
                            "transfer": transfer_price,
                            "total": total_price
                        }
                    
                    except Exception as pricing_error:
                        print(f"[PRICING ERROR] {pricing_error}")
                        package["price_breakdown"] = {
                            "hotel": 0,
                            "flight": 0,
                            "transfer": 0,
                            "total": 0
                        }
                    
                    # ============================================================
                    # ADIM 4: AKILLI ÖZET - LLM'e Paketi Göndererek Özet Oluştur
                    # ============================================================
                    intelligent_summary = self._generate_intelligent_summary(
                        package=package,
                        user_query=user_query,
                        travel_params=travel_params
                    )
                    
                    package["intelligent_summary"] = intelligent_summary
                    packages.append(package)
                
                except Exception as package_error:
                    # Bu oteli atla, sonraki otele geç
                    continue
            
            return (packages, None)
            
        except Exception as e:
            error_msg = f"Seyahat Planlama Hatası: {str(e)}\n{traceback.format_exc()}"
            print(f"[ERROR] {error_msg}")
            return ([], error_msg)

    def _normalize_city_name(self, city: str) -> str:
        """
        Türkçe karakterleri normalize et ve karşılaştırma için hazırla.
        Tüm harfleri lowercase'e çevir ve Türkçe karakterleri ASCII karşılıklarıyla değiştir.
        """
        if not city:
            return ""
        # Step 1: Replace Turkish uppercase special characters FIRST
        city = city.replace('İ', 'i')
        city = city.replace('Ç', 'c')
        city = city.replace('Ğ', 'g')
        city = city.replace('Ş', 's')
        city = city.replace('Ü', 'u')
        city = city.replace('Ö', 'o')
        # Step 2: Convert to lowercase (handles remaining uppercase)
        city = city.lower()
        # Step 3: Replace any remaining Turkish lowercase characters
        city = city.replace('ç', 'c')
        city = city.replace('ğ', 'g')
        city = city.replace('ş', 's')
        city = city.replace('ü', 'u')
        city = city.replace('ö', 'o')
        # Step 4: Strip whitespace
        return city.strip()

    def _clean_preferences(self, preferences: list) -> list:
        """
        Preferences'tan uçuş, transfer, bilet gibi irrelevant kelimeleri çıkar.
        KESIN: Multi-word phrases'leri word-by-word temizle
        """
        # KESIN ÇIKARILACAK KELIMELER
        irrelevant_words = {
            'uçuş', 'uçak', 'bilet', 'transfer', 'havaalanı', 'transferi', 'araç', 
            'araba', 'minibüs', 'taksi', 'shuttle', 'flight', 'ticket', 'airport',
            'sabah', 'akşam', 'gece', 'öğleden', 'havalimanı', 'otobüs', 'sefer',
            'kalkış', 'varış', 'saat', 'gidiş', 'dönüş', 'business', 'economy',
            'otel', 'oteli', 'otele'
        }
        
        cleaned = []
        for phrase in preferences:
            # Her phrase'ı kelimelere ayır
            words = phrase.lower().split()
            
            # Irrelevant kelimeler olmayan kelimeler tutulur
            filtered_words = [w for w in words if w not in irrelevant_words]
            
            # Eğer geriye kelime kaldıysa ekle
            if filtered_words:
                cleaned_phrase = ' '.join(filtered_words)
                cleaned.append(cleaned_phrase)
        
        return cleaned

    def _search_hotels_by_preferences(self, search_query: str, destination_city: str, top_k: int = 3) -> list:
        """
        Otel Arama: Preferences'ı kullanarak ChromaDB'de vektör araması yap
        
        KESIN KURALLAR:
        1. Türkçe karakter normalizasyonu: İ->i, I->ı, lowercase
        2. Partial matching: Tam eşleşme yerine içeriyor mu kontrol
        3. Fallback: Vektör araması boşsa, sadece şehre göre ilk 5 oteli getir
        """
        try:
            # 1. ŞEHİR NORMALIZASYONU
            normalized_city = self._normalize_city_name(destination_city)
            
            # Sorguyu vektore cevir
            query_vector = self.embedder.create_embeddings([search_query])[0].tolist()

            # 2. VEKTÖR ARAMASI YAP
            # Tüm otelleri al ve manual filtrele (flexible matching için)
            all_results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k * 3,  # Daha fazla getir, sonra filtrele
                include=['documents', 'metadatas']
            )

            # Sonuçları düzenle ve şehre göre filtrele
            matched_hotels = []
            for i in range(len(all_results['ids'][0])):
                db_city = all_results['metadatas'][0][i].get('city', '')
                normalized_db_city = self._normalize_city_name(db_city)
                
                # PARTIAL MATCH: normalized_city in normalized_db_city
                if normalized_city in normalized_db_city or normalized_db_city in normalized_city:
                    amenities_data = all_results['metadatas'][0][i].get('amenities', '[]')
                    try:
                        amenities_list = json.loads(amenities_data) if isinstance(amenities_data, str) else amenities_data
                    except:
                        amenities_list = []
                    
                    # SYNC: Price fetching with standardized metadata field name
                    price_value = all_results['metadatas'][0][i].get('price', 0.0)
                    price = float(price_value) if price_value else 0.0
                    
                    matched_hotels.append({
                        "id": all_results['ids'][0][i],
                        "name": all_results['metadatas'][0][i].get('name', 'Unknown'),
                        "city": all_results['metadatas'][0][i].get('city', ''),
                        "concept": all_results['metadatas'][0][i].get('concept', ''),
                        "price": price,
                        "description": all_results['documents'][0][i],
                        "amenities": amenities_list
                    })
                    
                    if len(matched_hotels) >= top_k:
                        break
            
            # 3. FALLBACK: Vektör araması sonuç vermezse, sadece şehre göre al
            if not matched_hotels:
                try:
                    all_hotels = self.collection.get(limit=1000, include=['documents', 'metadatas'])
                    
                    for i, metadata in enumerate(all_hotels['metadatas']):
                        db_city = metadata.get('city', '')
                        normalized_db_city = self._normalize_city_name(db_city)
                        
                        if normalized_city in normalized_db_city or normalized_db_city in normalized_city:
                            amenities_data = metadata.get('amenities', '[]')
                            try:
                                amenities_list = json.loads(amenities_data) if isinstance(amenities_data, str) else amenities_data
                            except:
                                amenities_list = []
                            
                            # SYNC: Price and city fetching using standardized metadata field names
                            price_value = metadata.get('price', 0.0)
                            price = float(price_value) if price_value else 0.0
                            hotel_name = metadata.get('name', 'Unknown')
                            hotel_city = metadata.get('city', '')
                            
                            matched_hotels.append({
                                "id": all_hotels['ids'][i],
                                "name": hotel_name,
                                "city": hotel_city,
                                "concept": metadata.get('concept', ''),
                                "price": price,
                                "description": all_hotels['documents'][i],
                                "amenities": amenities_list
                            })
                            print(f"[FALLBACK] Added: {hotel_name} in {hotel_city}")
                            
                            if len(matched_hotels) >= top_k:
                                break
                    
                    if matched_hotels:
                        print(f"[FALLBACK SUCCESS] Found {len(matched_hotels)} hotels by city filter")
                except Exception as fallback_error:
                    print(f"[FALLBACK ERROR] {fallback_error}")
                    import traceback
                    traceback.print_exc()
            
            # 4. FORCE MATCH: Hala boşsa, şehir metadata'sında kesinlikle city_param geçenleri zorla getir
            if not matched_hotels:
                print(f"[FORCE MATCH] Fallback 1 failed. Using FORCE MATCH...")
                try:
                    all_hotels = self.collection.get(limit=1000, include=['documents', 'metadatas'])
                    print(f"[FORCE MATCH] Checking {len(all_hotels['metadatas'])} hotels for '{destination_city}'...")
                    
                    for i, metadata in enumerate(all_hotels['metadatas']):
                        db_city = metadata.get('city', '')
                        # FORCE: Tam metadata'ya bak, küçük harfe çevir ve kontrol et
                        if destination_city.lower() in db_city.lower() or db_city.lower() in destination_city.lower():
                            amenities_data = metadata.get('amenities', '[]')
                            try:
                                amenities_list = json.loads(amenities_data) if isinstance(amenities_data, str) else amenities_data
                            except:
                                amenities_list = []
                            
                            # SYNC: Price fetching with type safety + force metadata extraction
                            price_value = metadata.get('price', 0) or metadata.get('price_value', 0) or metadata.get('price_per_night', 0)
                            price = float(price_value) if price_value is not None else 0.0
                            hotel_name = metadata.get('name', '') or metadata.get('hotel_name', '') or 'Unknown'
                            hotel_city = metadata.get('city', '') or metadata.get('city_name', '') or ''
                            
                            matched_hotels.append({
                                "id": all_hotels['ids'][i],
                                "name": hotel_name,
                                "city": hotel_city,
                                "concept": metadata.get('concept', ''),
                                "price": price,
                                "description": all_hotels['documents'][i],
                                "amenities": amenities_list
                            })
                            print(f"[FORCE MATCH] Added: {hotel_name} in {hotel_city}")
                            
                            if len(matched_hotels) >= top_k:
                                break
                    
                    if matched_hotels:
                        print(f"[FORCE MATCH SUCCESS] Found {len(matched_hotels)} hotels!")
                    else:
                        print(f"[FORCE MATCH FAILED] No hotels found even with force match")
                except Exception as force_error:
                    print(f"[FORCE MATCH ERROR] {force_error}")
                    import traceback
                    traceback.print_exc()
            
            # DEBUG: Eğer hala boşsa, available cities'i göster
            if not matched_hotels:
                print(f"[WARNING] No hotels found for city: {destination_city}")
                try:
                    all_results = self.collection.get(limit=1000, include=['metadatas'])
                    if all_results['metadatas']:
                        cities_in_db = set()
                        for metadata in all_results['metadatas']:
                            city = metadata.get('city', '')
                            if city:
                                cities_in_db.add(city)
                        example_cities = sorted(list(cities_in_db))
                        print(f"[DEBUG] Available cities in DB: {example_cities}")
                except Exception as debug_error:
                    print(f"[DEBUG] Could not fetch available cities: {debug_error}")
            
            print(f"[SUCCESS] Found {len(matched_hotels)} hotels for {destination_city}\n")
            return matched_hotels
        except Exception as e:
            print(f"[ERROR] Otel arama hatası: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _filter_flights(self, origin_iata: str, destination_iata: str, travel_style: str) -> tuple:
        """
        Uçuş Filtreleme: Teknik kriterlerle uygun uçuşları bul
        
        Returns: (flight_object, reason_text)
        """
        try:
            matching_flights = []
            
            for flight in self.flights:
                leg = flight.get("leg", {})
                
                # IATA kodu eşleştirmesi
                if (leg.get("origin") == origin_iata and 
                    leg.get("destination") == destination_iata):
                    matching_flights.append(flight)
            
            if not matching_flights:
                return (None, "")
            
            # Travel style'a göre filtrele
            if travel_style == "lüks":
                # Premium kabin ara
                premium_flights = [f for f in matching_flights 
                                  if f.get("pricing", {}).get("cabin") in ["BUSINESS", "PREMIUM_ECONOMY"]]
                matching_flights = premium_flights if premium_flights else matching_flights
            
            # Fiyata göre sırala ve en uygununu seç
            matching_flights.sort(key=lambda x: x.get("pricing", {}).get("amount", 0))
            selected_flight = matching_flights[0] if matching_flights else None
            
            if selected_flight:
                airline_name = self.llm.translate_code(selected_flight.get("carrier", ""))
                cabin = selected_flight.get("pricing", {}).get("cabin", "")
                price = float(selected_flight.get("pricing", {}).get("amount", 0))
                
                reason = f"{airline_name} ({cabin}) - ₺{price:,.0f}"
                
                # GERÇEK uçuş objesini döndür
                flight_object = {
                    "flight_id": selected_flight.get("flight_id"),
                    "carrier": selected_flight.get("carrier"),
                    "flight_no": selected_flight.get("flight_no"),
                    "departure": selected_flight.get("leg", {}).get("departure"),
                    "arrival": selected_flight.get("leg", {}).get("arrival"),
                    "price": price,
                    "cabin": cabin,
                    "baggage": selected_flight.get("baggage")
                }
                return (flight_object, reason)
            
            return (None, "")
            
        except Exception as e:
            print(f"[ERROR] Uçuş filtreleme hatası: {e}")
            return (None, "")

    def _filter_transfers(self, airport_code: str, hotel: dict, travel_style: str) -> tuple:
        """
        ✅ DISTRICT-PRIORITY & AREA TRANSFER MATCHING (YENİ MANTIK):
        
        1. PRIORITY HIERARCHY: AREA > DISTRICT > CITY
           - AREA (Alan): 'Belek', 'Alanya' vb. transfer_route'ta tam eşleşme arar
           - DISTRICT (İlçe): Fallback, district ile eşleşme
           - CITY (Şehir): Son fallback, şehir bazlı genel transfer
        
        2. FUZZY SEARCH: Örn. hotel.area='Belek' ise:
           - transfer_route.to_area_name='Belek - Antalya' → 'belek' in 'belek - antalya' ✅
        
        3. FALLBACK: Alan/District match yoksa şehir → sonra default (merkez)
        
        Test Uyumu: Kullanıcı 'Belek'teki otelimize' dediğinde:
        - hotel.area = 'Belek' (location.area'dan geliyor)
        - transfer_route.to_area_name = 'Belek' veya 'Belek - Antalya'
        - 'belek' in 'belek - antalya' → ✅ MATCH!
        
        Returns: (transfer_object, reason_text)
        """
        try:
            # Transfer dosyasının yapısını kontrol et
            if isinstance(self.transfers, dict) and "transfer_routes" in self.transfers:
                routes = self.transfers.get("transfer_routes", [])
            else:
                routes = self.transfers if isinstance(self.transfers, list) else []
            
            # ✅ ADIM 1: Hotel metadata'sından city, district, area bilgisini çıkart
            hotel_city = hotel.get("city", "")
            hotel_district = hotel.get("district", "")
            hotel_area = hotel.get("area", "")  # ✅ YENİ: Area (Belek, Alanya vb.)
            
            hotel_city_normalized = self._normalize_city_name(hotel_city)
            hotel_district_normalized = self._normalize_city_name(hotel_district) if hotel_district else ""
            hotel_area_normalized = self._normalize_city_name(hotel_area) if hotel_area else ""
            
            area_matches = []      # Area üzerinden match (YÜKSEKPRİORİTETİ)
            district_matches = []  # District üzerinden match
            city_matches = []      # City üzerinden match (fallback)
            default_transfer = None
            
            for transfer in routes:
                route = transfer.get("route", {})

                
                # Havalimanı eşleştirmesi (KESIN KURAL)
                if route.get("from_code") == airport_code:
                    to_area_name = route.get("to_area_name", "")
                    to_area_normalized = self._normalize_city_name(to_area_name)
                    
                    # ============================================================
                    # ✅ ADIM 2: AREA > DISTRICT > CITY PRIORITY MATCHING
                    # ============================================================
                    
                    # 1. AREA MATCHING (YÜKSEKPRİORİTETİ - Belek, Alanya vb.)
                    if hotel_area_normalized:
                        # Exact match: 'belek' == 'belek'
                        is_area_exact = hotel_area_normalized == to_area_normalized
                        
                        # Partial match: 'belek' in 'belek - antalya'
                        is_area_partial = (
                            hotel_area_normalized in to_area_normalized or
                            to_area_normalized in hotel_area_normalized
                        )
                        
                        # Fuzzy match
                        area_similarity = SequenceMatcher(None, hotel_area_normalized, to_area_normalized).ratio()
                        is_area_fuzzy = area_similarity > 0.6
                        
                        if is_area_exact or is_area_partial or is_area_fuzzy:
                            area_matches.append((transfer, area_similarity, is_area_exact))
                    
                    # 2. DISTRICT MATCHING (Fallback - eğer area match yoksa)
                    if hotel_district_normalized:
                        # Exact match: 'serik' == 'serik'
                        is_district_exact = hotel_district_normalized == to_area_normalized
                        
                        # Partial match: 'serik' in 'serik - merkez'
                        is_district_partial = (
                            hotel_district_normalized in to_area_normalized or
                            to_area_normalized in hotel_district_normalized
                        )
                        
                        # Fuzzy match
                        district_similarity = SequenceMatcher(None, hotel_district_normalized, to_area_normalized).ratio()
                        is_district_fuzzy = district_similarity > 0.6
                        
                        if is_district_exact or is_district_partial or is_district_fuzzy:
                            district_matches.append((transfer, district_similarity, is_district_exact))
                    
                    # 3. CITY MATCHING (Fallback - sadece area & district match yoksa kullanılır)
                    # Exact match: 'antalya' == 'antalya'
                    is_city_exact = hotel_city_normalized == to_area_normalized
                    
                    # Partial match: 'antalya' in 'merkez antalya'
                    is_city_partial = (
                        hotel_city_normalized in to_area_normalized or
                        to_area_normalized in hotel_city_normalized
                    )
                    
                    # Fuzzy match
                    city_similarity = SequenceMatcher(None, hotel_city_normalized, to_area_normalized).ratio()
                    is_city_fuzzy = city_similarity > 0.6
                    
                    if is_city_exact or is_city_partial or is_city_fuzzy:
                        city_matches.append((transfer, city_similarity, is_city_exact))
                    
                    # 4. DEFAULT TRANSFER (merkez/center - sonuncu çare)
                    if not default_transfer and ("merkez" in to_area_normalized or "center" in to_area_normalized):
                        default_transfer = transfer
            
            selected_transfer = None
            reason = ""
            
            # ============================================================
            # ✅ ADIM 3: MATCH SEÇİMİ (AREA > DISTRICT > CITY > DEFAULT)
            # ============================================================
            
            # AREA MATCH VAR MI? (YÜKSEKPRİORİTETİ)
            if area_matches:
                # Exact match'leri ayırt et
                exact_area = [t for t in area_matches if t[2]]
                
                if exact_area:
                    exact_area.sort(key=lambda x: float(x[0].get("total_price", 0)))
                    best_transfer = exact_area[0][0]
                else:
                    area_matches.sort(key=lambda x: (x[1], float(x[0].get("total_price", 0))), reverse=True)
                    best_transfer = area_matches[0][0]
                
                selected_transfer = best_transfer
            
            # DISTRICT MATCH VAR MI? (İkinci öncelik)
            elif district_matches:
                # Exact match'leri ayırt et
                exact_district = [t for t in district_matches if t[2]]
                
                if exact_district:
                    exact_district.sort(key=lambda x: float(x[0].get("total_price", 0)))
                    best_transfer = exact_district[0][0]
                else:
                    district_matches.sort(key=lambda x: (x[1], float(x[0].get("total_price", 0))), reverse=True)
                    best_transfer = district_matches[0][0]
                
                selected_transfer = best_transfer
            
            # CITY MATCH VAR MI? (Üçüncü öncelik)
            elif city_matches:
                # Exact match'leri ayırt et
                exact_city = [t for t in city_matches if t[2]]
                
                if exact_city:
                    exact_city.sort(key=lambda x: float(x[0].get("total_price", 0)))
                    best_transfer = exact_city[0][0]
                else:
                    city_matches.sort(key=lambda x: (x[1], float(x[0].get("total_price", 0))), reverse=True)
                    best_transfer = city_matches[0][0]
                
                selected_transfer = best_transfer
            
            # HIÇBÎR MATCH YOK, DEFAULT'Yİ KULLAN
            elif default_transfer:
                selected_transfer = default_transfer
            
            # TRANSFER SEÇİLDİ, DETAYLARI HAZIRLA
            if selected_transfer:
                vehicle_type = selected_transfer.get("vehicle_info", {}).get("category", "")
                vehicle_name = self.llm.translate_code(vehicle_type)
                price = float(selected_transfer.get("total_price", 0))
                duration = selected_transfer.get("route", {}).get("estimated_duration", 0)
                
                # Travel style tercihini uygula (VIP vs standard)
                if travel_style == "lüks":
                    vip_candidates = None
                    
                    # District match varsa VIP kontrol et
                    if district_matches:
                        vip_candidates = [t for t in district_matches 
                                         if "VIP" in t[0].get("vehicle_info", {}).get("category", "")]
                    # City match varsa VIP kontrol et
                    elif city_matches:
                        vip_candidates = [t for t in city_matches 
                                         if "VIP" in t[0].get("vehicle_info", {}).get("category", "")]
                    
                    if vip_candidates:
                        vip_candidates.sort(key=lambda x: float(x[0].get("total_price", 0)))
                        selected_transfer = vip_candidates[0][0]
                        vehicle_type = selected_transfer.get("vehicle_info", {}).get("category", "")
                        vehicle_name = self.llm.translate_code(vehicle_type)
                        price = float(selected_transfer.get("total_price", 0))
                
                reason = f"{vehicle_name} - {duration} dakika - ₺{price:,.0f}"
                
                transfer_obj = {
                    "service_code": selected_transfer.get("service_code"),
                    "from": selected_transfer.get("route", {}).get("from_name"),
                    "to": selected_transfer.get("route", {}).get("to_area_name"),
                    "duration": duration,
                    "vehicle_category": vehicle_type,
                    "vehicle_features": selected_transfer.get("vehicle_info", {}).get("features", []),
                    "price": price
                }
                
                return (transfer_obj, reason)
            
            return (None, "")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return (None, "")

    def _generate_intelligent_summary(self, package: dict, user_query: str, travel_params: dict) -> str:
        """
        Akıllı Özet: LLM'e paketi göndererek '✨ Seyahat Planınız' özeti oluştur
        
        Özet içeriği:
        - Bu oteli neden seçtim (tercihlerle eşleştirme)
        - Bu uçuşu neden seçtim (ekonomik/lüks tercihine uygunluk)
        - Bu transferi neden seçtim (konfor + süre + fiyat)
        """
        try:
            hotel = package["hotel"]
            flight = package["flight"]
            transfer = package["transfer"]
            preferences = travel_params.get("preferences", [])
            travel_style = travel_params.get("travel_style", "aile")
            
            # Tercüme edilen bilgiler
            hotel_amenities = ", ".join(hotel.get("amenities", [])[:3])
            
            flight_info = ""
            if flight:
                airline = self.llm.translate_code(flight.get("carrier", ""))
                flight_info = f"Uçuş: {airline} ({flight.get('cabin', '')})"
            
            transfer_info = ""
            if transfer:
                vehicle = self.llm.translate_code(transfer.get("vehicle_category", ""))
                transfer_info = f"Transfer: {vehicle} ({transfer.get('duration')} dakika)"
            
            # Uçuş ve transfer satırlarını hazırla
            flight_section = ""
            if flight:
                flight_price = flight.get("price", 0)
                flight_section = f"✈️ {flight_info} - ₺{flight_price:,.0f}\n"
            
            transfer_section = ""
            if transfer:
                transfer_price = transfer.get("price", 0)
                transfer_section = f"🚗 {transfer_info} - ₺{transfer_price:,.0f}\n"
            
            prompt = f"""
            SEÇİLEN PAKET:
            🏨 {hotel['name']} ({hotel['city']}) - ₺{hotel['price']:,.0f}/gece
            Ameniteler: {hotel_amenities}
            {flight_section}{transfer_section}
            
            GÖREV - ALTTIN ORAN (Akıcı Pazarlama Özeti):
            
            ⚠️ **KATYON KURALLAR:**
            
            1. **FORMAT**: Liste formatını bırak, tek akıcı paragraf yaz. 2-3 cümle, maksimum 30-40 kelime.
            
            2. **PAZARLAMA ZEKASı**: Teknik veriler (sabah uçuşu, bebek koltuğu, butik otel) ile pazarlama dilini harmanla.
               - KÖTÜ: 'Ekonomik uçuş, butik otel.'
               - İYİ: 'Sabah uçuşuyla güne erken başlarken, bebeğiniz için hazırladığımız VIP transfer ve sessiz butik otel tercihimizle konforun tadını çıkaracaksınız.'
            
            3. **DİL**: Sadece temiz, ikna edici İstanbul Türkçesi. Yabancı karakter KESINLIKLE YASAKLI:
               - ❌ İngilizce: morning, hotel, available, thought
               - ❌ Çince: 安全, 设计
               - ❌ Portekizce: bem-vindo
               - ❌ Diğer: szy, vytváracak
            
            4. **GEREKSIZ KALIPLAR YASAKLI**: 'Hazır mısınız?', 'Bu seyahat için hazırladık' vb. Doğrudan paketin değerine odaklan.
            
            5. **HALLUCINATION YASAKLI**: Veri dosyasında olmayan özellik/hizmet yazma.
            
            6. **ÖRNEK ÇIKTI** (İyi yazım):
            'Bebek koltuğu ve sabah uçuşuyla çocuğunuz rahat edecek, sessiz butik otelimiz de huzurlu bir konaklamaya davet ediyor. VIP transfer servisiyle de otelden kapıdan kapıya sakin bir yolculuk sağlıyoruz.'
            
            **ÇIKTI**: Sadece pazarlama paragrafını yaz. Başka bir şey yazma.
            """
            
            completion = self.llm.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.llm.model,
            )
            summary = completion.choices[0].message.content.strip()
            
            # Yabancı karakter kontrolü (İngilizce, Çince, Portekizce kelimeleri)
            forbidden_patterns = ['morning', 'hotel', 'available', '安全', '设计', 'bem-vindo', 'szy', 'vytváracak', 'thought', 'phürsiniz', 'setting']
            
            has_forbidden = any(pattern.lower() in summary.lower() for pattern in forbidden_patterns)
            
            # Kelime sayısı kontrolü (30-40 kelime hedefi, max 45)
            word_count = len(summary.split())
            
            if has_forbidden or word_count > 50:
                # Hata varsa fallback paragraf kullan
                amenities_text = hotel_amenities.split(", ")[0] if hotel_amenities else "ekstra hizmetler"
                summary = f"{hotel['name']}, {amenities_text} ve konforlu bir ortamda, tercihlerinize uyumlu bir paket sunar. Uçuş ve transfer hizmetleriyle tam kaynaklanmış bir tatil deneyimi yaşayacaksınız."
            
            return summary
        
        except Exception as e:
            # Fallback: Pazarlama paragrafı
            hotel_name = hotel.get('name', 'Tesis')
            hotel_city = hotel.get('city', '')
            amenities_first = hotel.get('amenities', ['ekstra hizmetler'])[0] if hotel.get('amenities') else "ekstra hizmetler"
            return f"{hotel_name}, {amenities_first} ve konforlu bir ortamda tercihlerinize uyumlu bir paket sunar. Uçuş ve transfer hizmetleriyle tam kaynaklanmış bir tatil deneyimi yaşayacaksınız."

    def search(self, query: str, top_k: int = 3):
        """
        Backward compatibility: Eski search fonksiyonu, yeni plan_travel'ı çağırır
        """
        packages, error = self.plan_travel(query, top_k)
        
        if error:
            return ([], error)
        
        # Eski format için hotels dizisine dönüştür
        hotels = []
        for package in packages:
            hotel = package["hotel"].copy()
            hotel["reason"] = package.get("intelligent_summary", "Kriterlerinizle tam uyumlu harika bir tesis.")
            hotel["package"] = package
            hotels.append(hotel)
        
        return (hotels, None)

if __name__ == "__main__":
    # Test amacli seyahat planlama
    planner = TravelPlanner()
    test_query = "İzmir'e uçak biletim ve otel transferim olacak şekilde, denize yakın, ailemle gidebileceğim uygun fiyatlı bir otel"
    packages, error_msg = planner.plan_travel(test_query)
    
    if error_msg:
        print(f"\n❌ HATA: {error_msg}\n")
    else:
        print("\n--- MergenX Seyahat Planlama Sonuçları ---\n")
        if packages:
            for idx, package in enumerate(packages, 1):
                print(f"📦 PAKET {idx}")
                print(f"🏨 {package['hotel']['name']} ({package['hotel']['city']})")
                if package['flight']:
                    airline = package['flight'].get('carrier', '')
                    print(f"✈️  {airline} - ₺{package['flight']['price']:,.0f}")
                if package['transfer']:
                    print(f"🚗 Transfer - ₺{package['transfer']['price']:,.0f}")
                total = package['hotel']['price']
                if package['flight']:
                    total += package['flight']['price']
                if package['transfer']:
                    total += package['transfer']['price']
                print(f"💰 Toplam: ₺{total:,.0f}")
                print(f"\n✨ {package.get('intelligent_summary', 'N/A')}\n")
                print("-" * 60 + "\n")
        else:
            print("Sonuç bulunamadı.")

# Backward compatibility: Eski isim için alias
MergenSearchEngine = TravelPlanner
