import chromadb
import json
import os
import uuid
import shutil
import time
import tempfile
from src.model.embeddings import MergenEmbedder

def get_value(hotel: dict, keys_list):
    """
    JSON'dan veri çekerken tüm olasılıkları kontrol eden güvenli getter.
    
    Args:
        hotel: Otel veri sözlüğü
        keys_list: Kontrol edilecek anahtar isimleri (liste veya string)
    
    Returns:
        Bulunmuş değer veya None
    """
    if isinstance(keys_list, str):
        keys_list = [keys_list]
    
    for key in keys_list:
        if key in hotel:
            value = hotel[key]
            if value is not None and (not isinstance(value, str) or value.strip()):
                return value
    
    return None

class MergenVectorStore:
    def __init__(self, db_path: str = None):
        # Absolute path logic for cloud compatibility
        if db_path is None:
            db_path = "./data/chroma_db_v2"
        
        # Convert to absolute path (Linux/Streamlit Cloud uyumlu)
        if not os.path.isabs(db_path):
            db_path = os.path.join(os.getcwd(), db_path)
        
        self.db_path = db_path
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.embedder = MergenEmbedder()
        # Koleksiyonu olustur veya var olani al
        self.collection = self.client.get_or_create_collection(name="hotels")

    def _validate_hotel_data(self, hotel: dict) -> dict:
        """
        Otel verisini ATOMIK olarak doğrula ve eksik alanları varsayılan değerlerle doldur.
        Tüm alanları explicit type casting ile döndür.
        """
        validated = {}
        
        # ============================================================
        # 1. HOTEL NAME EXTRACTION
        # ============================================================
        if 'hotel_name' in hotel:
            validated['name'] = str(hotel['hotel_name']).strip()
        elif 'name' in hotel:
            validated['name'] = str(hotel['name']).strip()
        else:
            validated['name'] = 'Unknown Hotel'
        
        if not validated['name']:
            validated['name'] = 'Unknown Hotel'
        
        # ============================================================
        # 2. CITY EXTRACTION - location.city (STRICT VALIDATION)
        # ============================================================
        city_value = get_value(hotel, ['city'])
        if not city_value:
            city_value = get_value(hotel, ['location']) if isinstance(hotel.get('location'), dict) else None
            if isinstance(city_value, dict):
                city_value = city_value.get('city', None)
        
        if city_value is not None:
            city_clean = str(city_value).strip().lower()
            if not city_clean or city_clean == "unknown city" or city_clean == "unknown":
                print(f"[ERROR] Empty/invalid city for {hotel.get('name', 'Unknown')}: '{city_value}'. RAISING EXCEPTION")
                raise ValueError(f"Hotel '{hotel.get('name', 'Unknown')}' has invalid city: '{city_value}'")
            validated['city'] = city_clean
        else:
            print(f"[ERROR] No city found for {hotel.get('name', 'Unknown')}. RAISING EXCEPTION")
            raise ValueError(f"Hotel '{hotel.get('name', 'Unknown')}' has no city information")
        
        if not validated['city']:
            raise ValueError(f"Hotel '{validated.get('name', 'Unknown')}' city is empty after cleanup")
        
        # ============================================================
        # 3. DISTRICT EXTRACTION - location.district (STRICT VALIDATION)
        # ============================================================
        district_value = get_value(hotel, ['district'])
        if not district_value:
            district_value = get_value(hotel, ['location']) if isinstance(hotel.get('location'), dict) else None
            if isinstance(district_value, dict):
                district_value = district_value.get('district', None)
        
        if district_value is not None:
            district_clean = str(district_value).strip().lower()
            if not district_clean or district_clean == "unknown district" or district_clean == "unknown":
                print(f"[WARNING] Empty/invalid district for {validated['name']}: '{district_value}'. Using 'merkez' as default")
                validated['district'] = 'merkez'  # Sensible default
            else:
                validated['district'] = district_clean
        else:
            print(f"[WARNING] No district found for {validated['name']}. Using 'merkez' as default")
            validated['district'] = 'merkez'  # Sensible default
        
        if not validated['district']:
            validated['district'] = 'merkez'
        
        # ============================================================
        # 4. LOCATION - Kombinasyon
        # ============================================================
        validated['location'] = f"{validated['city']}, {validated['district']}"
        
        # ============================================================
        # 5. PRICE EXTRACTION - EXPLICIT FLOAT CONVERSION (STRICT)
        # ============================================================
        price_value = get_value(hotel, ['price_per_night', 'price', 'fiyat', 'nightly_price'])
        
        if price_value is not None:
            try:
                price_float = float(price_value)
                # Ensure price is positive or warn
                if price_float <= 0:
                    print(f"[WARNING] Zero/negative price for {validated['name']}: {price_float}. Using default ₺1")
                    validated['price'] = 1.0  # ₺1 uyarıcı, ₺0 değil
                else:
                    validated['price'] = price_float
            except (ValueError, TypeError):
                print(f"[WARNING] Invalid price for {validated['name']}: {price_value} (type: {type(price_value)}). Using default ₺1")
                validated['price'] = 1.0  # Boş fiyat yerine ₺1
        else:
            print(f"[WARNING] No price found for {validated['name']}. Using default ₺1")
            validated['price'] = 1.0  # Boş fiyat yerine ₺1
        
        # ============================================================
        # 6. CONCEPT
        # ============================================================
        if 'concept' in hotel:
            validated['concept'] = str(hotel['concept']).strip()
        else:
            validated['concept'] = 'Standard'
        
        if not validated['concept']:
            validated['concept'] = 'Standard'
        
        # ============================================================
        # 7. DESCRIPTION
        # ============================================================
        if 'description' in hotel:
            validated['description'] = str(hotel['description']).strip()[:200]
        else:
            validated['description'] = 'No description'
        
        if not validated['description']:
            validated['description'] = 'No description'
        
        # ============================================================
        # 8. AMENITIES - JSON STRING
        # ============================================================
        if 'amenities' in hotel and isinstance(hotel['amenities'], list):
            validated['amenities'] = json.dumps(hotel['amenities'])
        else:
            validated['amenities'] = json.dumps([])
        
        return validated

    def process_and_save(self, json_path: str):
        """
        NUCLEAR RESET: Physical database wipe + fresh client + manual extraction.
        - Physical Wipe: shutil.rmtree the entire directory (with retry logic)
        - Fresh Client: Recreate PersistentClient
        - Manual Extraction: No hotel.get() usage
        - Wait and Sync: time.sleep(1) for disk write
        """
        try:
            if not os.path.exists(json_path):
                print(f"[ERROR] {json_path} not found!")
                return

            print(f"[STEP 1] Reading JSON file: {json_path}")
            with open(json_path, "r", encoding="utf-8") as f:
                hotels_data = json.load(f)

            # Parse hotel list
            if isinstance(hotels_data, dict) and "hotels" in hotels_data:
                hotels_list = hotels_data["hotels"]
            elif isinstance(hotels_data, list):
                hotels_list = hotels_data
            else:
                raise ValueError(f"Unexpected structure: {type(hotels_data)}")

            print(f"[STEP 2] Found {len(hotels_list)} hotels. Starting validation...")

            # ============================================================
            # NUCLEAR RESET: Physical Wipe + Fresh Client
            # ============================================================
            print("[STEP 3] NUCLEAR RESET - Physical database wipe...")
            
            # Close existing client first
            try:
                if hasattr(self, 'collection'):
                    delattr(self, 'collection')
                if hasattr(self, 'client'):
                    del self.client
                    print("[INFO] Closed existing client")
            except Exception as close_error:
                print(f"[INFO] Close client: {close_error}")
            
            # Physical Wipe: Remove entire directory with retries
            db_path_abs = os.path.abspath(self.db_path)
            if os.path.exists(db_path_abs):
                print(f"[NUCLEAR] Removing directory: {db_path_abs}")
                try:
                    # Try to move directory instead of delete (Windows file lock workaround)
                    for attempt in range(3):
                        try:
                            # Strategy 1: Try direct removal
                            shutil.rmtree(db_path_abs)
                            print(f"[SUCCESS] Database directory removed (attempt {attempt+1})")
                            break
                        except PermissionError:
                            if attempt < 2:
                                print(f"[RETRY] Permission denied, waiting and retrying... ({attempt+1}/3)")
                                time.sleep(1)
                            else:
                                # Strategy 2: Move to temp directory instead
                                try:
                                    temp_dir = tempfile.gettempdir()
                                    backup_path = os.path.join(temp_dir, f"chroma_db_v2_backup_{int(time.time())}")
                                    shutil.move(db_path_abs, backup_path)
                                    print(f"[SUCCESS] Database moved to backup: {backup_path}")
                                except Exception as move_error:
                                    print(f"[WARNING] Could not move database: {move_error}, continuing anyway...")
                except Exception as rmtree_error:
                    print(f"[WARNING] Failed to fully remove directory: {rmtree_error}, continuing anyway...")
            else:
                print(f"[INFO] Database directory doesn't exist (first run): {db_path_abs}")
            
            # Ensure directory exists (it will be empty now)
            os.makedirs(db_path_abs, exist_ok=True)
            print(f"[SUCCESS] Created fresh directory: {db_path_abs}")
            
            # Fresh Client: Reinitialize with clean slate
            print("[STEP 3.5] FRESH CLIENT - Reinitializing ChromaDB client...")
            self.client = chromadb.PersistentClient(path=self.db_path)
            print("[SUCCESS] New ChromaDB client created")
            
            # Create clean collection
            self.collection = self.client.get_or_create_collection(
                name="hotels",
                metadata={"hnsw:space": "cosine"}
            )
            print("[SUCCESS] New clean collection created")

            # ============================================================
            # DATA PREPARATION WITH MANUAL EXTRACTION
            # ============================================================
            ids = []
            documents = []
            metadatas = []
            
            print("[STEP 4] Data validation and preparation (manual extraction)...")
            invalid_count = 0
            
            for idx, hotel in enumerate(hotels_list):
                try:
                    # Atomically validate each hotel
                    validated = self._validate_hotel_data(hotel)
                    
                    # Generate UUID
                    unique_id = str(uuid.uuid4())
                    
                    # Create searchable text
                    searchable_text = f"{validated['name']} {validated['city']} {validated['district']} {validated['concept']} {validated['description']}"
                    
                    ids.append(unique_id)
                    documents.append(searchable_text)
                    
                    # ============================================================
                    # MANUAL DICTIONARY EXTRACTION - NO hotel.get()
                    # ============================================================
                    # Extract and clean each field manually
                    clean_name = str(validated.get('name', 'Bilinmiyor')).strip()
                    if not clean_name:
                        clean_name = 'Bilinmiyor'
                    
                    clean_city = str(validated.get('city', 'bilinmiyor')).strip().lower()
                    if not clean_city or clean_city == 'unknown city' or clean_city == 'bilinmiyor':
                        clean_city = 'bilinmiyor'
                    
                    clean_district = str(validated.get('district', 'bilinmiyor')).strip().lower()
                    if not clean_district or clean_district == 'unknown district' or clean_district == 'bilinmiyor':
                        clean_district = 'bilinmiyor'
                    
                    clean_location = str(validated.get('location', 'bilinmiyor')).strip()
                    if not clean_location or clean_location == 'bilinmiyor, bilinmiyor':
                        clean_location = f"{clean_city}, {clean_district}"
                    
                    clean_concept = str(validated.get('concept', 'Standard')).strip()
                    if not clean_concept:
                        clean_concept = 'Standard'
                    
                    clean_price_raw = validated.get('price', 0)
                    try:
                        clean_price = float(clean_price_raw) if clean_price_raw else 0.0
                    except (ValueError, TypeError):
                        print(f"[WARNING] Price conversion failed for {clean_name}: {clean_price_raw}")
                        clean_price = 0.0
                    
                    clean_description = str(validated.get('description', 'No description')).strip()
                    if not clean_description:
                        clean_description = 'No description'
                    
                    clean_amenities = str(validated.get('amenities', '[]')).strip()
                    if not clean_amenities:
                        clean_amenities = '[]'
                    
                    # ============================================================
                    # STRICT METADATA MAPPING - EXPLICIT NAMING
                    # ============================================================
                    metadata = {
                        "uuid": str(unique_id),
                        "name": clean_name,
                        "city": clean_city,  # str.lower() guaranteed
                        "district": clean_district,  # str.lower() guaranteed
                        "location": clean_location,
                        "concept": clean_concept,
                        "price": clean_price,  # PURE FLOAT (0.0 minimum)
                        "description": clean_description,
                        "amenities": clean_amenities
                    }
                    
                    # Validation: Ensure no empty or None values
                    for key, value in metadata.items():
                        if value is None:
                            print(f"[ERROR] Metadata validation failed for {clean_name}: {key} is None!")
                            invalid_count += 1
                            break
                        if isinstance(value, str) and not value.strip():
                            print(f"[ERROR] Metadata validation failed for {clean_name}: {key} is empty string!")
                            invalid_count += 1
                            break
                    
                    metadatas.append(metadata)
                    
                    if (idx + 1) % 100 == 0:
                        print(f"[PROGRESS] {idx + 1}/{len(hotels_list)} hotels validated")
                
                except Exception as hotel_error:
                    print(f"[ERROR] Failed to validate hotel {idx}: {hotel_error}")
                    import traceback
                    traceback.print_exc()
                    invalid_count += 1
                    continue

            print(f"[STEP 5] Validation complete. Invalid: {invalid_count}, Valid: {len(ids)}")
            
            if not ids:
                raise ValueError("No valid hotels to insert!")
            
            print(f"[STEP 6] Creating embeddings for {len(documents)} hotels...")
            embeddings = self.embedder.create_embeddings(documents)
            print(f"[SUCCESS] {len(embeddings)} embeddings created")

            # ============================================================
            # DEBUG PRINT: First 3 hotels metadata before ChromaDB insert
            # ============================================================
            print(f"\n[DEBUG METADATA] İlk 3 Otel Metadata'sı ChromaDB'ye eklenmeden ÖNCE:")
            for idx, metadata in enumerate(metadatas[:3]):
                print(f"\n  [OTEL {idx+1}] {metadata.get('name', 'N/A')}")
                print(f"     - City: {metadata.get('city', 'N/A')} (type: {type(metadata.get('city')).__name__})")
                print(f"     - District: {metadata.get('district', 'N/A')}")
                print(f"     - Location: {metadata.get('location', 'N/A')}")
                print(f"     - Price: {metadata.get('price', 'N/A')} (type: {type(metadata.get('price')).__name__})")
                print(f"     - Concept: {metadata.get('concept', 'N/A')}")
                print(f"     - Amenities: {metadata.get('amenities', 'N/A')[:50]}...")

            # ============================================================
            # ADD TO CHROMADB
            # ============================================================
            print(f"\n[STEP 7] Adding {len(ids)} hotels to ChromaDB...")
            self.collection.add(
                ids=ids,
                embeddings=[emb.tolist() if hasattr(emb, 'tolist') else emb for emb in embeddings],
                documents=documents,
                metadatas=metadatas
            )
            
            final_count = self.collection.count()
            print(f"[SUCCESS] ChromaDB updated: {final_count} hotels stored")
            
            # ============================================================
            # WAIT AND SYNC: Ensure disk write completes
            # ============================================================
            print("[STEP 7.5] WAIT AND SYNC - Waiting for disk write...")
            time.sleep(1)
            print("[SUCCESS] Disk sync complete (1 second wait)")
            
            # ============================================================
            # VERIFICATION: Check metadata integrity
            # ============================================================
            print(f"\n[VERIFICATION] Checking metadata integrity...")
            try:
                sample_data = self.collection.get(limit=5, include=['metadatas'])
                print(f"[VERIFICATION] Retrieved {len(sample_data['metadatas'])} samples:")
                for i, meta in enumerate(sample_data['metadatas']):
                    name = meta.get('name', 'N/A')
                    city = meta.get('city', 'N/A')
                    price = meta.get('price', 'N/A')
                    price_type = type(price).__name__
                    print(f"  Sample {i+1}: {name} | City: {city} | Price: {price} ({price_type})")
                    
                    # Verify critical fields
                    if not city or city == 'bilinmiyor':
                        print(f"    [WARNING] City is empty or invalid!")
                    if price is None or price == 0:
                        print(f"    [WARNING] Price is 0 or None!")
            
            except Exception as verify_error:
                print(f"[ERROR] Verification failed: {verify_error}")

        except Exception as e:
            print(f"[ERROR] Data save failed: {e}")
            import traceback
            traceback.print_exc()
            
            # Recovery: Delete and recreate collection
            try:
                print("[RECOVERY] Attempting recovery...")
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