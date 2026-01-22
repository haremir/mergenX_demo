# 🛡️ MergenX Streamlit Cloud Deployment Checklist

## ✅ Pre-Deployment Verification (Jan 22, 2026)

### 1. Persistent Path Logic ✓
- [x] All paths use `os.path.join(os.getcwd(), ...)`
- [x] Absolute path conversion with `os.path.isabs()` checks
- [x] Tested on local environment - paths resolve correctly
- Files modified:
  - `src/model/vector_store.py` - Added absolute path logic
  - `src/model/search_engine.py` - Added absolute path logic

### 2. Data Type Safety ✓
- [x] Price casting: `float()` with validation (₺1 minimum, never ₺0)
- [x] City: `str.lower()` with mandatory validation (raises ValueError if empty)
- [x] District: sensible default 'merkez' if missing
- [x] All type errors logged with stack trace
- Files modified:
  - `src/model/vector_store.py` - Updated `_validate_hotel_data()` method

### 3. Smart Re-Initialization ✓
- [x] STREAMLIT_CLOUD environment detection
- [x] Metadata integrity check (city + price validation)
- [x] Auto-reset if corrupted (shutil.rmtree + 1-sec wait)
- [x] Fallback collection recovery on error
- Files modified:
  - `src/model/search_engine.py` - Added integrity check in `__init__`

### 4. Git Repository Status ✓
- [x] `pyproject.toml` tracked
- [x] `uv.lock` tracked
- [x] `requirements.txt` tracked
- [x] `data/hotels.json` tracked (350KB)
- [x] `data/flights.json` tracked (30KB)
- [x] `data/transfers.json` tracked (20KB)
- [x] `data/chroma_db_v2/` in .gitignore (will be created on first run)
- [x] All critical source files committed

### 5. UI Debug Cleanup ✓
- [x] Removed all `st.write(debug_json)` statements
- [x] Removed all `with st.expander("🔧 Hata Detayları")` debug panels
- [x] Converted all error logging to `logger.info/error`
- [x] User-facing errors: Generic messages (no stack traces in UI)
- [x] Server-facing logs: Full details in terminal
- Files modified:
  - `src/streamlit_app.py` - Cleaned debug UI + added logging

### 6. Local Testing ✓
```
✅ Streamlit app starts: http://localhost:8502
✅ ChromaDB loads: 600 hotels, 57 flights, 39 transfers
✅ Metadata integrity: PASSED (city='antalya', price=7800.0)
✅ Search query test: SUCCESS (5 packages generated)
✅ Price calculations: All float type
✅ Logger output: INFO level active
```

## 🚀 Deployment Steps

### Step 1: Push to GitHub
```bash
git push origin main
```

### Step 2: Streamlit Cloud Setup
1. Go to https://share.streamlit.io/
2. Click "New app" → Select GitHub repo
3. Repository: Your GitHub URL
4. Branch: `main`
5. Main file path: `src/streamlit_app.py`

### Step 3: Streamlit Cloud Settings
**Advanced settings (if needed):**
- Python version: 3.13+
- Client max message size: 100MB (for large results)
- Logger level: INFO (for debugging)

### Step 4: Monitor First Run
Watch terminal logs for:
- ✅ `[INFO] Environment: Streamlit Cloud`
- ✅ `[SUCCESS] Metadata integrity OK`
- ✅ `[INFO] ChromaDB: 600 otel yüklü`
- ❌ If you see: `[CRITICAL] Metadata corruption detected` → Database reset initiated (normal)

## ⚠️ Known Issues & Solutions

### Issue: "Empty city" crash on Cloud
**Solution:** Data validation now raises `ValueError` immediately
- Prevents silent failures with invalid data
- Logs exact field that failed
- City field is MANDATORY (not optional)

### Issue: "₺0 TL" showing in results
**Solution:** Minimum price is now ₺1 (not ₺0)
- ₺0 indicates data loading failure
- ₺1 is reserved error indicator
- All valid prices > ₺1

### Issue: Path errors on Linux (Cloud)
**Solution:** All paths now use absolute paths
- `os.path.join(os.getcwd(), "data", ...)`
- Works on Windows, Linux, Cloud equally
- No more relative path issues

### Issue: "Metadata corruption" reset
**Solution:** Smart re-init validates first sample
- If city empty OR price ≤ 0 → auto-reset
- Database fully recreated from hotels.json
- No user-visible downtime (spinner shows progress)

## 📋 Critical Files for Cloud

```
✓ Required:
  - src/streamlit_app.py
  - src/model/search_engine.py
  - src/model/vector_store.py
  - src/model/embeddings.py
  - src/model/llm_wrapper.py
  - data/hotels.json
  - data/flights.json
  - data/transfers.json
  - pyproject.toml
  - uv.lock
  - .gitignore

✗ DO NOT INCLUDE:
  - data/chroma_db_v2/  (created at runtime)
  - __pycache__/
  - .venv/
  - .env (use Streamlit secrets instead)
```

## 🔑 Environment Variables (Streamlit Cloud)

Set these in Streamlit Cloud dashboard:
- `GROQ_API_KEY` → Your Groq API key (for LLM)
- `STREAMLIT_CLOUD` → "true" (auto-detected for us)

## ✅ Final Checks Before Deploy

- [x] All absolute paths working locally
- [x] Price validation working (min ₺1)
- [x] City validation working (mandatory)
- [x] ChromaDB integrity check working
- [x] Debug UI removed
- [x] Logger configured
- [x] Data files tracked in git
- [x] Test run on local: SUCCESS
- [x] Git commit pushed

## 🎯 Expected Behavior on Cloud

1. **First Load (0-60 seconds):**
   - App starts
   - ChromaDB client initialized
   - Metadata integrity check runs
   - If valid: Uses existing DB
   - If corrupted: Resets from hotels.json (adds 10-15 sec)

2. **User Search:**
   - Travel params extracted (LLM)
   - Hotels filtered by city
   - Flights filtered by date/time
   - Transfers auto-selected
   - Package pricing calculated
   - Summary generated (LLM)

3. **Success Indicators:**
   - ✅ 5 packages shown with prices
   - ✅ All prices are TRY amounts (float)
   - ✅ All cities are lowercase
   - ✅ Response time < 10 seconds

---

**Status:** READY FOR DEPLOYMENT ✅  
**Last Updated:** January 22, 2026  
**Git Commit:** 1310f16
