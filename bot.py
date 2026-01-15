import telebot
from telebot import types
import random
import json
import os

TOKEN = "8514427167:AAGHlZLD06Wey6AlDt4RCjuxHDx7wj_GAp8"
DATA_FILE = "movies.json"

bot = telebot.TeleBot(TOKEN)
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

# кто сейчас в режиме добавления
add_mode = set()  # chat_id


# ------------------ Меню ------------------

def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Добавить фильм", callback_data="add"),
        types.InlineKeyboardButton("🎲 Выбрать", callback_data="random"),
        types.InlineKeyboardButton("📋 Список", callback_data="list"),
        types.InlineKeyboardButton("🧹 Очистить", callback_data="clear")
    )
    return kb


# ------------------ /start ------------------

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🎬 Бот для выбора фильма\n\nВыбирай действие:",
        reply_markup=main_menu()
    )


# ------------------ Кнопки меню ------------------

@bot.callback_query_handler(func=lambda c: c.data == "add")
def add_button(call):
    add_mode.add(call.message.chat.id)
    bot.send_message(call.message.chat.id, "🎬 Отправь ссылку на фильм")


@bot.callback_query_handler(func=lambda c: c.data == "list")
def list_button(call):
    chat_id = str(call.message.chat.id)
    films = movies.get(chat_id, [])

    if not films:
        bot.send_message(chat_id, "📭 Список пуст")
        return

    text = "📋 Фильмы:\n\n"
    for f in films:
        status = "✅ Просмотрен" if f["watched"] else "🎬 Участвует в рандоме"
        text += f"{f['id']}. {f['url']} {status}\n"

    bot.send_message(chat_id, text)


#-----------очистка------
@bot.callback_query_handler(func=lambda c: c.data == "clear")
def clear_menu(call):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🗑 Удалить по ID", callback_data="clear_one"),
        types.InlineKeyboardButton("✅ Удалить просмотренные", callback_data="clear_watched")
    )
    kb.add(
        types.InlineKeyboardButton("💥 Очистить всё", callback_data="clear_all"),
        types.InlineKeyboardButton("↩️ Отмена", callback_data="menu")
    )

    bot.send_message(call.message.chat.id, "Что именно очистить?", reply_markup=kb)

#--------удаление по id ---------------
wait_delete_id = set()

@bot.callback_query_handler(func=lambda c: c.data == "clear_one")
def ask_id(call):
    wait_delete_id.add(call.message.chat.id)
    bot.send_message(call.message.chat.id, "Введи ID фильма для удаления:")

@bot.message_handler(func=lambda m: m.chat.id in wait_delete_id)
def delete_by_id(message):
    chat_id = str(message.chat.id)
    wait_delete_id.discard(message.chat.id)

    try:
        fid = int(message.text.strip())
    except:
        bot.send_message(chat_id, "❌ Нужно ввести число", reply_markup=main_menu())
        return

    before = len(movies.get(chat_id, []))
    movies[chat_id] = [f for f in movies.get(chat_id, []) if f["id"] != fid]

    if len(movies[chat_id]) == before:
        bot.send_message(chat_id, "❌ Фильм с таким ID не найден", reply_markup=main_menu())
    else:
        save_movies()
        bot.send_message(chat_id, f"🗑 Фильм {fid} удалён", reply_markup=main_menu())


#----------удаление всех просмотренных--------------
@bot.callback_query_handler(func=lambda c: c.data == "clear_watched")
def clear_watched(call):
    chat_id = str(call.message.chat.id)

    before = len(movies.get(chat_id, []))
    movies[chat_id] = [f for f in movies.get(chat_id, []) if not f["watched"]]

    deleted = before - len(movies[chat_id])
    save_movies()

    bot.send_message(chat_id, f"✅ Удалено просмотренных: {deleted}", reply_markup=main_menu())

#----------полная очистка-----------
@bot.callback_query_handler(func=lambda c: c.data == "clear_all")
def clear_all_confirm(call):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("💥 Да, удалить всё", callback_data="clear_all_yes"),
        types.InlineKeyboardButton("↩️ Отмена", callback_data="menu")
    )
    bot.send_message(call.message.chat.id, "⚠️ Точно удалить ВСЕ фильмы?", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "clear_all_yes")
def clear_all_yes(call):
    chat_id = str(call.message.chat.id)
    movies[chat_id] = []
    save_movies()
    bot.send_message(chat_id, "💥 Всё удалено", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "clear_yes")
def clear_yes(call):
    chat_id = str(call.message.chat.id)
    movies[chat_id] = []
    save_movies()
    bot.send_message(chat_id, "🧹 Список очищен", reply_markup=main_menu())


@bot.callback_query_handler(func=lambda c: c.data == "clear_no")
def clear_no(call):
    bot.send_message(call.message.chat.id, "❎ Очистка отменена", reply_markup=main_menu())

#----------кнопка рандома----------
@bot.callback_query_handler(func=lambda c: c.data == "random")
def random_button(call):
    chat_id = str(call.message.chat.id)
    films = [f for f in movies.get(chat_id, []) if not f["watched"]]

    if not films:
        bot.send_message(chat_id, "❌ Нет доступных фильмов")
        return

    film = random.choice(films)

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🔄 Выбрать заново", callback_data="random")
    )
    kb.add(
        types.InlineKeyboardButton("✅ Просмотрено", callback_data=f"watched:{film['id']}"),
        types.InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{film['id']}")
    )

    bot.send_message(chat_id, f"🎥 Выбран фильм:\n{film['url']}", reply_markup=kb)


# ------------------ Добавление фильма ------------------

@bot.message_handler(func=lambda m: m.chat.id in add_mode)
def add_movie(message):
    chat_id = str(message.chat.id)
    text = message.text.strip()

    # Режим добавления выключаем в любом случае
    add_mode.discard(message.chat.id)

    # Проверка на ссылку
    if not text.startswith("http"):
        bot.send_message(
            chat_id,
            "❌ Это не ссылка. Попробуй ещё раз через меню.",
            reply_markup=main_menu()
        )
        return

    movies.setdefault(chat_id, [])

    # Проверка на дубликат
    if any(f["url"] == text for f in movies[chat_id]):
        bot.send_message(
            chat_id,
            "⚠️ Такой фильм уже есть в списке.",
            reply_markup=main_menu()
        )
        return

    # Добавление нового фильма
    new_id = max([f["id"] for f in movies[chat_id]], default=0) + 1

    movies[chat_id].append({
        "id": new_id,
        "url": text,
        "watched": False
    })

    save_movies()

    kb = types.InlineKeyboardMarkup()
    kb.add(
    types.InlineKeyboardButton("➕ Добавить ещё один", callback_data="add"),
    types.InlineKeyboardButton("🏠 В меню", callback_data="menu")
    )

    bot.send_message(
        chat_id,
        "✅ Фильм добавлен!",
        reply_markup=kb
    )


# ------------------ Кнопки под фильмом ------------------

@bot.callback_query_handler(func=lambda c: c.data.startswith("watched:"))
def watched(call):
    chat_id = str(call.message.chat.id)
    fid = int(call.data.split(":")[1])

    for f in movies.get(chat_id, []):
        if f["id"] == fid:
            f["watched"] = True

    save_movies()
    bot.edit_message_reply_markup(chat_id, call.message.message_id, None)
    bot.send_message(chat_id, "✅ Отмечено как просмотренное")


@bot.callback_query_handler(func=lambda c: c.data.startswith("delete:"))
def delete(call):
    chat_id = str(call.message.chat.id)
    fid = int(call.data.split(":")[1])

    movies[chat_id] = [f for f in movies.get(chat_id, []) if f["id"] != fid]
    save_movies()

    bot.edit_message_reply_markup(chat_id, call.message.message_id, None)
    bot.send_message(chat_id, "🗑 Фильм удалён")

@bot.callback_query_handler(func=lambda c: c.data == "menu")
def back_to_menu(call):
    bot.send_message(call.message.chat.id, "Выбери действие:", reply_markup=main_menu())
# ------------------

print("🤖 Бот запущен")
bot.infinity_polling()
