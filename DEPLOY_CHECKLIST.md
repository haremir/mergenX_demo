# 📋 Streamlit Cloud Deploy Checklist

## ✅ Yapılan Hazırlıklar

### 1. **Otomatik DB Kurulumu**
- [x] `search_engine.py` içinde `_initialize_db_from_hotels_json()` fonksiyonu eklendi
- [x] ChromaDB koleksiyonu boşsa hotels.json'dan veritabanı otomatik oluşturulur
- [x] `st.spinner()` ile kullanıcıya bilgi verilir
- [x] Batch processing ile 50'lik gruplar halinde otel eklenir
- [x] Embedding vektörleri otomatik hesaplanır

### 2. **Dosya Yolu Güvenliği**
- [x] `os.path.join()` kullanarak OS-bağımsız dosya yolları
- [x] `flights.json` → `os.path.join("data", "flights.json")`
- [x] `transfers.json` → `os.path.join("data", "transfers.json")`
- [x] `chroma_db` → `os.path.join("data", "chroma_db")`
- [x] Relative paths kullanılarak sunucu uyumluluğu sağlandı

### 3. **Git Ignore Ayarları**
- [x] `data/hotels.json` takip edilir (GIT'te)
- [x] `data/flights.json` takip edilir (GIT'te)
- [x] `data/transfers.json` takip edilir (GIT'te)
- [x] `data/chroma_db/` ignore edilir (sunucuda oluşturulacak)
- [x] `.venv/` ignore edilir (sunucuya yüklenmeyecek)
- [x] `pyproject.toml` takip edilir (UV için)
- [x] `uv.lock` takip edilir (deterministic deployment)

### 4. **Bağımlılıklar**
- [x] `pyproject.toml` mevcut ve doğru yapılandırılmış
- [x] `requirements.txt` oluşturuldu (pip uyumluluğu için)
- [x] Tüm dependencies eklenmiş:
  - chromadb>=1.4.0
  - groq>=1.0.0
  - pandas>=2.3.3
  - pydantic>=2.12.5
  - python-dotenv>=1.2.1
  - sentence-transformers>=5.2.0
  - streamlit>=1.52.2

### 5. **Streamlit Konfigürasyonu**
- [x] `.streamlit/config.toml` oluşturuldu
- [x] Theme ayarları yapılandırıldı
- [x] Server security ayarları

### 6. **Environment Variables**
- [x] `.env.example` hazırlandı
- [x] `GROQ_API_KEY` tanımlandı
- [x] Streamlit Cloud Secrets'ta eklenecek

## 🚀 Deploy Adımları

### GitHub'a Push:
```bash
git add .
git commit -m "Prepare for Streamlit Cloud deployment"
git push origin main
```

### Streamlit Cloud'da:
1. https://share.streamlit.io adresine git
2. "New app" seç
3. GitHub repository seç: `mergenx_demo`
4. Branch: `main`
5. Main file: `src/streamlit_app.py`
6. "Deploy" tıkla

### Secret Variables:
Streamlit Cloud dashboard → App settings → Secrets
```toml
GROQ_API_KEY = "your_groq_api_key_here"
```

## ⚡ İlk Çalıştırmada Neler Olur

1. Streamlit uygulaması yüklenmeye başlar
2. ChromaDB koleksiyonu boş bulunur
3. `hotels.json` okunur (600 otel)
4. Vektör embeddings oluşturulur (parallel processing)
5. ChromaDB'ye batch olarak eklenir
6. Toplam ~2-3 dakika alır
7. Ardından kullanıcıya normal arayüz gösterilir

## 🔍 Sorun Giderme

**Problem**: "ModuleNotFoundError: No module named 'sentence_transformers'"
- Çözüm: Streamlit Cloud otomatik `requirements.txt` yükler, sabırlı olun

**Problem**: "ChromaDB cannot find collection"
- Çözüm: Otomatik kurulum başlanır, birkaç saniye bekleyin

**Problem**: "Hotels JSON not found"
- Çözüm: `data/hotels.json` GitHub'a pushlenmişse, Streamlit Cloud'da otomatik tanınır

**Problem**: "GROQ_API_KEY not set"
- Çözüm: Streamlit Cloud dashboard → Secrets tab'da ekleyin

## 📊 Performans Notları

- **İlk yükleme**: ~2-3 dakika (DB kurulumu)
- **Sonraki yüklemeler**: ~2-3 saniye (cached)
- **Vektör arama**: ~1-2 saniye (600 otel arasında)
- **LLM response**: ~3-5 saniye (Groq API)

## ✨ Başarılı Deployment Göstergeleri

- ✅ Uygulama açılırsa ve hata vermezse
- ✅ "Vektör veritabanı oluşturuluyor..." spinner gösterilir
- ✅ Spinner bittikten sonra arama yapılabilir
- ✅ İzmir araması sonuç döner
- ✅ Paket bilgisi (otel + uçuş + transfer) gösterilir
- ✅ Toplam fiyat hesaplanır ve gösterilir
