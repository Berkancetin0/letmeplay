<div align="center">

<img src="https://img.shields.io/badge/Platform-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white"/>
<img src="https://img.shields.io/badge/Spotify-API-1ed760?style=for-the-badge&logo=spotify&logoColor=black"/>
<img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge"/>

# 🎮 Spotify Mini Player

**Oyun oynarken alt-tab atmana gerek yok.**  
Ekranının köşesinde duran, oyunun üzerinde kalan minimal Spotify kontrolcüsü.

</div>

---

## ✨ Özellikler

- 🖥️ **Always-on-top** — Tam ekran oyunların üzerinde kalır
- 🔽 **Küçültülebilir** — Tek tıkla sadece şarkı adı + EQ animasyonu
- 🖱️ **Sürükle & bırak** — İstediğin köşeye taşı
- 🔁 **Tam kontrol** — Oynat/duraklat, ileri/geri, shuffle, repeat, ses
- 🔐 **OAuth 2.0** — Güvenli giriş, token otomatik yenilenir
- 💾 **Oturumu hatırlar** — Her açılışta tekrar giriş gerekmez
- 📦 **Tek dosya EXE** — Kurulum yok, çift tıkla çalışır

---

## ⬇️ İndir

### En kolay yol — hazır EXE

**[Releases](../../releases/latest)** sayfasına git → `SpotifyMiniPlayer.exe` dosyasını indir.

> Windows Defender "bilinmeyen uygulama" uyarısı verebilir.  
> "Daha fazla bilgi" → "Yine de çalıştır" tıkla. Bu normaldir (code signing sertifikası olmadığı için).

---

## 🚀 Kurulum

### 1. Spotify Uygulaması Oluştur (tek seferlik, 2 dakika)

1. [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) adresine git
2. **"Create App"** tıkla
3. Şunları doldur:
   - App name: `Mini Player` (istediğin isim)
   - Redirect URI: `http://localhost:8888/callback`  ← **bu önemli**
4. **"Save"** → oluşturulan uygulamaya tıkla → **Settings**
5. **Client ID** ve **Client Secret**'ı kopyala

### 2. EXE'yi Çalıştır

1. `SpotifyMiniPlayer.exe` dosyasına çift tıkla
2. Giriş ekranında Client ID ve Client Secret'ı gir
3. **"Spotify ile Giriş Yap"** butonuna tıkla
4. Açılan tarayıcıda Spotify hesabınla izin ver
5. ✅ Player açılır — bir daha giriş yapman gerekmez!

---

## 🎮 Oyun İçinde Kullanım

```
Oyunu Borderless Windowed modda aç
→ Player otomatik üstte kalır
→ ▾ ile küçült, ▸ ile büyüt
→ Sürükleyerek köşeye taşı
```

| Buton | İşlev |
|-------|-------|
| ▾ / ▸ | Küçült / Büyüt |
| ⏮ / ⏭ | Önceki / Sonraki şarkı |
| ▶ / ⏸ | Oynat / Duraklat |
| ⇄ | Shuffle aç/kapat |
| ↻ | Repeat aç/kapat |
| 🔉 slider | Ses seviyesi |

---

## 🛠️ Kaynaktan Derle

Python kuruluysa kendin de derleyebilirsin:

```bash
git clone https://github.com/KULLANICI_ADIN/spotify-mini-player
cd spotify-mini-player
pip install -r requirements.txt

# Direkt çalıştır
python main.py

# EXE oluştur
pyinstaller --onefile --windowed --name SpotifyMiniPlayer main.py
```

---

## ❓ Sık Sorulan Sorular

**"Port 8888 meşgul" hatası alıyorum**  
`main.py` dosyasında `PORT = 8888` satırını `8889` yap, Spotify Dashboard'da da Redirect URI'yi güncelle.

**Spotify "çalmıyor" diyor**  
Spotify masaüstü veya web uygulaması açık olmalı ve aktif bir cihazda çalıyor olmalı.

**Windows Defender engelledi**  
"Daha fazla bilgi" → "Yine de çalıştır" tıkla. Güven vermek için kaynaktan derleyebilirsin.

**Token süresi doldu**  
Uygulama otomatik yeniler. Yenileyemezse çıkış yap, tekrar giriş yap.

---

## 📄 Lisans

MIT License — dilediğin gibi kullan, değiştir, dağıt.

---

<div align="center">
  <sub>Made with ♥ for gamers who love music</sub>
</div>
