import os
import requests
from datetime import datetime, timedelta, date
from dateutil import tz

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

WB_API_BASE = "https://statistics-api.wildberries.ru"

WB_TOKEN = os.getenv("WB_TOKEN")
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")
REPORT_HOUR = int(os.getenv("REPORT_HOUR", "9"))
REPORT_MINUTE = int(os.getenv("REPORT_MINUTE", "0"))

TZ_MSK = tz.gettz("Europe/Moscow")

def wb_get(path: str, params: dict):
    headers = {"Authorization": WB_TOKEN}
    url = f"{WB_API_BASE}{path}"
    r = requests.get(url, headers=headers, params=params, timeout=60)
    r.raise_for_status()
    return r.json()

def get_day_orders(target_day: date):
    data = wb_get("/api/v1/supplier/orders", {"dateFrom": target_day.isoformat(), "flag": 1})
    return [x for x in data if not x.get("isCancel", False)]

def get_day_sales(target_day: date):
    return wb_get("/api/v1/supplier/sales", {"dateFrom": target_day.isoformat(), "flag": 1})

def is_return(row: dict) -> bool:
    sale_id = str(row.get("saleID", "")).upper()
    for_pay = row.get("forPay")
    if sale_id.startswith("S"):
        return False
    if isinstance(for_pay, (int, float)) and for_pay < 0:
        return True
    return True

def build_report_text(target_day: date) -> str:
    orders = get_day_orders(target_day)
    sales = get_day_sales(target_day)

    agg = {}
    def art(x): return str(x.get("supplierArticle", "")).strip() or "(без артикула)"

    for o in orders:
        a = art(o)
        agg.setdefault(a, {"orders": 0, "returns": 0})
        agg[a]["orders"] += 1

    for s in sales:
        a = art(s)
        agg.setdefault(a, {"orders": 0, "returns": 0})
        if is_return(s):
            agg[a]["returns"] += 1

    items = sorted(agg.items(), key=lambda kv: kv[1]["orders"], reverse=True)

    lines = [f"📊 <b>WB</b> — <b>{target_day.strftime('%d.%m.%Y')}</b> (МСК)", ""]
    if not items:
        lines.append("Нет данных за день.")
        return "\n".join(lines)

    def badge(buyout: float):
        if buyout < 0.22: return "🔴"
        if buyout < 0.30: return "🟡"
        return "🟢"

    for a, v in items[:40]:
        o = v["orders"]
        r = v["returns"]
        buyout = (o - r) / o if o > 0 else 0.0
        lines.append(
            f"{badge(buyout)} <b>{a}</b>\n"
            f"Заказано: <b>{o}</b> | Возвраты: <b>{r}</b> | Выкуп: <b>{buyout*100:.1f}%</b>\n"
        )

    return "\n".join(lines).strip()

def msk_today() -> date:
    return datetime.now(tz=TZ_MSK).date()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я WB-бот отчётов.\n"
        "Команды:\n"
        "/myid — показать chat_id\n"
        "/yesterday — отчёт за вчера (МСК)\n"
        "/today — отчёт за сегодня (МСК)"
    )

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ваш chat_id: {update.effective_chat.id}")

async def yesterday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = msk_today() - timedelta(days=1)
    await update.message.reply_text(build_report_text(d), parse_mode=ParseMode.HTML)

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    d = msk_today()
    await update.message.reply_text(build_report_text(d), parse_mode=ParseMode.HTML)

async def scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    if not OWNER_CHAT_ID:
        return
    chat_id = int(OWNER_CHAT_ID)
    d = msk_today() - timedelta(days=1)
    await context.bot.send_message(chat_id=chat_id, text=build_report_text(d), parse_mode=ParseMode.HTML)

def main():
    if not WB_TOKEN:
        raise RuntimeError("Нет WB_TOKEN")
    if not TG_TOKEN:
        raise RuntimeError("Нет TG_BOT_TOKEN")

    app = Application.builder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("yesterday", yesterday))
    app.add_handler(CommandHandler("today", today))

   
    app.run_polling()


if __name__ == "__main__":
    main()
