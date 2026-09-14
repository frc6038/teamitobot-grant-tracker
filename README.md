# 🤖 İtobot - FIRST Robotics Grant Tracker

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12.x-blue)

![Status](https://img.shields.io/badge/Status-Active-brightgreen)

**FIRST Robotics hibe fırsatlarını otomatik olarak takip eden Telegram ve e-posta bildirim botu**

[Hızlı Başlangıç](#-hızlı-başlangıç) • [Özellikler](#-özellikler) • [Çalışma Mantığı](#-çalışma-mantığı) • [Kurulum](#-kurulum) • [Bot Komutları](#-bot-komutları)

</div>

---

## 📋 Nedir?

**İtobot Grant Tracker**, FIRST Inspires web sitesinde yayınlanan **FRC hibe fırsatlarını otomatik olarak takip eden** ve yeni fırsatlar yayınlandığında Telegram üzerinden **bildirim gönderen** bir bot uygulamasıdır.

Bot, FIRST'in hibe fırsatları sayfasını **15 dakikada bir** kontrol eder. Yeni bir FRC hibesi tespit edildiğinde hibenin:

* Başlığını
* Başlangıç tarihini
* Bitiş tarihini
* Doğrudan başvuru bağlantısını

PostgreSQL veritabanına kaydeder ve abone olan kullanıcılara bildirir.

Kullanıcıların herhangi bir kod değişikliği yapmasına gerek yoktur. Telegram'da botu açıp `/start` komutunu kullanmaları yeterlidir.

---

## ✨ Özellikler

* 🔍 **Otomatik Tarama** - FIRST hibe portalını 15 dakikada bir kontrol eder
* 🚨 **Otomatik Bildirim** - Yeni FRC hibeleri bulunduğunda abone kullanıcılara Telegram bildirimi gönderir
* ✉️ **SMTP Bildirimi** - Yapılandırıldığında yeni hibeleri operasyon e-posta adreslerine de gönderir
* 🔗 **Doğrudan Başvuru Linki** - Bildirimlerde ilgili hibenin başvuru bağlantısı bulunur
* 📅 **Hibe Tarihleri** - Başlangıç ve bitiş tarihleri bildirimlerde gösterilir
* 👥 **Çok Kullanıcı Desteği** - Birden fazla kullanıcı aynı botu kullanabilir
* 📊 **Kişisel İstatistikler** - Kullanıcılar aldıkları hibe bildirimlerini görüntüleyebilir
* 🟢 **Bot Durumu** - Aktif kullanıcı sayısı, abonelik durumu ve sistem durumu görüntülenebilir
* ⏱️ **Sonraki Tarama** - Bir sonraki otomatik taramaya kalan süre görüntülenebilir
* 📈 **Son Tarama ve Çalışma Süresi** - Botun son tarama zamanı ve mevcut çalışma süresi görüntülenebilir
* 🔔 **Abonelik Yönetimi** - Bildirimler istenildiğinde açılıp kapatılabilir
* 🛡️ **Tekrarlı Bildirim Önleme** - Aynı hibe aynı kullanıcıya tekrar tekrar gönderilmez
* ☁️ **Production Ready** - Render ve PostgreSQL üzerinde çalışacak şekilde yapılandırılmıştır
* ❤️ **Graceful Shutdown** - Bot kapatılırken devam eden görevler kontrollü şekilde sonlandırılır

---

## ⚙️ Çalışma Mantığı

İtobot sürekli olarak aşağıdaki akışla çalışır:

```text
                    FIRST Inspires
                          │
                          ▼
                   ┌───────────┐
                   │  Scraper  │
                   └─────┬─────┘
                         │
                  Hibe bilgileri
                         │
                         ▼
                ┌─────────────────┐
                │ Yeni hibe kontrol│
                └────────┬────────┘
                         │
                    Yeni hibe?
                   ┌─────┴─────┐
                   │           │
                 Hayır         Evet
                   │           │
                   │           ▼
                   │    PostgreSQL'e kaydet
                   │           │
                   │           ▼
                   │    Abone kullanıcıları bul
                   │           │
                   │           ▼
                   │    Pending bildirim oluştur
                   │           │
                   │           ▼
                   │     Telegram bildirimi
                   │           │
                   │           ▼
                   │     Gönderildi olarak işaretle
                   │
                   └──────────────►
                          │
                          ▼
                    15 dakika bekle
                          │
                          └──────► Tekrar tara
```

### Hibe tespit sistemi

Bir hibenin daha önce görülüp görülmediği kontrol edilirken hibenin:

* **Başlığı**
* **Başlangıç tarihi**
* **Bitiş tarihi**

birlikte değerlendirilir.

Bu sayede yalnızca başlığa bakılarak farklı tarih aralığına sahip hibelerin yanlış şekilde aynı hibe kabul edilmesi önlenir.

Ayrıca aynı kullanıcı için aynı hibe hakkında birden fazla bildirim oluşturulması veritabanı seviyesinde de engellenir.

---

## ⚡ Hızlı Başlangıç

### 30 saniyede başla

```text
1. Telegram'da arama kısmına @itobot_grant_tracker_bot yaz

2. /start komutunu gönder

3. "📨 Abone Ol" butonuna bas

4. Tamamlandı! ✅
```

Bundan sonra yeni FRC hibe fırsatları bulunduğunda Telegram üzerinden bildirim alırsınız.

### Canonical runtime configuration

Uygulama ayarları tek bir immutable settings nesnesi olarak startup sırasında
oluşturulur. Kaynak önceliği `process environment > local .env > varsayılanlar`
şeklindedir. `.env` yalnız `development` modunda okunur; `test`, `staging` ve
`production` secret ve ayarları explicit process/deployment environment'ından
alınır. Güncel local şablon [`.env.example`](.env.example) dosyasıdır.

| Değişken | Sözleşme / varsayılan |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Zorunlu secret |
| `DATABASE_URL` | Zorunlu PostgreSQL URL'si; secret olarak saklanır |
| `ENVIRONMENT` | `development`, `test`, `staging`, `production`; varsayılan `development` |
| `RELEASE_ID` | 1–128 karakterli release/build kimliği; varsayılan `local` |
| `CHECK_INTERVAL` | `1..86400` saniye; varsayılan `900` |
| `PORT` | `1..65535`; test modunda `0` da kabul edilir; varsayılan `8080` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; varsayılan `INFO` |
| `GRANT_URL` | Absolute HTTP(S) provider adresi |
| `PROVIDER_TIMEOUT`, `TELEGRAM_TIMEOUT`, `DATABASE_TIMEOUT` | `0.1..300` saniye |
| `POLLING_BACKLOG_POLICY` | `process` veya `discard`; varsayılan `process` |
| `OUTBOX_MAX_ATTEMPTS` | `1..100`; varsayılan `5` |
| `OUTBOX_BASE_BACKOFF`, `OUTBOX_MAX_BACKOFF` | Pozitif retry aralıkları; max değeri base'den küçük olamaz |
| `OUTBOX_LEASE_SECONDS` | `1..86400`; Telegram timeout'undan büyük olmalıdır |

Eksik veya geçersiz yapılandırma, herhangi bir secret değerini stdout/stderr'a
yazmadan değişken adını raporlar ve process'i kaynaklar başlatılmadan non-zero
exit ile durdurur.

### SMTP operasyon konfigürasyonu

v0.2.0 — Operational Grant Notifications sürümünde SMTP kanalı opsiyoneldir ve
yalnız runtime environment üzerinden yapılandırılır. Aşağıdaki altı değişken birlikte
sağlanmalıdır; değerlerini source code'a veya repository'ye yazmayın:

| Değişken | Açıklama |
| --- | --- |
| `SMTP_HOST` | SMTP provider host adı |
| `SMTP_PORT` | Provider'ın güvenli SMTP portu (`587` veya `465` gibi) |
| `SMTP_USERNAME` | SMTP kullanıcı adı |
| `SMTP_PASSWORD` | SMTP parolası; provider secret store'da tutulur |
| `SMTP_FROM` | Gönderen e-posta adresi |
| `SMTP_TO` | Virgülle ayrılabilen alıcı adresleri |

Opsiyonel `SMTP_SECURITY`, güvenli varsayılan olan `STARTTLS` değerini kullanır.
Implicit TLS isteyen provider'lar için `SSL` olarak ayarlanmalıdır. Plaintext modu
desteklenmez. `SMTP_TIMEOUT` saniye cinsinden pozitif bir ağ timeout'udur ve varsayılanı
`10` değeridir. SMTP değişkenleri hiç verilmezse e-posta kanalı kapalı kalır; kısmi veya
geçersiz config secret değerleri yazılmadan loglanır ve Telegram akışı çalışmaya devam
eder.

SMTP gönderimi bu operasyonel ara sürümde best-effort'tur. SMTP/Telegram fan-out henüz
durable/atomic değildir; kalıcı güvenilirlik çözümü architecture roadmap'indeki
Transactional Outbox görevlerinde kalır.

---

## 🤖 Bot Komutları

Bot içerisindeki temel işlemler butonlar üzerinden yapılır.

| Buton                    | Açıklama                                                          |
| ------------------------ | ----------------------------------------------------------------- |
| 📨 **Abone Ol**          | Yeni hibe bildirimlerini almaya başla                             |
| ❌ **Abone Olmaktan Çık** | Hibe bildirimlerini durdur                                        |
| ⏱️ **Sonraki Tarama**    | Bir sonraki otomatik taramaya kalan süreyi göster                 |
| 📈 **İstatistik**        | Kişisel bildirim ve bot istatistiklerini göster                   |
| 🟢 **Durum**             | Aktif kullanıcı sayısı, abonelik durumu ve sistem durumunu göster |
| ❓ **Yardım**             | Botun kullanım bilgilerini göster                                 |

---

## 📊 İstatistikler

Bot iki farklı istatistik görünümü sunar.

### 📈 İstatistik

Kullanıcılar:

* 📨 Aldıkları hibe bildirimlerinin sayısını
* 🕐 Botun son başarılı tarama zamanını
* ⏱️ Botun mevcut çalışma süresini

görebilir.

### 🟢 Bot Durumu

Genel sistem durumu:

* 👥 Aktif kullanıcı sayısı
* 🔔 Kullanıcının abonelik durumu
* 🔍 Toplam başarılı tarama sayısı
* ⚙️ Sistem çalışma durumu

görüntülenebilir.

Başarısız scraper çalışmaları toplam başarılı tarama sayısına dahil edilmez.

---

## 📁 Proje Yapısı

```text
frc-grant-tracker/

│
├── 📄 bot.py                 ← Ana Telegram botu
├── 📄 database.py            ← PostgreSQL modelleri ve işlemleri
├── 📄 scraper.py             ← FIRST hibe scraper'ı
├── 📄 smtp_notifier.py       ← Best-effort SMTP bildirim adaptörü
├── 📄 config.py              ← Konfigürasyon yönetimi
│
├── 📄 .env                   ← Environment değişkenleri
├── 📄 .gitignore             ← Git ignore kuralları
├── 📄 requirements.txt       ← Python bağımlılıkları
├── 📄 Procfile               ← Render deployment
│
├── 📚 Dokümantasyon
│   ├── README.md             ← Bu dosya
│   ├── QUICK_START.md        ← Hızlı başlangıç
│   ├── SETUP-GUIDE.md        ← Detaylı kurulum
│   └── SECURITY.md           ← Güvenlik bilgileri
```

Production ortamında tüm kalıcı veriler **PostgreSQL** üzerinde tutulur.

---

## 🔐 Güvenlik

* ✅ Telegram bot token'ı environment değişkeni üzerinden okunur
* ✅ SMTP credentials yalnız runtime environment/provider secret store'dan okunur
* ✅ Secret değerler GitHub repository'sine commit edilmez
* ✅ Environment değişkenleri production configuration için kullanılır
* ✅ SQLAlchemy ORM kullanılır
* ✅ PostgreSQL production veritabanı olarak kullanılır
* ✅ Veritabanı kimlik bilgileri kaynak kodundan ayrı tutulur

### ❌ Asla

Bot token'ını, database şifresini veya diğer secret bilgileri GitHub repository'sine commit etmeyin.

---

## 🛠️ Teknolojiler

* **Python 3.12.x** - Desteklenen çalışma zamanı
* **python-telegram-bot** - Telegram Bot API
* **BeautifulSoup4** - Web scraping
* **Requests** - HTTP istekleri
* **SQLAlchemy** - ORM
* **PostgreSQL** - Veritabanı
* **Render** - Hosting ve deployment
* **UptimeRobot** - Monitoring

---

## 🧪 Geliştirme ve Test

Desteklenen çalışma zamanı **Python 3.12.x**'tir (bkz. `.python-version`).

Temiz bir checkout'ta kurulum, compile, Ruff format, Ruff lint, production kritik
lint ve fast pytest kontrollerinin tamamını tek cross-platform komutla çalıştırın:

```bash
python scripts/quality.py
```

GitHub Actions da `main`'e açılan her pull request için aynı canonical quality
entrypoint'i çalıştırır. Merge engellemesi repository branch protection/ruleset
ayarındaki required `fast-checks` status check'ine bağlıdır.

### Paket Metadata ve Bağımlılık Grupları

`pyproject.toml`, doğrudan bağımlılıkların (`[project.dependencies]`) ve
`test`/`dev` extra gruplarının tek kaynağıdır; `dev` extra'sı `test`'i içerir
(`itobot-grant-tracker[test]`). `requirements.txt`, mevcut Render `Procfile`
akışıyla uyumluluk için elle senkron tutulan bir aynadır. `requirements.lock`,
son üretilen tam çözümün (tüm transitive bağımlılıklar dahil) birebir pin'idir
ve gerçekten tekrarlanabilir bir kurulum isteyen ortamlar için kullanılır:

```bash
pip install .            # sadece runtime
pip install .[test]      # runtime + pytest
pip install .[dev]       # runtime + test + ruff
pip install -r requirements.lock  # tam pinlenmiş, tekrarlanabilir kurulum
```

### PostgreSQL Test Altyapısı

`tests/postgres/` altındaki testler gerçek, izole bir PostgreSQL'e ihtiyaç duyar
ve `TEST_DATABASE_URL` tanımlı değilse otomatik olarak atlanır — `scripts/quality.py`
akışını etkilemezler.

Lokalde çalıştırmak için:

```bash
docker compose -f docker-compose.test.yml up -d
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/itobot_test python -m pytest tests/postgres -q
```

CI aynı testleri `postgres:16` service container'ı ile çalıştırır. Bu sürüm,
production'da kullanılan gerçek PostgreSQL major sürümüyle eşleşecek şekilde
doğrulanmıştır (GRANT-09 kapsamında Alembic baseline oluşturulurken resmi olarak
kayıt altına alınacaktır).

`TEST_DATABASE_URL` yalnızca `localhost`/`127.0.0.1` host'una ve adı `_test` ile
biten bir veritabanına işaret edebilir; aksi halde testler production'a
yanlışlıkla bağlanmayı önlemek için hemen hata verir.

---

## ☁️ Production

İtobot production ortamında Render üzerinde sürekli çalışacak şekilde yapılandırılmıştır.

```text
┌─────────────────────┐
│   FIRST Inspires    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│       Scraper       │
│       Render        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│     PostgreSQL      │
│       Render        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    Telegram Bot     │
│       Render        │
└──────────┬──────────┘
           │
           ▼
     Abone Kullanıcılar
```

Bot ayrıca Render health-check sistemi tarafından kontrol edilebilen bir HTTP health endpoint'i çalıştırır.

### Veritabanı Şema Yönetimi (Alembic)

Şema artık `bot.py` başlangıcındaki `create_all()` ile değil, Alembic migration'larıyla
yönetilir. `init_db()` artık tablo oluşturmaz; sadece şemanın migrate edildiğini
doğrular ve migrate edilmemişse net bir hatayla durur.

**⚠️ Render, Heroku'nun aksine Procfile'daki `release:` satırını çalıştırmaz.**
Migration'ların her deploy'da otomatik uygulanması için Render Dashboard'ında
servisin Settings sayfasından **"Pre-Deploy Command"** olarak
`alembic upgrade head` ayarlanmalıdır (bu özellik ücretli planlarda mevcuttur).
Bu ayar sadece Render erişimi olan biri tarafından yapılabilir.

**⚠️ Tek seferlik cutover adımı:** Yukarıdaki ayar aktif edilmeden/ilk deploy'dan
önce, gerçek production veritabanına erişimi olan biri şu komutu bir kez elle
çalıştırmalıdır:

```bash
DATABASE_URL=<production-url> python scripts/verify_and_stamp_baseline.py
```

Çıplak `alembic stamp head` KULLANILMAMALIDIR — production şeması baseline'dan
(kolon/type/nullable/constraint/index) sapmışsa fark edilmeden yanlış revizyon
işaretlenmiş olur. Bu script önce production şemasını baseline migration'ın
(`9ffc96b8fba3`) beklediği şemayla karşılaştırır:

* **Eşleşmiyorsa:** hiçbir şey yazmadan durur, farkları listeler (exit code 1).
  Go/no-go kararı burada — fark varsa production şeması düzeltilmeden stamp
  uygulanmamalıdır.
* **Eşleşiyorsa:** `alembic stamp head` çalıştırır.

Bu adım atlanırsa bot, `alembic_version` tablosu bulunamadığı için başlatılamaz. Script
mevcut tabloları silmez/yeniden oluşturmaz — sadece production'ın zaten baseline
şemayla (`users`, `grants`, `notifications`, `stats`) uyumlu olduğunu doğrulayıp işaretler.

**⚠️ AÇIK KABUL KRİTERİ — production şema envanteri henüz teslim edilmedi:**
Issue #9 / MG-001'in kabul kriteri baseline'ın **gerçek production şema envanteriyle**
eşleşmesidir. `verify_and_stamp_baseline.py` production'ı baseline migration'dan elle
çıkarılmış bir sözleşmeyle (`EXPECTED_SCHEMA`) karşılaştırıyor ve bu sözleşme gerçek bir
`alembic upgrade head` çalıştırmasına karşı test ediliyor, ama gerçek production'ın
sanitize edilmiş bir yapı envanteri henüz repository'de yok — bu, migration'dan bağımsız
bir kanıt değil. Bunun sebebi teknik bir tercih değil: ne geliştirme ortamında ne de bu
depoya erişen ekip üyelerinde gerçek production veritabanına erişim var. Bu kriter
**tek taraflı olarak kapsam dışı sayılamaz** — ya production erişimi olan biri aşağıdaki
adımı tamamlamalı, ya da issue'nun kabul kriteri projeden sorumlu kişi tarafından açıkça
gözden geçirilip onaylanmalı/değiştirilmelidir.

Production erişimi olan biri, cutover'dan önce (veya sonrasında doğrulama amacıyla) şunu
bir kez çalıştırıp çıktısını commit etmelidir:

```bash
DATABASE_URL=<production-url> ENVIRONMENT_ID=render-prod \
    python scripts/capture_schema_inventory.py > docs/production_schema_inventory.json
```

Bu script yalnızca tablo/kolon/type/nullable/constraint/index YAPISINI okur — hiçbir satır
verisi veya secret sorgulamaz/yazmaz; PostgreSQL sürümünün de yalnız major numarasını
tutar (patch/build/OS detayı sızdırmaz). Çıktı; yakalama zamanı, ortam kimliği ve şema
içeriğinin SHA-256 checksum'ını içerir, böylece envanterin ne zaman/nereden alındığı
izlenebilir olur.

### Production davranışı

* 🔍 Hibe sayfası **15 dakikada bir** kontrol edilir
* 🟢 Başarılı taramalar istatistiklere eklenir
* ⚠️ Başarısız taramalar başarılı tarama sayısına eklenmez
* 🚨 Yeni hibeler abone kullanıcılara bildirilir
* ✉️ SMTP yapılandırılmışsa yeni hibeler operasyon alıcılarına da bildirilir
* 🔁 Başarısız Telegram gönderimleri daha sonra tekrar denenebilir
* ⚠️ SMTP gönderimi best-effort'tur; başarısızlık Telegram akışını durdurmaz
* 🛑 Render tarafından gönderilen SIGTERM sinyali kontrollü şekilde işlenir

---

## 📧 İletişim

Sorular, öneriler veya geliştirme fikirleri için:

**E-posta:**

[iletisimemirhancoskun@gmail.com](mailto:iletisimemirhancoskun@gmail.com)

---

## 🙏 Teşekkürler

* [python-telegram-bot](https://python-telegram-bot.readthedocs.io/) - Telegram Bot API
* [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) - Web scraping
* [SQLAlchemy](https://www.sqlalchemy.org/) - ORM
* [FIRST Inspires](https://www.firstinspires.org/) - Grant opportunities

---

<div align="center">

**Made with ❤️ by Team İTOBOT**

**⭐ Bu projeyi beğendiysen yıldız atabilirsin!**

</div>
```
