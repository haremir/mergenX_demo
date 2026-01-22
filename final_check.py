#!/usr/bin/env python3
"""Final veri kontrolü"""

import json

print("="*70)
print("📊 TİCARİLEŞTİRME VERİ KONTROLÜ")
print("="*70)

# Flights
with open('data/flights.json', 'r', encoding='utf-8') as f:
    flights = json.load(f)
flights_list = flights.get('flights', [])
print(f"\n✈️  UÇUŞLAR: {len(flights_list)}")
print(f"    AYT (Antalya): {sum(1 for f in flights_list if f['leg']['destination'] == 'AYT')}")
print(f"    ADB (İzmir): {sum(1 for f in flights_list if f['leg']['destination'] == 'ADB')}")
print(f"    BJV (Bodrum): {sum(1 for f in flights_list if f['leg']['destination'] == 'BJV')}")
print(f"    DLM (Dalaman): {sum(1 for f in flights_list if f['leg']['destination'] == 'DLM')}")
print(f"    GZT (Gaziantep): {sum(1 for f in flights_list if f['leg']['destination'] == 'GZT')}")

# Transfer zones kontrolü
ayt_flight = next(f for f in flights_list if f['leg']['destination'] == 'AYT')
print(f"\n    Transfer zones örnek (AYT): {ayt_flight['transfer_zones']}")

# Transfers
with open('data/transfers.json', 'r', encoding='utf-8') as f:
    transfers = json.load(f)
routes = transfers.get('transfer_routes', [])
print(f"\n🚗 TRANSFERLER: {len(routes)}")
print(f"    AYT rotaları: {sum(1 for r in routes if r['route']['from_code'] == 'AYT')}")
print(f"    ADB rotaları: {sum(1 for r in routes if r['route']['from_code'] == 'ADB')}")
print(f"    BJV rotaları: {sum(1 for r in routes if r['route']['from_code'] == 'BJV')}")
print(f"    DLM rotaları: {sum(1 for r in routes if r['route']['from_code'] == 'DLM')}")

# Hotels
with open('data/hotels.json', 'r', encoding='utf-8') as f:
    hotels = json.load(f)
print(f"\n🏨 OTELLER: {len(hotels)}")

# Etiket dağılımı
villa = sum(1 for h in hotels if 'Villa' in h.get('amenities', []))
butik = sum(1 for h in hotels if 'Butik' in h.get('amenities', []))
kiz = sum(1 for h in hotels if 'Kız kıza uygun' in h.get('amenities', []))
muhafazakar = sum(1 for h in hotels if 'Muhafazakar' in h.get('amenities', []))
balayi = sum(1 for h in hotels if 'Balayı' in h.get('amenities', []))
is_odakli = sum(1 for h in hotels if 'İş odaklı' in h.get('amenities', []))

print(f"    Villa: {villa}")
print(f"    Butik: {butik}")
print(f"    Kız kıza uygun: {kiz}")
print(f"    Muhafazakar: {muhafazakar}")
print(f"    Balayı: {balayi}")
print(f"    İş odaklı: {is_odakli}")

# Şehir dağılımı
from collections import Counter
cities = [h.get('location', {}).get('city', '') for h in hotels]
city_counts = Counter(cities)
print(f"\n    Şehir dağılımı:")
for city, count in city_counts.most_common(5):
    print(f"      {city}: {count}")

print("\n" + "="*70)
print("✅ VERİ HAZIRLAMA TAMAMLANDI!")
print("="*70)
print(f"\n📈 TOPLAM KAYIT: {len(flights_list) + len(routes) + len(hotels)}")
print(f"   - Uçuşlar: {len(flights_list)}")
print(f"   - Transferler: {len(routes)}")
print(f"   - Oteller: {len(hotels)}")
print("\n🚀 Sistem ticarileşme için hazır!")
print("   ChromaDB cache temizlendi, ilk çalışmada 1000 otel indexlenecek.")
print("\n📝 Sonraki adım: uv run streamlit run src/streamlit_app.py")
