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

# ─── Konfigurasi ───────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
BOT_TOKEN    = os.environ["BOT_TOKEN"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# ─── Web server kecil agar Render tidak sleep ──────────────────
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot keuangan aktif!")
    def log_message(self, format, *args):
        pass  # sembunyikan log request

def jalankan_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    print(f"Web server berjalan di port {port}")
    server.serve_forever()

# ─── Helper Supabase ───────────────────────────────────────────
def sb_get(table, params=None):
    with httpx.Client() as c:
        r = c.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=params)
    return r.json()

def sb_post(table, data):
    with httpx.Client() as c:
        r = c.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, json=data)
    return r.json()

def sb_patch(table, match, data):
    params = {k: f"eq.{v}" for k, v in match.items()}
    with httpx.Client() as c:
        r = c.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=HEADERS, params=params, json=data)
    return r.status_code

def get_dompets():
    rows = sb_get("dompets", {"select": "id,nama,saldo"})
    if not isinstance(rows, list):
        return {}
    return {row["nama"].lower(): row for row in rows}

# ─── Command handlers ──────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    dompets = get_dompets()
    daftar = "\n".join([f"  • {d['nama']}" for d in dompets.values()])
    pesan = (
        "💰 *Bot Keuangan Keluarga*\n\n"
        "*Format input transaksi:*\n"
        "`keluar [jumlah] [keterangan] [kategori] [dompet]`\n"
        "`masuk [jumlah] [keterangan] [dompet]`\n\n"
        "*Contoh:*\n"
        "`keluar 50000 bensin transport gopay`\n"
        "`masuk 5000000 gaji bca suami`\n\n"
        "*Kategori tersedia:*\n"
        "  makan · transport · utilitas · hiburan\n"
        "  jajan · sewa · kesehatan · lainnya\n\n"
        f"*Dompet tersedia:*\n{daftar}\n\n"
        "*Perintah lain:*\n"
        "/saldo — lihat semua saldo\n"
        "/bulan — ringkasan bulan ini\n"
        "/bantuan — panduan lengkap"
    )
    await update.message.reply_text(pesan, parse_mode="Markdown")

async def cmd_saldo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    dompets = get_dompets()
    if not dompets:
        await update.message.reply_text("Belum ada data dompet.")
        return
    pesan = "💳 *Saldo Semua Dompet:*\n\n"
    total = 0
    for d in dompets.values():
        saldo = int(d["saldo"])
        total += saldo
        pesan += f"• {d['nama']}: Rp {saldo:,}\n"
    pesan += f"\n*Total: Rp {total:,}*"
    await update.message.reply_text(pesan, parse_mode="Markdown")

async def cmd_bulan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    hari_ini = date.today()
    awal_bulan = hari_ini.replace(day=1).isoformat()
    rows = sb_get("transaksi", {
        "select": "jumlah,jenis,kategori",
        "tanggal": f"gte.{awal_bulan}"
    })
    if not isinstance(rows, list):
        await update.message.reply_text("Gagal mengambil data.")
        return
    total_keluar, total_masuk, per_kategori = 0, 0, {}
    for r in rows:
        jumlah = float(r.get("jumlah", 0))
        if r.get("jenis") == "keluar":
            total_keluar += jumlah
            kat = r.get("kategori", "lainnya")
            per_kategori[kat] = per_kategori.get(kat, 0) + jumlah
        else:
            total_masuk += jumlah
    bulan_nama = hari_ini.strftime("%B %Y")
    pesan = f"📊 *Ringkasan {bulan_nama}*\n\n"
    pesan += f"✅ Pemasukan : Rp {int(total_masuk):,}\n"
    pesan += f"❌ Pengeluaran: Rp {int(total_keluar):,}\n"
    pesan += f"💰 Selisih   : Rp {int(total_masuk - total_keluar):,}\n\n"
    if per_kategori:
        pesan += "*Pengeluaran per Kategori:*\n"
        for kat, jml in sorted(per_kategori.items(), key=lambda x: -x[1]):
            pesan += f"  • {kat}: Rp {int(jml):,}\n"
    await update.message.reply_text(pesan, parse_mode="Markdown")

async def cmd_bantuan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pesan = (
        "📖 *Panduan Lengkap Bot Keuangan*\n\n"
        "*1. Input pengeluaran:*\n"
        "`keluar 85000 sayur makan kas tunai`\n\n"
        "*2. Input pemasukan:*\n"
        "`masuk 5000000 gaji bca suami`\n\n"
        "*3. Format angka:*\n"
        "  • Tulis tanpa titik/koma\n"
        "  • 50000 bukan 50.000\n\n"
        "*4. Nama dompet:*\n"
        "  • Boleh sebagian, contoh: `gopay` saja\n"
        "  • Tidak perlu huruf besar\n\n"
        "*5. Kategori:*\n"
        "  makan · transport · utilitas\n"
        "  hiburan · jajan · sewa · kesehatan · lainnya\n\n"
        "*6. Cek saldo:* /saldo\n"
        "*7. Ringkasan bulan:* /bulan"
    )
    await update.message.reply_text(pesan, parse_mode="Markdown")

async def terima_pesan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    teks = update.message.text.strip().lower().split()
    if len(teks) < 2:
        await update.message.reply_text(
            "Format tidak dikenali.\nContoh: `keluar 50000 bensin transport gopay`",
            parse_mode="Markdown"
        )
        return
    jenis = teks[0]
    if jenis not in ["keluar", "masuk"]:
        await update.message.reply_text(
            "Mulai pesan dengan *keluar* atau *masuk*.",
            parse_mode="Markdown"
        )
        return
    try:
        jumlah = float(teks[1].replace(",", "").replace(".", ""))
    except ValueError:
        await update.message.reply_text("Jumlah tidak valid. Tulis angka saja, contoh: `50000`", parse_mode="Markdown")
        return

    keterangan = teks[2] if len(teks) > 2 else "tidak ada keterangan"
    kategori   = teks[3] if len(teks) > 3 else "lainnya"
    dompet_cari = " ".join(teks[4:]) if len(teks) > 4 else ""

    dompets = get_dompets()
    dompet_id, dompet_nama, saldo_lama = None, "Kas Tunai", 0
    for nama, data in dompets.items():
        if dompet_cari in nama or nama in dompet_cari or dompet_cari == "":
            dompet_id   = data["id"]
            dompet_nama = data["nama"]
            saldo_lama  = float(data["saldo"])
            break
    if not dompet_id and dompets:
        first = next(iter(dompets.values()))
        dompet_id, dompet_nama, saldo_lama = first["id"], first["nama"], float(first["saldo"])

    sb_post("transaksi", {
        "tanggal": date.today().isoformat(),
        "keterangan": keterangan,
        "jumlah": jumlah,
        "jenis": jenis,
        "kategori": kategori,
        "dompet_id": dompet_id,
        "sumber": "bot",
        "diverifikasi": False
    })

    saldo_baru = saldo_lama - jumlah if jenis == "keluar" else saldo_lama + jumlah
    sb_patch("dompets", {"id": dompet_id}, {"saldo": saldo_baru})

    emoji = "💸" if jenis == "keluar" else "💰"
    tanda = "-" if jenis == "keluar" else "+"
    await update.message.reply_text(
        f"{emoji} *{'Pengeluaran' if jenis=='keluar' else 'Pemasukan'} tersimpan!*\n\n"
        f"📝 {keterangan.capitalize()}\n"
        f"💵 {tanda}Rp {int(jumlah):,}\n"
        f"🏷️ Kategori : {kategori}\n"
        f"👛 Dompet   : {dompet_nama}\n"
        f"💳 Saldo baru: Rp {int(saldo_baru):,}\n\n"
        f"_Data menunggu verifikasi di dashboard_",
        parse_mode="Markdown"
    )

# ─── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    # Jalankan web server di thread terpisah
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
