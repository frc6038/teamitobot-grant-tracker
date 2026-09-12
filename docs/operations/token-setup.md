# Token Setup and Validation

Bu doküman, İTOBOT Grant Tracker için Telegram bot token'ının canonical yapılandırma ve doğrulama akışını tanımlar.

## 1. Canonical Secret Flow

Telegram bot token'ı uygulamanın configuration kaynağıdır ve runtime environment üzerinden sağlanır.

Canonical akış:

```text
Telegram / BotFather
        │
        │ Bot token
        ▼
Deployment Provider / Secret Store
        │
        │ TELEGRAM_BOT_TOKEN
        ▼
Process Environment
        │
        ▼
Application Bootstrap
        │
        ▼
Typed Settings
```

Production ortamında `TELEGRAM_BOT_TOKEN`, provider'ın environment/secret mekanizması üzerinden tanımlanmalıdır.

Token:

* source code içine yazılmamalıdır.
* Git repository'sine commit edilmemelidir.
* README, issue, log veya test çıktısına yazılmamalıdır.
* command-line argümanı olarak verilmemelidir.
* kalıcı bir token dosyasına yazılmamalıdır.

`TELEGRAM_BOT_TOKEN` uygulama tarafından startup sırasında environment'tan okunur ve typed settings yapısına aktarılır.

Production ortamlarında `.env` dosyası configuration kaynağı değildir. Secret değerleri deployment provider'ın secret/environment yönetiminden sağlanmalıdır.

Development ortamında `.env` kullanılabilir; bu dosya yalnızca local development configuration akışının bir parçasıdır ve repository'ye commit edilmemelidir.

## 2. Required Environment Variable

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram Bot API authentication token |

Eksik veya geçersiz configuration uygulamanın startup sırasında non-zero exit ile durmasına neden olur.

Configuration hataları secret değerini göstermez. Yalnızca ilgili environment variable'ın adı raporlanabilir.

## 3. Optional Token Validator

Repository, token'ın Telegram Bot API tarafından kabul edilip edilmediğini kontrol etmek için non-persisting bir validator CLI içerir.

Çalıştırma:

```bash
python -m tools.token_setup
```

CLI yalnızca mevcut process environment'ındaki:

```text
TELEGRAM_BOT_TOKEN
```

değerini okur.

Validator:

1. Environment variable'ın mevcut olup olmadığını kontrol eder.
2. Token'ın yerel olarak tanınabilir Telegram token formatına uyup uymadığını kontrol eder.
3. Telegram Bot API `getMe` endpoint'ine istek gönderir.
4. Sonucu `VALID`, `INVALID` veya `UNAVAILABLE` olarak sınıflandırır.
5. Token'ı hiçbir zaman stdout/stderr çıktısına yazmaz.
6. Token'ı dosyaya kaydetmez.
7. Token'ı validation sonucunda saklamaz.
8. Token'ı exception mesajına dahil etmez.

CLI, token kurulumunun zorunlu bir parçası değildir. Deployment provider'ın secret/environment yönetimi canonical configuration kaynağı olmaya devam eder.

## 4. Validation Results

Validator üç güvenli sonuç üretir.

### Valid

Telegram Bot API başarılı bir `getMe` yanıtı verdiğinde sonuç `VALID` olarak sınıflandırılır.

Başarılı yanıt yalnızca HTTP `200` status code ile belirlenmez. Yanıtın JSON gövdesi:

* bir object/dictionary olmalı,
* `ok` alanı boolean `true` olmalı,
* `result` alanı bir object/dictionary olmalıdır.

Örnek olarak aşağıdaki yanıt başarılı kabul edilmez:

```json
{
  "ok": true
}
```

Bu tür bir yanıt `UNAVAILABLE` olarak sınıflandırılır.

Başarılı sonuç mesajı:

```text
Telegram bot token is valid.
```

Process exit code:

```text
0
```

Bu sonuç, Telegram'ın verilen token'ı kabul ettiğini gösterir.

### Invalid

Aşağıdaki durumlarda token `INVALID` olarak sınıflandırılır:

* Environment variable hiç sağlanmamışsa,
* Token yerel format kontrolünden geçemiyorsa,
* Telegram açıkça HTTP `401 Unauthorized` döndürüyorsa.

Sonuç:

```text
invalid
```

Process exit code:

```text
1
```

HTTP `401 Unauthorized`, token'ın Telegram tarafından geçersiz kabul edildiğini gösteren açık bir kanıttır.

### Unavailable

Aşağıdaki durumlarda token'ın kendisinin geçersiz olduğu sonucuna varılmaz:

* Network bağlantı hatası,
* timeout,
* Telegram server hatası,
* rate limiting,
* beklenmeyen HTTP status code,
* geçerli olmayan veya beklenmeyen JSON response,
* HTTP `200` olup `ok` alanı `true` olmayan response,
* HTTP `200` olup `result` alanı bulunmayan veya object olmayan response.

Bu durumda:

```text
Telegram Bot API could not be reached or returned an unexpected response.
```

mesajı verilir.

Process exit code:

```text
2
```

HTTP `401` dışındaki beklenmeyen status code'lar `UNAVAILABLE` olarak sınıflandırılır. Örneğin HTTP `400`, `403`, `404`, `429` ve `5xx` yanıtları, kod tarafından açıkça `401` olarak değerlendirilmediği sürece `UNAVAILABLE` sonucuna gider.

Bu ayrım önemlidir:

```text
401 Unauthorized
    → token geçersiz

Network / timeout / server / unexpected response
    → token'ın geçersiz olduğu kanıtlanmadı
```

Bir API outage veya network problemi yalnızca token problemi olarak raporlanmamalıdır.

## 5. Non-Disclosure Rules

Validator'ın temel güvenlik sözleşmesi token değerinin disclosure edilmemesidir.

Token:

* stdout'a yazılmaz.
* stderr'a yazılmaz.
* exception mesajına yazılmaz.
* validation result içinde tutulmaz.
* dosyaya yazılmaz.
* CLI argümanı olarak alınmaz.
* log mesajlarına dahil edilmez.

HTTP isteği oluşturulurken token, Telegram API isteğinin URL'sinde geçici olarak bulunabilir. Ancak bu URL hiçbir şekilde kullanıcıya gösterilmemeli, stdout/stderr çıktısına, exception mesajına, loglara, test sonuçlarına veya kalıcı dosya içeriğine aktarılmamalıdır.

Test suite bu davranışları özellikle doğrular.

## 6. File Creation Contract

Validator herhangi bir token dosyası oluşturmaz.

Özellikle aşağıdaki workflow canonical değildir:

```text
token
  ↓
token.json
  ↓
Flask setup application
  ↓
bot
```

Token'ın plaintext dosyada saklanması bu repository'nin configuration mimarisiyle uyumlu değildir.

Validator'ın amacı token'ı **saklamak değil, doğrulamaktır**.

## 7. Deprecated Flask Token Setup

Eski Flask tabanlı token setup workflow'u canonical configuration kaynağı değildir.

Eski workflow'un temel problemi token'ın local plaintext dosyasına yazılması ve bunun runtime configuration mimarisiyle ayrışmasıdır.

Yeni canonical workflow:

```text
Provider Secret Store / Process Environment
                    │
                    ▼
              Application
```

Opsiyonel validation:

```text
Process Environment
        │
        ▼
Token Validator
        │
        ▼
Telegram getMe
```

Eski Flask/token-file workflow'u yeni deployment'larda kullanılmamalıdır.

Eski setup uygulamasının archive/delete işlemi, yeni canonical Render workflow'u production'da başarıyla doğrulandıktan sonra ve Software Captain onayıyla ayrı bir repository operasyonu olarak gerçekleştirilmelidir.

## 8. Production Render Operations

Production'daki canonical secret workflow, repository'deki Flask/file-based token setup workflow'undan bağımsız olarak Render environment/secret yönetimi üzerinden yürütülür.

### 8.1 Initial Secret Setup

Production Render service linked to this repository için:

1. Render Dashboard'da production service'i açın.
2. `Environment` bölümüne gidin.
3. Environment Variables altında `TELEGRAM_BOT_TOKEN` değişkenini ekleyin veya mevcut değeri güncelleyin.
4. Token değerini yalnızca Render'ın secret/environment alanına girin.
5. Değişiklik için `Save and deploy` seçeneğini kullanın. Secret değişikliğinin deploy edilmeden production runtime'a uygulanacağı varsayılmamalıdır.
6. Deploy tamamlandıktan sonra `Deploys` bölümünden ilgili deploy'un başarılı olduğunu doğrulayın.
7. Service logs içinde token değerinin görünmediğini kontrol edin.

Render'daki environment variable değişiklikleri için `Save and deploy` mevcut build'i yeni environment değerleriyle yeniden deploy eder. `Save only` seçilirse yeni değer bir sonraki deploy'a kadar service tarafından kullanılmaz.

### 8.2 Token Validation

Gerekirse token, controlled bir operator environment'ında non-persisting validator ile doğrulanabilir:

```bash
python -m tools.token_setup
```

Validator token'ı yalnızca `TELEGRAM_BOT_TOKEN` process environment'ından okur.

Token:

* command-line argument olarak verilmemelidir.
* shell history'ye yazılmamalıdır.
* source code'a veya repository dosyasına yazılmamalıdır.
* loglara veya deployment çıktısına yazılmamalıdır.

Production Render environment'ında token'ın kendisini loglamak veya ekrana çıkarmak yerine service'in başarılı şekilde deploy olup startup configuration validation'dan geçmesi doğrulanmalıdır.

### 8.3 Secret Rotation

Telegram bot token'ının yenilenmesi, kimlik bilgisi değiştirme işlemidir. Uygulamanın deployment işlemini geri alma işlemiyle aynı işlem olarak değerlendirilmemelidir.

İşleme başlamadan önce:

- Yenileme işleminden sorumlu kişi ve gerektiğinde ulaşılacak kişi belirlenmelidir.
- Standart kurulumda canonical secret source olarak Render servis Environment Variables alanı doğrulanmalıdır.
- Onaylanmış bir Environment Group kullanılıyorsa bunun canonical secret source olup olmadığı doğrulanmalıdır.
- Render ve BotFather erişiminin hazır olduğu kontrol edilmelidir.
- Gerçek token; loglara, terminal geçmişine, kaynak koduna, ekran görüntülerine, sohbet mesajlarına, ticket'lara, issue'lara, pull request'lere veya review yorumlarına yazılmamalıdır.

Yenileme sırası:

1. Bakım zamanı, sorumlu kişi ve gerektiğinde ulaşılacak kişi belirlenmelidir.
2. BotFather üzerinden yeni ve geçerli bir token oluşturulmalıdır.
3. Token oluşturma veya iptal etme işleminin anında etkili olan bir kimlik bilgisi değişikliği olduğu kabul edilmelidir.
4. İptal edilmiş eski token'ın artık geçerli olmadığı ve rollback için kullanılamayacağı unutulmamalıdır.
5. `TELEGRAM_BOT_TOKEN`, canonical Render secret source içinde güncellenmelidir.
6. Değişiklik kaydedilmeli ve servis yeniden deploy edilmelidir.
7. Deployment işleminin başarıyla tamamlandığı doğrulanmalıdır.
8. Uygulamanın başlatılması ve sağlık kontrolleri doğrulanmalıdır.
9. Telegram kimlik doğrulaması, uygulamanın token'ı açığa çıkarmayan başlangıç doğrulaması veya `getMe` tabanlı doğrulama yöntemiyle kontrol edilmelidir.
10. Loglarda ve deployment çıktısında token bulunmadığı doğrulanmalıdır.
11. Doğrulama başarısız olursa olay eskale edilmelidir. İptal edilmiş eski token geri yüklenmemelidir. BotFather üzerinden yeni ve geçerli bir token oluşturulmalı, canonical secret source güncellenmeli, yeniden deploy edilmeli ve doğrulama adımları tekrarlanmalıdır.

Yeni token'ı güncelleme ve deploy etme süreci hazır olmadan geçerli token iptal edilmemelidir.

Bir token iptal edildikten sonra eski değer kullanılamaz kabul edilmelidir. Eski token'ın önceki bir deployment içinde bulunması, onu geçerli bir kurtarma seçeneğine dönüştürmez.

### 8.4 Rollback

Render deployment rollback işlemi ile Telegram token yenileme işlemi farklı işlemlerdir ve farklı güvenlik kurallarına sahiptir.

Render rollback işlemi, hedef deployment'a ait build çıktısını yeniden kullanabilir. Ayrıca hedef deployment'a ait servis özelindeki Environment Variables değerlerini de geri getirebilir. Bu nedenle token yenilemesinden önceki bir deployment'a dönmek, eski bir `TELEGRAM_BOT_TOKEN` değerinin tekrar kullanılmasına neden olabilir.

Kod rollback işlemi, iptal edilmiş veya geçersiz bir Telegram token'ını kurtarmak için kullanılmamalıdır.

Olay türü birbirinden ayrılmalıdır:

- Kod veya uygulama hatası varsa Render deployment rollback gerekebilir.
- İptal edilmiş veya geçersiz token, eski deployment'a dönülerek kurtarılmamalıdır.
- İptal edilmiş token geçerli bir rollback kimlik bilgisi değildir.
- Mevcut token kaybedilmiş, geçersiz hâle gelmiş veya iptal edilmişse BotFather üzerinden yeni ve geçerli bir token oluşturulmalıdır.

Kod rollback sırası:

1. Sorunun kimlik bilgisi değil, kod veya deployment kaynaklı olduğu doğrulanmalıdır.
2. Başarılı olan hedef deployment belirlenmelidir.
3. Mevcut geçerli token'ın kaynağı, token değeri açığa çıkarılmadan belirlenmelidir.
4. Render deployment rollback işlemi başlatılmalıdır.
5. Rollback işleminin hedef deployment'a ait servis özelindeki Environment Variables değerlerini geri getirebileceği kabul edilmelidir.
6. Geçerli `TELEGRAM_BOT_TOKEN`, canonical secret source içinde açıkça yeniden uygulanmalıdır.
7. Değişiklik kaydedilmeli ve servis yeniden deploy edilmelidir.
8. Uygulamanın başlangıcı, Telegram kimlik doğrulaması, sağlık kontrolleri ve loglar doğrulanmalıdır.
9. Geçerli token açıkça yeniden uygulanıp başarıyla doğrulanmadan rollback işlemi tamamlanmış kabul edilmemelidir.

Environment Group ile ilgili hususlar:

- Render rollback işlemi Environment Group içindeki değerleri doğrudan değiştirmez.
- Ancak rollback, hedef deployment'a bağlı Environment Group bağlantılarını değiştirebilir.
- Rollback sonrasında etkin Environment kaynağı doğrulanmalı ve amaçlanan geçerli token'ın kullanıldığı kontrol edilmelidir.
- Kontrol listesinde tam olarak bir canonical token source belirtilmelidir.
- Servis değişkenleri, Environment Group, yerel yapılandırma ve deployment'a özel ayarlar arasında birbiriyle yarışan token değerleri bulunmamalıdır.

### 8.5 Cutover from the Deprecated Workflow

Yeni canonical workflow production'da başarıyla doğrulanmadan eski Flask/file-based token setup workflow'u kaldırılmamalıdır.

Cutover sırası:

1. Render environment/secret configuration'ı tamamlayın.
2. Production service'i yeni canonical configuration ile deploy edin.
3. Startup configuration validation ve service health durumunu doğrulayın.
4. `TELEGRAM_BOT_TOKEN` değerinin yalnızca provider environment/secret yönetiminden geldiğini doğrulayın.
5. Production'ın Flask/token-file workflow'una bağımlı olmadığını doğrulayın.
6. Başarılı cutover sonrasında eski Flask/file-based setup workflow'unu production configuration kaynağı olarak tamamen devre dışı bırakın.
7. Eski setup repository'sinin archive veya delete edilmesi gerekiyorsa bu işlem Software Captain onayıyla ayrı bir repository operasyonu olarak gerçekleştirilmelidir.

Eski workflow, yeni canonical workflow başarıyla doğrulanmadan production'dan kaldırılmamalıdır.

### 8.6 Production Secret Checklist

Her secret kurulumu veya rotation işleminden sonra:

* [ ] `TELEGRAM_BOT_TOKEN` Render production service environment'ında tanımlı.
* [ ] Değişiklik `Save and deploy` ile production'a uygulandı.
* [ ] Deploy başarıyla tamamlandı.
* [ ] Service logs içinde token değeri bulunmuyor.
* [ ] Application startup configuration validation başarılı.
* [ ] Service health/status kontrolleri başarılı.
* [ ] Token command-line argument olarak kullanılmadı.
* [ ] Token repository veya plaintext dosyaya yazılmadı.
* [ ] Eski Flask/file-based workflow production configuration kaynağı olarak kullanılmıyor.
* [ ] Yenileme sonrasında eski token'ın artık kullanılmadığı doğrulandı.
* [ ] İptal edilmiş eski token'ın rollback için kullanılmayacağı doğrulandı.
* [ ] Yeni token'ın canonical secret source içinde açıkça uygulandığı ve doğrulandığı kontrol edildi.

### 8.7 Protection of Confidential Information

Gerçek Telegram bot token'ı aşağıdaki alanların hiçbirinde bulunmamalıdır:

- Uygulama logları
- Deployment logları
- Terminal geçmişi
- Komut satırı argümanları
- Kaynak kodu
- Commit edilmiş yapılandırma dosyaları
- Commit edilmiş `.env` dosyaları
- Ekran görüntüleri
- GitHub issue'ları
- Pull request'ler
- Review yorumları
- Olay kayıtları
- Support ticket'ları
- Sohbet mesajları

Yalnızca token'ı açığa çıkarmayan, maskelenmiş durum bilgileri ve doğrulama sonuçları kullanılmalıdır.

Token yalnızca onaylanmış secret-management arayüzü üzerinden veya yerel doğrulama işlemi açıkça gerektiriyorsa process environment aracılığıyla girilmelidir.

## 9. Production Setup Checklist

Production deployment öncesinde:

* [ ] `TELEGRAM_BOT_TOKEN` provider secret/environment alanında tanımlandı.
* [ ] Token source code'a yazılmadı.
* [ ] Token repository'ye commit edilmedi.
* [ ] Token herhangi bir plaintext dosyaya yazılmadı.
* [ ] `DATABASE_URL` provider secret/environment alanında tanımlandı.
* [ ] Application startup configuration validation'dan geçiyor.
* [ ] Gerekirse `python -m tools.token_setup` ile token doğrulandı.
* [ ] Validator çıktısında token değeri bulunmadığı kontrol edildi.
* [ ] Eski Flask/token-file setup workflow'u production configuration kaynağı olarak kullanılmıyor.

## 10. Local Validation

Local validation yapılacaksa validator process environment'ındaki `TELEGRAM_BOT_TOKEN` değerini kullanır.

Secret değerini command-line argümanı olarak vermeyin.

Örneğin aşağıdaki kullanım canonical değildir:

```bash
python -m tools.token_setup 123456789:secret
```

Validator bu kullanım şeklini desteklemez.

Token, process environment üzerinden sağlanmalıdır.

Windows, Linux veya CI/CD ortamında environment variable'ın nasıl tanımlanacağı kullanılan shell, IDE veya deployment provider'a göre değişebilir. Önemli olan token'ın process environment'a secret olarak aktarılması ve command-line/history, source code veya repository dosyalarına yazılmamasıdır.

## 11. Verification

Token setup değişikliklerinden sonra repository quality gate çalıştırılmalıdır:

```bash
ruff check .
ruff format --check .
pytest -v
```

Beklenen sonuç:

* Ruff lint başarılı.
* Ruff format kontrolü başarılı.
* Token setup testleri başarılı.
* Packaging testleri başarılı.
* Full test suite başarısız olmamalı.

Packaging ve end-to-end testleri validator'ın kurulu wheel üzerinden çalıştırılmasını doğrular.

Testler ayrıca:

* CLI'nin çağıran çalışma dizininden bağımsız çalıştığını,
* `INVALID`, `UNAVAILABLE` ve `VALID` sonuçlarının doğru exit code ürettiğini,
* Token'ın stdout veya stderr çıktısına sızmadığını,
* Repository root path'inin çıktıya sızmadığını,
* CLI çalışırken token dosyası oluşturulmadığını,
* Geçici çalışma dizininin işlem sonrasında boş kaldığını,
* Network, unauthorized ve malformed response senaryolarının birbirinden doğru şekilde ayrıldığını

doğrular.

Token validator'ın davranışı özellikle aşağıdaki sözleşmelerle korunur:

* valid token → `VALID`
* explicit HTTP 401 → `INVALID`
* network/provider failure → `UNAVAILABLE`
* malformed successful HTTP response → `UNAVAILABLE`
* unexpected HTTP response → `UNAVAILABLE`
* token disclosure → yasak
* token persistence → yasak
* token file creation → yasak
* CLI token argument → desteklenmez