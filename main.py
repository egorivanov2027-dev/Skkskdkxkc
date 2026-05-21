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
from aiogram.exceptions import TelegramBadRequest

logging.basicConfig(level=logging.INFO)

# ══════════════════════════════════════════════════════════
#  ⚙️  НАСТРОЙКИ
# ══════════════════════════════════════════════════════════

API_TOKEN    = '8362657958:AAGEYo2DkC3ux72gilefmtcKmbKeDT7Zod8'
ADMIN_ID     = 69198496        # ← ЗАМЕНИ на свой ID (@userinfobot)
CHANNEL_ID   = -1002590130150   # ← ЗАМЕНИ на ID канала (@getmyid_bot)
CHANNEL_LINK = "https://t.me/+rJjA9cFAPMs3ZmVi"

MAX_ACCOUNTS_PER_USER = 5
MAX_ACCOUNTS_ADMIN    = 9999
MAX_MESSAGE_LENGTH    = 3800

# ══════════════════════════════════════════════════════════

BASE_URL = "https://api.mail.tm"
HEADERS  = {"Content-Type": "application/json", "Accept": "application/json"}

ACCOUNTS_FILE  = "user_accounts.json"
USER_INFO_FILE = "user_info.json"

bot = Bot(token=API_TOKEN)
dp  = Dispatcher()

user_tokens: dict = {}


# ── Хранилище ─────────────────────────────────────────────────────────────────

def _load(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save(path: str, data: dict) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

user_accounts: dict = _load(ACCOUNTS_FILE)
user_info:     dict = _load(USER_INFO_FILE)

def save_all():
    _save(ACCOUNTS_FILE, user_accounts)
    _save(USER_INFO_FILE, user_info)

def update_user_info(user: types.User):
    uid = str(user.id)
    user_info[uid] = {
        "username":   user.username or "",
        "first_name": user.first_name or "",
        "last_seen":  datetime.now().strftime("%d.%m.%Y %H:%M")
    }
    _save(USER_INFO_FILE, user_info)


# ── Получение имени пользователя (с фолбэком в Telegram API) ──────────────────

async def get_user_display(uid: str) -> dict:
    """
    Возвращает {username, first_name, name} для uid.
    Если нет в кэше — пробует получить из Telegram.
    """
    info = user_info.get(uid, {})
    if info.get('first_name') or info.get('username'):
        uname = info.get('username', '')
        fname = info.get('first_name', '')
        name  = f"@{uname}" if uname else fname
        return {"username": uname, "first_name": fname, "name": name,
                "last_seen": info.get('last_seen', '—')}

    # Фолбэк: пробуем получить из Telegram
    try:
        chat = await bot.get_chat(int(uid))
        uname = chat.username or ""
        fname = chat.first_name or ""
        # Сохраняем в кэш
        user_info[uid] = {
            "username":   uname,
            "first_name": fname,
            "last_seen":  user_info.get(uid, {}).get('last_seen', '—')
        }
        _save(USER_INFO_FILE, user_info)
        name = f"@{uname}" if uname else (fname or f"ID:{uid}")
        return {"username": uname, "first_name": fname, "name": name,
                "last_seen": user_info[uid]['last_seen']}
    except Exception:
        pass

    return {"username": "", "first_name": "", "name": f"ID:{uid}", "last_seen": "—"}


# ── Проверка подписки ─────────────────────────────────────────────────────────

async def is_subscribed(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ('left', 'kicked', 'banned')
    except Exception:
        return True   # если бот не в канале — не блокируем

def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я подписался",         callback_data="check_sub")]
    ])

async def guard_sub(callback: types.CallbackQuery) -> bool:
    if callback.data == "check_sub":
        return True
    if not await is_subscribed(callback.from_user.id):
        await callback.answer("❌ Сначала подпишитесь на канал!", show_alert=True)
        return False
    return True


# ── mail.tm API ───────────────────────────────────────────────────────────────

def generate_random_username(length: int = 10) -> str:
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_random_password(length: int = 14) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def get_domain() -> str | None:
    for _ in range(3):
        try:
            r = requests.get(f"{BASE_URL}/domains", headers=HEADERS, timeout=10)
            data = r.json()
            if isinstance(data, list) and data:
                return data[0]['domain']
            if isinstance(data, dict):
                members = data.get('hydra:member', [])
                if members:
                    return members[0]['domain']
        except Exception as e:
            logging.warning(f"get_domain: {e}")
    return None

def create_account_api(email: str, password: str) -> dict | None:
    try:
        r = requests.post(f"{BASE_URL}/accounts", headers=HEADERS,
                          json={"address": email, "password": password}, timeout=15)
        if r.status_code in (200, 201):
            return r.json()
        logging.warning(f"create_account [{r.status_code}]: {r.text[:200]}")
    except Exception as e:
        logging.error(f"create_account: {e}")
    return None

def get_token_api(email: str, password: str) -> str | None:
    for _ in range(3):
        try:
            r = requests.post(f"{BASE_URL}/token", headers=HEADERS,
                              json={"address": email, "password": password}, timeout=15)
            if r.status_code == 200:
                return r.json().get('token')
            logging.warning(f"get_token [{r.status_code}]: {r.text[:200]}")
        except Exception as e:
            logging.warning(f"get_token: {e}")
    return None

def list_messages_api(token: str) -> list:
    try:
        r = requests.get(f"{BASE_URL}/messages",
                         headers={**HEADERS, "Authorization": f"Bearer {token}"}, timeout=10)
        data = r.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get('hydra:member', [])
    except Exception as e:
        logging.error(f"list_messages: {e}")
    return []

def get_message_api(message_id: str, token: str) -> dict | None:
    try:
        r = requests.get(f"{BASE_URL}/messages/{message_id}",
                         headers={**HEADERS, "Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logging.error(f"get_message: {e}")
    return None

def html_to_text(html_parts: list) -> str:
    soup = BeautifulSoup(''.join(html_parts), 'html.parser')
    for tag in soup.find_all(['a', 'img', 'script', 'style']):
        tag.decompose()
    return re.sub(r'\s+', ' ', soup.get_text()).strip()


# ── Создание почты с повторами ────────────────────────────────────────────────

async def try_create_email() -> dict | None:
    domain = get_domain()
    if not domain:
        return None
    for attempt in range(5):
        username = generate_random_username(10 + attempt * 2)
        password = generate_random_password()
        email    = f"{username}@{domain}"
        if not create_account_api(email, password):
            await asyncio.sleep(1.5)
            continue
        await asyncio.sleep(2)
        token = get_token_api(email, password)
        if token:
            return {"email": email, "password": password, "token": token}
        await asyncio.sleep(1)
    return None


# ── Лимит ─────────────────────────────────────────────────────────────────────

def get_limit(uid: str) -> int:
    return MAX_ACCOUNTS_ADMIN if int(uid) == ADMIN_ID else MAX_ACCOUNTS_PER_USER

def limit_str(uid: str) -> str:
    return "∞" if int(uid) == ADMIN_ID else str(MAX_ACCOUNTS_PER_USER)


# ── Клавиатуры ───────────────────────────────────────────────────────────────

def main_keyboard(uid: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📧 Мои почты",            callback_data="my_emails")],
        [InlineKeyboardButton(text="➕ Создать новую почту",   callback_data="create_email")],
        [InlineKeyboardButton(text="💼 Купить место для почт", url="https://t.me/internetcomunity")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support"),
         InlineKeyboardButton(text="ℹ️ О боте",   callback_data="about")],
    ]
    if int(uid) == ADMIN_ID:
        rows.append([InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")]
    ])


# ── Приветствие ───────────────────────────────────────────────────────────────

def welcome_text(uid: str) -> str:
    accounts = user_accounts.get(uid, [])
    is_adm   = int(uid) == ADMIN_ID
    badge    = "👑 <b>Администратор</b>\n\n" if is_adm else ""
    cnt, lim = len(accounts), limit_str(uid)
    if accounts:
        return (
            f"🌟 <b>TrueMail</b>\n\n{badge}"
            f"📊 <b>Почт:</b> {cnt}/{lim}\n\n"
            "📧 Выберите действие 👇"
        )
    return (
        f"🌟 <b>Добро пожаловать в TrueMail!</b>\n\n{badge}"
        "📧 Временные email-адреса прямо в Telegram\n\n"
        "✨ <b>Возможности:</b>\n"
        f"• До {lim} почт на аккаунт\n"
        "• Постоянное хранение\n"
        "• Письма прямо в боте\n\n"
        "➕ <b>Создайте первую почту!</b>"
    )


# ══════════════════════════════════════════════════════════
#  🤖  ХЕНДЛЕРЫ
# ══════════════════════════════════════════════════════════

async def safe_edit(msg: types.Message, text: str, **kwargs):
    try:
        await msg.edit_text(text, **kwargs)
    except TelegramBadRequest:
        pass


@dp.message(Command('start'))
async def cmd_start(message: types.Message):
    uid = str(message.from_user.id)
    update_user_info(message.from_user)
    if not await is_subscribed(message.from_user.id):
        await message.answer(
            "🔒 <b>Доступ закрыт!</b>\n\nПодпишитесь на канал 👇",
            parse_mode='HTML', reply_markup=sub_keyboard()
        )
        return
    await message.answer(welcome_text(uid), parse_mode='HTML', reply_markup=main_keyboard(uid))


@dp.callback_query(lambda c: c.data == "check_sub")
async def cb_check_sub(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    update_user_info(callback.from_user)
    if not await is_subscribed(callback.from_user.id):
        await callback.answer("❌ Вы ещё не подписались!", show_alert=True)
        return
    await safe_edit(callback.message, welcome_text(uid), parse_mode='HTML', reply_markup=main_keyboard(uid))
    await callback.answer("✅ Добро пожаловать!")


@dp.callback_query(lambda c: c.data == "back_to_menu")
async def cb_back_to_menu(callback: types.CallbackQuery):
    uid = str(callback.from_user.id)
    update_user_info(callback.from_user)
    await safe_edit(callback.message, welcome_text(uid), parse_mode='HTML', reply_markup=main_keyboard(uid))
    await callback.answer()


# ── Список почт ───────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data == "my_emails")
async def cb_my_emails(callback: types.CallbackQuery):
    if not await guard_sub(callback): return
    uid      = str(callback.from_user.id)
    accounts = user_accounts.get(uid, [])
    lim      = limit_str(uid)

    if not accounts:
        await safe_edit(callback.message,
            "📭 <b>У вас пока нет почт!</b>\n\nНажмите «➕ Создать», чтобы начать.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Создать почту", callback_data="create_email")],
                [InlineKeyboardButton(text="🔙 Назад",        callback_data="back_to_menu")]
            ])
        )
        await callback.answer()
        return

    text    = f"📧 <b>Ваши почты</b> ({len(accounts)}/{lim})\n━━━━━━━━━━━━━━━━━━\n\n"
    buttons = []
    for idx, acc in enumerate(accounts):
        email   = acc['email']
        created = acc.get('created_at', '—')
        text   += f"<b>{idx+1}.</b> <code>{email}</code>\n   🕐 {created}\n\n"
        label   = email[:28] + "…" if len(email) > 28 else email
        buttons.append([InlineKeyboardButton(text=f"📬 {label}", callback_data=f"sel_{idx}")])

    buttons.append([InlineKeyboardButton(text="➕ Создать новую", callback_data="create_email")])
    buttons.append([InlineKeyboardButton(text="🔙 Главное меню",  callback_data="back_to_menu")])
    await safe_edit(callback.message, text, parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


# ── Входящие ─────────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data.startswith('sel_'))
async def cb_select_email(callback: types.CallbackQuery):
    if not await guard_sub(callback): return
    uid         = str(callback.from_user.id)
    email_index = int(callback.data[4:])
    accounts    = user_accounts.get(uid, [])
    if email_index >= len(accounts):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return
    acc = accounts[email_index]
    user_tokens[uid] = {'token': acc['token'], 'email': acc['email'], 'index': email_index}
    await _show_inbox(callback, acc['email'], acc['token'], email_index, False)


@dp.callback_query(lambda c: c.data.startswith('ref_'))
async def cb_refresh(callback: types.CallbackQuery):
    if not await guard_sub(callback): return
    uid         = str(callback.from_user.id)
    email_index = int(callback.data[4:])
    accounts    = user_accounts.get(uid, [])
    if email_index >= len(accounts):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return
    acc = accounts[email_index]
    user_tokens[uid] = {'token': acc['token'], 'email': acc['email'], 'index': email_index}
    await _show_inbox(callback, acc['email'], acc['token'], email_index, True)


async def _show_inbox(callback: types.CallbackQuery, email: str,
                      token: str, email_index: int, refresh: bool):
    messages = list_messages_api(token)
    text     = f"📬 <b>Почта:</b>\n<code>{email}</code>\n━━━━━━━━━━━━━━━━━━\n\n"
    buttons  = []

    if not messages:
        text += "📭 <b>Писем нет</b>\n\nПоделитесь адресом — письма появятся здесь."
    else:
        text += f"📨 <b>Писем: {len(messages)}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        for idx, msg in enumerate(messages[:10], 1):
            subject   = (msg.get('subject') or '(без темы)')[:40]
            from_addr = (msg.get('from') or {}).get('address', '?')[:30]
            text += f"<b>{idx}.</b> 📨 <code>{from_addr}</code>\n   📌 {subject}\n\n"
            safe_id = msg['id'].replace('_', '-')
            btn_text = f"📖 {subject[:25]}…" if len(subject) > 25 else f"📖 {subject}"
            buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"msg_{email_index}_{safe_id}")])

    buttons.append([InlineKeyboardButton(text="🔄 Обновить",     callback_data=f"ref_{email_index}")])
    buttons.append([InlineKeyboardButton(text="🗑 Удалить почту", callback_data=f"del_{email_index}")])
    buttons.append([InlineKeyboardButton(text="🔙 Мои почты",    callback_data="my_emails")])
    await safe_edit(callback.message, text, parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer("✅ Обновлено" if refresh else "")


# ── Чтение письма ─────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data.startswith('msg_'))
async def cb_read_msg(callback: types.CallbackQuery):
    if not await guard_sub(callback): return
    uid   = str(callback.from_user.id)
    # msg_{email_index}_{safe_id}
    parts = callback.data.split('_', 2)
    email_index = int(parts[1])
    message_id  = parts[2].replace('-', '_')

    accounts = user_accounts.get(uid, [])
    if email_index >= len(accounts):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return

    details = get_message_api(message_id, accounts[email_index]['token'])
    if not details:
        await callback.answer("❌ Не удалось загрузить", show_alert=True)
        return

    body = ""
    if details.get('html'):
        body = html_to_text(details['html'])
    elif details.get('text'):
        body = details['text']
    if not body.strip():
        body = "📝 Письмо не содержит текста."
    if len(body) > MAX_MESSAGE_LENGTH:
        body = body[:MAX_MESSAGE_LENGTH] + "\n… [текст обрезан]"

    body      = body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    from_addr = (details.get('from') or {}).get('address', '?')
    subject   = details.get('subject', '(без темы)')

    output = (
        f"📨 <b>От:</b> <code>{from_addr}</code>\n"
        f"📌 <b>Тема:</b> {subject}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<i>✨ Ссылки удалены для безопасности</i>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 К письмам",    callback_data=f"ref_{email_index}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
    ])
    try:
        await callback.message.edit_text(output, parse_mode='HTML', reply_markup=keyboard)
    except TelegramBadRequest:
        await callback.message.edit_text(
            f"⚠️ Не удалось отобразить.\n<b>От:</b> {from_addr}\n<b>Тема:</b> {subject}",
            parse_mode='HTML', reply_markup=keyboard
        )
    await callback.answer()


# ── Создание почты ────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data == "create_email")
async def cb_create_email(callback: types.CallbackQuery):
    if not await guard_sub(callback): return
    uid      = str(callback.from_user.id)
    accounts = user_accounts.get(uid, [])
    limit    = get_limit(uid)

    if len(accounts) >= limit:
        await callback.answer(
            f"❌ Лимит {limit_str(uid)} почт!\nУдалите одну или купите доп. место.",
            show_alert=True
        )
        return

    await safe_edit(callback.message,
        "⏳ <b>Создаём почту…</b>\n\n<i>Несколько секунд, подождите</i>",
        parse_mode='HTML'
    )

    result = await try_create_email()

    if not result:
        await safe_edit(callback.message,
            "❌ <b>Не удалось создать email.</b>\n\n"
            "Сервис mail.tm временно недоступен.\nПопробуйте через 1–2 минуты.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="create_email")],
                [InlineKeyboardButton(text="🔙 Главное меню",      callback_data="back_to_menu")]
            ])
        )
        await callback.answer()
        return

    email, password, token = result['email'], result['password'], result['token']
    new_acc = {
        'email':      email,
        'password':   password,
        'token':      token,
        'created_at': datetime.now().strftime("%d.%m.%Y %H:%M"),
        'owner_uid':  uid
    }
    if uid not in user_accounts:
        user_accounts[uid] = []
    user_accounts[uid].append(new_acc)
    save_all()

    cnt = len(user_accounts[uid])

    # Уведомление админу
    if int(uid) != ADMIN_ID:
        info  = user_info.get(uid, {})
        uname = info.get('username', '')
        fname = info.get('first_name', 'Неизвестно')
        name  = f"@{uname}" if uname else fname
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🆕 <b>Новая почта создана!</b>\n\n"
                f"👤 <b>Юзер:</b> {name}\n"
                f"🆔 <b>ID:</b> <code>{uid}</code>\n"
                f"📧 <b>Email:</b> <code>{email}</code>\n"
                f"🕐 <b>Время:</b> {new_acc['created_at']}",
                parse_mode='HTML'
            )
        except Exception:
            pass

    await safe_edit(callback.message,
        "✅ <b>Почта создана!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📧 <b>Email:</b>\n<code>{email}</code>\n\n"
        f"🔑 <b>Пароль:</b> <code>{password}</code>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Почт:</b> {cnt}/{limit_str(uid)}\n\n"
        "<i>📌 Сохранена навсегда в вашем профиле</i>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📬 Открыть почту", callback_data=f"sel_{cnt-1}")],
            [InlineKeyboardButton(text="➕ Создать ещё",   callback_data="create_email")],
            [InlineKeyboardButton(text="🏠 Главное меню",  callback_data="back_to_menu")]
        ])
    )
    await callback.answer("✅ Готово!")


# ── Удаление почты ────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data.startswith('del_'))
async def cb_delete_email(callback: types.CallbackQuery):
    if not await guard_sub(callback): return
    uid         = str(callback.from_user.id)
    email_index = int(callback.data[4:])
    accounts    = user_accounts.get(uid, [])
    if email_index >= len(accounts):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return
    email = accounts[email_index]['email']
    await safe_edit(callback.message,
        f"⚠️ <b>Удалить почту?</b>\n\n📧 <code>{email}</code>\n\n"
        "<i>Все письма будут потеряны безвозвратно!</i>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"cfdel_{email_index}")],
            [InlineKeyboardButton(text="❌ Отмена",      callback_data=f"ref_{email_index}")]
        ])
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith('cfdel_'))
async def cb_confirm_delete(callback: types.CallbackQuery):
    if not await guard_sub(callback): return
    uid         = str(callback.from_user.id)
    email_index = int(callback.data[6:])
    if email_index >= len(user_accounts.get(uid, [])):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return
    deleted = user_accounts[uid].pop(email_index)
    save_all()
    if uid in user_tokens and user_tokens[uid].get('index') == email_index:
        del user_tokens[uid]
    await safe_edit(callback.message,
        f"🗑 <b>Почта удалена!</b>\n\n📧 <code>{deleted['email']}</code>\n\n"
        f"Осталось: {len(user_accounts.get(uid, []))}/{limit_str(uid)}",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📧 Мои почты",    callback_data="my_emails")],
            [InlineKeyboardButton(text="➕ Создать новую", callback_data="create_email")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
        ])
    )
    await callback.answer()


# ── Поддержка / О боте ────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data == "support")
async def cb_support(callback: types.CallbackQuery):
    if not await guard_sub(callback): return
    await safe_edit(callback.message,
        "🆘 <b>Поддержка TrueMail</b>\n\n"
        "Вопросы, баги, предложения → @internetcomunity",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📩 Написать разработчику", url="https://t.me/internetcomunity")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
        ])
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "about")
async def cb_about(callback: types.CallbackQuery):
    if not await guard_sub(callback): return
    await safe_edit(callback.message,
        "ℹ️ <b>О TrueMail</b>\n\n"
        "🤖 <b>Версия:</b> 4.1\n"
        "📧 <b>Сервис:</b> mail.tm\n"
        "👨‍💻 <b>Разработчик:</b> @internetcomunity\n\n"
        "✨ <b>Особенности:</b>\n"
        "• До 5 почт на аккаунт\n"
        "• Постоянное хранение\n"
        "• Письма прямо в боте\n"
        "• Безопасность и анонимность",
        parse_mode='HTML', reply_markup=back_kb()
    )
    await callback.answer()


# ══════════════════════════════════════════════════════════
#  👑  АДМИН-ПАНЕЛЬ
# ══════════════════════════════════════════════════════════

def adm_only(uid: str) -> bool:
    return int(uid) == ADMIN_ID


@dp.message(Command('admin'))
async def cmd_admin(message: types.Message):
    if not adm_only(str(message.from_user.id)):
        await message.answer("❌ Нет доступа.")
        return
    await message.answer(
        _admin_panel_text(),
        parse_mode='HTML', reply_markup=_admin_panel_kb()
    )


def _admin_panel_text() -> str:
    total_users  = len(user_accounts)
    total_emails = sum(len(v) for v in user_accounts.values())
    return (
        "👑 <b>Админ-панель TrueMail</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Пользователей:</b> {total_users}\n"
        f"📧 <b>Всего почт:</b> {total_emails}"
    )

def _admin_panel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="adm_users_p0")],
        [InlineKeyboardButton(text="📊 Статистика",           callback_data="adm_stats")],
        [InlineKeyboardButton(text="🔙 Главное меню",         callback_data="back_to_menu")]
    ])


@dp.callback_query(lambda c: c.data == "admin_panel")
async def cb_admin_panel(callback: types.CallbackQuery):
    if not adm_only(str(callback.from_user.id)):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    await safe_edit(callback.message, _admin_panel_text(),
                    parse_mode='HTML', reply_markup=_admin_panel_kb())
    await callback.answer()


# ── Статистика ────────────────────────────────────────────────────────────────

@dp.callback_query(lambda c: c.data == "adm_stats")
async def cb_adm_stats(callback: types.CallbackQuery):
    if not adm_only(str(callback.from_user.id)):
        await callback.answer("❌", show_alert=True)
        return

    total_u = len(user_accounts)
    total_e = sum(len(v) for v in user_accounts.values())
    top     = sorted(user_accounts.items(), key=lambda x: len(x[1]), reverse=True)[:5]

    text = (
        "📊 <b>Статистика</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Пользователей: <b>{total_u}</b>\n"
        f"📧 Всего почт: <b>{total_e}</b>\n\n"
    )
    if top:
        text += "🏆 <b>Топ-5:</b>\n"
        for uid, accs in top:
            info  = user_info.get(uid, {})
            uname = info.get('username', '')
            fname = info.get('first_name', '')
            name  = f"@{uname}" if uname else (fname or f"ID:{uid}")
            text += f"  • {name} — {len(accs)} почт\n"

    await safe_edit(callback.message, text, parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
                    ]))
    await callback.answer()


# ── Список пользователей (постранично) ────────────────────────────────────────
# Callback: adm_users_p{page}

@dp.callback_query(lambda c: c.data.startswith("adm_users_p"))
async def cb_adm_users(callback: types.CallbackQuery):
    if not adm_only(str(callback.from_user.id)):
        await callback.answer("❌", show_alert=True)
        return

    PAGE      = 8
    page      = int(callback.data[len("adm_users_p"):])
    all_uids  = list(user_accounts.keys())
    total     = len(all_uids)

    if not all_uids:
        await callback.answer("Пользователей нет", show_alert=True)
        return

    start     = page * PAGE
    end       = min(start + PAGE, total)
    page_uids = all_uids[start:end]
    pages     = (total - 1) // PAGE + 1

    text    = f"👥 <b>Пользователи</b> (стр. {page+1}/{pages})\n━━━━━━━━━━━━━━━━━━\n\n"
    buttons = []

    for uid in page_uids:
        info  = user_info.get(uid, {})
        uname = info.get('username', '')
        fname = info.get('first_name', '')
        name  = f"@{uname}" if uname else (fname or f"ID:{uid}")
        cnt   = len(user_accounts.get(uid, []))
        text += f"👤 {name} — <b>{cnt}</b> почт(ы) | <code>{uid}</code>\n"
        # Используем короткий ключ: adm_u_{uid}_p0
        buttons.append([InlineKeyboardButton(
            text=f"👤 {name[:22]} [{cnt} почт]",
            callback_data=f"adm_u_{uid}_p0"
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Пред.", callback_data=f"adm_users_p{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="След. ▶️", callback_data=f"adm_users_p{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")])

    await safe_edit(callback.message, text, parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


# ── Профиль пользователя ─────────────────────────────────────────────────────
# Callback: adm_u_{uid}_p{page}
# UID — числовой, page — числовой, разделяем по "_p" в конце

def _parse_adm_u(data: str):
    """adm_u_{uid}_p{page} → (uid_str, page_int)"""
    body = data[len("adm_u_"):]          # "8643353267_p0"
    idx  = body.rfind("_p")
    uid  = body[:idx]
    page = int(body[idx+2:])
    return uid, page


@dp.callback_query(lambda c: c.data.startswith("adm_u_") and "_p" in c.data)
async def cb_adm_view_user(callback: types.CallbackQuery):
    if not adm_only(str(callback.from_user.id)):
        await callback.answer("❌", show_alert=True)
        return

    target_uid, page = _parse_adm_u(callback.data)
    accounts         = user_accounts.get(target_uid, [])
    udata            = await get_user_display(target_uid)
    last_seen        = user_info.get(target_uid, {}).get('last_seen', '—')

    PAGE  = 5
    start = page * PAGE
    end   = min(start + PAGE, len(accounts))
    pages = max(1, (len(accounts) - 1) // PAGE + 1)

    text = (
        f"👤 <b>{udata['name']}</b>\n"
        f"🆔 <code>{target_uid}</code>\n"
        f"🕐 Последний визит: {last_seen}\n"
        f"📧 Почт: <b>{len(accounts)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
    )
    buttons = []

    if not accounts:
        text += "📭 Почт нет."
    else:
        text += f"<i>Страница {page+1}/{pages}</i>\n\n"
        for idx in range(start, end):
            acc     = accounts[idx]
            email   = acc['email']
            created = acc.get('created_at', '—')
            text   += f"<b>{idx+1}.</b> <code>{email}</code>\n   🕐 {created}\n\n"
            label   = email[:28] + "…" if len(email) > 28 else email
            # adm_mail_{uid}_e{email_index}
            buttons.append([InlineKeyboardButton(
                text=f"📬 {label}",
                callback_data=f"adm_mail_{target_uid}_e{idx}"
            )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm_u_{target_uid}_p{page-1}"))
    if end < len(accounts):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm_u_{target_uid}_p{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Пользователи", callback_data="adm_users_p0")])

    await safe_edit(callback.message, text, parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


# ── Входящие конкретной почты (admin) ─────────────────────────────────────────
# Callback: adm_mail_{uid}_e{email_index}

def _parse_adm_mail(data: str):
    """adm_mail_{uid}_e{email_index} → (uid, email_index)"""
    body  = data[len("adm_mail_"):]       # "8643353267_e0"
    idx   = body.rfind("_e")
    uid   = body[:idx]
    eidx  = int(body[idx+2:])
    return uid, eidx


@dp.callback_query(lambda c: c.data.startswith("adm_mail_") and "_e" in c.data)
async def cb_adm_inbox(callback: types.CallbackQuery):
    if not adm_only(str(callback.from_user.id)):
        await callback.answer("❌", show_alert=True)
        return

    target_uid, email_index = _parse_adm_mail(callback.data)
    accounts = user_accounts.get(target_uid, [])

    if email_index >= len(accounts):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return

    acc      = accounts[email_index]
    email    = acc['email']
    token    = acc['token']
    messages = list_messages_api(token)
    udata    = await get_user_display(target_uid)

    text    = (
        f"📬 <b>Почта:</b> <code>{email}</code>\n"
        f"👤 <b>Владелец:</b> {udata['name']} (<code>{target_uid}</code>)\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
    )
    buttons = []

    if not messages:
        text += "📭 Писем нет."
    else:
        text += f"📨 <b>Писем: {len(messages)}</b>\n━━━━━━━━━━━━━━━━━━\n\n"
        for idx, msg in enumerate(messages[:10], 1):
            subject   = (msg.get('subject') or '(без темы)')[:38]
            from_addr = (msg.get('from') or {}).get('address', '?')[:32]
            # Показываем домен отправителя — это и есть "сервис"
            service = from_addr.split('@')[-1] if '@' in from_addr else from_addr
            text   += f"<b>{idx}.</b> 🌐 <code>{service}</code>\n   📌 {subject}\n   📨 {from_addr}\n\n"
            safe_id  = msg['id'].replace('_', '-')
            # adm_rmsg_{uid}_e{email_index}_m{safe_id}
            buttons.append([InlineKeyboardButton(
                text=f"📖 Письмо {idx}: {subject[:20]}",
                callback_data=f"adm_rmsg_{target_uid}_e{email_index}_m{safe_id}"
            )])

    buttons.append([InlineKeyboardButton(
        text="🔙 К пользователю",
        callback_data=f"adm_u_{target_uid}_p0"
    )])
    await safe_edit(callback.message, text, parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


# ── Чтение письма (admin) ─────────────────────────────────────────────────────
# Callback: adm_rmsg_{uid}_e{email_index}_m{safe_msg_id}

def _parse_adm_rmsg(data: str):
    """adm_rmsg_{uid}_e{ei}_m{safe_id} → (uid, email_index, message_id)"""
    body     = data[len("adm_rmsg_"):]       # "8643353267_e0_mABCDEF"
    m_idx    = body.rfind("_m")
    safe_id  = body[m_idx+2:]
    rest     = body[:m_idx]                  # "8643353267_e0"
    e_idx    = rest.rfind("_e")
    uid      = rest[:e_idx]
    eidx     = int(rest[e_idx+2:])
    return uid, eidx, safe_id.replace('-', '_')


@dp.callback_query(lambda c: c.data.startswith("adm_rmsg_"))
async def cb_adm_read_msg(callback: types.CallbackQuery):
    if not adm_only(str(callback.from_user.id)):
        await callback.answer("❌", show_alert=True)
        return

    target_uid, email_index, message_id = _parse_adm_rmsg(callback.data)
    accounts = user_accounts.get(target_uid, [])
    if email_index >= len(accounts):
        await callback.answer("❌ Почта не найдена", show_alert=True)
        return

    token   = accounts[email_index]['token']
    details = get_message_api(message_id, token)
    if not details:
        await callback.answer("❌ Не удалось загрузить", show_alert=True)
        return

    body = ""
    if details.get('html'):
        body = html_to_text(details['html'])
    elif details.get('text'):
        body = details['text']
    if not body.strip():
        body = "Пусто."
    if len(body) > MAX_MESSAGE_LENGTH:
        body = body[:MAX_MESSAGE_LENGTH] + "\n… [обрезано]"

    body      = body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    from_addr = (details.get('from') or {}).get('address', '?')
    subject   = details.get('subject', '(без темы)')
    service   = from_addr.split('@')[-1] if '@' in from_addr else from_addr
    udata     = await get_user_display(target_uid)

    output = (
        f"👑 <b>[ADMIN] Письмо пользователя {udata['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Сервис:</b> <code>{service}</code>\n"
        f"📨 <b>От:</b> <code>{from_addr}</code>\n"
        f"📌 <b>Тема:</b> {subject}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{body}"
    )

    safe_id  = message_id.replace('_', '-')
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔙 Назад",
            callback_data=f"adm_mail_{target_uid}_e{email_index}"
        )]
    ])

    try:
        await callback.message.edit_text(output, parse_mode='HTML', reply_markup=keyboard)
    except TelegramBadRequest:
        await callback.message.edit_text(
            f"⚠️ Не удалось отобразить.\n<b>От:</b> {from_addr}\n<b>Тема:</b> {subject}",
            parse_mode='HTML', reply_markup=keyboard
        )
    await callback.answer()


# ══════════════════════════════════════════════════════════
#  🚀  ЗАПУСК
# ══════════════════════════════════════════════════════════

async def main():
    me           = await bot.get_me()
    total_users  = len(user_accounts)
    total_emails = sum(len(v) for v in user_accounts.values())

    print("=" * 50)
    print("🌟  TrueMail Bot v4.1")
    print("=" * 50)
    print(f"✅  Бот:            @{me.username}")
    print(f"✅  Пользователей:  {total_users}")
    print(f"✅  Всего почт:     {total_emails}")
    print(f"✅  Лимит/юзер:    {MAX_ACCOUNTS_PER_USER}")
    print(f"✅  ADMIN ID:       {ADMIN_ID}")
    print("🚀  Polling запущен…")
    print("=" * 50)

    await bot.set_my_commands([
        types.BotCommand(command="start", description="🏠 Главное меню"),
        types.BotCommand(command="admin", description="👑 Админ-панель")
    ])
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
