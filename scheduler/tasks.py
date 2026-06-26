import asyncio
import os
from datetime import datetime

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from database.db import SessionLocal
from database.models import TrackedProduct, PriceHistory
from scrapers.amazon import search_amazon
from scrapers.google_shop import search_google_shopping

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
scheduler = BlockingScheduler()


def fetch_all_prices(query: str) -> list[dict]:
    results = []
    results.extend(search_amazon(query, limit=2))
    results.extend(search_google_shopping(query, limit=2))
    results = [r for r in results if r["price"] and r["price"] > 0]
    results.sort(key=lambda x: x["price"])
    return results


async def send_alert(telegram_id: int, query: str, source: str, old_price: float, new_price: float, url: str):
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    savings = old_price - new_price
    percent = (savings / old_price) * 100 if old_price else 0

    text = (
        f"🚨 <b>Price Alert!</b>\n\n"
        f"📦 <b>{query}</b> on {source}\n\n"
        f"📉 Price dropped!\n"
        f"   Was:  ${old_price:.2f}\n"
        f"   Now:  ${new_price:.2f}\n"
        f"   Save: ${savings:.2f} (-{percent:.1f}%)\n\n"
        f"🔗 <a href='{url}'>Buy now</a>\n"
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    try:
        await bot.send_message(telegram_id, text, disable_web_page_preview=True)
    finally:
        await bot.session.close()


def check_prices():
    print(f"\n⏰ Checking prices: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    db = SessionLocal()
    try:
        products = db.query(TrackedProduct).filter(TrackedProduct.is_active == True).all()

        for product in products:
            print(f"  🔍 {product.query}...")
            results = fetch_all_prices(product.query)

            for item in results:
                last = (
                    db.query(PriceHistory)
                    .filter(
                        PriceHistory.tracked_product_id == product.id,
                        PriceHistory.source == item["source"],
                        PriceHistory.title == item["title"],
                    )
                    .order_by(PriceHistory.fetched_at.desc())
                    .first()
                )

                # save new price point
                history = PriceHistory(
                    tracked_product_id=product.id,
                    source=item["source"],
                    title=item["title"],
                    price=item["price"],
                    rating=item["rating"],
                    reviews=item["reviews"],
                    url=item["url"]
                )
                db.add(history)
                db.commit()

                # check for price drop
                if last and item["price"] < last.price:
                    asyncio.run(send_alert(
                        product.telegram_id,
                        product.query,
                        item["source"],
                        last.price,
                        item["price"],
                        item["url"]
                    ))
                    print(f"    🚨 Alert sent: {item['source']} ${last.price} -> ${item['price']}")

        print("✅ Price check completed!")
    finally:
        db.close()


# Run once a day at 09:00
scheduler.add_job(
    check_prices,
    trigger=CronTrigger(hour=9, minute=0),
    id="daily_price_check",
    name="Daily Price Check",
    replace_existing=True
)

if __name__ == "__main__":
    print("🕐 Price Monitor Scheduler started...")
    print("📅 Checking prices every day at 09:00")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\n🛑 Scheduler stopped")
        scheduler.shutdown()