import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class MergenLLM:
    def __init__(self):
        # Streamlit Cloud Secrets entegrasyonu
        try:
            import streamlit as st
            # Streamlit içindeyiz - secrets'tan dene
            try:
                api_key = st.secrets["GROQ_API_KEY"]
            except (KeyError, AttributeError, FileNotFoundError):
                # Secrets'ta yoksa environment variable'dan al
                api_key = os.getenv("GROQ_API_KEY")
        except ImportError:
            # Streamlit olmadığı için doğrudan environment variable'dan al
            api_key = os.getenv("GROQ_API_KEY")
        
        if not api_key:
            raise ValueError("GROQ_API_KEY bulunamadı! Lütfen .env dosyasında veya Streamlit Secrets'ta ayarlayınız.")
        
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile"

    def generate_reasons(self, query: str, hotels: list):
        """Her otel için kullanıcı sorgusuna özel bir 'neden' cümlesi üretir."""
        hotel_list_text = "\n".join([f"- {h['name']}: {h['description']}" for h in hotels])
        
        prompt = f"""
        Kullanıcı Sorgusu: "{query}"
        Bulunan Oteller:
        {hotel_list_text}

        GÖREV:
        Her otel için, kullanıcının kriterleriyle neden eşleştiğini anlatan 15 kelimelik, çok vurucu bir cümle yaz.
        Yanıtı SADECE şu JSON formatında ver:
        {{
            "Otel Adı": "Neden cümlesi...",
            "Otel Adı 2": "Neden cümlesi..."
        }}
        Asla giriş/sonuç yazma, sadece JSON dön. Türkçe konuş.
        """

        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                response_format={"type": "json_object"}
            )
            return json.loads(completion.choices[0].message.content)
        except Exception as e:
            print(f"LLM Hatası: {e}")
            return {}

    def parse_intent(self, user_sentence: str) -> dict:
        """
        Kullanıcının cümlesinden varış yerini, uçuş ihtiyacını ve transfer ihtiyacını ayıklar.
        
        Args:
            user_sentence: Kullanıcının yazıp seyahat isteği
            
        Returns:
            {
                "destination_iata": "İSTANBUL kodu örneğin IST",
                "needs_flight": true/false,
                "needs_transfer": true/false
            }
        """
        prompt = f"""
        Kullanıcı Sorgusu: "{user_sentence}"

        GÖREV:
        Aşağıdaki bilgileri çıkar:
        1. Varış yeri IATA kodu (örn: IST, ADB, VAN, GZT, GNY, vb.)
        2. Kullanıcı uçuş mı istiyor? (Soruda uçak, flight, ticket, uçuş vs. geçiyor mu?)
        3. Kullanıcı transfer mi istiyor? (Soruda araç, transfer, shuttle, vb. geçiyor mu?)

        Yanıtı SADECE şu JSON formatında ver:
        {{
            "destination_iata": "IST",
            "needs_flight": true,
            "needs_transfer": true
        }}
        
        Asla giriş/sonuç yazma, sadece JSON dön.
        """
        
        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                response_format={"type": "json_object"}
            )
            result = json.loads(completion.choices[0].message.content)
            return result
        except Exception as e:
            print(f"Intent Parsing Hatası: {e}")
            return {"destination_iata": "", "needs_flight": False, "needs_transfer": False}

    def translate_code(self, code: str) -> str:
        """
        API'den gelen teknik kodları kullanıcı dostu Türkçeye çevirir.
        
        Args:
            code: API kodu (örn: VAN_VIP, TK, ADB)
            
        Returns:
            Tercüme edilmiş metin
        """
        # Yaygın tercüme sözlüğü
        translations = {
            # Araç tipleri
            "VAN_VIP": "Lüks VIP Araç",
            "VAN_STANDARD": "Standart Minibüs",
            "CAR_ECONOMY": "Ekonomik Sedan",
            "CAR_COMFORT": "Konforlu Sedan",
            "CAR_PREMIUM": "Premium Araç",
            "SUV": "SUV",
            "LUXURY": "Lüks Araç",
            
            # Havayolu Kodları (IATA)
            "TK": "Türk Hava Yolları",
            "PC": "Pegasus Airlines",
            "HV": "Havayolu Express",
            "U6": "Bees Airline",
            
            # Havaalanı Kodları (IATA)
            "IST": "İstanbul Havalimanı",
            "SAW": "Sabiha Gökçen Havalimanı",
            "ADB": "İzmir Adnan Menderes Havalimanı",
            "VAN": "Van Ferit Melen Havalimanı",
            "GZT": "Gaziantep Havalimanı",
            "GNY": "Gazipaşa Havalimanı",
            "DLM": "Dalaman Havalimanı",
            "BJV": "Bodrum Havalimanı",
            "ESB": "Ankara Esenboğa Havalimanı",
            "KYA": "Kayseri Havalimanı",
        }
        
        return translations.get(code, code)

    def generate_package_response(self, hotel: dict, flight: dict = None, transfer: dict = None) -> str:
        """
        Seçilen otel, uçuş ve transfer bilgilerini sıcak, samimi ve ikna edici bir 
        seyahat paketi sunumuna dönüştürür.
        
        KESIN: Sadece gerçek verilerle çalışır. Olmayan uçuş/transfer için "Maalesef uygun ... bulunamadı" der.
        Asla hayal etmez, asla "seçtik" veya "ayarladık" demez. Sadece gerçek veriler kullanır.
        
        Args:
            hotel: Otel bilgisi dict'i
            flight: Uçuş bilgisi dict'i (opsiyonel)
            transfer: Transfer bilgisi dict'i (opsiyonel)
            
        Returns:
            Güzel formatlanmış seyahat paketi sunumu (Türkçe) - SADECE gerçek veriler içerir
        """
        # Veri hazırlama
        hotel_name = hotel.get("name", "Otel")
        hotel_city = hotel.get("city", "")
        hotel_price = hotel.get("price", 0)
        
        # GERÇEK Uçuş bilgisi - veri varsa SADECE gerçek bilgi, yoksa açıkça söyle
        flight_text = ""
        if flight and isinstance(flight, dict) and flight.get("flight_no"):
            # Sadece gerçek bilgiler - zaman ve havayolu
            departure_time = flight.get("departure", "")[:16] if flight.get("departure") else ""
            carrier_code = flight.get("carrier", "")
            carrier_name = self.translate_code(carrier_code)
            price = flight.get("price", 0)
            flight_text = f"\n✈️ **Uçuş**: {carrier_name} - Saat: {departure_time} - ₺{price:,.0f}"
        elif not flight:
            # Açıkça söyle ki uçuş bulunamadı
            flight_text = "\n✈️ **Uçuş**: Maalesef uygun uçuş bulunamadı"
        
        # GERÇEK Transfer bilgisi - veri varsa SADECE gerçek bilgi, yoksa açıkça söyle
        transfer_text = ""
        if transfer and isinstance(transfer, dict) and transfer.get("vehicle_category"):
            # Sadece gerçek bilgiler - araç tipi ve durasyonu
            vehicle_type = self.translate_code(transfer.get("vehicle_category", ""))
            duration = transfer.get("duration", 0)
            price = transfer.get("price", 0)
            transfer_text = f"\n🚗 **Transfer**: {vehicle_type} - {duration} dakika - ₺{price:,.0f}"
        elif not transfer:
            # Açıkça söyle ki transfer bulunamadı
            transfer_text = "\n🚗 **Transfer**: Maalesef uygun transfer bulunamadı"
        
        # LLM'e SADECE gerçek veriler ile prompt ver
        prompt = f"""
        Aşağıdaki seyahat paketi bilgilerini kullanarak, sıcak ve samimi bir sunum yaz:

        **PAKET:**
        - Otel: {hotel_name} ({hotel_city}) - ₺{hotel_price:,.0f}/gece
        {flight_text}
        {transfer_text}

        GÖREV:
        Paketi kullanıcıya sunumunu yap. Sıcak, kişisel ve samimi bir ton kullan.
        
        KESIN KURALLAR (BU KURALLAR KATIDIR):
        1. Eğer metinde "Maalesef uygun" yazıyorsa, o hizmete söyle: "İlk defa kullanıyorsanız, bunu hayal etmeyeceksiniz" gibi olumsuz hayal YAZMA
        2. Sadece metnin içinde gördüğün gerçek verileri kullan - ASLA UYDURMA
        3. ASLA "seçtim", "ayarladım", "buldum" gibi eylemler yazma - bunlar yalan olur
        4. Basit, gerçekçi, samimi yaz
        5. En fazla 3-4 cümle
        6. Türkçe yaz
        
        Yanıtı SADECE sunum metni olarak ver, başka şey yazma.
        """
        
        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
            )
            response = completion.choices[0].message.content
            print(f"[PACKAGE_RESPONSE] Generated: {response[:100]}...")
            return response
        except Exception as e:
            print(f"Paket Sunumu Hatası: {e}")
            # Fallback: Sadece gerçek veriler
            return f"{hotel_name} ({hotel_city}) - ₺{hotel_price:,.0f}/gece{flight_text}{transfer_text}"

    def extract_travel_params(self, user_query: str) -> dict:
        """
        Kullanıcının sorgusunu analiz ederek seyahat parametrelerini çıkarır.
        
        Args:
            user_query: Kullanıcının seyahat sorgusu
            
        Returns:
            {
                "intent": {"flight": true/false, "transfer": true/false, "hotel": true},
                "destination_city": "İzmir",
                "destination_iata": "ADB",
                "origin_iata": "IST",
                "travel_style": "ekonomik/lüks/aile",
                "preferences": ["aquapark", "sessiz", "denize sıfır"]
            }
        """
        # Şehir-IATA eşleştirme sözlüğü
        city_to_iata = {
            "istanbul": "IST",
            "ankara": "ESB",
            "izmir": "ADB",
            "antalya": "GZT",
            "bodrum": "BJV",
            "dalaman": "DLM",
            "adana": "AYT",
            "gaziantep": "GZT",
            "gazipaşa": "GNY",
            "van": "VAN",
            "kayseri": "KYA",
            "konya": "KYA",
            "rize": "RZS",
            "aydın": "ADB",
            "muğla": "BJV",
            "balıkesir": "BJV",
            "çeşme": "ADB",
            "alaçatı": "ADB",
            "kuşadası": "ADB",
            "didim": "ADB",
            "belek": "GZT",
            "lara": "GZT",
            "konyaaltı": "GZT",
        }
        
        # Prompt hazırlama
        prompt = f"""
        Kullanıcı Sorgusu: "{user_query}"

        GÖREV:
        Aşağıdaki bilgileri çıkar ve JSON olarak döndür:

        1. **INTENT**: Kullanıcı uçuş, transfer ve otel istiyor mu?
        2. **DESTINATION_CITY**: Varış şehri adı (Türkçe)
        3. **DESTINATION_IATA**: Varış havalimanı kodu
        4. **ORIGIN_IATA**: Kalkış havalimanı (belirtilmemişse "IST" kullan)
        5. **TRAVEL_STYLE**: Seyahat stili - "ekonomik", "lüks" veya "aile" seçeneklerinden biri
        6. **PREFERENCES**: Kullanıcı tercihlerinin listesi (5-6 adet, örn: ["aquapark", "sessiz", "denize sıfır"])

        Bilinen havalimanı kodları:
        - IST: İstanbul
        - SAW: Sabiha Gökçen (İstanbul)
        - ADB: İzmir (Adnan Menderes)
        - AYT: Adana
        - BJV: Bodrum
        - DLM: Dalaman
        - EDR: Edirne
        - GZT: Gaziantep
        - GNY: Gazipaşa
        - VAN: Van
        - KYA: Kayseri
        - RZS: Rize
        - ESB: Ankara (Esenboğa)

        Yanıtı SADECE şu JSON formatında ver, başka şey yazma:
        {{
            "intent": {{"flight": true, "transfer": false, "hotel": true}},
            "destination_city": "İzmir",
            "destination_iata": "ADB",
            "origin_iata": "IST",
            "travel_style": "aile",
            "preferences": ["denize sıfır", "çocuk havuzu", "animasyon", "sessiz bölge", "açık buffet"]
        }}
        
        Kurallar:
        - Destination city'yi Türkçe yaz
        - IATA kodlarını büyük harfle ver
        - Preferences'ı kullanıcının vurguladığı kriterlere göre belirle
        - Travel style şu 3 seçenekten biri olmalı: "ekonomik", "lüks", "aile"
        - Kalkış yeri belirtilmemişse varsayılan olarak "IST" kullan
        - Asla giriş/sonuç yazma, sadece JSON dön
        """
        
        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                response_format={"type": "json_object"}
            )
            result = json.loads(completion.choices[0].message.content)
            
            # Varsayılan değerleri kontrol et
            if not result.get("origin_iata"):
                result["origin_iata"] = "IST"
            
            if not result.get("destination_iata"):
                # Şehir adından IATA kodu çıkarmaya çalış
                city_lower = result.get("destination_city", "").lower()
                result["destination_iata"] = city_to_iata.get(city_lower, "ADB")
            
            if not result.get("travel_style"):
                result["travel_style"] = "aile"
            
            if not result.get("preferences"):
                result["preferences"] = []
            
            print(f"[DEBUG] Extracted Travel Params: {result}")
            return result
            
        except Exception as e:
            print(f"Travel Params Extraction Hatası: {e}")
            # Fallback değerleri döndür
            return {
                "intent": {"flight": False, "transfer": False, "hotel": True},
                "destination_city": "İzmir",
                "destination_iata": "ADB",
                "origin_iata": "IST",
                "travel_style": "aile",
                "preferences": []
            }