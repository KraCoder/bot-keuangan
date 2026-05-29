import os
import httpx
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
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

# ─── Helper: panggil Supabase REST API langsung ────────────────
def sb_get(table: str, params: dict = None):
    with httpx.Client() as client:
        r = client.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS, params=params
        )
    return r.json()

def sb_post(table: str, data: dict):
    with httpx.Client() as client:
        r = client.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS, json=data
        )
    return r.json()

def sb_patch(table: str, match: dict, data: dict):
    params = {k: f"eq.{v}" for k, v in match.items()}
    with httpx.Client() as client:
        r = client.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS, params=params, json=data
        )
    return r.status_code

# ─── Ambil semua dompet dari database ─────────────────────────
def get_dompets() -> dict:
    rows = sb_get("dompets", {"select": "id,nama,saldo"})
    if not isinstance(rows, list):
        return {}
    return {row["nama"].lower(): row for row in rows}

# ─────────────────────────────────────────────────────────────
# COMMAND: /start
# ─────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────
# COMMAND: /saldo
# ─────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────
# COMMAND: /bulan — ringkasan pengeluaran bulan ini
# ─────────────────────────────────────────────────────────────
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

    total_keluar = 0
    total_masuk  = 0
    per_kategori = {}

    for r in rows:
        jumlah = float(r.get("jumlah", 0))
        if r.get("jenis") == "keluar":
            total_keluar += jumlah
            kat = r.get("kategori", "lainnya")
            per_kategori[kat] = per_kategori.get(kat, 0) + jumlah
        elif r.get("jenis") == "masuk":
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

# ─────────────────────────────────────────────────────────────
# COMMAND: /bantuan
# ─────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────
# PESAN BIASA — input transaksi utama
# ─────────────────────────────────────────────────────────────
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
            "Mulai pesan dengan *keluar* atau *masuk*.\n"
            "Contoh: `keluar 50000 bensin transport gopay`",
            parse_mode="Markdown"
        )
        return

    # Parse jumlah
    try:
        jumlah = float(teks[1].replace(",", "").replace(".", ""))
    except ValueError:
        await update.message.reply_text(
            "Jumlah tidak valid. Tulis angka saja tanpa titik/koma.\n"
            "Contoh: `keluar 50000 bensin`",
            parse_mode="Markdown"
        )
        return

    keterangan = teks[2] if len(teks) > 2 else "tidak ada keterangan"
    kategori   = teks[3] if len(teks) > 3 else "lainnya"
    dompet_cari = " ".join(teks[4:]) if len(teks) > 4 else ""

    # Cari dompet yang cocok
    dompets = get_dompets()
    dompet_id   = None
    dompet_nama = "Kas Tunai"
    saldo_lama  = 0

    for nama, data in dompets.items():
        if dompet_cari in nama or nama in dompet_cari or dompet_cari == "":
            dompet_id   = data["id"]
            dompet_nama = data["nama"]
            saldo_lama  = float(data["saldo"])
            break

    # Jika tidak ketemu, pakai dompet pertama
    if not dompet_id and dompets:
        first = next(iter(dompets.values()))
        dompet_id   = first["id"]
        dompet_nama = first["nama"]
        saldo_lama  = float(first["saldo"])

    # Simpan transaksi ke Supabase
    sb_post("transaksi", {
        "tanggal"     : date.today().isoformat(),
        "keterangan"  : keterangan,
        "jumlah"      : jumlah,
        "jenis"       : jenis,
        "kategori"    : kategori,
        "dompet_id"   : dompet_id,
        "sumber"      : "bot",
        "diverifikasi": False
    })

    # Update saldo dompet
    saldo_baru = saldo_lama - jumlah if jenis == "keluar" else saldo_lama + jumlah
    sb_patch("dompets", {"id": dompet_id}, {"saldo": saldo_baru})

    # Balas konfirmasi
    emoji = "💸" if jenis == "keluar" else "💰"
    tanda = "-" if jenis == "keluar" else "+"
    jenis_label = "Pengeluaran" if jenis == "keluar" else "Pemasukan"

    pesan = (
        f"{emoji} *{jenis_label} tersimpan!*\n\n"
        f"📝 {keterangan.capitalize()}\n"
        f"💵 {tanda}Rp {int(jumlah):,}\n"
        f"🏷️ Kategori : {kategori}\n"
        f"👛 Dompet   : {dompet_nama}\n"
        f"💳 Saldo baru: Rp {int(saldo_baru):,}\n\n"
        f"_Data menunggu verifikasi di dashboard_"
    )
    await update.message.reply_text(pesan, parse_mode="Markdown")

# ─────────────────────────────────────────────────────────────
# JALANKAN BOT
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Bot keuangan berjalan...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("saldo",   cmd_saldo))
    app.add_handler(CommandHandler("bulan",   cmd_bulan))
    app.add_handler(CommandHandler("bantuan", cmd_bantuan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, terima_pesan))
    app.run_polling()
