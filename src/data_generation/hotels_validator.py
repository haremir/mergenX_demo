import json

try:
    with open(r'c:\Users\PC\Desktop\mergenX_demo\data\hotels.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f'✓ Dosya başarıyla yüklendi')
    print(f'✓ Toplam otel sayısı: {len(data)}')
    print(f'✓ İlk otel: {data[0]["hotel_name"]}')
    print(f'✓ Son otel: {data[-1]["hotel_name"]}')
    
    # Şehir bazında otel sayısını kontrol et
    cities = {}
    for hotel in data:
        city = hotel.get('location', {}).get('city', 'Bilinmiyor')
        cities[city] = cities.get(city, 0) + 1
    
    print('\nŞehir bazında otel sayısı:')
    for city, count in sorted(cities.items()):
        print(f'  {city}: {count} otel')
        
except json.JSONDecodeError as e:
    print(f'✗ JSON Parse Hatası!')
    print(f'  Satır: {e.lineno}, Kolon: {e.colno}')
    print(f'  Hata: {e.msg}')
except Exception as e:
    print(f'✗ Hata: {e}')
