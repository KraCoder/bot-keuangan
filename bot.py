#!/usr/bin/env python3
"""
MoneyManager Bot Telegram - mode webhook + health check
Tetap responsif di Render free tier dengan bantuan UptimeRobot.
"""

import os
import json
import re
import logging
from datetime import date, datetime

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    WebhookApp,
)
from aiohttp import web

# --------------------------- CONFIG ENV ---------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "supersecret")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")  # https://bot-keuangan.onrender.com
PORT = int(os.environ.get("PORT", 10000))

# Headers untuk Supabase REST API
HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

# --------------------------- LOGGING ---------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --------------------------- SUPABASE CLIENT (httpx) ---------------------------
async def supabase_get(endpoint, params=None):
    """GET request ke Supabase REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        return resp.json()

async def supabase_post(endpoint, data):
    """POST request ke Supabase REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=HEADERS, json=data)
        resp.raise_for_status()
        return resp.json() if resp.text else None

async def supabase_patch(endpoint, data, params=None):
    """PATCH request."""
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.patch(url, headers=HEADERS, json=data, params=params)
        resp.raise_for_status()
        return resp.json() if resp.text else None

# --------------------------- AKSES ---------------------------
async def cek_akses(update: Update) -> str | None:
    """Cek apakah pengirim terdaftar, return user_id ('suami'/'istri') atau None."""
    telegram_id = update.effective_user.id
    try:
        data = await supabase_get("telegram_users", {"telegram_id": f"eq.{telegram_id}"})
    except Exception as e:
        logger.error(f"Gagal cek akses: {e}")
        return None
    if data:
        return data[0]["user_id"]
    return None

# --------------------------- HELPER PARSING ---------------------------
async def parse_input_transaksi(user_id: str, text: str):
    """
    Parse input pengguna.
    Format: <jenis> <jumlah> <keterangan> [dompet]
    Contoh: 'keluar 50000 bensin transport gopay'
    Return: dict dengan jenis, jumlah, keterangan, kategori, dompet_id.
    """
    parts = text.strip().split()
    if len(parts) < 2:
        return None

    jenis = parts[0].lower()
    if jenis not in ("masuk", "keluar"):
        return None

    try:
        jumlah = int(parts[1])
    except ValueError:
        return None

    # Ambil keterangan (kata setelah jumlah, sebelum kemungkinan nama dompet)
    sisanya = parts[2:]
    if not sisanya:
        return None

    # Cek apakah kata terakhir adalah nama dompet milik user
    dompet_nama = sisanya[-1].lower()
    # Ambil daftar dompet user
    dompets = await supabase_get("dompets", {"user_id": f"eq.{user_id}"})
    dompet_map = {d["nama"].lower(): d["id"] for d in dompets}
    if dompet_nama in dompet_map:
        dompet_id = dompet_map[dompet_nama]
        keterangan = " ".join(sisanya[:-1])
    else:
        # Pakai dompet pertama (default)
        dompet_id = dompets[0]["id"] if dompets else None
        keterangan = " ".join(sisanya)

    # Kategori: default 'lainnya', bisa ditingkatkan nanti dengan deteksi kata kunci
    kategori = "lainnya"

    return {
        "jenis": jenis,
        "jumlah": jumlah,
        "keterangan": keterangan,
        "kategori": kategori,
        "dompet_id": dompet_id,
    }

# --------------------------- FUNGSI SIMPAN TRANSAKSI ---------------------------
async def simpan_transaksi(user_id: str, tgl: str, ket: str, jml: int,
                           jenis: str, kat: str, dompet_id: int):
    """Simpan transaksi dan update saldo dompet."""
    data = {
        "tanggal": tgl,
        "keterangan": ket,
        "jumlah": jml,
        "jenis": jenis,
        "kategori": kat,
        "dompet_id": dompet_id,
        "user_id": user_id,
        "sumber": "bot",
        "diverifikasi": False,
    }
    await supabase_post("transaksi", data)
    # Update saldo dompet
    delta = jml if jenis == "masuk" else -jml
    await supabase_patch(
        "dompets",
        {"saldo": None},  # akan kita set dengan query SQL mentah? Bisa pakai RPC.
        # Di sini kita pakai PATCH via REST dengan header Prefer return=representation,
        # dan kita butuh update saldo eksisting. Kita bisa hitung dulu saldo sekarang.
        # Alternatif: gunakan function update_saldo_dompet. Untuk mempersingkat,
        # kita akan update dengan menambah/delta secara manual setelah GET saldo.
    )
    # Dapatkan saldo saat ini
    dompet_data = await supabase_get("dompets", {"id": f"eq.{dompet_id}"})
    if dompet_data:
        current_saldo = float(dompet_data[0]["saldo"])
        new_saldo = current_saldo + delta
        await supabase_patch(
            "dompets",
            {"saldo": new_saldo},
            {"id": f"eq.{dompet_id}"}
        )

# --------------------------- COMMAND HANDLERS ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await cek_akses(update)
    if not user_id:
        await update.message.reply_text("Anda belum terdaftar.")
        return
    await update.message.reply_text(
        f"Halo, {user_id}! Gunakan perintah:\n"
        "/saldo - Cek saldo\n"
        "/bulan - Ringkasan bulan ini\n"
        "/bantuan - Cara input"
    )

async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await cek_akses(update)
    if not user_id:
        await update.message.reply_text("Akses ditolak.")
        return
    dompets = await supabase_get("dompets", {"user_id": f"eq.{user_id}"})
    total = sum(float(d["saldo"]) for d in dompets)
    await update.message.reply_text(f"Total saldo Anda: Rp {total:,.0f}")

async def bulan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await cek_akses(update)
    if not user_id:
        await update.message.reply_text("Akses ditolak.")
        return
    # Bulan ini
    now = date.today()
    tgl_awal = now.replace(day=1).isoformat()
    tgl_akhir = now.isoformat()
    try:
        masuk = await supabase_get(
            "transaksi",
            {
                "user_id": f"eq.{user_id}",
                "jenis": "eq.masuk",
                "tanggal": f"gte.{tgl_awal}",
                "tanggal": f"lte.{tgl_akhir}",
            },
        )
        keluar = await supabase_get(
            "transaksi",
            {
                "user_id": f"eq.{user_id}",
                "jenis": "eq.keluar",
                "tanggal": f"gte.{tgl_awal}",
                "tanggal": f"lte.{tgl_akhir}",
            },
        )
        tot_masuk = sum(float(t["jumlah"]) for t in masuk)
        tot_keluar = sum(float(t["jumlah"]) for t in keluar)
        teks = (
            f"Ringkasan bulan ini ({tgl_awal} s.d {tgl_akhir}):\n"
            f"Pemasukan: Rp {tot_masuk:,.0f}\n"
            f"Pengeluaran: Rp {tot_keluar:,.0f}\n"
            f"Selisih: Rp {tot_masuk - tot_keluar:,.0f}"
        )
        await update.message.reply_text(teks)
    except Exception as e:
        await update.message.reply_text(f"Gagal mengambil data: {e}")

async def bantuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Format input:\n"
        "<jenis> <jumlah> <keterangan> [dompet]\n"
        "Contoh: keluar 50000 bensin transport gopay\n"
        "Jenis: masuk / keluar\n"
        "Dompet (opsional): nama dompet (tunai/bank/ewallet), jika tidak disebutkan pakai dompet pertama."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await cek_akses(update)
    if not user_id:
        await update.message.reply_text("Anda tidak terdaftar. Hubungi admin.")
        return

    text = update.message.text.strip()
    parsed = await parse_input_transaksi(user_id, text)
    if not parsed:
        await update.message.reply_text("Format salah. Gunakan: keluar 50000 bensin transport gopay")
        return

    if parsed["dompet_id"] is None:
        await update.message.reply_text("Anda belum memiliki dompet. Tambahkan di dashboard.")
        return

    try:
        today = date.today().isoformat()
        await simpan_transaksi(
            user_id=user_id,
            tgl=today,
            ket=parsed["keterangan"],
            jml=parsed["jumlah"],
            jenis=parsed["jenis"],
            kat=parsed["kategori"],
            dompet_id=parsed["dompet_id"],
        )
        await update.message.reply_text(
            f"✅ Tercatat: {parsed['jenis']} Rp {parsed['jumlah']:,} - {parsed['keterangan']}"
        )
    except Exception as e:
        logger.error(f"Gagal simpan: {e}")
        await update.message.reply_text("Gagal menyimpan transaksi. Silakan coba lagi.")

# --------------------------- HEALTH CHECK (untuk UptimeRobot) ---------------------------
class HealthCheckWebhookApp(WebhookApp):
    """Override WebhookApp agar bisa melayani GET /health"""
    async def _handle_request(self, request):
        if request.method == "GET" and request.path == "/health":
            return web.Response(text="Bot is alive")
        # Untuk POST /webhook, biarkan parent yang menangani
        return await super()._handle_request(request)

# --------------------------- MAIN ---------------------------
def main():
    if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        logger.error("Environment BOT_TOKEN, SUPABASE_URL, SUPABASE_ANON_KEY harus diset!")
        return

    # Buat Application
    app = Application.builder().token(BOT_TOKEN).build()

    # Daftarkan handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(CommandHandler("bulan", bulan))
    app.add_handler(CommandHandler("bantuan", bantuan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Jalankan webhook
    webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
    logger.info(f"Menjalankan webhook di {webhook_url}")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        secret_token=WEBHOOK_SECRET,
        webhook_url=webhook_url,
        web_app=HealthCheckWebhookApp,  # custom class untuk health check
    )

if __name__ == "__main__":
    main()
