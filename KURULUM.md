# Video Transkript Aracı: Kurulum

Videonu yükle ya da YouTube Shorts veya Instagram Reel linkini yapıştır; cümle cümle zaman damgalı yazıya dök. Her şey kendi bilgisayarında çalışır.

## 1. Gerekenler
- Windows 10 ya da 11.
- İlk açılışta internet.
- Boş disk yeri: yaklaşık 400 MB (Python, paketler, ffmpeg, video indirme aracı instapuller ve YouTube için küçük bir JS aracı).
- **Bilinen sınır:** Akıllı Uygulama Denetimi (Smart App Control) imzasız araçları (Python, ffmpeg vb.) engellediği için açık olduğu bilgisayarda uygulama çalışmaz. `baslat.cmd` denetim açıksa bunu söyleyip kapanır, değerlendirme modundaysa uyarıp devam eder. İsteyen, Windows Güvenliği → Uygulama ve tarayıcı denetimi → Akıllı Uygulama Denetimi bölümünden kapatabilir; karar kullanıcınındır.

## 2. İndir ve aç
1. Zip dosyasına sağ tıkla, "Özellikler"i seç.
2. Altta "Engellemeyi kaldır" kutusunu işaretle, "Tamam"a bas. (Kutu yoksa bu adım gerekmez.)
3. Zip dosyasına sağ tıkla, "Tümünü ayıkla"yı seç. Klasörü `C:\video-transkript` gibi bir yere ayıkla (Masaüstü ve Belgeler OneDrive ile buluta eşitlenebilir, anahtarların ve büyük araçlar buluta gitmesin).

Zip'in içinden çalıştırma. Önce ayıkla. Ayıklayınca `video-transkript` adlı bir klasör açılır. `baslat.cmd` bu klasörün içindedir.

## 3. Çift tıkla
1. Ayıkladığın klasörde `baslat.cmd` dosyasına çift tıkla.
2. İlk açılış birkaç dakika sürer. Gereken her şey bu klasörün içine inmeye başlar. Bilgisayarının başka yerine bir şey kurulmaz.
3. Siyah pencere açık kalmalı. Kapatırsan uygulama durur.

## 4. Anahtarını yapıştır
Tarayıcı kurulum sayfasıyla açılır.
1. ElevenLabs'ta hesap aç, API Keys sayfasına git: https://elevenlabs.io/app/settings/api-keys
2. "Create API Key"e bas. İzinlerde "Speech to Text" açık kalsın.
3. Anahtarı kopyala, sayfadaki kutuya yapıştır.
4. Önce "Test et"e, sonra "Kaydet"e bas.

Groq anahtarı isteğe bağlıdır. ElevenLabs çalışmazsa yedek olarak kullanılır. Kaydettiğin anahtar ekranda gizli görünür. Groq anahtarını "Kaldır" ile silebilirsin.

## 5. Kullan
Video dosyasını seç ya da bir YouTube Shorts veya Instagram Reel linki yapıştır, "Dök"e bas. Bitince TXT, SRT ya da JSON olarak indir.
- Link yapıştırınca dosya seçimi, dosya seçince link temizlenir. İkisinden yalnızca biri kullanılır.
- YouTube linkinde yalnızca videonun sesi indirilir.
- Her site kendi sırasıyla işlenir: aynı siteden iki indirme arasında en az 15 saniye beklenir. Sıra varsa ekranda "YouTube için sıra bekleniyor" ya da "Instagram için sıra bekleniyor" yazar. Bir YouTube linki Instagram sırasını beklemez, Instagram linki de YouTube sırasını beklemez.
- Site indirmeyi engellerse uygulama nedenini söyler. "Dosya yükle" düğmesiyle videoyu kendin yükleyebilirsin.
- Instagram'da yalnızca tek video ya da Reel desteklenir; çoklu gönderide videoyu dosya olarak yükle.
- Instagram'da uzun gönderi açıklaması ilk 3 satırla gösterilir; "Devamını göster" ile tamamı açılır.
- **Dil:** Sağ üstteki "English" düğmesi arayüzü İngilizceye, "Türkçe" düğmesi Türkçeye çevirir. Seçim hatırlanır. Bir iş sürerken düğme kapalıdır. İndirilen TXT ve SRT'deki "[müzik]" gibi etiketler de seçili dilde yazılır.
- **Kullanım şartları uyarısı:** YouTube ve Instagram linkleri resmi bir yol kullanmaz ve sitelerin kullanım şartlarıyla çelişebilir. Hiçbir hesap ya da şifre kullanılmaz. Yalnızca hakkın olan içerik için kullan.

## 6. Gizlilik
- Anahtarların yalnızca bu klasördeki `.env` dosyasında durur.
- Videonun sesi, yazıya dökülmek için ElevenLabs'a gönderilir. ElevenLabs çalışmazsa Groq'a gönderilir.
- Videolar ve ses dosyaları iş bitince silinir. Linkten indirilen video da iş bitince silinir. Transkriptler bu klasördeki `data` içinde kalır.
- Hiçbir YouTube ya da Instagram hesabı, şifresi ya da çerezi kullanılmaz.
- Kullanım, ElevenLabs hesabındaki krediden düşer. Güncel fiyatı ElevenLabs'tan öğren.

## 7. Sorun olursa
- **"Oturum yok. Uygulamayı baslat.cmd ile açın.":** Sayfayı kendin açmışsın. `baslat.cmd`'ye yeniden çift tıkla.
- **İndirme hatası:** İnternetini kontrol et, `baslat.cmd`'ye yeniden çift tıkla. Hata olursa pencere bir tuşa basmanı bekler.
- **"Uygulama zaten açılıyor":** Bekle. Hazır olunca tarayıcıda açılır. Çalışırken tekrar çift tıklarsan açık uygulama tarayıcıda görünür.
- **"Video indirme aracı kurulu değil":** Link için gereken araç (instapuller) kurulmamış ya da bulunamıyor. `baslat.cmd`'ye yeniden çift tıkla, internetin açık olsun. Sürerse videoyu dosya olarak yükle.
- **"YouTube indirme aracı eksik ya da güncel değil":** YouTube için gereken küçük JS aracı kurulamamış. `baslat.cmd`'yi kapatıp yeniden aç. Instagram linkleri ve dosya yükleme bu sırada da çalışır.
- **Müzikli bölümlerde uydurma metin görürsen:** Konuşmasız bölüm dedektörü varsayılan olarak kapalıdır. Açmak için klasördeki `.env` dosyasına `NONSPEECH_DETECTOR=silero` satırını ekle, siyah pencereyi kapatıp `baslat.cmd`'yi yeniden aç. İlk açılışta ek paketler iner (internet gerekir).
- **Antivirüs uyarısı:** Bazı antivirüsler indirilen araçlara takılabilir. Bu klasörü izinli listeye ekle.
- **Sorun sürerse:** Klasördeki `tools` klasörünü silip `baslat.cmd`'ye yeniden çift tıkla. Anahtarların silinmez.
- **Güncelleme:** Yeni zip'i ayrı bir klasöre ayıkla. Eski klasördeki `.env` dosyasını yeni klasöre kopyala.
