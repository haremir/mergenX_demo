#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import os

def fix_json_file(filepath):
    """
    Dosyayı binary olarak oku, JSON parse et, UTF-8 (BOM yok) olarak kaydet
    """
    filename = os.path.basename(filepath)
    print(f"\nProcessing: {filename}")
    print("-" * 50)
    
    try:
        # 1. Binary olarak oku
        with open(filepath, 'rb') as f:
            raw_bytes = f.read()
        print(f"[1] Read {len(raw_bytes)} bytes")
        
        # 2. UTF-8 decode (BOM varsa otomatik kaldırılır)
        if raw_bytes.startswith(b'\xef\xbb\xbf'):
            print("[2] BOM detected and removing...")
            content = raw_bytes[3:].decode('utf-8')
        else:
            content = raw_bytes.decode('utf-8')
        print(f"[2] Decoded to {len(content)} characters")
        
        # 3. Boşlukları temizle
        content = content.strip()
        print(f"[3] Whitespace trimmed")
        
        # 4. JSON parse et
        data = json.loads(content)
        print(f"[4] JSON parsed successfully")
        if isinstance(data, (list, dict)):
            print(f"    Type: {type(data).__name__}, Size: {len(data)}")
        
        # 5. UTF-8 (BOM yok) formatında kaydet
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[5] Saved as UTF-8 (no BOM)")
        
        # 6. Doğrula
        with open(filepath, 'r', encoding='utf-8') as f:
            verify = json.load(f)
        print(f"[6] Verification OK: {len(verify)} items/keys")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON Parse Error: {e}")
        return False
    except UnicodeDecodeError as e:
        print(f"[ERROR] Encoding Error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return False

# Main
print("="*50)
print("JSON File Encoding Fixer")
print("="*50)

files_to_fix = [
    "data/flights.json",
    "data/transfers.json"
]

results = {}
for filepath in files_to_fix:
    if os.path.exists(filepath):
        results[filepath] = fix_json_file(filepath)
    else:
        print(f"\nWARNING: {filepath} not found")
        results[filepath] = False

# Report
print("\n" + "="*50)
print("Summary")
print("="*50)
for filepath, success in results.items():
    status = "OK" if success else "FAILED"
    print(f"{os.path.basename(filepath)}: {status}")

if all(results.values()):
    print("\n[SUCCESS] All files processed!")
else:
    print("\n[ERROR] Some files failed!")
