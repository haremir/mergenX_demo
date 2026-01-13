import streamlit as st
import time
import os
import sys
import re

# Proje kök dizinini Python yoluna ekle (Import hatalarını önlemek için)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from src.model.search_engine import MergenSearchEngine
except ImportError as e:
    st.error(f"Modül yükleme hatası: {e}. Lütfen src klasörünün ve içindeki __init__.py dosyalarının olduğundan emin olun.")
    st.stop()

# Sayfa Yapılandırması
st.set_page_config(
    page_title="MergenX - Akıllı Otel Arama Motoru",
    page_icon="🏨",
    layout="wide"
)

# Oturum Durumu Değişkenleri
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
if "search_results" not in st.session_state:
    st.session_state.search_results = None
if "search_time" not in st.session_state:
    st.session_state.search_time = 0

# Yardımcı Fonksiyonlar
def clean_description(text, hotel_name="", city="", concept=""):
    """
    Description'daki tekrar eden kelimeleri ve tesise özgü bilgileri temizler.
    Sadece tesisin özelliklerini anlatan saf cümle kalır.
    """
    if not text:
        return ""
    
    # Temizlenecek kelimeleri listele (şehir, otel adı, konsept)
    words_to_remove = []
    if hotel_name:
        words_to_remove.extend(hotel_name.split())
    if city:
        words_to_remove.extend(city.split())
    if concept:
        words_to_remove.extend(concept.split())
    
    # Kelimeleri normalize et (lowercase, accent kaldır)
    words_to_remove = [re.sub(r'[^a-zA-ZçğıöşüÇĞİÖŞÜ]', '', w.lower()) for w in words_to_remove]
    words_to_remove = [w for w in words_to_remove if w]  # Boş strings'i kaldır
    
    # Metni işle
    words = text.split()
    cleaned = []
    
    for word in words:
        # Kelimeyi normalize et
        word_clean = re.sub(r'[^a-zA-ZçğıöşüÇĞİÖŞÜ]', '', word.lower())
        
        # Tekrar eden kelime değilse ve kaldırılacak listede değilse ekle
        if word_clean and word_clean not in words_to_remove:
            # Önceki kelimeyle aynı değilse ekle
            if not cleaned or re.sub(r'[^a-zA-ZçğıöşüÇĞİÖŞÜ]', '', cleaned[-1].lower()) != word_clean:
                cleaned.append(word)
    
    return " ".join(cleaned)

def clear_search():
    """Aramayı temizle fonksiyonu"""
    st.session_state.search_query = ""
    st.session_state.search_results = None
    st.session_state.search_time = 0

# UI Başlıkları
st.title("🚀 MergenX")
st.markdown("### Bitur.com.tr Akıllı Konuşma Tabanlı Arama Motoru")

# Arama Motorunu Yükle
@st.cache_resource
def load_engine():
    try:
        engine = MergenSearchEngine()
        if engine.error_message:
            st.warning(f"⚠️ {engine.error_message}")
        return engine
    except Exception as e:
        st.error(f"Arama motoru başlatılamadı: {str(e)}")
        with st.expander("🔧 Hata Detayları"):
            st.code(str(e), language="python")
        return None

engine = load_engine()

if engine:
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Sistem Durumu")
        
        # Engine error kontrolü
        if engine.error_message:
            st.error(engine.error_message)
        else:
            st.success("Vektör DB: Bağlı")
            st.success("LLM: Aktif")
        top_k = st.slider("Öneri Sayısı", 1, 10, 3)
        st.divider()
        if st.button("🔄 Aramayı Temizle", use_container_width=True):
            clear_search()
            st.rerun()

    # Arama Girişi (Form ile)
    with st.form("search_form"):
        col1, col2 = st.columns([5, 1])
        with col1:
            query = st.text_input("Nasıl bir tatil hayal ediyorsunuz?", placeholder="Örn: Antalya'da denize yakın uygun fiyatlı oteller...", key="search_input")
        with col2:
            search_button = st.form_submit_button("🔍 Ara", use_container_width=True)
    
    # Hız Göstergesi Badge (Form dışında)
    if st.session_state.search_time > 0:
        col1, col2, col3 = st.columns([5, 5, 1])
        with col3:
            st.metric("⏱️ Hız", f"{st.session_state.search_time:.2f}s")

    # Arama sonuçlarını sadece butona basıldığında göster
    if search_button and query:
        with st.spinner("MergenX analiz ediyor..."):
            start_time = time.time()
            results, error_msg = engine.search(query, top_k=top_k)
            elapsed_time = time.time() - start_time
            
            st.session_state.search_results = results
            st.session_state.search_time = elapsed_time
            
            # Sonuç kontrolü
            if error_msg:
                st.error(f"❌ Hata: {error_msg}")
                with st.expander("🔧 Teknik Detaylar"):
                    st.code(error_msg, language="python")
            elif not results or not isinstance(results, list):
                st.error("❌ Arama sonucu bulunamadı. Lütfen bir daha deneyin.")
            else:
                # Yeni Arama Yap Butonu
                st.divider()
                if st.button("🔎 Yeni Arama Yap", use_container_width=True):
                    clear_search()
                    st.rerun()
                
                st.divider()
                st.markdown("### 🏨 Önerilen Oteller")
                
                # Otel ikonları listesi
                hotel_icons = ["🏩", "🏛️", "🏰", "🏯", "🏟️", "⛩️", "🏢"]
                
                # Otel Kartları
                for idx, hotel in enumerate(results):
                    icon = hotel_icons[idx % len(hotel_icons)]
                    
                    with st.container(border=True):
                        # Başlık satırı
                        col_name, col_price = st.columns([3, 1])
                        with col_name:
                            st.markdown(f"### {icon} {hotel['name']}")
                        with col_price:
                            st.markdown(f"**{hotel['price']} TL**")
                        
                        # Şehir ve Konsept
                        col1, col2 = st.columns(2)
                        with col1:
                            st.caption(f"📍 {hotel['city']}")
                        with col2:
                            st.caption(f"🎯 {hotel['concept']}")
                        
                        st.divider()
                        
                        # Neden Bu Otel? Bölümü (LLM tarafından oluşturulan)
                        st.markdown("**✨ Neden Bu Otel?**")
                        if 'reason' in hotel:
                            st.write(hotel['reason'])
                        else:
                            st.write("Kriterlerinizle tam uyumlu bir tesis.")
                        
                        st.divider()
                        
                        # Otel Açıklaması (Temizlenmiş)
                        st.markdown("**📄 Otel Hakkında**")
                        description_text = hotel['description']
                        cleaned_description = clean_description(description_text, hotel['name'], hotel['city'], hotel['concept'])
                        st.write(cleaned_description)
                    
else:
    st.warning("Sistem yüklenemedi. Lütfen terminal loglarını kontrol edin.")