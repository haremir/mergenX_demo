import chromadb
import json
import traceback
import os
import uuid
from pathlib import Path
from src.model.embeddings import MergenEmbedder
from src.model.llm_wrapper import MergenLLM

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
    
    def __init__(self, db_path: str = "./data/chroma_db"):
        self.db_path = db_path
        self.error_message = None
        
        try:
            # Dosya yollarını güvenli hale getir (OS-bağımsız)
            self.db_path = os.path.join("data", "chroma_db")
            self.hotels_json_path = os.path.join("data", "hotels.json")
            
            print(f"[INFO] DB Path: {self.db_path}")
            print(f"[INFO] Hotels JSON Path: {self.hotels_json_path}")
            
            # ChromaDB client'ı oluştur
            self.client = chromadb.PersistentClient(path=self.db_path)
            
            # Koleksiyon var mı kontrol et
            try:
                self.collection = self.client.get_collection(name="hotels")
                collection_count = self.collection.count()
                print(f"[INFO] ChromaDB: {collection_count} otel yüklü")
                
                if collection_count == 0:
                    print(f"[WARNING] ChromaDB koleksiyonu boş! Veri yükleniyor...")
                    self._initialize_db_from_hotels_json()
            
            except Exception as collection_error:
                print(f"[WARNING] ChromaDB koleksiyonu bulunamadı: {collection_error}")
                print(f"[INFO] Vektör veritabanı oluşturuluyor...")
                self._initialize_db_from_hotels_json()
            
            self.embedder = MergenEmbedder()
            self.llm = MergenLLM()
            
            # Veri yükleme
            self._load_flight_data()
            self._load_transfer_data()
            
            print(f"[SUCCESS] Seyahat Planlayıcı başarıyla başlatıldı")
            
        except Exception as e:
            self.error_message = f"Seyahat Planlayıcı Başlatma Hatası: {str(e)}"
            print(f"[ERROR] {self.error_message}")
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
            
            print(f"[INFO] hotels.json okuluyor: {self.hotels_json_path}")
            
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
                
                print(f"[INFO] {len(hotels_list)} otel bulundu")
                
                # STEP 1: Eski koleksiyonu sil
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
                        
                        # Metadata hazırla
                        amenities_list = hotel.get("amenities", [])
                        amenities_str = json.dumps(amenities_list) if amenities_list else "[]"
                        
                        ids.append(unique_id)
                        documents.append(hotel_desc)
                        metadatas.append({
                            "uuid": unique_id,
                            "name": hotel_name,
                            "city": hotel.get("city", "").lower(),
                            "concept": hotel.get("concept", ""),
                            "price": str(hotel.get("price", 0)),
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
                    print(f"[INFO] {len(self.flights)} uçuş verisi yüklendi")
            else:
                self.flights = []
                print(f"[WARNING] flights.json bulunamadı: {flights_path}")
        except Exception as e:
            self.flights = []
            print(f"[ERROR] Uçuş verisi yükleme hatası: {e}")

    def _load_transfer_data(self):
        """transfers.json dosyasını yükle (OS-bağımsız dosya yolları)"""
        try:
            transfers_path = os.path.join("data", "transfers.json")
            if os.path.exists(transfers_path):
                with open(transfers_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # transfers.json bir obje, "transfer_routes" anahtarı altında liste var
                    self.transfers = data  # Tüm veriyi tut, sonra filter_transfers'ta extract et
                    routes_count = len(data.get("transfer_routes", [])) if isinstance(data, dict) else 0
                    print(f"[INFO] {routes_count} transfer rotası yüklendi")
            else:
                self.transfers = {"transfer_routes": []}
                print(f"[WARNING] transfers.json bulunamadı: {transfers_path}")
        except Exception as e:
            self.transfers = {"transfer_routes": []}
            print(f"[ERROR] Transfer verisi yükleme hatası: {e}")

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
            print(f"[ERROR] Initialization Error: {self.error_message}")
            return ([], self.error_message)
        
        try:
            # ============================================================
            # ADIM 1: NİYET ANALİZİ
            # ============================================================
            print(f"\n[STEP 1] Niyeti Analiz Ediliyor: {user_query}")
            travel_params = self.llm.extract_travel_params(user_query)
            print(f"[DEBUG] Travel Params: {travel_params}")
            
            intent = travel_params.get("intent", {})
            destination_city = travel_params.get("destination_city", "")
            destination_iata = travel_params.get("destination_iata", "ADB")
            origin_iata = travel_params.get("origin_iata", "IST")
            travel_style = travel_params.get("travel_style", "aile")
            preferences = travel_params.get("preferences", [])
            
            # ============================================================
            # ADIM 2: OTEL ARAMA (Preferences'ı Kullanarak)
            # ============================================================
            print(f"\n[STEP 2] Otel Aranıyor - Tercihler: {preferences}")
            
            # Preferences'tan irrelevant kelimeleri temizle (uçuş, transfer vb.)
            clean_preferences = self._clean_preferences(preferences)
            
            # Temizlenmiş preferences'ı sorgu olarak kullan (destination_city'yi ayrı parameter olarak geç)
            search_query = f"{' '.join(clean_preferences)}" if clean_preferences else destination_city
            hotels = self._search_hotels_by_preferences(search_query, destination_city, top_k)
            
            if not hotels:
                return ([], f"{destination_city} için uygun otel bulunamadı")
            
            print(f"[SUCCESS] {len(hotels)} otel bulundu")
            
            # ============================================================
            # ADIM 3: PAKETLEME VE FİLTRELEME
            # ============================================================
            packages = []
            
            for idx, hotel in enumerate(hotels, 1):
                print(f"\n[PACKAGE {idx}] {hotel['name']} için paket oluşturuluyor...")
                
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
                            hotel_city=hotel.get("city", ""),
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
                        
                        print(f"[PRICING] Hotel: ₺{hotel_price:.0f} | Flight: ₺{flight_price:.0f} | Transfer: ₺{transfer_price:.0f} | TOTAL: ₺{total_price:.0f}")
                    
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
                    print(f"[PACKAGE OK] Paket başarıyla oluşturuldu")
                
                except Exception as package_error:
                    print(f"[PACKAGE ERROR] {hotel['name']} için paket oluşturulamadı: {package_error}")
                    import traceback
                    traceback.print_exc()
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
        İ -> i, I -> ı, lowercase, trim
        """
        if not city:
            return ""
        return city.replace('İ', 'i').replace('I', 'ı').lower().strip()

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
            print(f"[CLEAN] Processing phrase: '{phrase}'")
            # Her phrase'ı kelimelere ayır
            words = phrase.lower().split()
            print(f"[CLEAN]   Words: {words}")
            
            # Irrelevant kelimeler olmayan kelimeler tutulur
            filtered_words = [w for w in words if w not in irrelevant_words]
            print(f"[CLEAN]   After filtering: {filtered_words}")
            
            # Eğer geriye kelime kaldıysa ekle
            if filtered_words:
                cleaned_phrase = ' '.join(filtered_words)
                cleaned.append(cleaned_phrase)
                print(f"[CLEAN]   Added: '{cleaned_phrase}'")
            else:
                print(f"[CLEAN]   Skipped (all words filtered out)")
        
        print(f"[DEBUG] Preferences cleaned: {preferences} -> {cleaned}")
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
            print(f"\n[DEBUG] Hotel search query: {search_query}")
            print(f"[DEBUG] Destination city (raw): {destination_city}")
            
            # 1. ŞEHİR NORMALIZASYONU
            normalized_city = self._normalize_city_name(destination_city)
            print(f"[DEBUG] Normalized city: {destination_city} -> '{normalized_city}'")
            
            # Sorguyu vektore cevir
            query_vector = self.embedder.create_embeddings([search_query])[0].tolist()
            print(f"[DEBUG] Query vector created")

            # 2. VEKTÖR ARAMASI YAP
            # Tüm otelleri al ve manual filtrele (flexible matching için)
            print(f"[DEBUG] Querying vector DB (fetching {top_k * 3} results for filtering)...")
            all_results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k * 3,  # Daha fazla getir, sonra filtrele
                include=['documents', 'metadatas']
            )
            print(f"[DEBUG] Vector query returned {len(all_results['ids'][0])} results")

            # Sonuçları düzenle ve şehre göre filtrele
            matched_hotels = []
            for i in range(len(all_results['ids'][0])):
                db_city = all_results['metadatas'][0][i].get('city', '')
                normalized_db_city = self._normalize_city_name(db_city)
                
                print(f"[DEBUG] Checking hotel {i+1}: '{db_city}' -> '{normalized_db_city}'")
                
                # PARTIAL MATCH: normalized_city in normalized_db_city
                if normalized_city in normalized_db_city or normalized_db_city in normalized_city:
                    print(f"[DEBUG]   ✓ MATCH!")
                    amenities_data = all_results['metadatas'][0][i].get('amenities', '[]')
                    try:
                        amenities_list = json.loads(amenities_data) if isinstance(amenities_data, str) else amenities_data
                    except:
                        amenities_list = []
                    
                    # Fiyat güvenli fetching
                    price_value = all_results['metadatas'][0][i].get('price', 0)
                    try:
                        price = float(price_value) if price_value is not None else 0
                    except (ValueError, TypeError):
                        price = 0
                    
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
                else:
                    print(f"[DEBUG]   ✗ No match")
            
            # 3. FALLBACK: Vektör araması sonuç vermezse, sadece şehre göre al
            if not matched_hotels:
                print(f"[FALLBACK] Vector search returned nothing. Searching by city only...")
                try:
                    all_hotels = self.collection.get(limit=1000, include=['documents', 'metadatas'])
                    print(f"[FALLBACK] Total hotels in DB: {len(all_hotels['metadatas'])}")
                    
                    for i, metadata in enumerate(all_hotels['metadatas']):
                        db_city = metadata.get('city', '')
                        normalized_db_city = self._normalize_city_name(db_city)
                        
                        if normalized_city in normalized_db_city or normalized_db_city in normalized_city:
                            amenities_data = metadata.get('amenities', '[]')
                            try:
                                amenities_list = json.loads(amenities_data) if isinstance(amenities_data, str) else amenities_data
                            except:
                                amenities_list = []
                            
                            # Fiyat güvenli fetching
                            price_value = metadata.get('price', 0)
                            try:
                                price = float(price_value) if price_value is not None else 0
                            except (ValueError, TypeError):
                                price = 0
                            
                            matched_hotels.append({
                                "id": all_hotels['ids'][i],
                                "name": metadata.get('name', 'Unknown'),
                                "city": metadata.get('city', ''),
                                "concept": metadata.get('concept', ''),
                                "price": price,
                                "description": all_hotels['documents'][i],
                                "amenities": amenities_list
                            })
                            print(f"[FALLBACK] Added: {metadata['name']} in {metadata['city']}")
                            
                            if len(matched_hotels) >= 5:
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
                            
                            # Fiyat güvenli fetching
                            price_value = metadata.get('price', 0)
                            try:
                                price = float(price_value) if price_value is not None else 0
                            except (ValueError, TypeError):
                                price = 0
                            
                            matched_hotels.append({
                                "id": all_hotels['ids'][i],
                                "name": metadata.get('name', 'Unknown'),
                                "city": metadata.get('city', ''),
                                "concept": metadata.get('concept', ''),
                                "price": price,
                                "description": all_hotels['documents'][i],
                                "amenities": amenities_list
                            })
                            print(f"[FORCE MATCH] Added: {metadata['name']} in {metadata['city']}")
                            
                            if len(matched_hotels) >= 5:
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
            
            print(f"[DEBUG] Filtering flights: {origin_iata} -> {destination_iata}")
            print(f"[DEBUG] Total flights in DB: {len(self.flights)}")
            
            for flight in self.flights:
                leg = flight.get("leg", {})
                
                # IATA kodu eşleştirmesi
                if (leg.get("origin") == origin_iata and 
                    leg.get("destination") == destination_iata):
                    matching_flights.append(flight)
            
            print(f"[DEBUG] Matching flights found: {len(matching_flights)}")
            
            if not matching_flights:
                print(f"[WARNING] No flights found for {origin_iata}->{destination_iata}")
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
                print(f"[SUCCESS] Flight selected: {flight_object['flight_no']} - Price: ₺{price}")
                return (flight_object, reason)
                return ({
                    "flight_id": selected_flight.get("flight_id"),
                    "carrier": selected_flight.get("carrier"),
                    "flight_no": selected_flight.get("flight_no"),
                    "departure": selected_flight.get("leg", {}).get("departure"),
                    "arrival": selected_flight.get("leg", {}).get("arrival"),
                    "price": price,
                    "cabin": cabin,
                    "baggage": selected_flight.get("baggage")
                }, reason)
            
            return (None, "")
            
        except Exception as e:
            print(f"[ERROR] Uçuş filtreleme hatası: {e}")
            return (None, "")

    def _filter_transfers(self, airport_code: str, hotel_city: str, travel_style: str) -> tuple:
        """
        Transfer Filtreleme: Havalimanı + bölge bazlı uygun araçları bul
        
        KESIN KURALLAR:
        1. Fuzzy Matching: Otel bölgesi, transfer to_area_name'de kısmen eşleşirse kabul et
        2. Default Transfer: Bölge eşleşmezse, aynı havalimanından merkeze giden genel transferi getir
        
        Returns: (transfer_object, reason_text)
        """
        try:
            print(f"\n[TRANSFER] Searching transfers from {airport_code} to {hotel_city}")
            
            matching_transfers = []
            default_transfer = None  # Havalimanından merkeze giden genel transfer
            
            # Transfer dosyasının yapısını kontrol et
            if isinstance(self.transfers, dict) and "transfer_routes" in self.transfers:
                routes = self.transfers.get("transfer_routes", [])
            else:
                routes = self.transfers if isinstance(self.transfers, list) else []
            
            print(f"[TRANSFER] Total routes in DB: {len(routes)}")
            
            for transfer in routes:
                route = transfer.get("route", {})
                
                # Havalimanı eşleştirmesi
                if route.get("from_code") == airport_code:
                    to_area_name = route.get("to_area_name", "").lower()
                    hotel_city_lower = hotel_city.lower()
                    
                    # FUZZY MATCHING: Kısmen eşleşme
                    if hotel_city_lower in to_area_name or to_area_name in hotel_city_lower:
                        print(f"[TRANSFER] MATCH: {to_area_name} <-> {hotel_city_lower}")
                        matching_transfers.append(transfer)
                    
                    # Default transfer (merkez/şehir merkezi hedefi)
                    if not default_transfer and ("merkez" in to_area_name or "center" in to_area_name):
                        print(f"[TRANSFER] Default transfer candidate: {to_area_name}")
                        default_transfer = transfer
            
            selected_transfer = None
            reason = ""
            
            # Önce specific match'i dene
            if matching_transfers:
                # Travel style'a göre filtrele
                if travel_style == "lüks":
                    # VIP araç ara
                    vip_transfers = [t for t in matching_transfers 
                                    if "VIP" in t.get("vehicle_info", {}).get("category", "")]
                    matching_transfers = vip_transfers if vip_transfers else matching_transfers
                
                # Fiyata göre sırala ve en uygununu seç
                matching_transfers.sort(key=lambda x: float(x.get("total_price", 0)))
                selected_transfer = matching_transfers[0]
                print(f"[TRANSFER] Selected specific match: {selected_transfer.get('service_code')}")
            
            # Eğer specific match yoksa, default transfer'i kullan
            elif default_transfer:
                selected_transfer = default_transfer
                print(f"[TRANSFER] Using default transfer: {selected_transfer.get('service_code')}")
            
            if selected_transfer:
                vehicle_type = selected_transfer.get("vehicle_info", {}).get("category", "")
                vehicle_name = self.llm.translate_code(vehicle_type)
                price = float(selected_transfer.get("total_price", 0))
                duration = selected_transfer.get("route", {}).get("estimated_duration", 0)
                
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
                
                print(f"[TRANSFER SUCCESS] {vehicle_name} - ₺{price}")
                return (transfer_obj, reason)
            
            print(f"[TRANSFER] No suitable transfer found")
            return (None, "")
            
        except Exception as e:
            print(f"[ERROR] Transfer filtreleme hatası: {e}")
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
            Kullanıcının Sorgusu: "{user_query}"
            
            Seyahat Stilü: {travel_style}
            Kullanıcı Tercihleri: {', '.join(preferences)}
            
            SEÇİLEN PAKET:
            🏨 Otel: {hotel['name']} ({hotel['city']})
                - Konsept: {hotel.get('concept', 'N/A')}
                - Özellikleri: {hotel_amenities}
                - Fiyat: ₺{hotel['price']:,.0f}
            
            {flight_section}{transfer_section}
            GÖREV:
            Kullanıcının bu paketi neden mükemmel olduğunu anlatan, samimi ve ikna edici bir '✨ Seyahat Planınız' özeti yaz.
            
            Yapı:
            - Başlık: "✨ Seyahat Planınız"
            - Otel seçimi: Bu oteli neden seçtiğim (tercihlerle bağlantı)
            - Uçuş seçimi: Bu uçuşu neden seçtiğim (style + koşullar)
            - Transfer seçimi: Bu transferi neden seçtiğim (konfor + süre)
            - Kapanış: Heyecan verici cümle
            
            KURALLAR:
            - Maksimum 8-10 cümle
            - Türkçe yaz
            - Emojiler kullan (✈️ 🚗 🏨 etc.)
            - Kişiselleştirilmiş ve sıcak ton
            - Asla giriş/sonuç yazma, sadece özeti ver
            
            Yanıt:
            """
            
            completion = self.llm.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.llm.model,
            )
            
            return completion.choices[0].message.content
            
        except Exception as e:
            print(f"[ERROR] Akıllı özet oluşturma hatası: {e}")
            return "Seyahat paketiniz hazır! 🎉"

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
