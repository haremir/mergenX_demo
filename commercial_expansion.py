#!/usr/bin/env python3
"""
TİCARİLEŞTİRME İÇİN VERİ GENİŞLETME SCRIPT
Target: 300 uçuş, 150 transfer, 1000 otel
"""

import json
import random
import copy
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent / "data"
FLIGHTS_FILE = BASE_DIR / "flights.json"
TRANSFERS_FILE = BASE_DIR / "transfers.json"
HOTELS_FILE = BASE_DIR / "hotels.json"

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ============================================================
# ADIM 1: UÇUŞLARI 300'E ÇIKAR
# ============================================================
def expand_flights_to_300():
    print("\n" + "="*70)
    print("✈️ ADIM 1: Uçuşları 300'e Çıkar")
    print("="*70)
    
    flights_data = load_json(FLIGHTS_FILE)
    existing_flights = flights_data.get("flights", [])
    print(f"Mevcut uçuş sayısı: {len(existing_flights)}")
    
    # Hedef dağılım
    targets = {
        "AYT": 100,  # Antalya
        "ADB": 100,  # İzmir
        "BJV": 50,   # Bodrum
        "DLM": 30,   # Dalaman
        "GZT": 20    # Gaziantep
    }
    
    # Transfer zones tanımları
    transfer_zones_map = {
        "AYT": ["Alanya", "Belek", "Side", "Kemer", "Lara", "Konyaaltı", "Kaş"],
        "ADB": ["Çeşme", "Alaçatı", "Seferihisar", "Foça", "Urla"],
        "BJV": ["Bodrum Merkez", "Gümbet", "Bitez", "Turgutreis", "Yalıkavak"],
        "DLM": ["Marmaris", "Fethiye", "Ölüdeniz", "Dalyan"],
        "GZT": ["Gaziantep Merkez", "Şahinbey", "Şehitkamil"]
    }
    
    carriers = ["TK", "PC", "HV", "U6", "AJT"]
    cabins = ["ECONOMY", "BUSINESS"]
    
    new_flights = []
    flight_counter = 3000
    
    for destination, target_count in targets.items():
        # Mevcut destination için kaç uçuş var
        existing_count = sum(1 for f in existing_flights 
                           if f.get("leg", {}).get("destination") == destination)
        needed = target_count - existing_count
        
        print(f"\n{destination}:")
        print(f"  Mevcut: {existing_count}, Hedef: {target_count}, Eklenecek: {needed}")
        
        if needed <= 0:
            continue
        
        # Time slots: Her gün 2 sabah, 2 akşam
        time_slots = [
            {"time": "06:30:00", "slot": "Sabah"},
            {"time": "08:00:00", "slot": "Sabah"},
            {"time": "18:30:00", "slot": "Akşam"},
            {"time": "20:00:00", "slot": "Akşam"}
        ]
        
        # Tarihler: 15 gün boyunca
        start_date = datetime(2026, 6, 15)
        days_needed = (needed // len(time_slots)) + 1
        
        for day in range(days_needed):
            date = start_date + timedelta(days=day)
            date_str = date.strftime("%Y-%m-%d")
            
            for time_slot in time_slots:
                if len([f for f in new_flights if f["leg"]["destination"] == destination]) >= needed:
                    break
                
                carrier = random.choice(carriers)
                cabin = random.choice(cabins)
                
                # Base price
                base_prices = {"ECONOMY": 2500, "BUSINESS": 4500}
                price = base_prices[cabin] + random.randint(-300, 500)
                
                flight = {
                    "flight_id": f"{carrier}{flight_counter}-{date_str.replace('-', '')}",
                    "carrier": carrier,
                    "flight_no": str(flight_counter),
                    "status": "SCHEDULED",
                    "leg": {
                        "origin": "IST",
                        "destination": destination,
                        "departure": f"{date_str}T{time_slot['time']}",
                        "arrival": f"{date_str}T{(datetime.strptime(time_slot['time'], '%H:%M:%S') + timedelta(minutes=75)).strftime('%H:%M:%S')}"
                    },
                    "pricing": {
                        "amount": float(price),
                        "currency": "TRY",
                        "fare_class": "Y" if cabin == "ECONOMY" else "C",
                        "cabin": cabin
                    },
                    "baggage": "1PC x 20KG" if cabin == "ECONOMY" else "2PC x 30KG",
                    "transfer_zones": transfer_zones_map.get(destination, [])
                }
                
                new_flights.append(flight)
                flight_counter += 1
        
        print(f"  ✓ {len([f for f in new_flights if f['leg']['destination'] == destination])} yeni uçuş eklendi")
    
    # Birleştir
    all_flights = existing_flights + new_flights
    flights_data["flights"] = all_flights
    flights_data["metadata"]["total_flights"] = len(all_flights)
    flights_data["metadata"]["generation_date"] = datetime.now().strftime("%Y-%m-%d")
    
    save_json(FLIGHTS_FILE, flights_data)
    print(f"\n✅ Toplam uçuş sayısı: {len(all_flights)}")
    return len(all_flights)

# ============================================================
# ADIM 2: TRANSFER ROTALARINI 150'YE ÇIKAR
# ============================================================
def expand_transfers_to_150():
    print("\n" + "="*70)
    print("🚗 ADIM 2: Transfer Rotalarını 150'ye Çıkar")
    print("="*70)
    
    transfers_data = load_json(TRANSFERS_FILE)
    existing_routes = transfers_data.get("transfer_routes", [])
    print(f"Mevcut rota sayısı: {len(existing_routes)}")
    
    # Havalimanı-bölge kombinasyonları
    airport_areas = {
        "AYT": [
            ("Alanya", 120, 2800, 1800),
            ("Belek", 40, 950, 550),
            ("Side", 90, 2400, 1600),
            ("Kemer", 50, 1800, 1100),
            ("Lara", 25, 750, 450),
            ("Konyaaltı", 30, 850, 500),
            ("Kaş", 180, 3500, 2300),
            ("Manavgat", 70, 2000, 1300),
            ("Finike", 110, 2700, 1700)
        ],
        "ADB": [
            ("Çeşme", 65, 1850, 1100),
            ("Alaçatı", 70, 1900, 1150),
            ("Seferihisar", 45, 1400, 850),
            ("Foça", 55, 1650, 1000),
            ("Urla", 40, 1300, 800),
            ("Kuşadası", 90, 2200, 1400),
            ("Dikili", 120, 2600, 1650)
        ],
        "BJV": [
            ("Bodrum Merkez", 30, 800, 500),
            ("Gümbet", 35, 900, 550),
            ("Bitez", 40, 1000, 600),
            ("Turgutreis", 50, 1200, 750),
            ("Yalıkavak", 45, 1100, 700),
            ("Güvercinlik", 55, 1350, 850)
        ],
        "DLM": [
            ("Marmaris", 60, 1700, 1050),
            ("Fethiye", 45, 1400, 850),
            ("Ölüdeniz", 50, 1500, 950),
            ("Dalyan", 70, 1900, 1200)
        ]
    }
    
    new_routes = []
    service_counter = 2000
    
    for airport, areas in airport_areas.items():
        for area_name, duration, price_vip, price_eco in areas:
            # Kontrol: Zaten var mı?
            exists = any(
                r.get("route", {}).get("from_code") == airport and
                r.get("route", {}).get("to_area_name") == area_name
                for r in existing_routes
            )
            
            if exists:
                continue
            
            # VIP rota
            vip_route = {
                "service_code": f"TR-{airport}-VIP-{service_counter}",
                "operator_id": "MERGEN_LOJ",
                "route": {
                    "from_code": airport,
                    "from_name": f"{airport} Havalimanı",
                    "to_area_code": area_name.upper().replace(" ", "_"),
                    "to_area_name": area_name,
                    "estimated_duration": duration
                },
                "vehicle_info": {
                    "category": "VAN_VIP",
                    "max_pax": 6,
                    "features": ["WIFI", "BABY_SEAT_AVAIL", "LEATHER_SEATS", "CLIMATE_CONTROL"]
                },
                "total_price": float(price_vip),
                "currency": "TRY",
                "hotel_coverage": random.randint(10, 25)
            }
            
            # ECO rota
            eco_route = copy.deepcopy(vip_route)
            eco_route["service_code"] = f"TR-{airport}-ECO-{service_counter}"
            eco_route["vehicle_info"]["category"] = "VAN_ECONOMY"
            eco_route["vehicle_info"]["max_pax"] = 8
            eco_route["vehicle_info"]["features"] = ["AC", "LUGGAGE_SPACE"]
            eco_route["total_price"] = float(price_eco)
            
            new_routes.extend([vip_route, eco_route])
            service_counter += 1
    
    # Fallback genel rotalar
    for airport in ["AYT", "ADB", "BJV", "DLM"]:
        fallback = {
            "service_code": f"TR-{airport}-GENERAL-FB",
            "operator_id": "MERGEN_LOJ",
            "route": {
                "from_code": airport,
                "from_name": f"{airport} Havalimanı",
                "to_area_code": "GENERAL",
                "to_area_name": "Genel Şehir Transferi",
                "estimated_duration": 60
            },
            "vehicle_info": {
                "category": "VAN_STANDARD",
                "max_pax": 8,
                "features": ["AC"]
            },
            "total_price": 1000.0,
            "currency": "TRY",
            "hotel_coverage": 999
        }
        new_routes.append(fallback)
    
    all_routes = existing_routes + new_routes
    
    # 150'ye ulaşmak için dummy rotalar ekle
    target = 150
    if len(all_routes) < target:
        needed_more = target - len(all_routes)
        print(f"\n⚠️ 150'ye ulaşmak için {needed_more} ek rota oluşturuluyor...")
        
        for i in range(needed_more):
            airport = random.choice(["AYT", "ADB", "BJV", "DLM"])
            area = f"Bölge {i+1}"
            
            dummy_route = {
                "service_code": f"TR-{airport}-EXTRA-{3000+i}",
                "operator_id": "MERGEN_LOJ",
                "route": {
                    "from_code": airport,
                    "from_name": f"{airport} Havalimanı",
                    "to_area_code": f"EXTRA_{i}",
                    "to_area_name": area,
                    "estimated_duration": random.randint(30, 120)
                },
                "vehicle_info": {
                    "category": random.choice(["VAN_VIP", "VAN_ECONOMY"]),
                    "max_pax": random.randint(4, 8),
                    "features": ["AC"]
                },
                "total_price": float(random.randint(800, 3000)),
                "currency": "TRY",
                "hotel_coverage": random.randint(5, 20)
            }
            all_routes.append(dummy_route)
    
    transfers_data["transfer_routes"] = all_routes
    
    save_json(TRANSFERS_FILE, transfers_data)
    print(f"✅ Toplam rota sayısı: {len(all_routes)}")
    return len(all_routes)

# ============================================================
# ADIM 3: OTELLERİ 1000'E TAMAMLA + ETİKETLE
# ============================================================
def expand_hotels_to_1000():
    print("\n" + "="*70)
    print("🏨 ADIM 3: Otelleri 1000'e Tamamla + Etiketle")
    print("="*70)
    
    hotels = load_json(HOTELS_FILE)
    print(f"Mevcut otel sayısı: {len(hotels)}")
    
    # Etiketleme kelimeleri
    tags = {
        "Villa": ["villa", "private", "müstakil", "özel"],
        "Butik": ["butik", "boutique", "küçük", "intimate"],
        "Kız kıza uygun": ["sosyal", "merkezi", "eğlence", "nightlife", "bar"],
        "Muhafazakar": ["aile", "family", "çocuk", "hijab friendly", "kapalı havuz"],
        "Balayı": ["romantik", "romantic", "honeymoon", "couples", "jakuzi"],
        "İş odaklı": ["business", "conference", "meeting", "wifi", "workstation"]
    }
    
    # Mevcut otelleri etiketle
    print("\n📝 Mevcut oteller etiketleniyor...")
    tagged_count = 0
    for hotel in hotels:
        name = (hotel.get("hotel_name", "") or "").lower()
        concept = (hotel.get("concept", "") or "").lower()
        description = (hotel.get("description", "") or "").lower()
        amenities = hotel.get("amenities", [])
        
        if not isinstance(amenities, list):
            amenities = []
        
        text = f"{name} {concept} {description}"
        
        # Tag matching
        for tag, keywords in tags.items():
            if tag not in amenities and any(kw in text for kw in keywords):
                amenities.append(tag)
                tagged_count += 1
        
        hotel["amenities"] = list(set(amenities))
    
    print(f"  ✓ {tagged_count} etiket eklendi")
    
    # Yeni otel oluştur
    needed = 1000 - len(hotels)
    print(f"\n➕ {needed} yeni otel oluşturuluyor...")
    
    cities_districts = [
        ("Antalya", ["Alanya", "Belek", "Side", "Kemer", "Lara", "Manavgat"]),
        ("İzmir", ["Çeşme", "Alaçatı", "Seferihisar", "Foça", "Urla"]),
        ("Muğla", ["Bodrum", "Marmaris", "Fethiye", "Datça"]),
        ("Aydın", ["Kuşadası", "Didim"]),
        ("Balıkesir", ["Akçay", "Altınoluk", "Ayvalık"])
    ]
    
    concepts = ["Her Şey Dahil", "Yarım Pansiyon", "Oda Kahvaltı", "Ultra Her Şey Dahil"]
    
    hotel_prefixes = ["Grand", "Luxury", "Boutique", "Villa", "Resort", "Palace", "Paradise", "Golden"]
    hotel_suffixes = ["Hotel", "Resort", "Beach", "Club", "Palace", "Suites"]
    
    new_hotels = []
    for i in range(needed):
        city, districts = random.choice(cities_districts)
        district = random.choice(districts)
        
        name = f"{random.choice(hotel_prefixes)} {district} {random.choice(hotel_suffixes)}"
        
        # Rastgele amenities
        base_amenities = ["WiFi", "Restoran", "Havuz"]
        tag_selection = random.sample(list(tags.keys()), k=random.randint(1, 3))
        
        hotel = {
            "hotel_name": name,
            "location": {
                "city": city,
                "district": district,
                "area": district
            },
            "concept": random.choice(concepts),
            "price_per_night": random.randint(800, 8000),
            "description": f"{district} bölgesinde {random.choice(['lüks', 'konforlu', 'ekonomik', 'butik'])} konaklama.",
            "amenities": base_amenities + tag_selection
        }
        
        new_hotels.append(hotel)
    
    all_hotels = hotels + new_hotels
    save_json(HOTELS_FILE, all_hotels)
    print(f"✅ Toplam otel sayısı: {len(all_hotels)}")
    return len(all_hotels)

# ============================================================
# MAIN EXECUTION
# ============================================================
def main():
    print("\n" + "🚀 "*25)
    print("TİCARİLEŞTİRME VERİ GENİŞLETME BAŞLADI")
    print("🚀 "*25)
    
    try:
        # 1. Uçuşlar
        flights_count = expand_flights_to_300()
        
        # 2. Transferler
        transfers_count = expand_transfers_to_150()
        
        # 3. Oteller
        hotels_count = expand_hotels_to_1000()
        
        print("\n" + "✅ "*25)
        print("TÜM OPERASYONLAR BAŞARILI!")
        print("✅ "*25)
        print(f"\n📊 Final Sayılar:")
        print(f"  ✈️  Uçuşlar: {flights_count}")
        print(f"  🚗 Transferler: {transfers_count}")
        print(f"  🏨 Oteller: {hotels_count}")
        print(f"\n  TOPLAM: {flights_count + transfers_count + hotels_count} kayıt")
        
        return 0
    except Exception as e:
        print(f"\n❌ HATA: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
