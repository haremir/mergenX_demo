import json

# Dosyayı oku
with open(r'c:\Users\PC\Desktop\mergenX_demo\data\hotels.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Toplam otel: {len(data)}\n")

# İstatistikler
stats = {
    'price_per_night_eksik': 0,
    'price_varken_price_per_night_yok': 0,
    'ikisi_de_eksik': 0,
    'location_city_eksik': 0,
    'location_district_eksik': 0,
    'location_eksik': 0,
}

# Problemli kayıtları bul
problematic = []

for idx, hotel in enumerate(data):
    issues = []
    
    # Price kontrolü
    if 'price_per_night' not in hotel:
        if 'price' in hotel:
            stats['price_varken_price_per_night_yok'] += 1
            issues.append(f"'price' var ama 'price_per_night' yok (değer: {hotel.get('price')})")
        else:
            stats['ikisi_de_eksik'] += 1
            issues.append("'price_per_night' ve 'price' her ikisi de eksik")
    
    # Location kontrolü
    if 'location' not in hotel:
        stats['location_eksik'] += 1
        issues.append("'location' objesi eksik")
    else:
        location = hotel['location']
        if 'city' not in location:
            stats['location_city_eksik'] += 1
            issues.append("'location.city' eksik")
        if 'district' not in location:
            stats['location_district_eksik'] += 1
            issues.append("'location.district' eksik")
    
    if issues:
        problematic.append({
            'index': idx,
            'hotel_name': hotel.get('hotel_name', 'N/A'),
            'issues': issues
        })

# Sonuçları göster
print("=" * 60)
print("PROBLEMLER:")
print("=" * 60)
for key, count in stats.items():
    if count > 0:
        print(f"  {key}: {count}")

if problematic:
    print(f"\nDetaylar ({len(problematic)} otel):")
    for item in problematic[:10]:  # İlk 10'u göster
        print(f"\n  [{item['index']}] {item['hotel_name']}")
        for issue in item['issues']:
            print(f"      - {issue}")
    if len(problematic) > 10:
        print(f"\n  ... ve {len(problematic) - 10} otel daha")
else:
    print("\n✓ Hiç problem bulunamadı!")

print("\n" + "=" * 60)

