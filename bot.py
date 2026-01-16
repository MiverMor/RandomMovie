import telebot
from telebot import types
import random
import json
import os


TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "movies.json"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
bot.remove_webhook()

# ------------------ Загрузка ------------------

def load_movies():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_movies():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)

movies = load_movies()

add_mode = set()
wait_delete_id = set()

# ------------------ UI ------------------

def show_screen(call, text, keyboard):
    bot.edit_message_text(
        text=text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard
    )

def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Добавить", callback_data="add"),
        types.InlineKeyboardButton("🎲 Выбрать", callback_data="random"),
        types.InlineKeyboardButton("📋 Список", callback_data="list"),
        types.InlineKeyboardButton("🧹 Очистка", callback_data="clear")
    )
    return kb

# ------------------ Start ------------------

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🎬 <b>Бот для выбора фильмов</b>\n\nВыбери действие:",
        reply_markup=main_menu()
    )

# ------------------ Навигация ------------------

@bot.callback_query_handler(func=lambda c: c.data == "menu")
def back(call):
    show_screen(call, "🎬 Главное меню:", main_menu())

# ------------------ Добавление ------------------

@bot.callback_query_handler(func=lambda c: c.data == "add")
def add_button(call):
    add_mode.add(call.message.chat.id)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("↩️ Назад", callback_data="menu"))

    show_screen(call, "➕ Отправь ссылку на фильм:", kb)

@bot.message_handler(func=lambda m: m.chat.id in add_mode)
def add_movie(message):
    chat_id = str(message.chat.id)
    add_mode.discard(message.chat.id)

    text = message.text.strip()

    if not text.startswith("http"):
        bot.send_message(chat_id, "❌ Это не ссылка", reply_markup=main_menu())
        return

    movies.setdefault(chat_id, [])

    if any(f["url"] == text for f in movies[chat_id]):
        bot.send_message(chat_id, "⚠️ Такой фильм уже есть", reply_markup=main_menu())
        return

    new_id = max([f["id"] for f in movies[chat_id]], default=0) + 1

    movies[chat_id].append({
        "id": new_id,
        "url": text,
        "watched": False
    })

    save_movies()

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Добавить ещё", callback_data="add"),
        types.InlineKeyboardButton("🏠 В меню", callback_data="menu")
    )

    bot.send_message(chat_id, "✅ Фильм добавлен!", reply_markup=kb)

# ------------------ Список ------------------

@bot.callback_query_handler(func=lambda c: c.data == "list")
@bot.callback_query_handler(func=lambda c: c.data == "list")
def list_button(call):
    chat_id = str(call.message.chat.id)

    # Удаляем предыдущее сообщение с кнопками
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

    films = movies.get(chat_id, [])

    if not films:
        bot.send_message(chat_id, "📭 Список пуст", reply_markup=main_menu())
        return

    text = "📋 Список фильмов:\n\n"

    for f in films:
        status = "Просмотрен" if f["watched"] else "Не просмотрен"
        icon = "✅" if f["watched"] else "🎬"
        text += f"{icon} {f['id']} | {status}\n{f['url']}\n\n"

    bot.send_message(chat_id, text, reply_markup=main_menu())

# ------------------ Карточка фильма ------------------

@bot.callback_query_handler(func=lambda c: c.data.startswith("show:"))
def show_movie(call):
    chat_id = str(call.message.chat.id)
    fid = int(call.data.split(":")[1])

    film = next((f for f in movies.get(chat_id, []) if f["id"] == fid), None)

    if not film:
        show_screen(call, "❌ Фильм не найден", main_menu())
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Просмотрено", callback_data=f"watched:{fid}"),
        types.InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{fid}")
    )
    kb.add(types.InlineKeyboardButton("↩️ Назад", callback_data="list"))

    show_screen(call, f"🎥 <b>Фильм {fid}</b>\n{film['url']}", kb)

# ------------------ Random ------------------

@bot.callback_query_handler(func=lambda c: c.data == "random")
def random_screen(call):
    chat_id = str(call.message.chat.id)
    films = [f for f in movies.get(chat_id, []) if not f["watched"]]

    if not films:
        show_screen(call, "❌ Нет доступных фильмов", main_menu())
        return

    film = random.choice(films)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔄 Выбрать заново", callback_data="random"))
    kb.add(
        types.InlineKeyboardButton("✅ Просмотрено", callback_data=f"watched:{film['id']}"),
        types.InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{film['id']}")
    )
    kb.add(types.InlineKeyboardButton("↩️ В меню", callback_data="menu"))

    show_screen(call, f"🎲 <b>Случайный фильм:</b>\n{film['url']}", kb)

# ------------------ Просмотрено / Удаление ------------------

@bot.callback_query_handler(func=lambda c: c.data.startswith("watched:"))
def watched(call):
    chat_id = str(call.message.chat.id)
    fid = int(call.data.split(":")[1])

    for f in movies.get(chat_id, []):
        if f["id"] == fid:
            f["watched"] = True

    save_movies()
    show_screen(call, "✅ Отмечено как просмотренное", main_menu())

@bot.callback_query_handler(func=lambda c: c.data.startswith("delete:"))
def delete(call):
    chat_id = str(call.message.chat.id)
    fid = int(call.data.split(":")[1])

    movies[chat_id] = [f for f in movies.get(chat_id, []) if f["id"] != fid]
    save_movies()

    show_screen(call, "🗑 Фильм удалён", main_menu())

# ------------------ Очистка ------------------

@bot.callback_query_handler(func=lambda c: c.data == "clear")
def clear_menu(call):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🗑 Удалить по ID", callback_data="clear_one"),
        types.InlineKeyboardButton("✅ Удалить просмотренные", callback_data="clear_watched")
    )
    kb.add(
        types.InlineKeyboardButton("💥 Очистить всё", callback_data="clear_all"),
        types.InlineKeyboardButton("↩️ Назад", callback_data="menu")
    )
    show_screen(call, "Что удалить?", kb)

@bot.callback_query_handler(func=lambda c: c.data == "clear_one")
def clear_one(call):
    wait_delete_id.add(call.message.chat.id)

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("↩️ Отмена", callback_data="menu"))

    show_screen(call, "🗑 Введи ID фильма для удаления:", kb)
@bot.message_handler(func=lambda m: m.chat.id in wait_delete_id)
def delete_by_id(message):
    chat_id = str(message.chat.id)
    wait_delete_id.discard(message.chat.id)

    try:
        fid = int(message.text.strip())
    except:
        bot.send_message(chat_id, "❌ Нужно ввести число", reply_markup=main_menu())
        return

    films = movies.get(chat_id, [])
    before = len(films)

    movies[chat_id] = [f for f in films if f["id"] != fid]

    if len(movies[chat_id]) == before:
        bot.send_message(chat_id, "❌ Фильм с таким ID не найден", reply_markup=main_menu())
    else:
        save_movies()
        bot.send_message(chat_id, f"🗑 Фильм с ID {fid} удалён", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "clear_watched")
def clear_watched(call):
    chat_id = str(call.message.chat.id)

    before = len(movies.get(chat_id, []))
    movies[chat_id] = [f for f in movies.get(chat_id, []) if not f["watched"]]

    deleted = before - len(movies[chat_id])
    save_movies()

    show_screen(call, f"✅ Удалено просмотренных: {deleted}", main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "clear_all")
def clear_all_confirm(call):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("💥 Да, удалить всё", callback_data="clear_all_yes"),
        types.InlineKeyboardButton("↩️ Отмена", callback_data="menu")
    )
    show_screen(call, "⚠️ Точно удалить ВСЕ фильмы?", kb)

@bot.callback_query_handler(func=lambda c: c.data == "clear_all_yes")
def clear_all_yes(call):
    chat_id = str(call.message.chat.id)
    movies[chat_id] = []
    save_movies()

    show_screen(call, "💥 Всё очищено", main_menu())

# ------------------

print("🤖 Бот запущен")
bot.infinity_polling()
