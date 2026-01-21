import streamlit as st
import time
import os
import sys
import re
import logging

# Configure logging (PRODUCTION MODE: nur INFO level)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Proje kök dizinini Python yoluna ekle (Import hatalarını önlemek için)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from src.model.search_engine import MergenSearchEngine
except ImportError as e:
    logger.error(f"Modül yükleme hatası: {e}", exc_info=True)
    st.error(f"Modül yükleme hatası. Lütfen yöneticiyle iletişime geçin.")
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
st.markdown("""
    <div style='text-align: center; margin-bottom: 20px;'>
        <h1 style='color: #FF8C00; margin-bottom: 5px;'>🚀 MergenX</h1>
        <p style='color: #FFFFFF; font-size: 16px; margin: 0;'>
            <strong>Bitur.com.tr</strong> Akıllı Konuşma Tabanlı Arama Motoru
        </p>
        <p style='color: #AAAAAA; font-size: 13px; margin-top: 8px;'>
            AI-destekli özel paket önerileri • Anlık fiyatlandırma • Kişiselleştirilmiş planlar
        </p>
    </div>
""", unsafe_allow_html=True)

# Arama Motorunu Yükle
@st.cache_resource
def load_engine():
    try:
        engine = MergenSearchEngine()
        if engine.error_message:
            logger.warning(f"Engine warning: {engine.error_message}")
            st.warning(f"⚠️ {engine.error_message}")
        return engine
    except Exception as e:
        logger.error(f"Arama motoru başlatılamadı: {str(e)}", exc_info=True)
        st.error(f"Arama motoru başlatılamadı. Lütfen sayfayı yenileyin veya yöneticiyle iletişime geçin.")
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
            query = st.text_input(
                "✍️ Nasıl bir tatil hayal ediyorsunuz?",
                placeholder="Örn: Eşimle İzmir'e sessiz bir butik otel tatili, yüksek konforlu, özel havuz",
                key="search_input"
            )
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
                logger.error(f"Search error: {error_msg}")
                st.error(f"❌ Arama yapılamadı. Lütfen tekrar deneyin.")
            elif not results or not isinstance(results, list):
                logger.warning(f"No results for query: {query}")
                st.error("❌ Arama sonucu bulunamadı. Lütfen bir daha deneyin.")
            else:
                # Yeni Arama Yap Butonu
                st.divider()
                if st.button("🔎 Yeni Arama Yap", use_container_width=True):
                    clear_search()
                    st.rerun()
                
                st.divider()
                st.markdown("## 🤖 MergenX Seyahat Planı")
                
                # Paket Kartları - Revize Görünüm
                for idx, hotel in enumerate(results):
                    with st.container(border=True):
                        # ============================================================
                        # ÜSTTE: AKILLI ÖZET (LLM'in Önerisi)
                        # ============================================================
                        st.markdown("### ✨ Seyahat Öneriniz")
                        
                        # Package bilgisi kontrol et
                        package = hotel.get("package", {})
                        intelligent_summary = hotel.get("reason", "")
                        
                        if intelligent_summary:
                            st.info(intelligent_summary)
                        else:
                            st.info("Kriterlerinizle tam uyumlu bir paket hazırlandı!")
                        
                        st.divider()
                        
                        # ============================================================
                        # ORTA: PAKET BİLGİLERİ (3 Kolon)
                        # ============================================================
                        st.markdown("### 📦 Paket Detayları")
                        
                        col1, col2, col3 = st.columns(3)
                        
                        # ---- KOLON 1: OTEL BİLGİSİ ----
                        with col1:
                            st.markdown("#### 🏨 Konaklama")
                            
                            hotel_info = package.get("hotel", {})
                            st.markdown(f"**{hotel_info.get('name', hotel['name'])}**")
                            st.markdown(f"📍 {hotel_info.get('city', hotel['city'])}")
                            
                            if hotel_info.get("concept"):
                                st.markdown(f"🎯 {hotel_info.get('concept')}")
                            
                            # Amenities göster
                            amenities = hotel_info.get("amenities", [])
                            if amenities:
                                st.caption("**Tesisler:**")
                                for amenity in amenities[:3]:
                                    st.markdown(f"✓ {amenity}")
                            
                            # Fiyat
                            st.divider()
                            price = hotel_info.get("price", hotel['price'])
                            st.markdown(f"**₺{price:,.0f}** / gece")
                        
                        # ---- KOLON 2: UÇUŞ BİLGİSİ ----
                        with col2:
                            st.markdown("#### ✈️ Uçuş")
                            
                            flight = package.get("flight")
                            
                            if flight:
                                # Havayolu bilgisi
                                carrier = flight.get("carrier", "")
                                carrier_name = ""
                                
                                # Tercüme sözlüğü
                                carrier_names = {
                                    "TK": "🇹🇷 Türk Hava Yolları",
                                    "PC": "🟡 Pegasus Airlines",
                                    "HV": "Havayolu Express",
                                    "U6": "Bees Airline"
                                }
                                carrier_name = carrier_names.get(carrier, carrier)
                                
                                st.markdown(f"**{carrier_name}**")
                                st.markdown(f"Uçuş: {flight.get('flight_no', 'N/A')}")
                                st.markdown(f"Kabin: {flight.get('cabin', 'Ekonomi')}")
                                
                                if flight.get("departure"):
                                    dep_time = flight.get("departure", "")[:16] if flight.get("departure") else "N/A"
                                    st.markdown(f"📅 {dep_time}")
                                
                                if flight.get("baggage"):
                                    st.markdown(f"🛄 {flight.get('baggage')}")
                                
                                st.divider()
                                st.markdown(f"**₺{flight.get('price', 0):,.0f}**")
                            else:
                                st.markdown("ℹ️ *Uçuş pakete dahil değil*")
                                st.markdown("---")
                                st.markdown("**₺0**")
                        
                        # ---- KOLON 3: TRANSFER BİLGİSİ ----
                        with col3:
                            st.markdown("#### 🚗 Transfer")
                            
                            transfer = package.get("transfer")
                            
                            if transfer:
                                # Araç tipi tercümesi
                                vehicle_code = transfer.get("vehicle_category", "")
                                vehicle_names = {
                                    "VAN_VIP": "🚐 Lüks VIP Araç",
                                    "VAN_STANDARD": "🚌 Standart Minibüs",
                                    "CAR_ECONOMY": "🚗 Ekonomik Sedan",
                                    "CAR_COMFORT": "🚙 Konforlu Sedan",
                                    "CAR_PREMIUM": "🚘 Premium Araç",
                                    "SUV": "🚙 SUV",
                                    "LUXURY": "👑 Lüks Araç"
                                }
                                vehicle_name = vehicle_names.get(vehicle_code, vehicle_code)
                                
                                st.markdown(f"**{vehicle_name}**")
                                st.markdown(f"Route: {transfer.get('from', 'N/A')} → {transfer.get('to', 'N/A')}")
                                
                                duration = transfer.get("duration", 0)
                                if duration:
                                    st.markdown(f"⏱️ {duration} dakika")
                                
                                # Özellikler
                                features = transfer.get("vehicle_features", [])
                                if features:
                                    st.caption("**Olanaklar:**")
                                    for feature in features[:2]:
                                        feature_names = {
                                            "WIFI": "📶 WiFi",
                                            "BABY_SEAT_AVAIL": "👶 Bebek Koltuğu",
                                            "LEATHER_SEATS": "🛋️ Deri Koltuk",
                                            "CLIMATE_CONTROL": "❄️ İklim Kontrolü",
                                            "REFRESHMENTS": "🥤 İçecek Servisi"
                                        }
                                        feature_name = feature_names.get(feature, feature)
                                        st.markdown(f"✓ {feature_name}")
                                
                                st.divider()
                                # Fiyatı güvenli şekilde göster
                                transfer_price = transfer.get('price', 0)
                                if transfer_price is None:
                                    transfer_price = 0
                                st.markdown(f"**₺{float(transfer_price):,.0f}**")
                            else:
                                st.markdown("ℹ️ *Transfer pakete dahil değil*")
                                st.markdown("---")
                                st.markdown("**₺0**")
                        
                        # ============================================================
                        # ALT: TOPLAM PAKET TUTARI
                        # ============================================================
                        st.divider()
                        
                        # Fiyat hesaplaması - price_breakdown'dan al
                        price_breakdown = package.get("price_breakdown", {})
                        
                        if price_breakdown:
                            # Yeni yapıdan oku
                            hotel_price = price_breakdown.get("hotel", 0)
                            flight_price = price_breakdown.get("flight", 0)
                            transfer_price = price_breakdown.get("transfer", 0)
                            total_price = price_breakdown.get("total", 0)
                        else:
                            # Fallback: Eski yapıdan oku (compatibility)
                            hotel_price = package.get("hotel", {}).get("price", hotel['price'])
                            flight_price = package.get("flight", {}).get("price", 0) if package.get("flight") else 0
                            transfer_price = package.get("transfer", {}).get("price", 0) if package.get("transfer") else 0
                            total_price = hotel_price + flight_price + transfer_price
                        
                        # Fiyat dökümü
                        col_break1, col_break2, col_break3 = st.columns(3)
                        with col_break1:
                            st.metric("🏨 Otel", f"₺{hotel_price:,.0f}")
                        with col_break2:
                            if flight_price > 0:
                                st.metric("✈️ Uçuş", f"₺{flight_price:,.0f}")
                            else:
                                st.metric("✈️ Uçuş", "—")
                        with col_break3:
                            if transfer_price > 0:
                                st.metric("🚗 Transfer", f"₺{transfer_price:,.0f}")
                            else:
                                st.metric("🚗 Transfer", "—")
                        
                        # TOPLAM
                        st.divider()
                        st.markdown(f"### 💰 **TOPLAM PAKET TUTARI: ₺{total_price:,.0f}**")
                        
                        st.divider()

                    
else:
    st.warning("Sistem yüklenemedi. Lütfen terminal loglarını kontrol edin.")