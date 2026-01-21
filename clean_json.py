import json
import os

# Dosya yolları
flights_file = "data/flights.json"
transfers_file = "data/transfers.json"

def clean_and_validate_json(file_path):
    """
    JSON dosyasını temizler ve UTF-8 formatında (BOM yok) kaydeder
    """
    print("\n" + "="*60)
    print(f"Processing: {file_path}")
    print("="*60)
    
    try:
        # Dosyayı oku (UTF-8-SIG ile BOM'u otomatik kaldır)
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            raw_content = f.read()
        
        print(f"[OK] File read (size: {len(raw_content)} bytes)")
        
        # Başındaki/sonundaki boşlukları temizle
        cleaned = raw_content.strip()
        print(f"[OK] Whitespace removed")
        
        # JSON'u parse et (geçerliliği kontrol et)
        data = json.loads(cleaned)
        print(f"[OK] JSON is valid!")
        
        # Sayı kontrol et
        if isinstance(data, list):
            print(f"     -> Array with {len(data)} records")
        elif isinstance(data, dict):
            print(f"     -> Object with {len(data)} keys")
        
        # UTF-8 (BOM yok) formatında kaydet
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"[OK] Saved as UTF-8 (no BOM)")
        
        # Doğrula
        with open(file_path, 'r', encoding='utf-8') as f:
            verify_data = json.load(f)
        
        print(f"[OK] Verification passed: {len(verify_data) if isinstance(verify_data, list) else len(verify_data)} records")
        return True
        
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON Error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        return False

# Her iki dosyayı temizle
print("\n" + "="*60)
print("JSON Cleaning Operation Started")
print("="*60)

flights_ok = clean_and_validate_json(flights_file)
transfers_ok = clean_and_validate_json(transfers_file)

# Sonuç
print("\n" + "="*60)
print("Result Report")
print("="*60)
print(f"flights.json:   {'OK' if flights_ok else 'FAILED'}")
print(f"transfers.json: {'OK' if transfers_ok else 'FAILED'}")

if flights_ok and transfers_ok:
    print("\n[SUCCESS] All files cleaned successfully!")
else:
    print("\n[ERROR] Some files had issues")
