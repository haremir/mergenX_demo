import json

# Dosyayı oku
with open(r'c:\Users\PC\Desktop\mergenX_demo\data\hotels.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Şehir bazında otel sayısını hesapla
cities = {}
for hotel in data:
    city = hotel.get('location', {}).get('city', 'Bilinmiyor')
    cities[city] = cities.get(city, 0) + 1

# Sonuçları göster
print("=" * 50)
print("ŞEHİR BAZINDA OTEL SAYISI")
print("=" * 50)
total = 0
for city in sorted(cities.keys()):
    count = cities[city]
    total += count
    percentage = (count / len(data)) * 100
    print(f"{city:.<30} {count:>3} otel ({percentage:>5.1f}%)")

print("=" * 50)
print(f"{'TOPLAM':.<30} {total:>3} otel")
print("=" * 50)
