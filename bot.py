import os
import httpx
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import date
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
BOT_TOKEN    = os.environ["BOT_TOKEN"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# ─── Web server agar tidak sleep ───────────────────────────────
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot keuangan aktif!")
    def log_message(self, format, *args):
        pass

def jalankan_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    print(f"Web server berjalan di port {port}")
    server.serve_forever()

# ─── Helper Supabase ───────────────────────────────────────────
def sb_get(table, params=None):
    with httpx.Client() as c:
        r = c.get(f"{SUPABASE_URL}/rest/v1/{table}",
                  headers=HEADERS, params=params)
    return r.json()

def sb_post(table, data):
    with httpx.Client() as c:
        r = c.post(f"{SUPABASE_URL}/rest/v1/{table}",
                   headers=HEADERS, json=data)
    return r.json()

def sb_patch(table, match, data):
    params = {k: f"eq.{v}" for k, v in match.items()}
    with httpx.Client() as c:
        r = c.patch(f"{SUPABASE_URL}/rest/v1/{table}",
                    headers=HEADERS, params=params, json=data)
    return r.status_code

# ─── Kenali user berdasarkan Telegram ID ───────────────────────
def get_user_id(telegram_id: int) -> str | None:
    """Kembalikan user_id ('suami'/'istri') atau None jika tidak dikenal."""
    rows = sb_get("telegram_users", {
        "select": "user_id,nama",
        "telegram_id": f"eq.{telegram_id}"
    })
    if isinstance(rows, list) and rows:
        return rows[0]["user_id"], rows[0]["nama"]
    return None, None

def get_dompets(user_id: str) -> dict:
    """Ambil dompet milik user tertentu."""
    rows = sb_get("dompets", {
        "select": "id,nama,saldo",
        "user_id": f"eq.{user_id}"
    })
    if not isinstance(rows, list):
        return {}
    return {row["nama"].lower(): row for row in rows}

# ─── Guard: cek user terdaftar ────────────────────────────────
async def cek_akses(update: Update) -> tuple:
    """
    Cek apakah pengirim terdaftar.
    Return (user_id, nama) atau (None, None) jika tidak dikenal.
    """
    telegram_id = update.message.from_user.id
    user_id, nama = get_user_id(telegram_id)
    if not user_id:
        await update.message.reply_text(
            "⛔ Maaf, kamu tidak terdaftar.\n"
            "Hubungi admin untuk didaftarkan.",
        )
    return user_id, nama

# ─── Command: /start ──────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id, nama = await cek_akses(update)
    if not user_id:
        return
    dompets = get_dompets(user_id)
    daftar = "\n".join([f"  • {d['nama']}" for d in dompets.values()])
    await update.message.reply_text(
        f"💰 *Bot Keuangan — {nama}*\n\n"
        f"*Format input:*\n"
        f"`keluar [jumlah] [keterangan] [kategori] [dompet]`\n"
        f"`masuk [jumlah] [keterangan] [dompet]`\n\n"
        f"*Contoh:*\n"
        f"`keluar 50000 bensin transport gopay`\n"
        f"`masuk 5000000 gaji bca`\n\n"
        f"*Dompetmu:*\n{daftar if daftar else '  (belum ada dompet)'}\n\n"
        f"*Perintah:* /saldo /bulan /bantuan",
        parse_mode="Markdown"
    )

# ─── Command: /saldo ──────────────────────────────────────────
async def cmd_saldo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id, nama = await cek_akses(update)
    if not user_id:
        return
    dompets = get_dompets(user_id)
    if not dompets:
        await update.message.reply_text("Belum ada dompet terdaftar.")
        return
    pesan = f"💳 *Saldo {nama}:*\n\n"
    total = 0
    for d in dompets.values():
        saldo = int(d["saldo"])
        total += saldo
        pesan += f"• {d['nama']}: Rp {saldo:,}\n"
    pesan += f"\n*Total: Rp {total:,}*"
    await update.message.reply_text(pesan, parse_mode="Markdown")

# ─── Command: /bulan ──────────────────────────────────────────
async def cmd_bulan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id, nama = await cek_akses(update)
    if not user_id:
        return
    hari_ini = date.today()
    awal = hari_ini.replace(day=1).isoformat()
    rows = sb_get("transaksi", {
        "select": "jumlah,jenis,kategori",
        "tanggal": f"gte.{awal}",
        "user_id": f"eq.{user_id}"
    })
    if not isinstance(rows, list):
        await update.message.reply_text("Gagal mengambil data.")
        return
    total_keluar, total_masuk, per_kat = 0, 0, {}
    for r in rows:
        j = float(r.get("jumlah", 0))
        if r.get("jenis") == "keluar":
            total_keluar += j
            k = r.get("kategori", "lainnya")
            per_kat[k] = per_kat.get(k, 0) + j
        else:
            total_masuk += j
    pesan = f"📊 *Ringkasan {hari_ini.strftime('%B %Y')} — {nama}*\n\n"
    pesan += f"✅ Pemasukan  : Rp {int(total_masuk):,}\n"
    pesan += f"❌ Pengeluaran: Rp {int(total_keluar):,}\n"
    pesan += f"💰 Selisih    : Rp {int(total_masuk - total_keluar):,}\n\n"
    if per_kat:
        pesan += "*Per Kategori:*\n"
        for k, v in sorted(per_kat.items(), key=lambda x: -x[1]):
            pesan += f"  • {k}: Rp {int(v):,}\n"
    await update.message.reply_text(pesan, parse_mode="Markdown")

# ─── Command: /bantuan ────────────────────────────────────────
async def cmd_bantuan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Panduan Bot Keuangan*\n\n"
        "*Pengeluaran:*\n`keluar 85000 sayur makan kas tunai`\n\n"
        "*Pemasukan:*\n`masuk 5000000 gaji bca`\n\n"
        "*Angka:* tanpa titik/koma (50000 bukan 50.000)\n"
        "*Dompet:* boleh sebagian nama, misal `gopay`\n\n"
        "*Kategori:*\nmakan · transport · utilitas · hiburan\n"
        "jajan · sewa · kesehatan · lainnya\n\n"
        "/saldo — cek saldo\n"
        "/bulan — ringkasan bulan ini",
        parse_mode="Markdown"
    )

# ─── Pesan biasa: input transaksi ─────────────────────────────
async def terima_pesan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id, nama = await cek_akses(update)
    if not user_id:
        return

    teks = update.message.text.strip().lower().split()
    if len(teks) < 2:
        await update.message.reply_text(
            "Format tidak dikenali.\n"
            "Contoh: `keluar 50000 bensin transport gopay`",
            parse_mode="Markdown"
        )
        return

    jenis = teks[0]
    if jenis not in ["keluar", "masuk"]:
        await update.message.reply_text(
            "Mulai dengan *keluar* atau *masuk*.",
            parse_mode="Markdown"
        )
        return

    try:
        jumlah = float(teks[1].replace(",", "").replace(".", ""))
    except ValueError:
        await update.message.reply_text(
            "Jumlah tidak valid. Contoh: `50000`",
            parse_mode="Markdown"
        )
        return

    keterangan  = teks[2] if len(teks) > 2 else "tidak ada keterangan"
    kategori    = teks[3] if len(teks) > 3 else "lainnya"
    dompet_cari = " ".join(teks[4:]) if len(teks) > 4 else ""

    # Cari dompet milik user ini
    dompets = get_dompets(user_id)
    dompet_id, dompet_nama, saldo_lama = None, "Kas Tunai", 0
    for nama_d, data in dompets.items():
        if dompet_cari in nama_d or nama_d in dompet_cari or dompet_cari == "":
            dompet_id   = data["id"]
            dompet_nama = data["nama"]
            saldo_lama  = float(data["saldo"])
            break
    if not dompet_id and dompets:
        first = next(iter(dompets.values()))
        dompet_id, dompet_nama, saldo_lama = first["id"], first["nama"], float(first["saldo"])

    # Simpan transaksi dengan user_id
    sb_post("transaksi", {
        "tanggal"     : date.today().isoformat(),
        "keterangan"  : keterangan,
        "jumlah"      : jumlah,
        "jenis"       : jenis,
        "kategori"    : kategori,
        "dompet_id"   : dompet_id,
        "user_id"     : user_id,
        "sumber"      : "bot",
        "diverifikasi": False
    })

    # Update saldo dompet
    saldo_baru = saldo_lama - jumlah if jenis == "keluar" else saldo_lama + jumlah
    sb_patch("dompets", {"id": dompet_id}, {"saldo": saldo_baru})

    emoji = "💸" if jenis == "keluar" else "💰"
    tanda = "-" if jenis == "keluar" else "+"
    await update.message.reply_text(
        f"{emoji} *{'Pengeluaran' if jenis=='keluar' else 'Pemasukan'} tersimpan!*\n\n"
        f"📝 {keterangan.capitalize()}\n"
        f"💵 {tanda}Rp {int(jumlah):,}\n"
        f"🏷️ Kategori  : {kategori}\n"
        f"👛 Dompet    : {dompet_nama}\n"
        f"💳 Saldo baru: Rp {int(saldo_baru):,}\n\n"
        f"_Data masuk ke dashboard {nama}_",
        parse_mode="Markdown"
    )

# ─── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    t = threading.Thread(target=jalankan_web_server, daemon=True)
    t.start()
    print("Bot keuangan berjalan...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("saldo",   cmd_saldo))
    app.add_handler(CommandHandler("bulan",   cmd_bulan))
    app.add_handler(CommandHandler("bantuan", cmd_bantuan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, terima_pesan))
    app.run_polling()
