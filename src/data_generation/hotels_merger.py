import json
import re

# Dosyayı oku
with open(r'c:\Users\PC\Desktop\mergenX_demo\data\hotels.json', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Tüm JSON yapılarını çıkar
all_hotels = []

# 1. İlk array'i çıkar [...]
first_array_match = re.match(r'^\s*\[(.*?)\]\s*', content, re.DOTALL)
if first_array_match:
    try:
        first_data = json.loads(f"[{first_array_match.group(1)}]")
        all_hotels.extend(first_data)
        print(f"1. Array: {len(first_data)} otel ✓")
    except:
        print("1. Array: Parse hatası ✗")

# 2. Tüm {"hotels": [...]} yapılarını çıkar
pattern = r'\{\s*"hotels"\s*:\s*\[(.*?)\]\s*\}'
matches = re.findall(pattern, content, re.DOTALL)
print(f"\nToplam {len(matches)} 'hotels' yapısı bulundu")

for idx, match in enumerate(matches):
    try:
        hotels_data = json.loads(f"[{match}]")
        all_hotels.extend(hotels_data)
        print(f"  Yapı {idx+1}: {len(hotels_data)} otel ✓")
    except json.JSONDecodeError as e:
        print(f"  Yapı {idx+1}: Parse hatası ✗")

print(f"\n{'='*50}")
print(f"TOPLAM: {len(all_hotels)} otel")

# Şehir bazında kontrol
cities = {}
for hotel in all_hotels:
    city = hotel.get('location', {}).get('city', 'Bilinmiyor')
    cities[city] = cities.get(city, 0) + 1

print(f"\nŞehir bazında dağılım:")
for city in sorted(cities.keys()):
    print(f"  {city}: {cities[city]} otel")

# Dosyaya yaz
if all_hotels:
    with open(r'c:\Users\PC\Desktop\mergenX_demo\data\hotels.json', 'w', encoding='utf-8') as f:
        json.dump(all_hotels, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Dosya başarıyla düzeltildi!")
    print(f"  {len(all_hotels)} adet otel tek bir JSON array'e yazıldı")
else:
    print("\n✗ Otel bulunamadı!")

