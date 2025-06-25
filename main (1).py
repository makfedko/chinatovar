from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import pandas as pd


# === Настройки ===
ENTER YOU TELEGRAM TOKEN
EXCEL_FILE = 'Отстатки (1).xls'

admin_ids = []  # ← Замени на свой Telegram ID


# === Чтение данных из Excel ===
def load_products():
    try:
        df = pd.read_excel(EXCEL_FILE, header=None)

        # Поиск заголовков по ключевым словам
        headers = {}
        for j in range(min(50, len(df))):  # Проверяем первые 50 строк
            row = df.iloc[j]
            for i_col, cell in enumerate(row):
                if isinstance(cell, str) and str(cell).strip() != '':
                    cell = str(cell).strip().lower()
                    if 'код' in cell and 'code' not in headers:
                        headers['code'] = i_col
                    elif 'наименование' in cell or 'название' in cell:
                        headers['name'] = i_col
                    elif 'остаток' in cell:
                        headers['stock'] = i_col
                    elif 'цена' in cell:
                        headers['price'] = i_col

            if len(headers) >= 4:
                found_row_index = j + 1
                break
        else:
            raise Exception("Не найдены все необходимые столбцы в таблице")

        products_list = []
        start_row = found_row_index if found_row_index is not None else 0

        for idx in range(start_row, len(df)):
            row = df.iloc[idx]

            code = str(row[headers['code']]).strip() if not pd.isna(row[headers['code']]) else None
            name = str(row[headers['name']]).strip() if not pd.isna(row[headers['name']]) else None
            stock = int(float(row[headers['stock']])) if not pd.isna(row[headers['stock']]) else 0
            price = float(row[headers['price']]) if not pd.isna(row[headers['price']]) else 0

            if name and code:
                products_list.append({
                    'code': code,
                    'name': name,
                    'stock': stock,
                    'price': price
                })

        return products_list

    except Exception as e:
        print(f"❌ Ошибка при чтении файла: {e}")
        return []


# === Все товары из Excel файла ===
products = load_products()
print(f"✅ Загружено товаров: {len(products)}")


# === Категории и ключевые слова ===
categories = {
    "шампура": ["шампур", "шпажк"],
    "печи": ["печь", "мангал"],
    "гриль": ["гриль", "барбекю"],
    "наборы": ["набор", "комплект"],
    "миски": ["миска"],
    "турки": ["турка"],
    "чайники": ["чайник"],
    "овощерезки": ["овощерезк"],
    "обогреватели": ["обогреватель"],
    "для уборки": ["швабр"]
}


# === Функция фильтрации товаров по категории ===
def filter_products_by_category(category_key):
    keywords = categories.get(category_key, [])
    result = []
    for product in products:
        name = product["name"].lower()
        if any(kw in name for kw in keywords):
            result.append(product)
    return result


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🛍 Каталог", callback_data="catalog")],
        [InlineKeyboardButton("🛒 Корзина", callback_data="cart")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text("Добро пожаловать! Выберите действие:", reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text("Добро пожаловать! Выберите действие:", reply_markup=reply_markup)


# === Обработка кнопок ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "catalog":
        keyboard = [[InlineKeyboardButton(cat.capitalize(), callback_data=f"cat_{cat}")] for cat in categories.keys()]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        if query.message.text != "📦 Выберите категорию:" or query.message.reply_markup != reply_markup:
            await query.edit_message_text("📦 Выберите категорию:", reply_markup=reply_markup)

    elif data.startswith("cat_"):
        category_key = data[4:]  # Убираем префикс "cat_"
        filtered = filter_products_by_category(category_key)

        if not filtered:
            await query.edit_message_text(f"❌ В категории '{category_key}' товаров нет.")
            return

        buttons = [[InlineKeyboardButton(p['name'], callback_data=f"prod_{p['code']}")] for p in filtered]
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="catalog")])
        reply_markup = InlineKeyboardMarkup(buttons)

        if query.message.text != "📦 Выберите товар:" or query.message.reply_markup != reply_markup:
            await query.edit_message_text("📦 Выберите товар:", reply_markup=reply_markup)

    elif data.startswith("prod_"):
        code = data[5:]
        product = next((p for p in products if p['code'] == code), None)

        if not product:
            await query.edit_message_text("❌ Товар не найден.")
            return

        context.user_data['waiting_for_quantity'] = code
        msg = (
            f"📌 Товар: {product['name']}\n"
            f"📦 Остаток: {product['stock']} шт.\n"
            f"💰 Цена: {product['price']} ₽\n\n"
            f"Введите нужное количество:\n\n"
            f"📞 Хотите заказать больше? Свяжитесь с нами:\n"
            f"<b>+7 (928) 100-33-82</b>"
        )
        buttons = [[InlineKeyboardButton("⬅️ Назад", callback_data="catalog")]]
        reply_markup = InlineKeyboardMarkup(buttons)

        if query.message.text != msg or query.message.reply_markup != reply_markup:
            await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "cart":
        cart = context.user_data.get('cart', {})
        if not cart:
            await query.edit_message_text("🛒 Ваша корзина пока пуста.")
            return

        message = "🛒 Ваша корзина:\n\n"
        total = 0
        for code, item in cart.items():
            p = next((x for x in products if x['code'] == code), None)
            if p:
                cost = p['price'] * item['quantity']
                message += f"{p['name']} ×{item['quantity']} → {cost:.2f} ₽\n"
                total += cost
        message += f"\n💰 Итого: {total:.2f} ₽"

        buttons = [
            [InlineKeyboardButton("📱 WhatsApp", url="https://wa.me/79281003382")], 
            [InlineKeyboardButton("⬅️ Вернуться к каталогу", callback_data="catalog")]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        if query.message.text != message or query.message.reply_markup != reply_markup:
            await query.edit_message_text(message, reply_markup=reply_markup)

    elif data == "back_to_main":
        await start(query, context)


# === Админ-панель ===
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admin_ids:
        if update.message:
            await update.message.reply_text("⛔️ Доступ запрещён")
        else:
            await update.callback_query.edit_message_text("⛔️ Доступ запрещён")
        return

    page = int(context.args[0]) if context.args else 0
    per_page = 10
    start_idx = page * per_page
    end_idx = start_idx + per_page

    buttons = []
    for idx in range(start_idx, min(end_idx, len(products))):
        p = products[idx]
        buttons.append([
            InlineKeyboardButton(
                f"{p['name']} | {p['stock']} шт. | {p['price']}₽",
                callback_data=f"admin_edit_{p['code']}"
            )
        ])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"admin_page_{page - 1}"))
    if end_idx < len(products):
        nav_buttons.append(InlineKeyboardButton("➡️ Вперёд", callback_data=f"admin_page_{page + 1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton("➕ Добавить товар", callback_data="admin_add_product")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")])

    reply_markup = InlineKeyboardMarkup(buttons)
    if update.message:
        await update.message.reply_text("🔧 Админ-панель: список товаров", reply_markup=reply_markup)
    elif update.callback_query:
        if query.message.text != "🔧 Админ-панель: список товаров" or query.message.reply_markup != reply_markup:
            await query.edit_message_text("🔧 Админ-панель: список товаров", reply_markup=reply_markup)


# === Обработка кнопок админ-панели ===
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in admin_ids:
        await query.edit_message_text("⛔️ Доступ запрещён.")
        return

    data = query.data

    if data.startswith("admin_page_"):
        page = int(data.split("_")[-1])
        context.args = [page]
        await admin_panel(update, context)

    elif data.startswith("admin_edit_"):
        code = data.split("_")[-1]
        product = next((p for p in products if str(p['code']) == code), None)
        if not product:
            await query.edit_message_text("❌ Товар не найден.")
            return

        context.user_data['edit_product_code'] = code
        await query.edit_message_text(
            f"🔧 Редактирование товара:\n"
            f"<b>{product['name']}</b>\n"
            f"Остаток: <b>{product['stock']}</b> шт.\n"
            f"Цена: <b>{product['price']}₽</b>\n\n"
            f"Что хотите изменить?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Изменить цену", callback_data="admin_change_price"),
                 InlineKeyboardButton("📦 Изменить остаток", callback_data="admin_change_stock")],
                [InlineKeyboardButton("⬅️ Назад к списку", callback_data="admin_page_0")]
            ]),
            parse_mode="HTML"
        )

    elif data == "admin_change_price":
        code = context.user_data.get('edit_product_code')
        product = next((p for p in products if p['code'] == code), None)
        if not product:
            await query.edit_message_text("❌ Товар не найден.")
            return

        context.user_data['admin_wait_price'] = code
        await query.edit_message_text(
            f"Введите новую цену для <b>{product['name']}</b> (текущее: {product['price']}₽):",
            parse_mode="HTML"
        )

    elif data == "admin_change_stock":
        code = context.user_data.get('edit_product_code')
        product = next((p for p in products if p['code'] == code), None)
        if not product:
            await query.edit_message_text("❌ Товар не найден.")
            return

        context.user_data['admin_wait_stock'] = code
        await query.edit_message_text(
            f"Введите новый остаток для <b>{product['name']}</b> (текущее: {product['stock']} шт.):",
            parse_mode="HTML"
        )

    elif data == "admin_add_product":
        context.user_data['add_step'] = 0
        context.user_data['add_product'] = {}
        await query.edit_message_text("Введите <b>код</b> нового товара:", parse_mode="HTML")


# === Обработка текстовых сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'waiting_for_quantity' in context.user_data:
        code = context.user_data['waiting_for_quantity']
        product = next((p for p in products if p['code'] == code), None)

        if not product:
            del context.user_data['waiting_for_quantity']
            await update.message.reply_text("❌ Товар не найден.")
            return

        try:
            quantity = int(update.message.text)
            if quantity <= 0:
                raise ValueError
            if quantity > product['stock']:
                buttons = [[InlineKeyboardButton("📞 Связаться", url="tel:+79281003382")]]
                reply_markup = InlineKeyboardMarkup(buttons)
                await update.message.reply_text(
                    f"❌ На складе только {product['stock']} шт.\n"
                    "Хотите заказать больше? Свяжитесь с нами:",
                    reply_markup=reply_markup
                )
                return
        except:
            await update.message.reply_text("⚠️ Пожалуйста, введите число.")
            return

        # Добавляем в корзину
        cart = context.user_data.get('cart', {})
        if code in cart:
            cart[code]['quantity'] += quantity
        else:
            cart[code] = {'quantity': quantity}
        context.user_data['cart'] = cart
        del context.user_data['waiting_for_quantity']

        await update.message.reply_text(f"✅ {product['name']} ×{quantity} добавлено в корзину.")

        # Кнопка назад
        buttons = [[InlineKeyboardButton("⬅️ Продолжить выбор", callback_data="catalog")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("📦 Продолжить выбор?", reply_markup=reply_markup)

    # === Админ: изменение цены или остатка ===
    elif 'admin_wait_price' in context.user_data:
        code = context.user_data.pop('admin_wait_price')
        product = next((p for p in products if p['code'] == code), None)
        try:
            new_price = round(float(update.message.text.replace(',', '.')), 2)
            product['price'] = new_price
            await update.message.reply_text(f"✅ Цена обновлена: {new_price:.2f} ₽")
            save_products(products)
        except:
            await update.message.reply_text("⚠️ Некорректная цена. Попробуйте снова.")

    elif 'admin_wait_stock' in context.user_data:
        code = context.user_data.pop('admin_wait_stock')
        product = next((p for p in products if p['code'] == code), None)
        try:
            new_stock = int(update.message.text)
            if new_stock < 0:
                raise ValueError
            product['stock'] = new_stock
            await update.message.reply_text(f"✅ Остаток обновлён: {new_stock} шт.")
            save_products(products)
        except:
            await update.message.reply_text("⚠️ Некорректный остаток. Попробуйте снова.")

    # === Админ: добавление товара ===
    elif 'add_step' in context.user_data:
        step = context.user_data['add_step']
        new_prod = context.user_data['add_product']

        if step == 0:
            code = update.message.text.strip()
            if any(str(p['code']) == code for p in products):
                await update.message.reply_text("⚠️ Такой код уже существует. Введите другой:")
                return
            new_prod['code'] = code
            context.user_data['add_step'] = 1
            await update.message.reply_text("Введите <b>название</b> товара:", parse_mode="HTML")

        elif step == 1:
            new_prod['name'] = update.message.text.strip()
            context.user_data['add_step'] = 2
            await update.message.reply_text("Введите <b>остаток</b> (шт.):", parse_mode="HTML")

        elif step == 2:
            try:
                stock = int(update.message.text)
                if stock < 0:
                    raise ValueError
                new_prod['stock'] = stock
                context.user_data['add_step'] = 3
                await update.message.reply_text("Введите <b>цену</b> (₽):", parse_mode="HTML")
            except:
                await update.message.reply_text("⚠️ Введите целое число (0 и выше)")

        elif step == 3:
            try:
                price = round(float(update.message.text.replace(',', '.')), 2)
                new_prod['price'] = price
                products.append(new_prod.copy())
                save_products(products)
                await update.message.reply_text(
                    f"✅ Товар <b>{new_prod['name']}</b> добавлен!\n"
                    f"Код: <code>{new_prod['code']}</code>\n"
                    f"Остаток: <b>{new_prod['stock']}</b>\n"
                    f"Цена: <b>{new_prod['price']}₽</b>",
                    parse_mode="HTML"
                )
                context.user_data.clear()
            except:
                await update.message.reply_text("⚠️ Введите корректную цену (например, 150.50)")
                return


# === Сохранение обновлённых данных ===
def save_products(products_list):
    import pandas as pd
    df = pd.DataFrame(products_list)
    df.to_excel(EXCEL_FILE, index=False)
    print("💾 Товары сохранены")


# === Запуск бота ===
async def main():
    global products
    products = load_products()
    print(f"✅ Загружено товаров: {len(products)}")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin_"))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 Бот запущен...")
    await app.run_polling()


if __name__ == '__main__':
    import asyncio
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
