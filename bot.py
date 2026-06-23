#!/usr/bin/env python3
"""
MoneyManager Bot Telegram - webhook + health check
Server aiohttp menangani webhook dan health check di satu port.
"""

import os
import sys
import logging
from datetime import date
import asyncio

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import aiohttp  # Jangan gunakan 'from aiohttp import web'

# --------------------------- CONFIG ENV ---------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "supersecret")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 10000))

if not BOT_TOKEN or not SUPABASE_URL or not SUPABASE_ANON_KEY or not RENDER_EXTERNAL_URL:
    sys.exit("ERROR: Pastikan BOT_TOKEN, SUPABASE_URL, SUPABASE_ANON_KEY, RENDER_EXTERNAL_URL diset!")

HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --------------------------- SUPABASE ASYNC FUNCTIONS ---------------------------
async def supabase_get(endpoint: str, params: dict = None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        return resp.json()

async def supabase_post(endpoint: str, data: dict):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=HEADERS, json=data)
        resp.raise_for_status()
        return resp.json() if resp.text else None

async def supabase_patch(endpoint: str, data: dict, params: dict = None):
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    async with httpx.AsyncClient() as client:
        resp = await client.patch(url, headers=HEADERS, json=data, params=params)
        resp.raise_for_status()
        return resp.json() if resp.text else None

# --------------------------- AKSES & PARSING ---------------------------
async def cek_akses(update: Update) -> str | None:
    telegram_id = update.effective_user.id
    try:
        data = await supabase_get("telegram_users", {"telegram_id": f"eq.{telegram_id}"})
    except Exception as e:
        logger.error(f"Gagal cek akses: {e}")
        return None
    if data:
        return data[0]["user_id"]
    return None

async def parse_input_transaksi(user_id: str, text: str):
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

    sisanya = parts[2:]
    if not sisanya:
        return None

    dompet_nama = sisanya[-1].lower()
    dompets = await supabase_get("dompets", {"user_id": f"eq.{user_id}"})
    dompet_map = {d["nama"].lower(): d["id"] for d in dompets}
    if dompet_nama in dompet_map:
        dompet_id = dompet_map[dompet_nama]
        keterangan = " ".join(sisanya[:-1])
    else:
        dompet_id = dompets[0]["id"] if dompets else None
        keterangan = " ".join(sisanya)

    kategori = "lainnya"
    return {
        "jenis": jenis,
        "jumlah": jumlah,
        "keterangan": keterangan,
        "kategori": kategori,
        "dompet_id": dompet_id,
    }

async def simpan_transaksi(user_id: str, tgl: str, ket: str, jml: int,
                           jenis: str, kat: str, dompet_id: int):
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

    delta = jml if jenis == "masuk" else -jml
    dompet_data = await supabase_get("dompets", {"id": f"eq.{dompet_id}"})
    if dompet_data:
        current = float(dompet_data[0]["saldo"])
        new_saldo = current + delta
        await supabase_patch("dompets", {"saldo": new_saldo}, {"id": f"eq.{dompet_id}"})

# --------------------------- TELEGRAM HANDLERS ---------------------------
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
    now = date.today()
    tgl_awal = now.replace(day=1).isoformat()
    tgl_akhir = now.isoformat()
    try:
        masuk = await supabase_get("transaksi", {
            "user_id": f"eq.{user_id}",
            "jenis": "eq.masuk",
            "tanggal": f"gte.{tgl_awal}",
            "tanggal": f"lte.{tgl_akhir}"
        })
        keluar = await supabase_get("transaksi", {
            "user_id": f"eq.{user_id}",
            "jenis": "eq.keluar",
            "tanggal": f"gte.{tgl_awal}",
            "tanggal": f"lte.{tgl_akhir}"
        })
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
        await update.message.reply_text(f"Gagal: {e}")

async def bantuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Format input:\n"
        "<jenis> <jumlah> <keterangan> [dompet]\n"
        "Contoh: keluar 50000 bensin transport gopay\n"
        "Jenis: masuk / keluar\n"
        "Dompet opsional, jika tidak disebutkan pakai dompet pertama."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = await cek_akses(update)
    if not user_id:
        await update.message.reply_text("Anda tidak terdaftar.")
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

# --------------------------- WEBHOOK HANDLER ---------------------------
async def webhook_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        return aiohttp.web.Response(status=403, text="Unauthorized")
    try:
        data = await request.json()
    except:
        return aiohttp.web.Response(status=400, text="Bad Request")
    await app.process_update(Update.de_json(data, app.bot))
    return aiohttp.web.Response(text="OK")

async def health_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    return aiohttp.web.Response(text="Bot is alive")

# --------------------------- MAIN ---------------------------
def main():
    global app
    app = Application.builder().token(BOT_TOKEN).build()

    # Daftarkan handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("saldo", saldo))
    app.add_handler(CommandHandler("bulan", bulan))
    app.add_handler(CommandHandler("bantuan", bantuan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Buat server aiohttp
    web_app = aiohttp.web.Application()
    web_app.router.add_post("/webhook", webhook_handler)
    web_app.router.add_get("/health", health_handler)

    async def main_async():
        await app.initialize()
        await app.bot.set_webhook(
            url=f"{RENDER_EXTERNAL_URL}/webhook",
            secret_token=WEBHOOK_SECRET
        )
        logger.info("Webhook diset ke Telegram")
        runner = aiohttp.web.AppRunner(web_app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        logger.info(f"Server berjalan di port {PORT}")
        # Tetap hidup selamanya
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
