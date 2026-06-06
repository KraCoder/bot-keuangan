# 💰 Bot Keuangan

Bot Telegram untuk mencatat dan mengelola transaksi keuangan pribadi dengan mudah. Semua data disimpan secara aman di database Supabase.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Telegram Bot](https://img.shields.io/badge/Telegram%20Bot-API-blue)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Fitur

- 📊 **Catat Transaksi** - Pengeluaran dan pemasukan dengan keterangan, kategori, dan dompet
- 💳 **Kelola Dompet** - Multiple dompet/akun dengan saldo real-time
- 📈 **Ringkasan Bulanan** - Laporan pengeluaran per kategori
- 🔒 **Autentikasi** - Validasi user via Telegram ID
- 🌐 **Cloud Database** - Data tersimpan di Supabase
- 🛡️ **Akses Kontrol** - Hanya user terdaftar yang bisa menggunakan bot

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Telegram Bot Token (dari [@BotFather](https://t.me/BotFather))
- Supabase account dengan database
- Hosting platform (Render, Railway, Heroku, dll)

### Installation

1. **Clone repository**
   ```bash
   git clone https://github.com/yourusername/bot-keuangan.git
   cd bot-keuangan
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup environment variables**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` dengan:
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-supabase-key
   BOT_TOKEN=your-telegram-bot-token
   PORT=8080
   ```

4. **Jalankan bot**
   ```bash
   python bot.py
   ```

---

## 🛠️ Setup Database (Supabase)

### Buat 3 tabel berikut:

#### 1. `telegram_users`
```sql
CREATE TABLE telegram_users (
  id BIGSERIAL PRIMARY KEY,
  telegram_id BIGINT UNIQUE NOT NULL,
  user_id UUID NOT NULL REFERENCES auth.users(id),
  nama VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### 2. `dompets`
```sql
CREATE TABLE dompets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  nama VARCHAR(255) NOT NULL,
  saldo BIGINT DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW()
);
```

#### 3. `transaksi`
```sql
CREATE TABLE transaksi (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id),
  dompet_id UUID NOT NULL REFERENCES dompets(id),
  tanggal DATE NOT NULL,
  jumlah BIGINT NOT NULL,
  jenis VARCHAR(50) NOT NULL CHECK (jenis IN ('masuk', 'keluar')),
  kategori VARCHAR(100) NOT NULL,
  keterangan VARCHAR(500),
  sumber VARCHAR(50) DEFAULT 'bot',
  diverifikasi BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP DEFAULT NOW()
);
```

### Enable Row Level Security (RLS)
Pastikan setiap user hanya bisa akses data mereka sendiri.

---

## 📱 Cara Penggunaan

### Commands

| Perintah | Deskripsi |
|----------|-----------|
| `/start` | Menu utama dan daftar dompet |
| `/saldo` | Cek saldo semua dompet |
| `/bulan` | Ringkasan transaksi bulan ini |
| `/bantuan` | Panduan lengkap |

### Format Input

#### Pengeluaran
```
keluar [jumlah] [keterangan] [kategori] [dompet]
```
**Contoh:**
```
keluar 50000 bensin transport gopay
keluar 75000 makan makan kas tunai
```

#### Pemasukan
```
masuk [jumlah] [keterangan] [dompet]
```
**Contoh:**
```
masuk 5000000 gaji bca
masuk 500000 freelance gopay
```

### Parameter

- **jumlah**: Angka tanpa titik/koma (e.g., `50000` bukan `50.000`)
- **keterangan**: Deskripsi singkat transaksi
- **kategori**: Kategori pengeluaran (lihat tabel di bawah)
- **dompet**: Nama dompet (bisa partial match, e.g., `gopay` untuk "GoPay")

### Kategori Pengeluaran

```
makan · transport · utilitas · hiburan
jajan · sewa · kesehatan · lainnya
```

---

## 📊 Contoh Penggunaan

### 1. Catat pengeluaran untuk bensin
```
User: keluar 85000 bensin transport gopay

Bot: 💸 Pengeluaran tersimpan!

📝 Bensin
💵 -Rp 85.000
🏷️ Kategori  : transport
👛 Dompet    : GoPay
💳 Saldo baru: Rp 1.915.000

_Masuk ke dashboard Akbar_
```

### 2. Catat pemasukan gaji
```
User: masuk 5000000 gaji bca

Bot: 💰 Pemasukan tersimpan!

📝 Gaji
💵 +Rp 5.000.000
🏷️ Kategori  : (tidak ada kategori)
👛 Dompet    : BCA
💳 Saldo baru: Rp 6.000.000

_Masuk ke dashboard Akbar_
```

### 3. Cek saldo
```
User: /saldo

Bot: 💳 Saldo Akbar:

• GoPay: Rp 1.915.000
• BCA: Rp 6.000.000
• Kas Tunai: Rp 500.000

Total: Rp 8.415.000
```

### 4. Ringkasan bulanan
```
User: /bulan

Bot: 📊 Ringkasan June 2026 — Akbar

✅ Pemasukan  : Rp 5.500.000
❌ Pengeluaran: Rp 650.000
💰 Selisih    : Rp 4.850.000

Per Kategori:
  • transport: Rp 400.000
  • makan: Rp 200.000
  • jajan: Rp 50.000
```

---

## 🏗️ Arsitektur

```
┌─────────────────────────────────┐
│      Telegram User              │
│  (/start, /saldo, messages)    │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│     Bot Keuangan (Python)       │
│  - Command Handler              │
│  - Message Parser               │
│  - Validation                   │
└──────────┬──────────────────────┘
           │
      ┌────┴────────────────────┐
      ▼                         ▼
┌──────────────────┐  ┌────────────────────┐
│  HTTP Request    │  │  HTTP Server       │
│  (Supabase API)  │  │  (Keep Alive)      │
└────────┬─────────┘  └────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│    Supabase Database            │
│  - telegram_users               │
│  - dompets                       │
│  - transaksi                     │
└─────────────────────────────────┘
```

---

## 📦 Dependencies

```
python-telegram-bot==20.7   # Telegram Bot API
httpx==0.25.2              # HTTP Client
```

Install semua dependencies:
```bash
pip install -r requirements.txt
```

---

## ⚙️ Konfigurasi

### Environment Variables

| Variable | Deskripsi | Contoh |
|----------|-----------|--------|
| `SUPABASE_URL` | URL Supabase project | `https://xxx.supabase.co` |
| `SUPABASE_KEY` | API Key Supabase | `eyJhbGc...` |
| `BOT_TOKEN` | Token Telegram Bot | `123456:ABC-DEF...` |
| `PORT` | Port untuk web server | `8080` |

### Timeout & Rate Limiting

- API timeout: 10 detik
- Bot polling: real-time
- No built-in rate limiting (dapat ditambahkan)

---

## 🔒 Keamanan

- ✅ **User Authentication**: Validasi Telegram ID sebelum akses
- ✅ **Database Access**: Menggunakan API Key dengan permissions terbatas
- ✅ **Input Validation**: Validasi format dan tipe data transaksi
- ✅ **RLS Policy**: Row-level security di Supabase
- ⚠️ **TODO**: Tambahkan rate limiting per user
- ⚠️ **TODO**: Enkripsi sensitive data

---

## 🚀 Deployment

### Option 1: Render
1. Push code ke GitHub
2. Create New Web Service di Render
3. Connect ke GitHub repository
4. Set environment variables di Render dashboard
5. Deploy

### Option 2: Railway
1. Clone repository
2. `railway login`
3. `railway init`
4. `railway variables` (set env vars)
5. `railway up`

### Option 3: Heroku
```bash
heroku login
heroku create bot-keuangan
heroku config:set SUPABASE_URL="..." BOT_TOKEN="..."
git push heroku main
```

---

## 🔄 Fitur yang Akan Datang

- [ ] Edit/delete transaksi
- [ ] Export laporan (CSV, PDF)
- [ ] Budget setting per kategori
- [ ] Notifikasi reminder
- [ ] Multi-bahasa support
- [ ] Voice message support
- [ ] Integrasi expense split

---

## 🐛 Troubleshooting

### Bot tidak merespons
- Cek bot token valid
- Pastikan bot sudah started (`/start`)
- Cek internet connection

### Error "Kamu belum terdaftar"
- Telegram ID Anda belum terdaftar di `telegram_users`
- Hubungi admin dengan Telegram ID Anda

### Saldo tidak update
- Refresh saldo dengan `/saldo`
- Cek Supabase connection
- Cek API key dan permissions

### Web server error
- Pastikan PORT tidak digunakan
- Default PORT: 8080

---

## 📝 Struktur Kode

```
bot-keuangan/
├── bot.py                 # Main bot logic
├── requirements.txt       # Dependencies
├── README.md             # Dokumentasi
└── .env.example          # Environment template
```

### Modul Utama

- `PingHandler`: HTTP handler untuk keep-alive
- `sb_get/post/patch`: Supabase API wrappers
- `get_user_info`: Mapping Telegram ID → User
- `cmd_start/saldo/bulan/bantuan`: Command handlers
- `terima_pesan`: Message parser dan transaction handler

---

## 📄 License

MIT License - silakan gunakan, modifikasi, dan distribusikan sesuai kebutuhan.

---

## 👤 Author

**Akbar Ridho**
- GitHub: [@akbarridho](https://github.com/akbarridho)
- Telegram: [@akbarr](https://t.me/akbarr)

---

## 🤝 Kontribusi

Kontribusi sangat welcome! Cara berkontribusi:

1. Fork repository
2. Buat feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push ke branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

---

## 📮 Support

Jika ada pertanyaan atau bug, silakan buat [Issue](https://github.com/yourusername/bot-keuangan/issues) atau hubungi author.

---

**Made with ❤️ for personal finance tracking**
