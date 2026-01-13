import json

# Dosyayı oku
with open(r'c:\Users\PC\Desktop\mergenX_demo\data\hotels.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Başlangıç: {len(data)} otel\n")

fixes = {
    'price_degistirildi': 0,
    'price_per_night_varsayilan_eklendi': 0,
    'location_olustuldu': 0,
    'location_city_eklendi': 0,
    'location_district_eklendi': 0,
}

# Tüm otelleri düzelt
for hotel in data:
    # 1. Price kontrolü ve düzeltmesi
    if 'price_per_night' not in hotel:
        if 'price' in hotel:
            # 'price' varsa bunu 'price_per_night'a çevir
            hotel['price_per_night'] = hotel['price']
            del hotel['price']
            fixes['price_degistirildi'] += 1
        else:
            # İkisi de yoksa varsayılan ekle
            hotel['price_per_night'] = 5000
            fixes['price_per_night_varsayilan_eklendi'] += 1
    
    # 2. Location kontrolü ve düzeltmesi
    if 'location' not in hotel:
        hotel['location'] = {}
        fixes['location_olustuldu'] += 1
    
    if 'city' not in hotel['location']:
        hotel['location']['city'] = 'Bilinmiyor'
        fixes['location_city_eklendi'] += 1
    
    if 'district' not in hotel['location']:
        hotel['location']['district'] = 'Bilinmiyor'
        fixes['location_district_eklendi'] += 1

# Dosyaya yaz
with open(r'c:\Users\PC\Desktop\mergenX_demo\data\hotels.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# Sonuçları göster
print("=" * 60)
print("DÜZELTMELER:")
print("=" * 60)
for fix, count in fixes.items():
    if count > 0:
        print(f"  {fix}: {count}")

total_fixes = sum(fixes.values())
if total_fixes == 0:
    print("  ✓ Hiç düzeltme gerekli değildi!")
else:
    print(f"\n  TOPLAM: {total_fixes} işlem yapıldı")

print("\n✓ Dosya başarıyla güncellendi!")
print("=" * 60)

