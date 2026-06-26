from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.db import SessionLocal
from database.models import TrackedProduct, PriceHistory
from scrapers.amazon import search_amazon
from scrapers.google_shop import search_google_shopping
from bot.api_limiter import has_quota, increment_usage
from bot.utils import safe_text, split_lines
import html as html_module

router = Router()

MAX_TOTAL_TRACKED = 1000
MAX_SPECIFIC_PRODUCTS = 20
MAX_CATEGORY_PRODUCTS = 50

CATEGORIES = ["Electronics", "Fashion", "Home", "Auto", "Gaming"]


class BulkTrackStates(StatesGroup):
    choosing_category = State()
    choosing_mode = State()
    choosing_count_specific = State()
    entering_products = State()
    choosing_count_category = State()


def category_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"📦 {c}", callback_data=f"cat:{c}")] for c in CATEGORIES]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Specific products", callback_data="mode:specific")],
        [InlineKeyboardButton(text="🌐 Any products in category", callback_data="mode:category")],
    ])


def fetch_all_prices(query: str) -> list[dict]:
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
    for r in results:
        r["title"] = html_module.unescape(r["title"])
    results.sort(key=lambda x: x["price"])
    return results


def count_active_tracked(telegram_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(TrackedProduct).filter(
            TrackedProduct.telegram_id == telegram_id,
            TrackedProduct.is_active == True
        ).count()
    finally:
        db.close()


def save_tracked_product(telegram_id: int, query: str, category: str) -> tuple[TrackedProduct, list[dict]] | None:
    """Save a product and its initial prices. Returns None if it's a duplicate."""
    db = SessionLocal()
    try:
        existing = db.query(TrackedProduct).filter(
            TrackedProduct.telegram_id == telegram_id,
            TrackedProduct.query.ilike(query),
            TrackedProduct.is_active == True
        ).first()
        if existing:
            return None

        product = TrackedProduct(telegram_id=telegram_id, query=query)
        db.add(product)
        db.commit()
        db.refresh(product)

        results = fetch_all_prices(query)
        increment_usage(2)  # one Amazon + one Google call

        for item in results:
            try:
                safe_rating = float(item.get("rating") or 0)
            except (ValueError, TypeError):
                safe_rating = 0.0
            try:
                safe_reviews = int(float(item.get("reviews") or 0))
            except (ValueError, TypeError):
                safe_reviews = 0

            history = PriceHistory(
                tracked_product_id=product.id,
                source=item["source"],
                title=item["title"],
                price=item["price"],
                rating=safe_rating,
                reviews=safe_reviews,
                url=item["url"]
            )
            db.add(history)

        return product, results
    finally:
        db.close()


@router.message(Command("bulk_track"))
async def cmd_bulk_track(message: Message, state: FSMContext):
    current_count = count_active_tracked(message.from_user.id)
    if current_count >= MAX_TOTAL_TRACKED:
        await message.answer(
            f"⚠️ You've reached the maximum of {MAX_TOTAL_TRACKED} tracked products.\n"
            f"Remove some with /remove before adding more."
        )
        return

    await state.set_state(BulkTrackStates.choosing_category)
    await message.answer(
        "📦 <b>Let's set up product tracking!</b>\n\nChoose a category:",
        reply_markup=category_keyboard()
    )


@router.callback_query(BulkTrackStates.choosing_category, F.data.startswith("cat:"))
async def on_category_chosen(callback: CallbackQuery, state: FSMContext):
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)
    await state.set_state(BulkTrackStates.choosing_mode)

    await callback.message.edit_text(
        f"📦 Category: <b>{category}</b>\n\n🎯 How do you want to search?",
        reply_markup=mode_keyboard()
    )
    await callback.answer()


@router.callback_query(BulkTrackStates.choosing_mode, F.data == "mode:specific")
async def on_mode_specific(callback: CallbackQuery, state: FSMContext):
    await state.update_data(mode="specific")
    await state.set_state(BulkTrackStates.choosing_count_specific)
    await callback.message.edit_text(
        f"🔢 How many specific products do you want to add? (1-{MAX_SPECIFIC_PRODUCTS})"
    )
    await callback.answer()


@router.callback_query(BulkTrackStates.choosing_mode, F.data == "mode:category")
async def on_mode_category(callback: CallbackQuery, state: FSMContext):
    await state.update_data(mode="category")
    await state.set_state(BulkTrackStates.choosing_count_category)
    await callback.message.edit_text(
        f"🔢 How many products to fetch for this category? (1-{MAX_CATEGORY_PRODUCTS})"
    )
    await callback.answer()


@router.message(BulkTrackStates.choosing_count_specific)
async def on_count_specific(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Please send a number.")
        return

    if count < 1 or count > MAX_SPECIFIC_PRODUCTS:
        await message.answer(f"⚠️ Please choose a number between 1 and {MAX_SPECIFIC_PRODUCTS}.")
        return

    await state.update_data(count=count)
    await state.set_state(BulkTrackStates.entering_products)
    await message.answer(
        f"✍️ Send me {count} product names, <b>one per line</b>.\n\n"
        f"Example:\niphone 15\nmacbook air m3"
    )


@router.message(BulkTrackStates.entering_products)
async def on_products_entered(message: Message, state: FSMContext):
    data = await state.get_data()
    requested_count = data.get("count", MAX_SPECIFIC_PRODUCTS)
    category = data.get("category", "")

    lines = split_lines(message.text, max_lines=MAX_SPECIFIC_PRODUCTS, max_line_length=80)
    lines = lines[:requested_count]

    if not lines:
        await message.answer("⚠️ I didn't find any product names. Please try again.")
        return

    needed_api_calls = len(lines) * 2  # Amazon + Google per product
    if not has_quota(needed_api_calls):
        await message.answer(
            "⚠️ Daily API quota is almost used up. Please try again tomorrow, "
            "or request fewer products."
        )
        await state.clear()
        return

    current_count = count_active_tracked(message.from_user.id)
    remaining_slots = MAX_TOTAL_TRACKED - current_count
    if remaining_slots <= 0:
        await message.answer(f"⚠️ You've reached the {MAX_TOTAL_TRACKED} product limit.")
        await state.clear()
        return
    lines = lines[:remaining_slots]

    status_msg = await message.answer(f"🔍 Searching {len(lines)} products...")
    await state.clear()

    added = []
    skipped_duplicates = []
    not_found = []

    for name in lines:
        result = save_tracked_product(message.from_user.id, name, category)
        if result is None:
            skipped_duplicates.append(name)
            continue
        product, prices = result
        if prices:
            added.append((name, prices[0]))
        else:
            not_found.append(name)

    lines_out = [f"📊 <b>Bulk tracking results — {category}</b>\n"]

    if added:
        lines_out.append("✅ <b>Added:</b>")
        for name, best in added:
            lines_out.append(f"  • {safe_text(name)} — ${best['price']:.2f} ({best['source']})")

    if not_found:
        lines_out.append("\n😕 <b>No prices found for:</b>")
        for name in not_found:
            lines_out.append(f"  • {safe_text(name)}")

    if skipped_duplicates:
        lines_out.append("\n⏭️ <b>Already tracked (skipped):</b>")
        for name in skipped_duplicates:
            lines_out.append(f"  • {safe_text(name)}")

    total_tracked = count_active_tracked(message.from_user.id)
    lines_out.append(f"\n📦 Total tracked: {total_tracked}/{MAX_TOTAL_TRACKED}")

    await status_msg.edit_text("\n".join(lines_out), disable_web_page_preview=True)
    await state.clear()


@router.message(BulkTrackStates.choosing_count_category)
async def on_count_category(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Please send a number.")
        return

    if count < 1 or count > MAX_CATEGORY_PRODUCTS:
        await message.answer(f"⚠️ Please choose a number between 1 and {MAX_CATEGORY_PRODUCTS}.")
        return

    data = await state.get_data()
    category = data.get("category", "Electronics")

    needed_api_calls = 2  # one search call per source, category search itself is 1 query each
    if not has_quota(needed_api_calls):
        await message.answer("⚠️ Daily API quota is almost used up. Please try again tomorrow.")
        await state.clear()
        return

    current_count = count_active_tracked(message.from_user.id)
    remaining_slots = MAX_TOTAL_TRACKED - current_count
    if remaining_slots <= 0:
        await message.answer(f"⚠️ You've reached the {MAX_TOTAL_TRACKED} product limit.")
        await state.clear()
        return

    status_msg = await message.answer(f"🔍 Fetching up to {count} {category} products...")
    await state.clear()

    amazon_results = []
    google_results = []
    try:
        amazon_results = search_amazon(category, limit=count)
    except Exception as e:
        print(f"❌ Amazon category fetch failed: {e}")
    try:
        google_results = search_google_shopping(category, limit=count)
    except Exception as e:
        print(f"❌ Google category fetch failed: {e}")

    increment_usage(2)

    combined = amazon_results + google_results
    combined = [r for r in combined if r["price"] and r["price"] > 0]
    for r in combined:
        r["title"] = html_module.unescape(r["title"])

    seen_titles = set()
    unique_items = []
    for item in combined:
        key = item["title"].lower().strip()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        unique_items.append(item)

    unique_items = unique_items[:min(count, remaining_slots)]

    db = SessionLocal()
    added = []
    try:
        for item in unique_items:
            short_query = item["title"][:60].strip()
            product = TrackedProduct(telegram_id=message.from_user.id, query=short_query)
            db.add(product)
            db.commit()
            db.refresh(product)

            try:
                safe_rating = float(item.get("rating") or 0)
            except (ValueError, TypeError):
                safe_rating = 0.0
            try:
                safe_reviews = int(float(item.get("reviews") or 0))
            except (ValueError, TypeError):
                safe_reviews = 0

            history = PriceHistory(
                tracked_product_id=product.id,
                source=item["source"],
                title=item["title"],
                price=item["price"],
                rating=safe_rating,
                reviews=safe_reviews,
                url=item["url"]
            )
            db.add(history)
            db.commit()
            added.append(item)
    finally:
        db.close()

    if not added:
        await status_msg.edit_text(
            f"😕 No products found for category <b>{category}</b>. Try again later."
        )
        await state.clear()
        return

    lines_out = [f"📊 <b>Bulk tracking results — {category}</b>\n", "✅ <b>Added:</b>"]
    for item in added:
        lines_out.append(f"  • {safe_text(item['title'][:60])} — ${item['price']:.2f} ({item['source']})")

    total_tracked = count_active_tracked(message.from_user.id)
    lines_out.append(f"\n📦 Total tracked: {total_tracked}/{MAX_TOTAL_TRACKED}")

    await status_msg.edit_text("\n".join(lines_out), disable_web_page_preview=True)
    await state.clear()