demo/
├── pyproject.toml              # UV dependency management
├── uv.lock                     # Lock file
├── requirements.txt            # Pip-compatible requirements
│
├── src/
│   ├── data_generation/
│   │   ├── __init__.py
│   │   ├── scraper.py          
│   │   ├── synthetic_generator.py  
│   │   ├── data_validator.py   
│   │   └── seeds/
│   │       └── real_hotels.json
│   │
│   ├── model/
│   │   ├── __init__.py
│   │   ├── embeddings.py       
│   │   ├── vector_store.py     
│   │   ├── search_engine.py    
│   │   └── llm_wrapper.py      
│   │
│   └── streamlit_app.py        
│
├── data/
│   ├── hotels.json             
│   ├── flights.json            
│   ├── transfers.json          
│   └── chroma_db/              (Sunucuda otomatik oluşturulur)
│
├── .env.example
├── .streamlit/config.toml
└── README.md

## 🚀 Streamlit Cloud'da Yayınlama

### Ön Koşullar
- GitHub hesabı (repo bu hesapda olmalı)
- Streamlit Cloud hesabı (https://streamlit.io/cloud)
- GROQ_API_KEY (https://console.groq.com)

### Adımlar

1. **GitHub'a Push Et**
   ```bash
   git add .
   git commit -m "Deploy to Streamlit Cloud"
   git push origin main
   ```

2. **Streamlit Cloud'da Deploy Et**
   - https://share.streamlit.io adresine git
   - "New app" → "GitHub repo seç"
   - Repository: `mergenx_demo`
   - Branch: `main`
   - Main file path: `src/streamlit_app.py`

3. **Secrets Ayarla** (Streamlit Cloud dashboard'da)
   ```
   GROQ_API_KEY=your_groq_api_key_here
   ```

### 🔄 Otomatik DB Kurulumu
- İlk kez başlattığında, `data/hotels.json` dosyasından vektör veritabanı otomatik oluşturulur
- `st.spinner` ile "🏨 Vektör veritabanı oluşturuluyor..." mesajı gösterilir
- Bu işlem ilk sefer ~2-3 dakika alabilir
- Sonraki sefer hızlı başlar (veritabanı cached)

### 📦 Bağımlılıklar
- Streamlit Cloud `pyproject.toml` ve `requirements.txt` dosyalarını destekler
- `sentence-transformers`, `chromadb`, `groq` gibi heavy packages otomatik kurulur

# Setup (Lokal Geliştirme):

uv venv
uv pip install -e .
uv run python src/data_generation/synthetic_generator.py
uv run streamlit run src/streamlit_app.py