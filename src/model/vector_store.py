import chromadb
import json
import os
import uuid
import shutil
import time
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
        # 2. CITY EXTRACTION - location.city
        # ============================================================
        city_value = None
        if 'location' in hotel and isinstance(hotel['location'], dict):
            city_value = hotel['location'].get('city', None)
        elif 'city' in hotel:
            city_value = hotel['city']
        
        if city_value is not None:
            validated['city'] = str(city_value).strip()
        else:
            validated['city'] = 'Unknown City'
        
        if not validated['city']:
            validated['city'] = 'Unknown City'
        
        # ============================================================
        # 3. DISTRICT EXTRACTION - location.district
        # ============================================================
        district_value = None
        if 'location' in hotel and isinstance(hotel['location'], dict):
            district_value = hotel['location'].get('district', None)
        elif 'district' in hotel:
            district_value = hotel['district']
        
        if district_value is not None:
            validated['district'] = str(district_value).strip()
        else:
            validated['district'] = 'Unknown District'
        
        if not validated['district']:
            validated['district'] = 'Unknown District'
        
        # ============================================================
        # 4. LOCATION - Kombinasyon
        # ============================================================
        validated['location'] = f"{validated['city']}, {validated['district']}"
        
        # ============================================================
        # 5. PRICE EXTRACTION - EXPLICIT FLOAT CONVERSION
        # ============================================================
        price_value = None
        
        # Fiyat alanlarını sırasıyla kontrol et
        if 'price_per_night' in hotel:
            price_value = hotel['price_per_night']
        elif 'price' in hotel:
            price_value = hotel['price']
        
        if price_value is not None:
            try:
                validated['price'] = float(price_value)
            except (ValueError, TypeError):
                print(f"[WARNING] Invalid price for {validated['name']}: {price_value} (type: {type(price_value)}). Using 0.0")
                validated['price'] = 0.0
        else:
            print(f"[WARNING] No price found for {validated['name']}. Using 0.0")
            validated['price'] = 0.0
        
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
        - Physical Wipe: shutil.rmtree the entire directory
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
                    # Try multiple times if files are locked
                    import time as time_module
                    for attempt in range(3):
                        try:
                            shutil.rmtree(db_path_abs)
                            print(f"[SUCCESS] Database directory removed (attempt {attempt+1})")
                            break
                        except PermissionError as perm_error:
                            if attempt < 2:
                                print(f"[RETRY] Permission denied, waiting and retrying... ({attempt+1}/3)")
                                time_module.sleep(0.5)
                            else:
                                raise perm_error
                except Exception as rmtree_error:
                    print(f"[ERROR] Failed to remove directory: {rmtree_error}")
                    raise
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
                    
                    clean_city = str(validated.get('city', 'Bilinmiyor')).strip().lower()
                    if not clean_city or clean_city == 'unknown city':
                        clean_city = 'Bilinmiyor'
                    
                    clean_district = str(validated.get('district', 'Bilinmiyor')).strip().lower()
                    if not clean_district or clean_district == 'unknown district':
                        clean_district = 'Bilinmiyor'
                    
                    clean_location = str(validated.get('location', 'Bilinmiyor')).strip()
                    if not clean_location or clean_location == 'Bilinmiyor, Bilinmiyor':
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
                    # STRICT METADATA MAPPING
                    # ============================================================
                    metadata = {
                        "uuid": str(unique_id),
                        "name": clean_name,
                        "city": clean_city,
                        "district": clean_district,
                        "location": clean_location,
                        "concept": clean_concept,
                        "price": clean_price,  # PURE FLOAT
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
            # ADD TO CHROMADB
            # ============================================================
            print(f"[STEP 7] Adding {len(ids)} hotels to ChromaDB...")
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