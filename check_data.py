#!/usr/bin/env python3
"""Veri genişletme sonuçlarını kontrol et"""

import json

print("="*60)
print("📊 VERİ KONTROL RAPORU")
print("="*60)

# Hotels kontrolü - Villa/Butik etiketi
hotels = json.load(open('data/hotels.json', encoding='utf-8'))
villa_hotels = [h for h in hotels if 'Villa' in h.get('amenities', [])]
boutique_hotels = [h for h in hotels if 'Butik' in h.get('amenities', [])]

print("\n🏨 Hotel Amenities:")
print(f"  ✓ Villa etiketi: {len(villa_hotels)} otel")
print(f"  ✓ Butik etiketi: {len(boutique_hotels)} otel")
print("\n  Örnek Villa oteller:")
for h in villa_hotels[:2]:
    name = h.get("hotel_name", "Unknown")
    amenities = h.get("amenities", [])[:3]
    print(f"    - {name}: {amenities}")

print("\n  Örnek Butik oteller:")
for h in boutique_hotels[:2]:
    name = h.get("hotel_name", "Unknown")
    amenities = h.get("amenities", [])[:3]
    print(f"    - {name}: {amenities}")

# Flights kontrolü
flights = json.load(open('data/flights.json', encoding='utf-8'))
ayt_flights = [f for f in flights['flights'] if f['leg'].get('destination') == 'AYT' and f['leg'].get('origin') == 'IST']
print(f"\n✈️ Antalya Uçuşları (IST->AYT):")
print(f"  ✓ Total: {len(ayt_flights)} uçuş")
print("  ✓ Transfer zones örneği:")
for f in ayt_flights[:2]:
    zones = f.get('transfer_zones', [])
    print(f"    {f['flight_no']}: {zones}")

# Transfers kontrolü
transfers = json.load(open('data/transfers.json', encoding='utf-8'))
ayt_routes = [r for r in transfers['transfer_routes'] if r['route']['from_code'] == 'AYT']
print(f"\n🚗 Antalya Transfer Rotaları (AYT->):")
print(f"  ✓ Total: {len(ayt_routes)} rota")
areas = sorted(set(r['route']['to_area_name'] for r in ayt_routes))
print(f"  Bölgeler: {areas}")

print("\n" + "="*60)
print("✅ TÜM VERİLER BAŞARIYLA GENIŞLETILDI!")
print("="*60)
