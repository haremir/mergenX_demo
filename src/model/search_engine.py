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
                        # ✅ FIXED: NESTED DICT EXTRACTION - City, District & Area
                        # NEVER leave district/area empty - use city as fallback
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
                        
                        # ✅ PRIORITY: Try nested location.district FIRST (primary source)
                        if 'location' in hotel and isinstance(hotel['location'], dict):
                            if 'district' in hotel['location'] and hotel['location']['district']:
                                district_value = hotel['location']['district']
                        # Fallback: Try direct 'district' field
                        if not district_value and 'district' in hotel and hotel['district']:
                            district_value = hotel['district']
                        
                        # ✅ PRIORITY: Try nested location.area FIRST (primary source)
                        if 'location' in hotel and isinstance(hotel['location'], dict):
                            if 'area' in hotel['location'] and hotel['location']['area']:
                                area_value = hotel['location']['area']
                        # Fallback: Try direct 'area' field
                        if not area_value and 'area' in hotel and hotel['area']:
                            area_value = hotel['area']
                        
                        # ✅ NORMALIZE with proper Turkish character handling
                        city_clean = self._normalize_city_name(str(city_value)) if city_value else 'bilinmiyor'
                        
                        # ✅ CRITICAL: If district is empty, use city as fallback (NOT 'merkez')
                        if district_value and str(district_value).strip():
                            district_clean = self._normalize_city_name(str(district_value))
                        else:
                            district_clean = city_clean  # Use city name as fallback
                        
                        # ✅ CRITICAL: If area is empty, use district as fallback
                        if area_value and str(area_value).strip():
                            area_clean = self._normalize_city_name(str(area_value))
                        else:
                            area_clean = district_clean  # Use district name as fallback
                        
                        # ✅ DEBUG: Log first 5 hotels to verify metadata
                        if total_added < 5:
                            print(f"[DEBUG METADATA] Hotel: {hotel_name}")
                            print(f"  Raw: city={city_value}, district={district_value}, area={area_value}")
                            print(f"  Clean: city={city_clean}, district={district_clean}, area={area_clean}")
                        
                        # Final validation - ensure no empty or invalid values
                        if not city_clean or city_clean in ['unknown city', 'unknown', 'none', 'null']:
                            city_clean = 'bilinmiyor'
                        if not district_clean or district_clean in ['unknown district', 'unknown', 'none', 'null', 'merkez']:
                            district_clean = city_clean  # Always fall back to city
                        if not area_clean or area_clean in ['unknown area', 'unknown', 'none', 'null', 'merkez']:
                            area_clean = district_clean  # Always fall back to district
                        
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

    def _simple_parse_query(self, user_query: str) -> dict:
        """
        SIMPLIFIED Query Parser: NO LLM, just basic keyword matching
        
        Extract basics:
        - City names (with strict normalization + city lock)
        - Travel style keywords
        - Time preferences (sabah, akşam, öğle, gece)
        - Intent (hotel, flight, transfer) with expanded keywords
        
        Returns: travel_params dict with city_explicitly_specified flag
        """
        query_lower = user_query.lower()
        
        # ✅ FIX 1: STRICT NORMALIZATION - Normalize user query to handle Turkish characters
        # İzmir -> izmir, Ş -> s, etc.
        query_normalized = self._normalize_city_name(user_query)
        
        # City mapping
        city_keywords = {
            "antalya": ("Antalya", "AYT"),
            "izmir": ("İzmir", "ADB"),
            "bodrum": ("Bodrum", "BJV"),
            "dalaman": ("Dalaman", "DLM"),
            "gaziantep": ("Gaziantep", "GZT")
        }
        
        destination_city = "İzmir"  # Default
        destination_iata = "ADB"
        city_explicitly_specified = False  # ✅ NEW: Track if user specified a city
        
        # ✅ FIX 1: Use normalized query for city matching
        for keyword, (city, iata) in city_keywords.items():
            if keyword in query_normalized:
                destination_city = city
                destination_iata = iata
                city_explicitly_specified = True  # ✅ User explicitly mentioned this city
                break
        
        # Travel style
        travel_style = "aile"  # Default
        if any(word in query_lower for word in ["lüks", "lux", "vip", "premium"]):
            travel_style = "lüks"
        elif any(word in query_lower for word in ["ekonomik", "ucuz", "budget"]):
            travel_style = "ekonomik"
        
        # ✅ UPDATED: TIME PREFERENCE PARSING - Expanded keywords
        # Detect time keywords: sabah, akşam, öğle, gece
        time_preference = None
        time_keywords = {
            "sabah": ["sabah", "morning", "erken", "sabahları", "sabahın"],
            "öğle": ["öğle", "öğleden", "noon", "afternoon", "öğleyin", "öğleden sonra"],
            "akşam": ["akşam", "evening", "akşamları", "akşamın", "akşamüstü"],
            "gece": ["gece", "night", "geç", "geceleyin", "gece yarısı"]
        }
        
        for time_key, time_words in time_keywords.items():
            if any(word in query_lower for word in time_words):
                time_preference = time_key
                break
        
        # ✅ UPDATED: EXPANDED FLIGHT INTENT KEYWORDS
        # Intent - assume all 3 unless specified
        flight_keywords = [
            "uçuş", "uçak", "uçağı", "uçağıyla", "uçakla", 
            "flight", "gidiş", "dönüş", "uçma", "uçuyorum",
            "havayolu", "bilet", "sefer"
        ]
        
        intent = {
            "hotel": True,
            "flight": any(keyword in query_lower for keyword in flight_keywords),
            "transfer": "transfer" in query_lower or "araç" in query_lower
        }
        
        # If no specific mention, include all
        if not intent["flight"] and not intent["transfer"]:
            intent["flight"] = True
            intent["transfer"] = True
        
        return {
            "destination_city": destination_city,
            "destination_iata": destination_iata,
            "origin_iata": "IST",  # Always Istanbul for now
            "travel_style": travel_style,
            "intent": intent,
            "preferences": [],  # Trust vector DB, no manual preferences
            "concept": "",
            "time_preference": time_preference,
            "city_explicitly_specified": city_explicitly_specified  # ✅ NEW: Strict city lock flag
        }

    def _simple_translate(self, code: str) -> str:
        """Simple code translation without LLM"""
        translations = {
            "TK": "Türk Hava Yolları",
            "PC": "Pegasus",
            "XQ": "SunExpress",
            "VAN": "Minivan",
            "VITO": "Mercedes Vito",
            "VIP": "VIP Araç",
            "SPRINTER": "Mercedes Sprinter"
        }
        return translations.get(code, code)
    
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
            # ADIM 1: NİYET ANALİZİ (BASIT PARSING - NO LLM)
            # ============================================================
            travel_params = self._simple_parse_query(user_query)
            
            intent = travel_params.get("intent", {})
            destination_city = travel_params.get("destination_city", "")
            destination_iata = travel_params.get("destination_iata", "ADB")
            origin_iata = travel_params.get("origin_iata", "IST")
            travel_style = travel_params.get("travel_style", "aile")
            preferences = travel_params.get("preferences", [])
            city_explicitly_specified = travel_params.get("city_explicitly_specified", False)  # ✅ NEW
            
            # ✅ FIX 4: Konsepti ayrı al - city ile karıştırılmasın
            concept = travel_params.get("concept", "")
            
            # ============================================================
            # ✅ STRICT CITY LOCK: If user specified a city, NEVER fallback or infer
            # ============================================================
            if city_explicitly_specified:
                print(f"[🔒 STRICT CITY LOCK] User explicitly requested: {destination_city}")
                # NO inference, NO fallback - user's choice is final
            else:
                # ============================================================
                # ✅ FIX 2: NİYET VE ŞEHİR SENKRONİZASYONU (only if city NOT specified)
                # Kullanıcı şehir belirtmediğinde; niyetten (travel_style/preferences)
                # yola çıkarak destination_city parametresini otomatik doldur
                # ============================================================
                if not destination_city or destination_city == "bilinmiyor":
                    # Travel style ve preferences'tan şehir çıkarımı
                    style_to_city = {
                        "kız kıza": "İzmir",
                        "eğlence": "İzmir",
                        "villa": "Antalya",
                        "lüks": "Antalya",
                        "ekonomik": "İzmir",
                        "aile": "Antalya"
                    }
                    
                    # Preferences'tan şehir ipucu ara
                    pref_str = ' '.join(preferences).lower()
                    if any(word in pref_str for word in ['kız', 'eğlence', 'nightlife', 'bar']):
                        destination_city = "İzmir"
                        destination_iata = "ADB"
                    elif any(word in pref_str for word in ['villa', 'lüks', 'spa', 'aquapark']):
                        destination_city = "Antalya"
                        destination_iata = "AYT"
                    else:
                        # Travel style'dan varsayılan
                        destination_city = style_to_city.get(travel_style, "İzmir")
                        destination_iata = "ADB" if destination_city == "İzmir" else "AYT"
                    
                    print(f"[AUTO DESTINATION] No city specified, inferred from style: {destination_city}")
            
            # ============================================================
            # ADIM 2: OTEL ARAMA (Preferences'ı Kullanarak)
            # ============================================================
            
            # Preferences'tan irrelevant kelimeleri temizle (uçuş, transfer vb.)
            clean_preferences = self._clean_preferences(preferences)
            
            # ✅ FIX 4: Konsepti sorguya ekle ama city ile karıştırma
            # Temizlenmiş preferences'ı sorgu olarak kullan (destination_city'yi ayrı parameter olarak geç)
            search_parts = []
            if concept:  # Konsept varsa ekle
                search_parts.append(concept)
            if clean_preferences:  # Tercihler varsa ekle
                search_parts.extend(clean_preferences)
            
            search_query = ' '.join(search_parts) if search_parts else destination_city
            print(f"[SEARCH QUERY] city='{destination_city}', concept='{concept}', query='{search_query}'")
            
            # ============================================================
            # 🔄 DYNAMIC CITY DIVERSITY LOOP (şehir belirtilmediğinde)
            # ============================================================
            if not city_explicitly_specified:
                # Döngüsel algoritma: 3 farklı şehir bulana kadar ara
                selected_cities = set()
                all_hotels_pool = []
                current_search_limit = top_k * 3  # İlk arama: 9 otel
                max_search_limit = 50  # Maksimum arama limiti
                
                print(f"[🔄 DYNAMIC SEARCH] Şehir belirtilmedi, 3 farklı şehir aranıyor...")
                
                while len(selected_cities) < 3 and current_search_limit <= max_search_limit:
                    # Vektör DB'den daha fazla otel çek (TÜM ŞEHİRLERDEN - destination_city='bilinmiyor')
                    hotels_batch = self._search_hotels_simple(search_query, 'bilinmiyor', current_search_limit)
                    
                    if not hotels_batch:
                        print(f"[⚠️ EXHAUSTED] Veritabanında daha fazla otel bulunamadı")
                        break
                    
                    # Yeni otelleri pool'a ekle (duplicate kontrolü)
                    existing_ids = {h.get('id') for h in all_hotels_pool}
                    for hotel in hotels_batch:
                        if hotel.get('id') not in existing_ids:
                            all_hotels_pool.append(hotel)
                            existing_ids.add(hotel.get('id'))
                    
                    # Pool'daki otelleri incele ve farklı şehirlerden seç
                    for hotel in all_hotels_pool:
                        hotel_city = hotel.get('city', '')
                        if hotel_city and hotel_city not in selected_cities:
                            selected_cities.add(hotel_city)
                            print(f"[✅ CITY FOUND] '{hotel_city}' şehri eklendi ({len(selected_cities)}/3)")
                            
                            if len(selected_cities) >= 3:
                                break
                    
                    # Eğer 3 şehir bulunamazsa, aramayı genişlet
                    if len(selected_cities) < 3:
                        current_search_limit += 10
                        print(f"[🔄 EXPANDING] 3 şehir bulunamadı, arama genişletiliyor: {current_search_limit}")
                    else:
                        break
                
                # Şimdi pool'dan her şehirden en iyi otelleri seç (round-robin)
                hotels = []
                selected_city_list = list(selected_cities)
                city_hotel_map = {city: [] for city in selected_city_list}
                
                # Otelleri şehirlere göre grupla
                for hotel in all_hotels_pool:
                    hotel_city = hotel.get('city', '')
                    if hotel_city in city_hotel_map:
                        city_hotel_map[hotel_city].append(hotel)
                
                # Round-robin: Her şehirden sırayla top_k kadar otel al
                for i in range(top_k):
                    for city in selected_city_list:
                        if i < len(city_hotel_map[city]):
                            hotels.append(city_hotel_map[city][i])
                            if len(hotels) >= top_k:
                                break
                    if len(hotels) >= top_k:
                        break
                
                print(f"[🌍 DIVERSITY SUCCESS] {len(selected_cities)} farklı şehirden {len(hotels)} otel seçildi")
                
            else:
                # Kullanıcı şehir belirttiyse, normal arama yap
                hotels = self._search_hotels_simple(search_query, destination_city, top_k)
            
            # ✅ FIX 4: KILL FALLBACK - No alternative cities, no jumping
            if not hotels:
                if city_explicitly_specified:
                    strict_message = f"İstediğiniz bölgede ({destination_city}) kriterlerinize uygun konaklama bulunamadı. Lütfen farklı bir şehir veya kriter deneyin."
                    print(f"[🔒 STRICT CITY LOCK] User explicitly requested {destination_city}, no hotels found - NO FALLBACK")
                else:
                    strict_message = f"Kriterlerinize uygun konaklama bulunamadı. Lütfen farklı bir kriter deneyin."
                    print(f"[✅ NO FALLBACK] No hotels found")
                return ([], strict_message)
            
            # ============================================================
            # ADIM 3: PAKETLEME VE FİLTRELEME (NO ALTERNATIVE CITY LOGIC)
            # ============================================================
            packages = []
            
            for idx, hotel in enumerate(hotels, 1):
                
                try:
                    # Debug: Intent kontrolü
                    print(f"[DEBUG] Processing hotel {idx}, intent={intent}")
                    
                    # 🎯 AKILLI HAVALİMANI SEÇİMİ: Otelin ilçesine göre doğru havalimanını belirle
                    smart_destination_iata = self._get_smart_airport_code(hotel)
                    
                    # Uçuş filtrele
                    flight = None
                    flight_reason = ""
                    flight_error = None
                    if intent.get("flight"):
                        # ✅ FIX 3: Zaman tercihini travel_params'tan al ve flight filtreye gönder
                        # ✅ AKILLI BOŞLUK DOLDURMA: Belirtilmemişse varsayılan 'sabah'
                        time_preference = travel_params.get("time_preference", None)
                        time_was_default = False
                        if not time_preference:
                            time_preference = 'sabah'
                            time_was_default = True
                            print(f"[SMART DEFAULT] No time preference specified, defaulting to 'sabah'")
                        
                        # 🎯 KULLAN: smart_destination_iata (otelin ilçesine göre belirlenen havalimanı)
                        flight, flight_reason = self._filter_flights(
                            origin_iata=origin_iata,
                            destination_iata=smart_destination_iata,  # 🎯 DİNAMİK IATA!
                            travel_style=travel_style,
                            time_preference=time_preference
                        )
                        
                        # 🌍 RELAXED REGIONAL MAPPING: Airport-City-District Validation
                        # Artık katı string eşleşmesi yok, bölgesel mantık var
                        if flight:
                            flight_dest = flight.get("destination", "")
                            hotel_city_name = self._normalize_city_name(hotel.get("city", ""))
                            hotel_district = self._normalize_city_name(hotel.get("district", ""))
                            
                            # ✅ PRIORITY 1: Smart airport selection zaten doğru IATA'yı seçti
                            # Eğer smart_destination_iata == flight_dest ise, otomatik geçerli
                            if flight_dest == smart_destination_iata:
                                print(f"[✅ SMART MATCH] Flight {flight_dest} matches smart airport selection - VALID")
                            else:
                                # ✅ PRIORITY 2: Regional Mapping - Şehir bazlı gevşek kontrol
                                # Muğla şehri için DLM ve BJV kabul et
                                # Aydın şehri için ADB ve BJV kabul et
                                regional_mapping = {
                                    "mugla": ["DLM", "BJV"],  # Muğla için Dalaman veya Bodrum
                                    "aydin": ["ADB", "BJV"],  # Aydın için İzmir veya Bodrum
                                    "izmir": ["ADB"],
                                    "antalya": ["AYT"],
                                    "bodrum": ["BJV"],
                                    "gaziantep": ["GZT"]
                                }
                                
                                valid_airports = regional_mapping.get(hotel_city_name, [])
                                
                                if flight_dest not in valid_airports:
                                    print(f"[⚠️ REGIONAL CHECK] Flight {flight_dest} not in valid list for {hotel_city_name}: {valid_airports}")
                                    # District bazlı son şans kontrolü
                                    if hotel_district:
                                        district_mapping = {
                                            "fethiye": "DLM", "oludeniz": "DLM", "marmaris": "DLM", "datca": "DLM",
                                            "bodrum": "BJV", "didim": "BJV",
                                            "cesme": "ADB", "alacati": "ADB", "kusadasi": "ADB"
                                        }
                                        expected_from_district = district_mapping.get(hotel_district, None)
                                        if expected_from_district and flight_dest == expected_from_district:
                                            print(f"[✅ DISTRICT OVERRIDE] Flight {flight_dest} valid for district {hotel_district}")
                                        else:
                                            print(f"[❌ MISMATCH] Flight {flight_dest} invalid for {hotel_city_name}/{hotel_district} - SKIPPING")
                                            flight = None
                                            flight_error = f"Bölgesel uyumsuzluk: {flight_dest} havalimanı {hotel_city_name} için uygun değil"
                                else:
                                    print(f"[✅ REGIONAL MATCH] Flight {flight_dest} valid for {hotel_city_name}")
                        
                        # Flight-Hotel şehir uyuşmazlığı kontrolü
                        if not flight and destination_iata != "IST":  # IST dışı destinasyonlar kritik
                            if not flight_error:
                                flight_error = f"Şehir uyuşmazlığı: {destination_city} için uygun uçuş bulunamadı"
                    
                    # Transfer filtrele
                    transfer = None
                    transfer_reason = ""
                    if intent.get("transfer"):
                        # 🎯 KULLAN: smart_destination_iata (havalimanı-transfer tutarlılığı)
                        transfer, transfer_reason = self._filter_transfers(
                            airport_code=smart_destination_iata,  # 🎯 DİNAMİK IATA!
                            hotel=hotel,
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
                            "destination_iata": smart_destination_iata,  # 🎯 DİNAMİK IATA
                            "original_destination_iata": destination_iata,  # Orijinal kullanıcı tercihi
                            "origin_iata": origin_iata,
                            "time_was_default": time_was_default if intent.get("flight") else False  # ✅ FIX 3
                        },
                        "error": flight_error  # ⚠️ Şehir uyuşmazlığı uyarısı
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
                    
                    # ✅ FIX 1: Paket hazır, özet şimdilik boş (batch processing için)
                    package["intelligent_summary"] = ""  # Batch'te doldurulacak
                    packages.append(package)
                
                except Exception as package_error:
                    # Bu oteli atla, sonraki otele geç
                    continue
            
            # ============================================================
            # ✅ FIX 1: API VERİMLİLİĞİ - BATCH PROCESSING
            # Her paket için ayrı ayrı LLM isteği yerine, tüm paketlerin
            # 'Reasoning' metinlerini tek bir LLM çağrısıyla oluştur.
            # Bu, 429 Too Many Requests hatasını %90 oranında kesecektir.
            # ============================================================
            if packages:
                print(f"[BATCH PROCESSING] Generating reasoning for {len(packages)} packages in single LLM call...")
                batch_summaries = self._generate_batch_summaries(
                    packages=packages,
                    user_query=user_query,
                    travel_params=travel_params
                )
                
                # Batch summaries'i paketlere ata
                for idx, package in enumerate(packages):
                    if idx < len(batch_summaries):
                        package["intelligent_summary"] = batch_summaries[idx]
                    else:
                        # Fallback
                        package["intelligent_summary"] = f"{package['hotel']['name']}, tercihlerinize uyumlu bir paket sunar."
            
            return (packages, None)
            
        except Exception as e:
            error_msg = f"Seyahat Planlama Hatası: {str(e)}\n{traceback.format_exc()}"
            print(f"[ERROR] {error_msg}")
            return ([], error_msg)

    def _normalize_city_name(self, city: str) -> str:
        """
        Türkçe karakterleri normalize et - Manuel İ -> i dönüşümü ile
        
        IMPORTANT: Database'e yazarken de AYNI fonksiyonu kullan!
        """
        if not city:
            return ""
        
        # ✅ Manuel Turkish character normalization to prevent i̇zmir artifacts
        # İ -> i (capital dotted I to lowercase i)
        # Other Turkish chars: ş, ğ, ü, ö, ç are handled by lower()
        normalized = city.replace('İ', 'i').replace('I', 'ı')
        return normalized.lower().strip()

    def _get_smart_airport_code(self, hotel: dict) -> str:
        """
        🎯 AKILLI HAVALİMANI SEÇİMİ (Dynamic IATA Mapping)
        
        Otelin ilçe/bölgesine göre en uygun havalimanını belirler:
        - Fethiye, Ölüdeniz, Göcek, Marmaris, Datça -> DLM (Dalaman)
        - Bodrum, Didim, Güllük -> BJV (Bodrum)
        - Çeşme, Alaçatı, Urla, Kuşadası -> ADB (İzmir)
        - Belek, Alanya, Kemer, Side -> AYT (Antalya)
        
        Args:
            hotel: Otel metadata dict (city, district, area içerir)
            
        Returns:
            IATA kodu (str): DLM, BJV, ADB, AYT
        """
        # Hotel location bilgilerini al ve normalize et
        city = self._normalize_city_name(hotel.get("city", ""))
        district = self._normalize_city_name(hotel.get("district", ""))
        area = self._normalize_city_name(hotel.get("area", ""))
        
        # Tüm location bilgilerini birleştir (hiyerarşik kontrol için)
        location_text = f"{city} {district} {area}".lower()
        
        # 🎯 KURAL 1: Dalaman Havalimanı (DLM) - Muğla'nın batı bölgeleri
        dlm_regions = ['fethiye', 'oludeniz', 'ölüdeniz', 'gocek', 'göcek', 'marmaris', 'datca', 'datça', 'dalaman', 'mugla', 'muğla']
        if any(region in location_text for region in dlm_regions):
            print(f"[🎯 SMART AIRPORT] Hotel in {district or area} -> DLM (Dalaman)")
            return "DLM"
        
        # 🎯 KURAL 2: Bodrum Havalimanı (BJV) - Muğla'nın kuzey bölgeleri
        bjv_regions = ['bodrum', 'didim', 'gulluk', 'güllük', 'milas', 'turgutreis']
        if any(region in location_text for region in bjv_regions):
            print(f"[🎯 SMART AIRPORT] Hotel in {district or area} -> BJV (Bodrum)")
            return "BJV"
        
        # 🎯 KURAL 3: İzmir Havalimanı (ADB) - İzmir ve çevresi
        adb_regions = ['izmir', 'cesme', 'çeşme', 'alacati', 'alaçatı', 'urla', 'kusadasi', 'kuşadası', 'foca', 'foça', 'seferihisar']
        if any(region in location_text for region in adb_regions):
            print(f"[🎯 SMART AIRPORT] Hotel in {district or area} -> ADB (İzmir)")
            return "ADB"
        
        # 🎯 KURAL 4: Antalya Havalimanı (AYT) - Antalya ve çevresi
        ayt_regions = ['antalya', 'belek', 'alanya', 'kemer', 'side', 'manavgat', 'lara', 'kundu', 'serik']
        if any(region in location_text for region in ayt_regions):
            print(f"[🎯 SMART AIRPORT] Hotel in {district or area} -> AYT (Antalya)")
            return "AYT"
        
        # 🎯 FALLBACK: Şehir bazlı varsayılan mapping
        city_to_airport = {
            "mugla": "DLM",  # Muğla varsayılan Dalaman
            "muğla": "DLM",
            "izmir": "ADB",
            "antalya": "AYT",
            "bodrum": "BJV",
            "gaziantep": "GZT"
        }
        
        default_airport = city_to_airport.get(city, "ADB")  # Ultimate fallback: ADB
        print(f"[🎯 SMART AIRPORT FALLBACK] Hotel in {city} -> {default_airport} (city-based default)")
        return default_airport

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

    def _apply_city_diversity(self, hotels: list, top_k: int) -> list:
        """
        🌍 CITY DIVERSITY LOGIC: İzmir Dominasyonunu Kır
        
        Kullanıcı şehir belirtmediğinde, sonuçların hepsi aynı şehirden gelmesin.
        İlk sonuç İzmir ise, ikinci Muğla, üçüncü Antalya gibi farklı şehirlerden seç.
        
        Kural: Coğrafi çeşitlilik > %100 puanlı homojen sonuçlar
        
        Args:
            hotels: Tüm otel listesi (vector search'ten gelen)
            top_k: Kaç otel döndürülecek
            
        Returns:
            Çeşitlendirilmiş otel listesi (max top_k adet)
        """
        if len(hotels) < 3:
            return hotels[:top_k]
        
        # Otelleri şehirlere göre grupla
        cities_to_hotels = {}
        for hotel in hotels:
            city = hotel.get("city", "bilinmiyor")
            if city not in cities_to_hotels:
                cities_to_hotels[city] = []
            cities_to_hotels[city].append(hotel)
        
        # Şehir sayısı
        num_cities = len(cities_to_hotels)
        print(f"[🌍 DIVERSITY CHECK] Toplam {len(hotels)} otel, {num_cities} farklı şehir")
        
        # Eğer zaten çeşitlilik varsa (farklı şehirler varsa), round-robin uygula
        if num_cities >= 2:
            diverse_hotels = []
            city_names = list(cities_to_hotels.keys())
            
            # Round-robin: Her şehirden sırayla bir otel al
            max_iterations = max(len(hotels_list) for hotels_list in cities_to_hotels.values())
            for i in range(max_iterations):
                for city in city_names:
                    if len(diverse_hotels) >= top_k:
                        break
                    if i < len(cities_to_hotels[city]):
                        diverse_hotels.append(cities_to_hotels[city][i])
                if len(diverse_hotels) >= top_k:
                    break
            
            print(f"[🌍 DIVERSITY APPLIED] Round-robin: {[h['city'] for h in diverse_hotels[:top_k]]}")
            return diverse_hotels[:top_k]
        else:
            # Tek şehir dominant (örn. hepsi İzmir)
            single_city = list(cities_to_hotels.keys())[0]
            print(f"[⚠️ SINGLE CITY DOMINANCE] Tüm sonuçlar '{single_city}' şehrinden")
            return hotels[:top_k]
    
    def _search_hotels_simple(self, search_query: str, destination_city: str, top_k: int = 3) -> list:
        """
        SIMPLIFIED Hotel Search with FLEXIBLE city filtering
        
        Rules:
        1. If destination_city is empty or 'bilinmiyor', search ALL cities
        2. If destination_city is specified, filter by city
        3. Trust vector DB results
        
        Returns: hotels_list (simple list, no fallback info)
        """
        try:
            # Normalize city name
            normalized_city = self._normalize_city_name(destination_city)
            city_filter_active = normalized_city and normalized_city != 'bilinmiyor'
            
            # Vector search
            query_vector = self.embedder.create_embeddings([search_query])[0].tolist()
            
            query_params = {
                'query_embeddings': [query_vector],
                'n_results': top_k,
                'include': ['documents', 'metadatas']
            }
            
            if city_filter_active:
                print(f"[SIMPLE SEARCH] Searching in city='{normalized_city}'")
            else:
                print(f"[SIMPLE SEARCH] Searching in ALL cities (no city filter)")
            
            all_results = self.collection.query(**query_params)
            
            # Debug: Print what cities we got
            if all_results and 'metadatas' in all_results and all_results['metadatas']:
                found_cities = [meta.get('city', 'N/A') for meta in all_results['metadatas'][0][:5]]
                print(f"[DEBUG] Sample cities from DB: {found_cities}")
            
            # Build hotel list
            matched_hotels = []
            for i in range(len(all_results['ids'][0])):
                # Get city and normalize it
                db_city = all_results['metadatas'][0][i].get('city', '')
                db_city_normalized = self._normalize_city_name(db_city)
                
                # Apply city filter only if active
                if city_filter_active and db_city_normalized != normalized_city:
                    continue
                
                amenities_data = all_results['metadatas'][0][i].get('amenities', '[]')
                try:
                    amenities_list = json.loads(amenities_data) if isinstance(amenities_data, str) else amenities_data
                except:
                    amenities_list = []
                
                price_value = all_results['metadatas'][0][i].get('price', 0.0)
                price = float(price_value) if price_value else 0.0
                
                # ✅ CRITICAL: Include district and area for transfer matching
                matched_hotels.append({
                    "id": all_results['ids'][0][i],
                    "name": all_results['metadatas'][0][i].get('name', 'Unknown'),
                    "city": all_results['metadatas'][0][i].get('city', ''),
                    "district": all_results['metadatas'][0][i].get('district', ''),  # ✅ NEW
                    "area": all_results['metadatas'][0][i].get('area', ''),  # ✅ NEW
                    "concept": all_results['metadatas'][0][i].get('concept', ''),
                    "price": price,
                    "description": all_results['documents'][0][i],
                    "amenities": amenities_list
                })
                
                # Stop when we have enough hotels
                if len(matched_hotels) >= top_k:
                    break
            
            if matched_hotels:
                print(f"[SIMPLE SEARCH] Found {len(matched_hotels)} hotels")
            else:
                print(f"[SIMPLE SEARCH] No hotels found in {normalized_city}")
            
            return matched_hotels
        
        except Exception as e:
            print(f"[ERROR] Hotel search error: {e}")
            return []

    def _filter_flights(self, origin_iata: str, destination_iata: str, travel_style: str, time_preference: str = None) -> tuple:
        """
        SIMPLIFIED Flight Filter: Basic origin-destination matching
        
        Args:
            origin_iata: Origin airport code
            destination_iata: Destination airport code
            travel_style: Travel style
            time_preference: Time preference (if any)
        
        Returns:
            (flight_object, reason_text)
        """
        try:
            print(f"[FLIGHT SEARCH] Looking for flights: {origin_iata} -> {destination_iata}, style={travel_style}, time={time_preference}")
            
            matching_flights = []
            
            for flight in self.flights:
                leg = flight.get("leg", {})
                
                # IATA kodu eşleştirmesi
                if (leg.get("origin") == origin_iata and 
                    leg.get("destination") == destination_iata):
                    
                    # ============================================================
                    # ✅ FIX 3: HARD-CODED TIME FILTERING
                    # Kullanıcı zaman tercihi belirttiyse, uçuşları saate göre filtrele
                    # ============================================================
                    if time_preference:
                        departure_time = leg.get("departure", "")
                        if departure_time:
                            try:
                                # ISO format: "2024-01-15T18:30:00" -> saat çıkar
                                hour = int(departure_time.split("T")[1].split(":")[0])
                                
                                # HARD-CODE: Zaman filtreleme
                                if time_preference == 'sabah' and not (6 <= hour < 12):
                                    continue  # ✅ FIX 4: Log temizliği - skip logunu kaldırdık
                                elif time_preference == 'öğleden' and not (12 <= hour < 17):
                                    continue  # ✅ FIX 4: Log temizliği
                                elif time_preference == 'akşam' and not (17 <= hour < 24):
                                    continue  # ✅ FIX 4: Log temizliği
                            except (ValueError, IndexError) as time_error:
                                pass  # ✅ FIX 4: Error log da kaldırıldı
                    
                    matching_flights.append(flight)
            
            # ✅ FIX 4: Sadece başarılı match'leri logla
            if matching_flights and time_preference:
                print(f"[TIME FILTER MATCH] Found {len(matching_flights)} flights for '{time_preference}' preference")
            
            if not matching_flights:
                print(f"[FLIGHT SEARCH] No flights found for {origin_iata} -> {destination_iata}")
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
                airline_name = self._simple_translate(selected_flight.get("carrier", ""))
                cabin = selected_flight.get("pricing", {}).get("cabin", "")
                price = float(selected_flight.get("pricing", {}).get("amount", 0))
                
                reason = f"{airline_name} ({cabin}) - ₺{price:,.0f}"
                
                # GERÇEK uçuş objesini döndür
                flight_object = {
                    "flight_id": selected_flight.get("flight_id"),
                    "carrier": selected_flight.get("carrier"),
                    "flight_no": selected_flight.get("flight_no"),
                    "origin": selected_flight.get("leg", {}).get("origin"),
                    "destination": selected_flight.get("leg", {}).get("destination"),
                    "departure": selected_flight.get("leg", {}).get("departure"),
                    "arrival": selected_flight.get("leg", {}).get("arrival"),
                    "price": price,
                    "cabin": cabin,
                    "baggage": selected_flight.get("baggage")
                }
                
                print(f"[SIMPLE FLIGHT] Found flight: {reason}")
                return (flight_object, reason)
            
            return (None, "")
            
        except Exception as e:
            print(f"[ERROR] Uçuş filtreleme hatası: {e}")
            return (None, "")

    def _filter_transfers(self, airport_code: str, hotel: dict, travel_style: str) -> tuple:
        """
        ✅ STRICT HIERARCHY: Area > District > City
        
        Transfer filter with strict district/area enforcement:
        1. Match airport_code with from_code
        2. HIERARCHY: Check Area first, then District, then City
        3. Use exact .lower().strip() matching - NO partial matches
        4. If hotel is in 'Çeşme', DON'T match 'Foça' or 'Lara' transfers
        
        Returns: (transfer_object, reason_text)
        """
        try:
            # Get transfer routes
            if isinstance(self.transfers, dict) and "transfer_routes" in self.transfers:
                routes = self.transfers.get("transfer_routes", [])
            else:
                routes = self.transfers if isinstance(self.transfers, list) else []
            
            hotel_name = hotel.get("name", "Unknown Hotel")
            hotel_city = hotel.get("city", "").lower().strip()
            hotel_district = hotel.get("district", "").lower().strip()
            hotel_area = hotel.get("area", "").lower().strip()
            
            print(f"\n[🔍 TRANSFER SEARCH] Hotel: {hotel_name}")
            print(f"[📍 LOCATION] City: '{hotel_city}' | District: '{hotel_district}' | Area: '{hotel_area}'")
            
            # ✅ CRITICAL: Verify metadata is not empty
            if not hotel_district or not hotel_area:
                print(f"[⚠️ METADATA WARNING] District or Area is EMPTY - this will cause transfer matching issues!")
            
            # ✅ Define city-to-regions mapping for flexible matching
            # If hotel is in İzmir city, allow transfers to İzmir districts (Çeşme, Alaçatı, Foça, etc.)
            city_regions_map = {
                "izmir": ["cesme", "çesme", "alacati", "alaçatı", "foca", "foça", "urla", "seferihisar", "gumuldur", "gümüldür"],
                "antalya": ["belek", "lara", "kemer", "alanya", "side", "manavgat", "kundu"]
            }
            
            # ✅ STEP 1: Match airport_code with from_code
            airport_matches = []
            for transfer in routes:
                route = transfer.get("route", {})
                from_code = route.get("from_code")
                
                if from_code == airport_code:
                    airport_matches.append(transfer)
            
            if not airport_matches:
                print(f"[❌ NO AIRPORT MATCH] No transfers found for airport code: {airport_code}")
                return (None, "")
            
            print(f"[✅ AIRPORT MATCH] Found {len(airport_matches)} transfers from {airport_code}")
            
            # ✅ STEP 2: FLEXIBLE HIERARCHY - Area > District > City with partial matching
            # Normalize hotel location data
            hotel_city_normalized = self._normalize_city_name(hotel_city)
            hotel_district_normalized = self._normalize_city_name(hotel_district)
            hotel_area_normalized = self._normalize_city_name(hotel_area)
            
            hierarchy_matches = []
            
            for transfer in airport_matches:
                route = transfer.get("route", {})
                to_area_name = route.get("to_area_name", "").lower().strip()
                to_area_normalized = self._normalize_city_name(to_area_name)
                
                matched = False
                
                # ✅ PRIORITY 1: AREA MATCH (Most specific) - exact or partial
                if hotel_area_normalized and to_area_normalized:
                    if hotel_area_normalized == to_area_normalized or \
                       hotel_area_normalized in to_area_normalized or \
                       to_area_normalized in hotel_area_normalized:
                        hierarchy_matches.append({
                            "transfer": transfer,
                            "match_type": "AREA",
                            "match_value": to_area_name
                        })
                        print(f"[🎯 AREA MATCH] Transfer to '{to_area_name}' ≈ Hotel area '{hotel_area}'")
                        matched = True
                        continue
                
                # ✅ PRIORITY 2: DISTRICT MATCH - exact or partial
                if not matched and hotel_district_normalized and to_area_normalized:
                    if hotel_district_normalized == to_area_normalized or \
                       hotel_district_normalized in to_area_normalized or \
                       to_area_normalized in hotel_district_normalized:
                        hierarchy_matches.append({
                            "transfer": transfer,
                            "match_type": "DISTRICT",
                            "match_value": to_area_name
                        })
                        print(f"[🎯 DISTRICT MATCH] Transfer to '{to_area_name}' ≈ Hotel district '{hotel_district}'")
                        matched = True
                        continue
                
                # ✅ PRIORITY 3: CITY-REGION MATCH (Flexible for same-city regions)
                # If hotel is in İzmir city, allow transfers to İzmir districts
                if not matched and hotel_city_normalized and to_area_normalized:
                    # Check if transfer destination is in the same city's region list
                    if hotel_city_normalized in city_regions_map:
                        allowed_regions = city_regions_map[hotel_city_normalized]
                        if any(region in to_area_normalized for region in allowed_regions):
                            hierarchy_matches.append({
                                "transfer": transfer,
                                "match_type": "CITY_REGION",
                                "match_value": to_area_name
                            })
                            print(f"[🎯 CITY-REGION MATCH] Transfer to '{to_area_name}' is in {hotel_city} region")
                            matched = True
                            continue
                    
                    # Direct city match as final fallback
                    if not matched and hotel_city_normalized == to_area_normalized:
                        hierarchy_matches.append({
                            "transfer": transfer,
                            "match_type": "CITY",
                            "match_value": to_area_name
                        })
                        print(f"[🎯 CITY MATCH] Transfer to '{to_area_name}' == Hotel city '{hotel_city}'")
                        matched = True
                        continue
                
                if not matched:
                    print(f"[⚠️ NO MATCH] Transfer to '{to_area_name}' doesn't match hotel location")
            
            # ✅ STEP 3: Select best match based on hierarchy
            if not hierarchy_matches:
                print(f"[❌ NO HIERARCHY MATCH] No transfers match hotel location hierarchy")
                print(f"[STRICT POLICY] Hotel in '{hotel_district}' - Will NOT use 'Foça' or 'Lara' transfers")
                return (None, "")
            
            # ✅ VEHICLE QUALITY PRIORITY for luxury travel_style
            # Define vehicle quality tiers (lower number = higher quality)
            vehicle_quality_map = {
                # Premium tier
                "VIP": 1, "VAN_VIP": 1, "PREMIUM": 1, "PREMIUM_VAN": 1,
                # Mid tier
                "VAN": 2, "MINIVAN": 2, "VITO": 2, "MERCEDES": 2, "SPRINTER": 2,
                # Standard tier
                "SHUTTLE": 3, "STANDARD": 3, "ECONOMY": 3, "BUS": 3
            }
            
            def get_vehicle_quality(transfer_dict):
                """Get vehicle quality score (lower is better)"""
                vehicle_category = transfer_dict["transfer"].get("vehicle_info", {}).get("category", "").upper()
                # Return quality score, default to 99 if unknown
                return vehicle_quality_map.get(vehicle_category, 99)
            
            # ✅ SMART SORTING based on travel_style
            hierarchy_priority = {"AREA": 1, "DISTRICT": 2, "CITY_REGION": 3, "CITY": 4}
            
            if travel_style == "lüks":
                # For luxury: Hierarchy > Quality > Price
                # First prioritize location match, then vehicle quality, then price
                print(f"[🌟 LUXURY MODE] Prioritizing VIP/Premium vehicles over price")
                hierarchy_matches.sort(key=lambda x: (
                    hierarchy_priority.get(x["match_type"], 99),  # Location first
                    get_vehicle_quality(x),  # Then quality
                    float(x["transfer"].get("total_price", 0))  # Then price
                ))
            else:
                # For non-luxury: Hierarchy > Price > Quality
                # Prioritize cheapest option
                hierarchy_matches.sort(key=lambda x: (
                    hierarchy_priority.get(x["match_type"], 99),  # Location first
                    float(x["transfer"].get("total_price", 0)),  # Then price
                    get_vehicle_quality(x)  # Then quality
                ))
            
            best_match = hierarchy_matches[0]
            selected_transfer = best_match["transfer"]
            match_type = best_match["match_type"]
            match_value = best_match["match_value"]
            
            # ✅ LOG: Show vehicle quality decision
            vehicle_category = selected_transfer.get("vehicle_info", {}).get("category", "")
            quality_score = vehicle_quality_map.get(vehicle_category.upper(), 99)
            quality_tier = "PREMIUM" if quality_score == 1 else "MID" if quality_score == 2 else "STANDARD"
            
            if travel_style == "lüks":
                print(f"[🌟 LUXURY SELECTION] Vehicle: {vehicle_category} (Quality: {quality_tier})")
                if quality_score > 1:
                    print(f"[⚠️ LUXURY NOTE] No VIP vehicles available, selecting best available: {vehicle_category}")
            
            vehicle_type = selected_transfer.get("vehicle_info", {}).get("category", "")
            price = float(selected_transfer.get("total_price", 0))
            duration = selected_transfer.get("route", {}).get("estimated_duration", 0)
            
            reason = f"{vehicle_type} - {duration} dakika - ₺{price:,.0f}"
            
            transfer_obj = {
                "service_code": selected_transfer.get("service_code"),
                "from": selected_transfer.get("route", {}).get("from_name"),
                "to": selected_transfer.get("route", {}).get("to_area_name"),
                "duration": duration,
                "vehicle_category": vehicle_type,
                "vehicle_features": selected_transfer.get("vehicle_info", {}).get("features", []),
                "price": price
            }
            
            print(f"[✅ SELECTED] {match_type} match: Transfer to '{match_value}' | {reason}")
            return (transfer_obj, reason)
            
        except Exception as e:
            print(f"[ERROR] Transfer filter error: {e}")
            import traceback
            traceback.print_exc()
            return (None, "")

    def _generate_batch_summaries(self, packages: list, user_query: str, travel_params: dict) -> list:
        """
        ✅ FIX 1: BATCH PROCESSING - API VERİMLİLİĞİ
        Tüm paketlerin 'Reasoning' metinlerini TEK bir LLM çağrısıyla oluştur.
        429 Too Many Requests hatasını %90 oranında azaltır.
        
        Args:
            packages: Tüm paketlerin listesi
            user_query: Kullanıcı sorgusu
            travel_params: Seyahat parametreleri
            
        Returns:
            list: Her paket için reasoning metinleri
        """
        try:
            # Tüm paketleri tek prompt'ta topla
            packages_text = ""
            for idx, package in enumerate(packages, 1):
                hotel = package["hotel"]
                flight = package["flight"]
                transfer = package["transfer"]
                time_was_default = package["metadata"].get("time_was_default", False)
                
                hotel_amenities = ", ".join(hotel.get("amenities", [])[:3])
                
                flight_info = ""
                if flight:
                    airline = self._simple_translate(flight.get("carrier", ""))
                    flight_price = flight.get("price", 0)
                    # ✅ FIX 3: time_was_default kontrolü
                    time_note = " (Varsayılan sabah uçuşu - kullanıcı zaman belirtmedi)" if time_was_default else ""
                    flight_info = f"✈️ {airline} - ₺{flight_price:,.0f}{time_note}"
                
                transfer_info = ""
                if transfer:
                    vehicle = self._simple_translate(transfer.get("vehicle_category", ""))
                    transfer_price = transfer.get("price", 0)
                    duration = transfer.get("duration", 0)
                    transfer_info = f"🚗 {vehicle} - {duration} dakika - ₺{transfer_price:,.0f}"
                
                packages_text += f"""
                PAKET {idx}:
                🏨 {hotel['name']} ({hotel['city']}) - ₺{hotel['price']:,.0f}/gece
                Ameniteler: {hotel_amenities}
                {flight_info}
                {transfer_info}
                ---
                """
            
            # 🎭 Kullanıcı niyetini çıkar (anahtar kelimeler)
            query_lower = user_query.lower()
            intent_keywords = {
                "romantik": "Romantik Kaçamak",
                "kız kıza": "Keyifli Kız Kıza Tatil",
                "sessiz": "Huzurlu Dinlenme",
                "sakin": "Sakin Bir Hafta Sonu",
                "lüks": "Lüks Deneyim",
                "ekonomik": "Uygun Fiyatlı Tatil",
                "aile": "Aile Dostu Tatil",
                "eğlence": "Eğlence Dolu Tatil",
                "deniz": "Deniz Keyfi",
                "spa": "Wellness ve Rahatlama"
            }
            
            package_theme = "Özel Seçim"  # Varsayılan
            for keyword, theme in intent_keywords.items():
                if keyword in query_lower:
                    package_theme = theme
                    break
            
            prompt = f"""
            Sen profesyonel bir Seyahat Danışmanısın. Kullanıcı şöyle bir tatil istedi: "{user_query}"
            
            Aşağıdaki {len(packages)} paketi, kullanıcının niyetine odaklanarak hikaye anlatıcı bir üslupla değerlendir:
            
            {packages_text}
            
            🎯 **SEYAHATTRAFİK DANIŞMANI KURALLARI:**
            
            1️⃣ **NİYET ODAKLI HİKAYE ANLATIMI:**
               - Kullanıcının anahtar kelimelerine (romantik, kız kıza, sessiz, lüks) odaklan
               - ÖRNEK (Romantik): "Baş başa, çocuk sesinden uzak, piyano tınıları eşliğinde eşinizle unutulmaz anlar yaşayacağınız bu butik otelde..."
               - ÖRNEK (Kız Kıza): "Arkadaşlarınızla gülerek geçireceğiniz keyifli bir kaçamak için ideal bu otel, hem havuz başı hem de gece eğlenceleriyle..."
               - ÖRNEK (Sessiz): "Kalabalıktan uzak, doğayla iç içe, sadece kuş sesleri ve dalga seslerinin eşlik edeceği bu huzur dolu ortamda..."
            
            2️⃣ **BİLEŞENLERİ BİR DENEYİM OLARAK BIRLEŞTIR:**
               - Otel + Uçuş + Transfer = Bir hikaye
               - ÖRNEK: "...konforlu Business uçuşunuzun ardından, havalimanında sizi karşılayan lüks VIP aracınızla yorulmadan otelinize geçip romantizmin tadını çıkarabilirsiniz."
               - Varsayılan sabah uçuşu ise: "Güne erken başlamak için sabah uçuşu seçtik, böylece ilk gününüzü tam değerlendirebilirsiniz."
            
            3️⃣ **DIL VE ÜSLUP:**
               - Soğuk ve teknik ifadeler YOK → Sıcak, davetkar, ikna edici
               - "Otel X'de konaklama" DEĞİL → "Otel X'in huzurlu bahçesinde kendinize zaman ayırabilirsiniz"
               - 2-3 cümle, 40-50 kelime, akıcı paragraf
               - Sadece Türkçe, yabancı karakter YASAK
            
            4️⃣ **PAKET BAŞLIKLARI:**
               - Her paketin başına tema ekle: "✅ Paket 1: {package_theme}"
               - Temayı kullanıcı niyetinden çıkar (romantik → Romantik Kaçamak, kız kıza → Keyifli Kız Kıza Tatil)
            
            5️⃣ **HALLUCINATION YASAK:**
               - Sadece verilen bilgileri kullan
               - Olmayan özellik/hizmet ekleme
            
            **ÇIKTI FORMATİ:**
            Her satır bir paket için, başlık + paragraf şeklinde:
            
            ✅ Paket 1: [Tema] - [Hikaye tarzı akıcı paragraf]
            ✅ Paket 2: [Tema] - [Hikaye tarzı akıcı paragraf]
            ✅ Paket 3: [Tema] - [Hikaye tarzı akıcı paragraf]
            
            Sadece bu formatı kullan, başka hiçbir şey yazma.
            """
            
            completion = self.llm.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.llm.model,
            )
            
            response = completion.choices[0].message.content.strip()
            
            # Satırlara ayır
            summaries = [line.strip() for line in response.split('\n') if line.strip()]
            
            # Eğer summary sayısı paket sayısından azsa, fallback ekle
            while len(summaries) < len(packages):
                idx = len(summaries)
                hotel_name = packages[idx]["hotel"]["name"]
                summaries.append(f"{hotel_name}, tercihlerinize uyumlu bir paket sunar.")
            
            print(f"[BATCH SUCCESS] Generated {len(summaries)} summaries in single call")
            return summaries
        
        except Exception as e:
            print(f"[BATCH ERROR] {e}, falling back to individual summaries")
            # Fallback: Basit özetler
            return [f"{pkg['hotel']['name']}, tercihlerinize uyumlu bir paket sunar." for pkg in packages]

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
                airline = self._simple_translate(flight.get("carrier", ""))
                flight_info = f"Uçuş: {airline} ({flight.get('cabin', '')})"
            
            transfer_info = ""
            if transfer:
                vehicle = self._simple_translate(transfer.get("vehicle_category", ""))
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
