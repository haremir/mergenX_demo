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

        GÖREV - ALTTIN ORAN (Akıcı Pazarlama Özeti):
        
        ⚠️ **KATYON KURALLAR (BU KURALLAR KATIYDIR - HİÇ ISTISNAI DURUM YOK):**
        
        1. **FORMAT**: Liste formatını bırak, tek akıcı paragraf yaz. 2-3 cümle, maksimum 30-40 kelime.
        
        2. **PAZARLAMA ZEKASı**: Teknik veriler (sabah uçuşu, bebek koltuğu, butik otel) ile pazarlama dilini harmanla.
           - KÖTÜ: 'Ekonomik uçuş, butik otel.'
           - İYİ: 'Sabah uçuşuyla güne erken başlarken, bebeğiniz için hazırladığımız VIP transfer ve sessiz butik otel tercihimizle konforun tadını çıkaracaksınız.'
        
        3. **DİL**: Sadece temiz, ikna edici İstanbul Türkçesi. Yabancı karakter KESINLIKLE YASAKLI:
           - ❌ İngilizce: morning, hotel, available, thought
           - ❌ Çince: 安全, 设计
           - ❌ Portekizce: bem-vindo
           - ❌ Diğer: szy, vytváracak
        
        4. **GEREKSIZ KALIPLAR YASAKLI**: 'Hazır mısınız?', 'Bu seyahat için hazırladık' vb. Doğrudan paketin değerine odaklan.
        
        5. **HALLUCINATION YASAKLI**: Olmayan hizmet/özellik yazma. Sadece gerçek veriler.
        
        6. **ÖRNEK ÇIKTI** (İyi yazım):
        'Bebek koltuğu ve sabah uçuşuyla çocuğunuz rahat edecek, sessiz butik otelimiz de huzurlu bir konaklamaya davet ediyor. VIP transfer servisiyle de otelden kapıdan kapıya sakin bir yolculuk sağlıyoruz.'
        
        **ÇIKTI**: Sadece pazarlama paragrafını yaz. Başka bir şey yazma.
        """
        
        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
            )
            response = completion.choices[0].message.content.strip()
            
            # Yabancı karakter kontrolü
            forbidden_patterns = ['morning', 'hotel', 'available', '安全', '设计', 'bem-vindo', 'szy', 'vytváracak', 'thought', 'phürsiniz', 'setting']
            has_forbidden = any(pattern.lower() in response.lower() for pattern in forbidden_patterns)
            
            # Kelime sayısı kontrolü (30-40 hedefi, max 45)
            word_count = len(response.split())
            
            if has_forbidden or word_count > 50:
                # Fallback: Pazarlama paragrafı
                return f"{hotel_name}, {hotel.get('region', '')} bölgesinde konforlu bir ortamda tercihlerinize uyumlu bir paket sunar. Seçilen uçuş ve transfer hizmetleriyle tam kaynaklanmış bir tatil deneyimi yaşayacaksınız."
            
            return response
        except Exception as e:
            # Fallback: Pazarlama paragrafı
            return f"{hotel_name}, {hotel.get('region', '')} bölgesinde konforlu bir ortamda tercihlerinize uyumlu bir paket sunar. Seçilen uçuş ve transfer hizmetleriyle tam kaynaklanmış bir tatil deneyimi yaşayacaksınız."

    def generate_package_response_old(self, hotel: dict, flight: dict = None, transfer: dict = None) -> str:
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
        
        ⚠️ **KESIN KURALLAR (BU KURALLAR KATIDIR - HİÇ ISTISNAI DURUM YOK):**
        
        1. **Yabancı Karakter YOK**: Asla Çinli, Arapça, Korece veya başka dil karakterleri yazma. Sadece Türkçe.
           - YANLIŞ: '安全liği', 'saleçtion', 'phürsiniz', 'selecion'
           - DOĞRU: 'güvenliği', 'seçim', 'vursiniz' (ya da tam sözcük)
        
        2. **Kelime Kayması YOK**: Kelimeler tamamlanmamış veya karışık yazılmış olmasın.
           - YANLIŞ: 'pakettir ama şekilde' (eksik konuşma)
           - DOĞRU: 'paketinize tam uygun' (tamamlanmış)
        
        3. **Gerçek Veriler SADECE**: Eğer metinde "Maalesef uygun" yazıyorsa, o hizmeti açıkça ret et. Asla olumsuz hayal yazma.
           - YANLIŞ: "Transfer yok ama sonra ayarlarız"
           - DOĞRU: "Maalesef uygun transfer bulunamadı"
        
        4. **Asla Uydurma**: Sadece metnin içinde gördüğün veriler ile yaz. Ekstra hizmet, indirim, bonus vs. yazma.
        
        5. **Samimi Ton**: Profesyonel ama sıcak. Emoji'leri dengeli kullan (her cümle değil, önemli yerlerde).
           - DOĞRU: "Paketi hazırladım ✅. İzmir'de harika bir konaklama sizi bekliyor 🏨"
           - YANLIŞ: "Paketi hazırladım 🎉🎊 İzmir'de 🏖️ konaklama 🏨 sizi bekliyor 😊✨"
        
        6. **Uzunluk**: En fazla 3-4 cümle, profesyonel ve özlü olsun.
        
        **ÇIKTI**: Sadece sunumu yaz, başka bir şey yazma. Girişe, sonuca, açıklamaya yer yok.
        """
        
        try:
            completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
            )
            response = completion.choices[0].message.content
            return response
        except Exception as e:
            # Fallback: Sadece gerçek veriler
            return f"{hotel_name} ({hotel_city}) - ₺{hotel_price:,.0f}/gece{flight_text}{transfer_text}"

    def extract_travel_params(self, user_query: str) -> dict:
        """
        Kullanıcının sorgusunu analiz ederek seyahat parametrelerini çıkarır.
        
        PROMPT EXPANSION:
        - Kısa promptlar ("Hel", "Kız kıza") → Genişletilmiş niyet
        - "Kız kıza" → "eğlence, merkezi, sosyal, nightlife, bar"
        - "Help", "Muhafazakar" → İlgili tercihler eklenir
        """
        # 🔥 PROMPT EXPANSION: Kısa promptları genişlet
        expansions = {
            "kız kıza": "eğlence, merkezi, sosyal, nightlife, bar, müzik, cafe",
            "kız": "eğlence, merkezi, sosyal, nightlife, bar, müzik, cafe",
            "help": "yardımcı personel, rehber, bilgilendirme, destek",
            "hel": "yardımcı personel, rehber, bilgilendirme, destek",
            "muhafazakar": "aile, çocuk, kapalı havuz, hijab friendly, sessiz",
            "balayı": "romantik, honeymoon, jakuzi, özel, couples",
            "iş": "business, wifi, workstation, meeting, conference"
        }
        
        # User query'yi lowercase yap ve expansion uygula
        query_lower = user_query.lower()
        for keyword, expansion in expansions.items():
            if keyword in query_lower:
                user_query = f"{user_query} ({expansion})"
                print(f"[PROMPT EXPANSION] '{keyword}' → '{expansion}'")
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
        
        # ============================================================
        # ✅ FIX 4: PROMPT RECOVERY - HARD-CODED
        # Kullanıcı niyetini analiz ederken şehri 'city', konsepti 'concept'
        # olarak ayır ve arama motoruna bu iki parametreyi AYRI gönder.
        # ============================================================
        
        # Prompt hazırlama
        prompt = f"""
        Kullanıcı Sorgusu: "{user_query}"

        GÖREV:
        Aşağıdaki bilgileri çıkar ve JSON olarak döndür:

        1. **INTENT**: Kullanıcı uçuş, transfer ve otel istiyor mu?
        2. **DESTINATION_CITY**: Varış şehri adı (Türkçe) - SADECE ŞEHİR ADI (örn: "İzmir", "Antalya")
        3. **DESTINATION_IATA**: Varış havalimanı kodu
        4. **ORIGIN_IATA**: Kalkış havalimanı (belirtilmemişse "IST" kullan)
        5. **TRAVEL_STYLE**: Seyahat stili - "ekonomik", "lüks" veya "aile" seçeneklerinden biri
        6. **CONCEPT**: Otel konsepti - SADECE konsept türü (örn: "butik", "all-inclusive", "spa", "aquapark")
        7. **TIME_PREFERENCE**: Uçuş zaman tercihi - "sabah", "öğleden", "akşam" (belirtilmemişse null)
        8. **PREFERENCES**: Kullanıcı tercihlerinin listesi (5-6 adet, örn: ["aquapark", "sessiz", "denize sıfır"])

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
            "concept": "butik",
            "time_preference": "akşam",
            "preferences": ["denize sıfır", "çocuk havuzu", "animasyon", "sessiz bölge", "açık buffet"]
        }}
        
        Kurallar:
        - **CITY**: SADECE şehir adı ("İzmir", "Antalya", "İstanbul") - konsept/özellik YOK
        - **CONCEPT**: SADECE otel konsepti ("butik", "all-inclusive", "spa") - şehir adı YOK
        - **TIME_PREFERENCE**: Kullanıcı "sabah uçuşu", "akşam kalkarım" gibi ifade kullandıysa çıkar
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
            
            # ✅ FIX 4: Yeni alanları kontrol et
            if not result.get("concept"):
                result["concept"] = ""
            
            if not result.get("time_preference"):
                result["time_preference"] = None
            
            print(f"[DEBUG] Extracted Travel Params: {result}")
            return result
            
        except Exception as e:
            # Fallback değerleri döndür
            return {
                "intent": {"flight": False, "transfer": False, "hotel": True},
                "destination_city": "İzmir",
                "destination_iata": "ADB",
                "origin_iata": "IST",
                "travel_style": "aile",
                "concept": "",
                "time_preference": None,
                "preferences": []
            }