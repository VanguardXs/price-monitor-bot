import time
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from database.db import SessionLocal
from database.models import User, TrackedProduct, PriceHistory
from scrapers.amazon import search_amazon
from scrapers.google_shop import search_google_shopping
from reports.excel_report import generate_report

router = Router()

# --- Security & limits ---
MAX_TRACKED_PRODUCTS = 10
MAX_QUERY_LENGTH = 80
RATE_LIMIT_SECONDS = 3
_last_request_time: dict[int, float] = {}


def is_rate_limited(telegram_id: int) -> bool:
    now = time.time()
    last = _last_request_time.get(telegram_id, 0)
    if now - last < RATE_LIMIT_SECONDS:
        return True
    _last_request_time[telegram_id] = now
    return False


def clean_query(text: str, command: str) -> str:
    """Extract and sanitize the product query from a command message"""
    query = text.replace(command, "", 1).strip()
    query = " ".join(query.split())  # collapse multiple spaces
    return query[:MAX_QUERY_LENGTH]


def get_or_create_user(telegram_id: int, username: str, first_name: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id, username=username, first_name=first_name)
            db.add(user)
            db.commit()
        return user
    finally:
        db.close()


def fetch_all_prices(query: str) -> list[dict]:
    """Fetch prices from all sources and return combined, sorted results"""
    results = []
    try:
        results.extend(search_amazon(query, limit=2))
    except Exception as e:
        print(f"❌ Amazon fetch failed: {e}")
    try:
        results.extend(search_google_shopping(query, limit=2))
    except Exception as e:
        print(f"❌ Google Shopping fetch failed: {e}")

    results = [r for r in results if r["price"] and r["price"] > 0]
    results.sort(key=lambda x: x["price"])
    return results


def format_comparison(query: str, results: list[dict]) -> str:
    if not results:
        return f"😕 No results found for <b>{query}</b>. Try a different search term."

    lines = [f"🔍 <b>Price Comparison:</b> {query}\n"]
    lines.append("━━━━━━━━━━━━━━━━━━━━")

    best_price = results[0]["price"]

    for item in results:
        emoji = "📦" if item["source"] == "Amazon" else "🛒"
        is_best = "  🏆 <b>Best Price!</b>" if item["price"] == best_price else ""
        lines.append(f"{emoji} <b>{item['source']}</b>")
        lines.append(f"   💰 ${item['price']:.2f}{is_best}")
        if item["rating"]:
            lines.append(f"   ⭐ {item['rating']} ({item['reviews']} reviews)")
        lines.append(f"   🔗 <a href='{item['url']}'>View product</a>\n")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if len(results) > 1:
        savings = results[-1]["price"] - best_price
        lines.append(f"💡 Best deal: {results[0]['source']} (save ${savings:.2f})")

    return "\n".join(lines)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 My Tracked Products", callback_data="list")],
        [InlineKeyboardButton(text="📄 Get Excel Report", callback_data="report")],
        [InlineKeyboardButton(text="❓ Help", callback_data="help")],
    ])


@router.message(Command("start"))
async def cmd_start(message: Message):
    get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)

    text = (
        "👋 <b>Welcome to Price Monitor Bot!</b>\n\n"
        "I track prices across multiple platforms\n"
        "and alert you when prices drop.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📦 Amazon\n"
        "🛒 Google Shopping\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Commands:</b>\n"
        "/compare [product] — compare prices now\n"
        "/track [product] — start tracking a product\n"
        "/list — see your tracked products\n"
        "/remove [product] — stop tracking\n"
        "/remove_all — stop tracking everything\n"
        "/report — get an Excel report\n"
        "/bulk_track — track multiple products at once\n"
        "/help — show this message"
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await cmd_start(message)


@router.callback_query(lambda c: c.data == "help")
async def cb_help(callback):
    await cmd_start(callback.message)
    await callback.answer()


@router.message(Command("compare"))
async def cmd_compare(message: Message):
    if is_rate_limited(message.from_user.id):
        await message.answer("⏳ Please wait a few seconds before your next request.")
        return

    query = clean_query(message.text, "/compare")
    if not query:
        await message.answer("⚠️ Please specify a product.\nExample: <code>/compare iphone 15</code>")
        return

    await message.answer(f"🔎 Searching for <b>{query}</b>...")
    try:
        results = fetch_all_prices(query)
        text = format_comparison(query, results)
        await message.answer(text, disable_web_page_preview=True)
    except Exception:
        await message.answer("😕 Something went wrong while searching. Please try again later.")


@router.message(Command("track"))
async def cmd_track(message: Message):
    if is_rate_limited(message.from_user.id):
        await message.answer("⏳ Please wait a few seconds before your next request.")
        return

    query = clean_query(message.text, "/track")
    if not query:
        await message.answer("⚠️ Please specify a product.\nExample: <code>/track iphone 15</code>")
        return

    db = SessionLocal()
    try:
        active_count = db.query(TrackedProduct).filter(
            TrackedProduct.telegram_id == message.from_user.id,
            TrackedProduct.is_active == True
        ).count()

        if active_count >= MAX_TRACKED_PRODUCTS:
            await message.answer(
                f"⚠️ You've reached the limit of {MAX_TRACKED_PRODUCTS} tracked products.\n"
                f"Use /remove [product] to stop tracking one first."
            )
            return

        existing = db.query(TrackedProduct).filter(
            TrackedProduct.telegram_id == message.from_user.id,
            TrackedProduct.query.ilike(query),
            TrackedProduct.is_active == True
        ).first()

        if existing:
            await message.answer(f"✅ You're already tracking <b>{query}</b>")
            return

        product = TrackedProduct(telegram_id=message.from_user.id, query=query)
        db.add(product)
        db.commit()
        db.refresh(product)

        await message.answer(f"✅ Now tracking <b>{query}</b>\nI'll alert you when the price drops!")

        try:
            results = fetch_all_prices(query)
            for item in results:
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
        except Exception as e:
            print(f"❌ Failed to save initial prices: {e}")

    except Exception:
        await message.answer("😕 Something went wrong. Please try again later.")
    finally:
        db.close()


@router.message(Command("list"))
async def cmd_list(message: Message):
    await _send_list(message)


@router.callback_query(lambda c: c.data == "list")
async def cb_list(callback):
    await _send_list(callback.message, telegram_id=callback.from_user.id)
    await callback.answer()


async def _send_list(message: Message, telegram_id: int | None = None):
    tid = telegram_id or message.from_user.id
    db = SessionLocal()
    try:
        products = db.query(TrackedProduct).filter(
            TrackedProduct.telegram_id == tid,
            TrackedProduct.is_active == True
        ).all()

        if not products:
            await message.answer("📋 You're not tracking any products yet.\nUse /track [product] to start.")
            return

        lines = ["📋 <b>Your Tracked Products:</b>\n"]
        for p in products:
            lines.append(f"• {p.query}")
        await message.answer("\n".join(lines))
    finally:
        db.close()


@router.message(Command("remove"))
async def cmd_remove(message: Message):
    query = clean_query(message.text, "/remove")
    if not query:
        await message.answer("⚠️ Please specify a product.\nExample: <code>/remove iphone 15</code>")
        return

    db = SessionLocal()
    try:
        product = db.query(TrackedProduct).filter(
            TrackedProduct.telegram_id == message.from_user.id,
            TrackedProduct.query.ilike(query),
            TrackedProduct.is_active == True
        ).first()

        if not product:
            await message.answer(f"😕 Couldn't find <b>{query}</b> in your tracked products.")
            return

        product.is_active = False
        db.commit()
        await message.answer(f"🗑️ Stopped tracking <b>{query}</b>")
    except Exception:
        await message.answer("😕 Something went wrong. Please try again later.")
    finally:
        db.close()
@router.message(Command("remove_all"))
async def cmd_remove_all(message: Message):
    db = SessionLocal()
    try:
        count = db.query(TrackedProduct).filter(
            TrackedProduct.telegram_id == message.from_user.id,
            TrackedProduct.is_active == True
        ).update({"is_active": False})
        db.commit()

        if count == 0:
            await message.answer("📋 You're not tracking any products.")
        else:
            await message.answer(f"🗑️ Removed all {count} tracked products.")
    except Exception:
        await message.answer("😕 Something went wrong. Please try again later.")
    finally:
        db.close()


@router.message(Command("report"))
async def cmd_report(message: Message):
    await _send_report(message)


@router.callback_query(lambda c: c.data == "report")
async def cb_report(callback):
    await _send_report(callback.message)
    await callback.answer()


async def _send_report(message: Message):
    await message.answer("📊 Generating your report, please wait...")
    try:
        filepath = generate_report(telegram_id=message.from_user.id)
        file = FSInputFile(filepath)
        await message.answer_document(file, caption="📄 Here's your price report!")
    except Exception:
        await message.answer("😕 Couldn't generate the report. Please try again later.")