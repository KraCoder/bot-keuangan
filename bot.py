import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

DOMPETS = {}  # akan diisi saat start

def load_dompets():
    result = supabase.table("dompets").select("*").execute()
    for d in result.data:
        DOMPETS[d["nama"].lower()] = d["id"]

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    load_dompets()
    daftar = "\n".join([f"• {k}" for k in DOMPETS.keys()])
    await update.message.reply_text(
        f"Halo! Saya bot keuangan keluargamu 💰\n\n"
        f"*Format input:*\n"
        f"`keluar [jumlah] [keterangan] [kategori] [dompet]`\n"
        f"`masuk [jumlah] [keterangan] [dompet]`\n\n"
        f"*Contoh:*\n"
        f"`keluar 50000 bensin transport gopay`\n"
        f"`masuk 5000000 gaji bca suami`\n\n"
        f"*Dompet tersedia:*\n{daftar}\n\n"
        f"*Kategori:* makan, transport, utilitas, hiburan, jajan, sewa, kesehatan, lainnya",
        parse_mode="Markdown"
    )

async def saldo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    result = supabase.table("dompets").select("nama,saldo").execute()
    pesan = "💳 *Saldo semua dompet:*\n\n"
    total = 0
    for d in result.data:
        pesan += f"• {d['nama']}: Rp {int(d['saldo']):,}\n"
        total += d['saldo']
    pesan += f"\n*Total: Rp {int(total):,}*"
    await update.message.reply_text(pesan, parse_mode="Markdown")

async def terima_pesan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    load_dompets()
    teks = update.message.text.lower().strip().split()
    
    if len(teks) < 3:
        await update.message.reply_text("Format salah. Contoh:\n`keluar 50000 bensin transport gopay`", parse_mode="Markdown")
        return
    
    jenis = teks[0]
    if jenis not in ["keluar", "masuk"]:
        await update.message.reply_text("Mulai dengan 'keluar' atau 'masuk'")
        return
    
    try:
        jumlah = float(teks[1].replace(",", "").replace(".", ""))
    except:
        await update.message.reply_text("Jumlah tidak valid. Contoh: 50000")
        return
    
    keterangan = teks[2] if len(teks) > 2 else "tidak ada keterangan"
    kategori = teks[3] if len(teks) > 3 else "lainnya"
    dompet_nama = " ".join(teks[4:]) if len(teks) > 4 else "kas tunai"
    
    # cari dompet_id
    dompet_id = None
    for nama, did in DOMPETS.items():
        if dompet_nama in nama or nama in dompet_nama:
            dompet_id = did
            break
    
    if not dompet_id:
        dompet_id = list(DOMPETS.values())[0]  # default ke dompet pertama
    
    # simpan transaksi
    supabase.table("transaksi").insert({
        "keterangan": keterangan,
        "jumlah": jumlah,
        "jenis": jenis,
        "kategori": kategori,
        "dompet_id": dompet_id,
        "sumber": "bot",
        "diverifikasi": False
    }).execute()
    
    # update saldo
    dompet_data = supabase.table("dompets").select("saldo").eq("id", dompet_id).execute()
    saldo_lama = dompet_data.data[0]["saldo"]
    saldo_baru = saldo_lama - jumlah if jenis == "keluar" else saldo_lama + jumlah
    supabase.table("dompets").update({"saldo": saldo_baru}).eq("id", dompet_id).execute()
    
    emoji = "💸" if jenis == "keluar" else "💰"
    await update.message.reply_text(
        f"{emoji} *Tersimpan!*\n"
        f"{'Pengeluaran' if jenis=='keluar' else 'Pemasukan'}: Rp {int(jumlah):,}\n"
        f"Ket: {keterangan} | Kategori: {kategori}\n"
        f"_(akan muncul di dashboard untuk diverifikasi)_",
        parse_mode="Markdown"
    )

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("saldo", saldo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, terima_pesan))

if __name__ == "__main__":
    print("Bot berjalan...")
    app.run_polling()