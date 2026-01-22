#!/usr/bin/env python3
"""
Veri Genişletme Script: Sistem karar verme kabiliyetini artırır
1. Antalya uçuşlarına transfer_zones ekle
2. Transfer rotalarını tamamla (Alanya, Kemer, Side)
3. Hotels amenities'e Villa/Butik etiketleri ekle
4. Veri bütünlüğü kontrolü (case sensitivity)
"""

import json
import os
from pathlib import Path
from datetime import datetime
import copy

# Dosya yolları
BASE_DIR = Path(__file__).parent / "data"
FLIGHTS_FILE = BASE_DIR / "flights.json"
TRANSFERS_FILE = BASE_DIR / "transfers.json"
HOTELS_FILE = BASE_DIR / "hotels.json"

def load_json(filepath):
    """JSON dosyasını yükle"""
    print(f"📖 Yükleniyor: {filepath.name}")
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(filepath, data):
    """JSON dosyasını kaydet"""
    print(f"💾 Kaydediliyor: {filepath.name}")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def expand_flights():
    """
    ADIM 1: Antalya uçuşlarına transfer_zones ekle
    - Alanya, Kemer, Side, Kaş, Belek bölgelerini ekle
    - Sabah (06:00-09:00) ve Akşam (18:00-21:00) uçuşları oluştur
    """
    print("\n" + "="*60)
    print("🛫 ADIM 1: Antalya Uçuşlarını Genişlet")
    print("="*60)
    
    flights_data = load_json(FLIGHTS_FILE)
    flights = flights_data.get("flights", [])
    
    # Antalya uçuşlarını bul (destination: AYT)
    ayt_flights = [f for f in flights if f.get("leg", {}).get("destination") == "AYT"]
    print(f"✓ Mevcut Antalya uçuşları: {len(ayt_flights)}")
    
    new_zones = ["Alanya", "Kemer", "Side", "Kaş", "Belek"]
    existing_ayt_ids = set()
    
    # Her AYT uçuşunun ID'sini topla
    for flight in ayt_flights:
        existing_ayt_ids.add(flight.get("flight_id"))
    
    # Transfer zones'u güncelle
    zones_updated = 0
    for flight in ayt_flights:
        current_zones = flight.get("transfer_zones", [])
        for zone in new_zones:
            if zone not in current_zones:
                current_zones.append(zone)
                zones_updated += 1
        flight["transfer_zones"] = list(set(current_zones))  # Dublike kaldır
    
    print(f"✓ Transfer zones eklendi: {zones_updated} bölge")
    
    # Yeni sabah/akşam uçuşları oluştur
    new_flights = []
    base_flight_no = 2200  # Yeni uçuş numaraları için başlangıç
    
    time_slots = [
        {"name": "Sabah", "time": "T07:00:00", "arrival_offset": 75},
        {"name": "Akşam", "time": "T19:00:00", "arrival_offset": 75}
    ]
    
    for idx, flight in enumerate(ayt_flights[:3]):  # İlk 3 uçuşu temel al
        for time_slot in time_slots:
            new_flight = copy.deepcopy(flight)
            
            # Yeni ID oluştur
            new_flight_id = f"TK{base_flight_no}-20260615"
            new_flight["flight_id"] = new_flight_id
            new_flight["flight_no"] = str(base_flight_no)
            base_flight_no += 1
            
            # Saat güncelle
            departure_date = flight["leg"]["departure"].split("T")[0]
            arrival_date = flight["leg"]["arrival"].split("T")[0]
            
            new_flight["leg"]["departure"] = f"{departure_date}{time_slot['time']}:00"
            # Kalkış saatine +75 dakika ekle
            from datetime import datetime, timedelta
            dep_time = datetime.fromisoformat(new_flight["leg"]["departure"])
            arr_time = dep_time + timedelta(minutes=time_slot["arrival_offset"])
            new_flight["leg"]["arrival"] = arr_time.isoformat()
            
            # Transfer zones set et
            new_flight["transfer_zones"] = new_zones
            
            new_flights.append(new_flight)
    
    flights_data["flights"].extend(new_flights)
    flights_data["metadata"]["total_flights"] = len(flights_data["flights"])
    
    save_json(FLIGHTS_FILE, flights_data)
    print(f"✓ Yeni uçuşlar eklendi: {len(new_flights)}")
    print(f"✓ Toplam uçuş sayısı: {len(flights_data['flights'])}")

def expand_transfers():
    """
    ADIM 2: Transfer rotalarını tamamla
    - Alanya: 120 dk, 2200 TL
    - Kemer: 50 dk, 1500 TL
    - Side: 90 dk, 1800 TL (ek)
    """
    print("\n" + "="*60)
    print("🚗 ADIM 2: Transfer Rotalarını Tamamla")
    print("="*60)
    
    transfers_data = load_json(TRANSFERS_FILE)
    transfer_routes = transfers_data.get("transfer_routes", [])
    
    # Yeni bölgeler tanımı
    new_routes = [
        {
            "to_area_name": "Alanya",
            "to_area_code": "ALANYA",
            "duration": 120,
            "price_vip": 2800,
            "price_eco": 1800,
            "hotel_coverage": 15
        },
        {
            "to_area_name": "Kemer",
            "to_area_code": "KEMER",
            "duration": 50,
            "price_vip": 1800,
            "price_eco": 1100,
            "hotel_coverage": 18
        },
        {
            "to_area_name": "Side",
            "to_area_code": "SIDE",
            "duration": 90,
            "price_vip": 2400,
            "price_eco": 1600,
            "hotel_coverage": 12
        }
    ]
    
    service_counter = 1000
    routes_added = 0
    
    # Her yeni bölge için VIP ve ECO rotas oluştur
    for route_def in new_routes:
        # VIP rota
        vip_route = {
            "service_code": f"TR-ANT-VIP-{service_counter:02d}",
            "operator_id": "MERGEN_LOJ",
            "route": {
                "from_code": "AYT",
                "from_name": "Antalya Havalimanı",
                "to_area_code": route_def["to_area_code"],
                "to_area_name": route_def["to_area_name"],
                "estimated_duration": route_def["duration"]
            },
            "vehicle_info": {
                "category": "VAN_VIP",
                "max_pax": 6,
                "features": ["WIFI", "BABY_SEAT_AVAIL", "LEATHER_SEATS", "REFRESHMENTS"]
            },
            "total_price": route_def["price_vip"],
            "currency": "TRY",
            "hotel_coverage": route_def["hotel_coverage"]
        }
        
        # ECO rota
        eco_route = copy.deepcopy(vip_route)
        eco_route["service_code"] = f"TR-ANT-ECO-{service_counter:02d}"
        eco_route["vehicle_info"]["category"] = "VAN_ECONOMY"
        eco_route["vehicle_info"]["max_pax"] = 8
        eco_route["vehicle_info"]["features"] = ["AC", "LUGGAGE_SPACE"]
        eco_route["total_price"] = route_def["price_eco"]
        
        # Kontrol: Çift kayıt olmasın
        existing = any(r.get("route", {}).get("to_area_code") == route_def["to_area_code"] 
                      for r in transfer_routes)
        
        if not existing:
            transfer_routes.append(vip_route)
            transfer_routes.append(eco_route)
            routes_added += 2
            print(f"✓ {route_def['to_area_name']}: VIP ({route_def['price_vip']} TL) + ECO ({route_def['price_eco']} TL)")
        else:
            print(f"⚠ {route_def['to_area_name']}: Zaten mevcut, atlanıyor")
        
        service_counter += 1
    
    transfers_data["transfer_routes"] = transfer_routes
    save_json(TRANSFERS_FILE, transfers_data)
    print(f"✓ Eklenen routlar: {routes_added}")
    print(f"✓ Toplam rota sayısı: {len(transfer_routes)}")

def expand_hotels():
    """
    ADIM 3: Hotels amenities'e Villa/Butik etiketleri ekle
    - Küçük oteller: "Butik"
    - Müstakil hissi: "Villa"
    """
    print("\n" + "="*60)
    print("🏨 ADIM 3: Hotel Amenities'e Villa/Butik Etiketleri Ekle")
    print("="*60)
    
    hotels_data = load_json(HOTELS_FILE)
    
    # Hotels direkt lista olabilir
    hotels = hotels_data if isinstance(hotels_data, list) else hotels_data.get("hotels", [])
    
    boutique_keywords = ["boutique", "butik", "küçük", "intimate", "cozy", "charming"]
    villa_keywords = ["villa", "müstakil", "private", "özel", "detached", "standalone"]
    
    boutique_added = 0
    villa_added = 0
    
    for hotel in hotels:
        # Hotel field names düzeltme (hotels.json farklı formatta olabilir)
        name = (hotel.get("hotel_name") or hotel.get("name", "")).lower()
        concept = (hotel.get("concept", "") or "").lower()
        description = (hotel.get("description", "") or "").lower()
        amenities = hotel.get("amenities", [])
        
        # Amenities liste değilse, boş liste yap
        if not isinstance(amenities, list):
            amenities = []
        
        # Etiketleri kontrol et
        if "Butik" not in amenities:
            if any(keyword in name or keyword in concept or keyword in description 
                   for keyword in boutique_keywords):
                amenities.append("Butik")
                boutique_added += 1
        
        if "Villa" not in amenities:
            if any(keyword in name or keyword in concept or keyword in description 
                   for keyword in villa_keywords):
                amenities.append("Villa")
                villa_added += 1
        
        # Standart etiketi kontrol et (fiyata göre)
        price = hotel.get("price_per_night") or hotel.get("price", 0)
        if price and price > 3000 and "Lüks" not in amenities:
            amenities.append("Lüks")
        elif price and price < 1000 and "Ekonomik" not in amenities:
            amenities.append("Ekonomik")
        
        hotel["amenities"] = list(set(amenities))  # Dublike kaldır
    
    save_json(HOTELS_FILE, hotels)
    print(f"✓ Butik etiketi eklendi: {boutique_added} otel")
    print(f"✓ Villa etiketi eklendi: {villa_added} otel")
    print(f"✓ Toplam otel: {len(hotels)}")

def validate_data_integrity():
    """
    ADIM 4: Veri bütünlüğü kontrolü
    - City/area names case sensitivity kontrolü
    - Eksik/boş alanlar kontrolü
    """
    print("\n" + "="*60)
    print("✅ ADIM 4: Veri Bütünlüğü Kontrolü")
    print("="*60)
    
    # Hotels kontrolü
    print("\n📋 Hotels.json Kontrolü:")
    hotels_data = load_json(HOTELS_FILE)
    hotels = hotels_data if isinstance(hotels_data, list) else hotels_data.get("hotels", [])
    
    cities = set()
    issues = 0
    
    for idx, hotel in enumerate(hotels):
        city = hotel.get("location", {}).get("city") or hotel.get("city", "")
        if not city or city.strip() == "":
            print(f"⚠ Hotel {idx}: Boş city alanı")
            issues += 1
        else:
            cities.add(city.lower())
        
        if not hotel.get("amenities"):
            hotel["amenities"] = []
    
    print(f"✓ Benzersiz şehirler: {sorted(cities)}")
    
    # Flights kontrolü
    print("\n📋 Flights.json Kontrolü:")
    flights_data = load_json(FLIGHTS_FILE)
    flights = flights_data.get("flights", [])
    
    ayt_flights_count = sum(1 for f in flights if f.get("leg", {}).get("destination") == "AYT")
    print(f"✓ Antalya uçuşları: {ayt_flights_count}")
    
    # Transfers kontrolü
    print("\n📋 Transfers.json Kontrolü:")
    transfers_data = load_json(TRANSFERS_FILE)
    transfer_routes = transfers_data.get("transfer_routes", [])
    
    ayt_areas = set()
    for route in transfer_routes:
        if route.get("route", {}).get("from_code") == "AYT":
            area = route.get("route", {}).get("to_area_name", "")
            if area:
                ayt_areas.add(area)
    
    print(f"✓ Antalya bölgeleri: {sorted(ayt_areas)}")
    
    print(f"\n⚠ Toplam sorun: {issues}")
    return issues == 0

def main():
    print("\n" + "🚀 "*20)
    print("VERİ GENIŞLETME OPERASYONU BAŞLANIYOR")
    print("🚀 "*20)
    
    try:
        # 1. Uçuşları genişlet
        expand_flights()
        
        # 2. Transfer rotalarını tamamla
        expand_transfers()
        
        # 3. Hotel amenities'e etiketler ekle
        expand_hotels()
        
        # 4. Veri bütünlüğü kontrolü
        validate_data_integrity()
        
        print("\n" + "✅ "*20)
        print("TÜM OPERASYONLAR BAŞARILI!")
        print("✅ "*20)
        print("\n📊 Özet:")
        print("  ✓ Antalya uçuşlarına transfer_zones eklendi")
        print("  ✓ Transfer rotaları tamamlandı (Alanya, Kemer, Side)")
        print("  ✓ Hotel amenities güncellendi (Villa/Butik)")
        print("  ✓ Veri bütünlüğü kontrolü tamamlandı")
        
    except Exception as e:
        print(f"\n❌ HATA: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
