import asyncio
import logging
import re
import requests
import random
import string
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

API_TOKEN = '8362657958:AAGEYo2DkC3ux72gilefmtcKmbKeDT7Zod8'

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

ACCOUNTS_FILE = "user_accounts.json"
MAX_ACCOUNTS_PER_USER = 5
MAX_MESSAGE_LENGTH = 4000

BASE_URL = "https://api.mail.tm"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# ✅ ФИКС: объявляем user_tokens — это и было причиной ошибки
user_tokens: dict = {}


# ── Хранилище аккаунтов ──────────────────────────────────────────────────────

def load_accounts() -> dict:
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_accounts(accounts: dict) -> None:
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)


user_accounts: dict = load_accounts()


# ── Вспомогательные функции ──────────────────────────────────────────────────

def generate_random_username(length: int = 8) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))


def generate_random_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choices(chars, k=length))


def get_domain() -> str | None:
    try:
        r = requests.get(f"{BASE_URL}/domains", headers=HEADERS, timeout=10)
        data = r.json()
        if isinstance(data, list) and data:
            return data[0]['domain']
        if 'hydra:member' in data and data['hydra:member']:
            return data['hydra:member'][0]['domain']
    except Exception as e:
        logging.error(f"get_domain: {e}")
    return None


def create_account(email: str, password: str) -> dict | None:
    try:
        r = requests.post(
            f"{BASE_URL}/accounts",
            headers=HEADERS,
            json={"address": email, "password": password},
            timeout=10
        )
        if r.status_code in (200, 201):
            return r.json()
        logging.warning(f"create_account status={r.status_code}: {r.text}")
    except Exception as e:
        logging.error(f"create_account: {e}")
    return None


def get_token(email: str, password: str) -> str | None:
    try:
        r = requests.post(
            f"{BASE_URL}/token",
            headers=HEADERS,
            json={"address": email, "password": password},
            timeout=10
        )
        if r.status_code == 200:
            return r.json().get('token')
        logging.warning(f"get_token status={r.status_code}: {r.text}")
    except Exception as e:
        logging.error(f"get_token: {e}")
    return None


def list_messages(token: str) -> list:
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{BASE_URL}/messages", headers=headers, timeout=10)
        data = r.json()
        if isinstance(data, list):
            return data
        if 'hydra:member' in data:
            return data['hydra:member']
    except Exception as e:
        logging.error(f"list_messages: {e}")
    return []


def get_message_content(message_id: str, token: str) -> dict | None:
    headers = {**HEADERS, "Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{BASE_URL}/messages/{message_id}", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logging.error(f"get_message_content: {e}")
    return None


def html_to_text(html_parts: list) -> str:
    soup = BeautifulSoup(''.join(html_parts), 'html.parser')
    for tag in soup.find_all(['a', 'img', 'script', 'style']):
        tag.decompose()
    return re.sub(r'\s+', ' ', soup.get_text()).strip()


# ── Клавиатуры ───────────────────────────────────────────────────────────────

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Мои почты", callback_data="my_emails")],
        [InlineKeyboardButton(text="➕ Создать новую почту", callback_data="create_email")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data="about")]
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")]
    ])


# ── Приветственный текст ──────────────────────────────────────────────────────

def welcome_text(user_id: str) -> str:
    accounts = user_accounts.get(user_id, [])
    if accounts:
        return (
            " <b>Добро пожаловать в TrueMail!</b> \n\n"
            f"📊 <b>Почт создано:</b> {len(accounts)}/{MAX_ACCOUNTS_PER_USER}\n\n"
            "📧 <b>Что можно делать:</b>\n"
            "• Создавать временные email-адреса\n"
            "• Получать письма\n"
            "• Управлять почтами\n\n"
            "<i>Выберите действие 👇</i>"
        )
    return (
        "🌟 <b>Добро пожаловать в TrueMail!</b> 🌟\n\n"
        "📧 <b>TrueMail</b> — сервис временных email-адресов\n\n"
        "✨ <b>Особенности:</b>\n"
        "• До 5 почт на аккаунт\n"
        "• Почты хранятся постоянно\n"
        "• Удобное управление\n\n"
        "➕ <b>Создай свою первую анонимную почту тут!</b>"
    )


# ── Хендлеры ─────────────────────────────────────────────────────────────────

@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    uid = str(message.from_user.id)
    await message.answer(welcome_text(uid), parse_mode='HTML', reply_markup=main_keyboard())


# ── Главное меню (кнопка "Назад") ────────────────────────────────────────────

@dp.callback_query(lambda c: c.data == "back_to_menu")
async def cb_back_to_menu(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    await callback.message.edit_text(welcome_text(uid), parse_mode='HTML', reply_markup=main_keyboard())
    await callback.answer()


# ── Список почт ───────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data == "my_emails")
async def cb_my_emails(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    accounts = user_accounts.get(uid, [])

    if not accounts:
        await callback.message.edit_text(
            "📭 <b>У вас пока нет созданных почт!</b>\n\n"
            "Нажмите «➕ Создать новую почту», чтобы начать.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать почту", callback_data="create_email")],
                [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
            ])
        )
        await callback.answer()
        return

    text = "📧 <b>Ваши почты</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    buttons = []

    for idx, acc in enumerate(accounts):
        email = acc['email']
        created = acc.get('created_at', '—')
        text += f"<b>{idx + 1}.</b> 📨 <code>{email}</code>\n   🕐 Создана: {created}\n\n"
        label = email if len(email) <= 25 else email[:22] + "..."
        buttons.append([InlineKeyboardButton(text=f"📧 {label}", callback_data=f"select_email_{idx}")])

    buttons.append([InlineKeyboardButton(text="➕ Создать новую", callback_data="create_email")])
    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")])

    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


# ── Выбор почты ───────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data.startswith('select_email_'))
async def cb_select_email(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    # ✅ ФИКС: безопасный split — берём только последнюю часть
    email_index = int(callback.data.rsplit('_', 1)[-1])
    accounts = user_accounts.get(uid, [])

    if email_index >= len(accounts):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return

    acc = accounts[email_index]
    email = acc['email']
    token = acc['token']

    # Сохраняем текущую сессию
    user_tokens[uid] = {'token': token, 'email': email, 'index': email_index}

    await _show_inbox(callback, uid, email, token, email_index, refresh=False)


# ── Обновление входящих ──────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data.startswith('refresh_'))
async def cb_refresh(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    email_index = int(callback.data.rsplit('_', 1)[-1])
    accounts = user_accounts.get(uid, [])

    if email_index >= len(accounts):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return

    acc = accounts[email_index]
    user_tokens[uid] = {'token': acc['token'], 'email': acc['email'], 'index': email_index}
    await _show_inbox(callback, uid, acc['email'], acc['token'], email_index, refresh=True)


async def _show_inbox(callback: types.CallbackQuery, uid: str, email: str,
                      token: str, email_index: int, refresh: bool):
    """Общая логика отображения писем для select и refresh."""
    messages = list_messages(token)

    text = (
        f"📧 <b>Текущая почта:</b>\n"
        f"<code>{email}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )
    buttons = []

    if not messages:
        text += "📭 <b>Нет писем</b>\n\nДайте кому-нибудь этот email — письма появятся здесь."
    else:
        text += f"📨 <b>Писем:</b> {len(messages)}\n━━━━━━━━━━━━━━━━━━\n\n"
        for idx, msg in enumerate(messages[:10], 1):
            subject = msg.get('subject', '(без темы)')
            subj_short = subject[:40] + "…" if len(subject) > 40 else subject
            from_addr = msg.get('from', {}).get('address', '?')[:30]
            text += f"<b>{idx}.</b> 📨 <b>От:</b> {from_addr}\n   📌 <b>Тема:</b> {subj_short}\n\n"
            # ✅ ФИКС: ID письма кодируем безопасно (может содержать _)
            safe_id = msg['id'].replace('_', '-')
            buttons.append([InlineKeyboardButton(
                text=f"📖 Письмо {idx}",
                callback_data=f"rmsg_{email_index}_{safe_id}"
            )])

    buttons.append([InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_{email_index}")])
    buttons.append([InlineKeyboardButton(text="🗑 Удалить почту", callback_data=f"delete_email_{email_index}")])
    buttons.append([InlineKeyboardButton(text="🔙 К списку почт", callback_data="my_emails")])

    await callback.message.edit_text(text, parse_mode='HTML',
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer("✅ Обновлено" if refresh else "")


# ── Чтение письма ─────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data.startswith('rmsg_'))
async def cb_read_message(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    # Формат: rmsg_{email_index}_{safe_msg_id}
    parts = callback.data.split('_', 2)          # ['rmsg', email_index, safe_msg_id]
    email_index = int(parts[1])
    safe_msg_id = parts[2]
    message_id = safe_msg_id.replace('-', '_')   # восстанавливаем оригинальный ID

    accounts = user_accounts.get(uid, [])
    if email_index >= len(accounts):
        await callback.answer("❌ Ошибка: почта не найдена", show_alert=True)
        return

    token = accounts[email_index]['token']
    details = get_message_content(message_id, token)

    if not details:
        await callback.answer("❌ Не удалось загрузить письмо", show_alert=True)
        return

    # Извлекаем текст
    if details.get('html'):
        body = html_to_text(details['html'])
    elif details.get('text'):
        body = details['text']
    else:
        body = "Содержимое недоступно."

    if not body.strip():
        body = "📝 Сообщение не содержит текста (возможно, только изображения)."

    if len(body) > MAX_MESSAGE_LENGTH:
        body = body[:MAX_MESSAGE_LENGTH - 50] + "… [обрезано]"

    # Экранируем HTML-символы только в теле письма
    body = body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    from_addr = details.get('from', {}).get('address', '?')
    subject = details.get('subject', '(без темы)')

    output = (
        f"<b>📨 От:</b> {from_addr}\n"
        f"<b>📌 Тема:</b> {subject}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>✨ Ссылки и изображения удалены для безопасности</i>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К письмам", callback_data=f"refresh_{email_index}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
    ])

    await callback.message.edit_text(output, parse_mode='HTML', reply_markup=keyboard)
    await callback.answer()


# ── Создание почты ────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data == "create_email")
async def cb_create_email(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    accounts = user_accounts.get(uid, [])

    if len(accounts) >= MAX_ACCOUNTS_PER_USER:
        await callback.answer(
            f"❌ Достигнут лимит {MAX_ACCOUNTS_PER_USER} почт!\n"
            "Удалите одну из существующих, чтобы создать новую.",
            show_alert=True
        )
        return

    await callback.message.edit_text("⏳ <b>Создаём почту…</b>", parse_mode='HTML')

    username = generate_random_username()
    password = generate_random_password()

    domain = get_domain()
    if not domain:
        await callback.message.edit_text(
            "❌ <b>Ошибка подключения к сервису.</b>\nПопробуйте позже.",
            parse_mode='HTML', reply_markup=back_keyboard()
        )
        await callback.answer()
        return

    email = f"{username}@{domain}"
    account = create_account(email, password)

    if not account:
        await callback.message.edit_text(
            "❌ <b>Не удалось создать email.</b>\nПопробуйте ещё раз.",
            parse_mode='HTML', reply_markup=back_keyboard()
        )
        await callback.answer()
        return

    await asyncio.sleep(1)

    token = get_token(email, password)
    if not token:
        await callback.message.edit_text(
            "❌ <b>Почта создана, но не удалось авторизоваться.</b>\n"
            "Попробуйте ещё раз.",
            parse_mode='HTML', reply_markup=back_keyboard()
        )
        await callback.answer()
        return

    new_acc = {
        'email': email,
        'password': password,
        'token': token,
        'created_at': datetime.now().strftime("%d.%m.%Y %H:%M")
    }

    if uid not in user_accounts:
        user_accounts[uid] = []
    user_accounts[uid].append(new_acc)
    save_accounts(user_accounts)

    success_text = (
        "✅ <b>Почта успешно создана!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📧 <b>Email:</b> <code>{email}</code>\n"
        f"🔑 <b>Пароль:</b> <code>{password}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Всего почт:</b> {len(user_accounts[uid])}/{MAX_ACCOUNTS_PER_USER}\n\n"
        "<i>Почта сохранена и будет доступна всегда!</i>"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Мои почты", callback_data="my_emails")],
        [InlineKeyboardButton(text="➕ Создать ещё", callback_data="create_email")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
    ])

    await callback.message.edit_text(success_text, parse_mode='HTML', reply_markup=keyboard)
    await callback.answer()


# ── Удаление почты ────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data.startswith('delete_email_'))
async def cb_delete_email(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    email_index = int(callback.data.rsplit('_', 1)[-1])
    accounts = user_accounts.get(uid, [])

    if email_index >= len(accounts):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return

    email = accounts[email_index]['email']
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{email_index}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"refresh_{email_index}")]
    ])

    await callback.message.edit_text(
        f"⚠️ <b>Удалить почту?</b>\n\n"
        f"📧 <code>{email}</code>\n\n"
        f"<i>Все письма будут потеряны безвозвратно!</i>",
        parse_mode='HTML', reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith('confirm_delete_'))
async def cb_confirm_delete(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    email_index = int(callback.data.rsplit('_', 1)[-1])
    accounts = user_accounts.get(uid, [])

    if email_index >= len(accounts):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return

    deleted = user_accounts[uid].pop(email_index)
    save_accounts(user_accounts)

    # Чистим кэш сессии если был выбран этот ящик
    if uid in user_tokens and user_tokens[uid].get('index') == email_index:
        del user_tokens[uid]

    await callback.message.edit_text(
        f"🗑 <b>Почта удалена!</b>\n\n"
        f"📧 <code>{deleted['email']}</code>\n\n"
        f"Осталось почт: {len(user_accounts.get(uid, []))}/{MAX_ACCOUNTS_PER_USER}",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📧 Мои почты", callback_data="my_emails")],
            [InlineKeyboardButton(text="➕ Создать новую", callback_data="create_email")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
        ])
    )
    await callback.answer()


# ── Поддержка и О боте ────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data == "support")
async def cb_support(callback: types.CallbackQuery):
    text = (
        "🆘 <b>Поддержка TrueMail</b>\n\n"
        "❓ Вопросы или проблемы?\n"
        "🐛 Нашли баг?\n"
        "📝 Предложения?\n\n"
        "<b>Свяжитесь с разработчиком:</b>\n"
        "👨‍💻 @internetcomunity"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Написать разработчику", url="https://t.me/internetcomunity")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=keyboard)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "about")
async def cb_about(callback: types.CallbackQuery):
    text = (
        "ℹ️ <b>О TrueMail</b>\n\n"
        "🤖 <b>Версия:</b> 1.0\n"
        "👨‍💻 <b>Разработчик:</b> @internetcomunity\n\n"
        "<b>✨ Особенности:</b>\n"
        "• До 5 почт на аккаунт\n"
        "• Постоянное хранение\n"
        "• Удобное управление\n"
        "• Безопасность и анонимность\n\n"
        "<i>TrueMail — ваши временные почты всегда с вами!</i>"
    )
    await callback.message.edit_text(text, parse_mode='HTML', reply_markup=back_keyboard())
    await callback.answer()


# ── Запуск ────────────────────────────────────────────────────────────────────

async def main():
    try:
        me = await bot.get_me()
        total = sum(len(v) for v in user_accounts.values())
        print("=" * 45)
        print("🌟  TrueMail Bot v1.0")
        print("=" * 45)
        print(f"✅  Бот: @{me.username} (id={me.id})")
        print(f"✅  Загружено аккаунтов: {total}")
        print(f"✅  Лимит почт на юзера: {MAX_ACCOUNTS_PER_USER}")
        print("🚀  Polling запущен…")
        print("=" * 45)

        await bot.set_my_commands([
            types.BotCommand(command="start", description="🏠 Главное меню")
        ])
        await dp.start_polling(bot)
    except Exception as e:
        logging.critical(f"Ошибка запуска: {e}")


if __name__ == '__main__':
    asyncio.run(main())
