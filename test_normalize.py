#!/usr/bin/env python
# Test normalization function

def normalize_city_name(city: str) -> str:
    """
    Türkçe karakterleri normalize et ve karşılaştırma için hazırla.
    """
    if not city:
        return ""
    # Step 1: Replace Turkish uppercase special characters FIRST
    city = city.replace('İ', 'i')
    city = city.replace('Ç', 'c')
    city = city.replace('Ğ', 'g')
    city = city.replace('Ş', 's')
    city = city.replace('Ü', 'u')
    city = city.replace('Ö', 'o')
    # Step 2: Convert to lowercase (handles remaining uppercase)
    city = city.lower()
    # Step 3: Replace any remaining Turkish lowercase characters
    city = city.replace('ç', 'c')
    city = city.replace('ğ', 'g')
    city = city.replace('ş', 's')
    city = city.replace('ü', 'u')
    city = city.replace('ö', 'o')
    # Step 4: Strip whitespace
    return city.strip()

# Test cases
test_cases = [
    'İzmir',
    'IZMIR',
    'izmir',
    'iZmİr',
    'İSTANBUL',
    'istanbul',
    'ISTANBUL',
    'ANKARA',
    'Ankara',
    'ÇANKIRI',
    'çankırı',
    'Çankırı'
]

print("Normalization test results:")
print("-" * 40)
for city in test_cases:
    normalized = normalize_city_name(city)
    print(f"{city:15} -> {normalized}")

print("\n\nMatching test for İzmir variants:")
print("-" * 40)
target = normalize_city_name('İzmir')
print(f"Target: '{target}'")
for variant in ['İzmir', 'IZMIR', 'izmir', 'iZmİr']:
    norm = normalize_city_name(variant)
    match = (target == norm)
    print(f"{variant:15} -> '{norm:10}' | Exact match: {match}")
    print(f"                   Partial: {target in norm or norm in target}")

print("\n\nTest database city matching:")
print("-" * 40)
# Simulate database values
db_cities = ['izmir', 'Izmir', 'IZMIR', 'istanbul', 'ankara']
search_city = 'İzmir'
normalized_search = normalize_city_name(search_city)
print(f"Search city: '{search_city}' -> '{normalized_search}'")
for db_city in db_cities:
    normalized_db = normalize_city_name(db_city)
    match = normalized_search in normalized_db or normalized_db in normalized_search
    print(f"DB city: '{db_city:15}' -> '{normalized_db:15}' | Match: {match}")
