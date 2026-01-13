import json

# Dosyayı oku
with open(r'c:\Users\PC\Desktop\mergenX_demo\data\hotels.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"DOĞRULAMA RAPORU")
print("=" * 60)
print(f"Toplam otel: {len(data)}")

# Tüm oteller kontrol et
price_ok = 0
location_ok = 0
all_ok = 0

for idx, hotel in enumerate(data):
    price_valid = 'price_per_night' in hotel and isinstance(hotel['price_per_night'], (int, float))
    location_valid = (
        'location' in hotel and
        isinstance(hotel['location'], dict) and
        'city' in hotel['location'] and
        'district' in hotel['location']
    )
    
    if price_valid:
        price_ok += 1
    if location_valid:
        location_ok += 1
    if price_valid and location_valid:
        all_ok += 1

print(f"\n✓ 'price_per_night' geçerli: {price_ok}/{len(data)}")
print(f"✓ 'location' geçerli: {location_ok}/{len(data)}")
print(f"✓ Her ikisi geçerli: {all_ok}/{len(data)}")

if all_ok == len(data):
    print("\n✅ TÜM KAYITLAR BAŞARILI!")
else:
    print(f"\n⚠️  {len(data) - all_ok} kayıtta sorun var")

# Varsayılan değer alan otelleri göster
print("\n" + "=" * 60)
print("Varsayılan price_per_night (5000) alan oteller:")
print("=" * 60)
default_price_hotels = [h for h in data if h.get('price_per_night') == 5000]
print(f"Toplam: {len(default_price_hotels)}")
for hotel in default_price_hotels:
    print(f"  - {hotel.get('hotel_name', 'N/A')} ({hotel['location'].get('city', 'N/A')})")

# JSON doğruluğu kontrol et
try:
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    json.loads(json_str)
    print("\n✓ JSON formatı geçerli")
except json.JSONDecodeError as e:
    print(f"\n✗ JSON hatası: {e}")

