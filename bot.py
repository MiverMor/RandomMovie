import os
import telebot
from telebot import types
import random
import psycopg2
from urllib.parse import urlparse
from flask import Flask, request
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")  # Будет из Render
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ------------------ База данных ------------------
def get_connection():
    """Создание подключения к PostgreSQL"""
    try:
        # Парсинг URL базы данных Render
        result = urlparse(DATABASE_URL)
        conn = psycopg2.connect(
            database=result.path[1:],      # Имя БД (без /)
            user=result.username,          # Пользователь
            password=result.password,      # Пароль
            host=result.hostname,         # Хост
            port=result.port              # Порт
        )
        return conn
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return None

def init_db():
    """Инициализация таблицы при первом запуске"""
    conn = get_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                # Создаем таблицу если ее нет
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS movies (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT NOT NULL,
                        url TEXT NOT NULL,
                        watched BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(chat_id, url)
                    )
                """)
                # Создаем индекс для быстрого поиска
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_movies_chat_id 
                    ON movies(chat_id)
                """)
                conn.commit()
                print("✅ База данных инициализирована")
        except Exception as e:
            print(f"❌ Ошибка при инициализации БД: {e}")
            conn.rollback()
        finally:
            conn.close()
    else:
        print("⚠️ Не удалось подключиться к БД")

def load_movies(chat_id):
    """Загрузка фильмов для конкретного чата"""
    conn = get_connection()
    if not conn:
        return []
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, url, watched FROM movies WHERE chat_id = %s ORDER BY id",
                (chat_id,)
            )
            rows = cur.fetchall()
            return [
                {"id": row[0], "url": row[1], "watched": row[2]}
                for row in rows
            ]
    except Exception as e:
        print(f"❌ Ошибка при загрузке фильмов: {e}")
        return []
    finally:
        if conn:
            conn.close()

def save_movie(chat_id, url):
    """Сохранение нового фильма"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cur:
            # Проверяем, существует ли уже такой фильм
            cur.execute(
                "SELECT id FROM movies WHERE chat_id = %s AND url = %s",
                (chat_id, url)
            )
            if cur.fetchone():
                return None  # Фильм уже существует
            
            # Добавляем новый фильм
            cur.execute(
                """INSERT INTO movies (chat_id, url, watched) 
                   VALUES (%s, %s, FALSE) 
                   RETURNING id""",
                (chat_id, url)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    except Exception as e:
        print(f"❌ Ошибка при сохранении фильма: {e}")
        conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def update_watched(movie_id, chat_id):
    """Отметить фильм как просмотренный"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE movies SET watched = TRUE WHERE id = %s AND chat_id = %s",
                (movie_id, chat_id)
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        print(f"❌ Ошибка при обновлении фильма: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def delete_movie(movie_id, chat_id):
    """Удалить фильм"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM movies WHERE id = %s AND chat_id = %s",
                (movie_id, chat_id)
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        print(f"❌ Ошибка при удалении фильма: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def delete_watched(chat_id):
    """Удалить все просмотренные фильмы"""
    conn = get_connection()
    if not conn:
        return 0
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM movies WHERE chat_id = %s AND watched = TRUE",
                (chat_id,)
            )
            deleted = cur.rowcount
            conn.commit()
            return deleted
    except Exception as e:
        print(f"❌ Ошибка при удалении просмотренных: {e}")
        conn.rollback()
        return 0
    finally:
        if conn:
            conn.close()

def delete_all(chat_id):
    """Удалить все фильмы чата"""
    conn = get_connection()
    if not conn:
        return False
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM movies WHERE chat_id = %s",
                (chat_id,)
            )
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Ошибка при полной очистке: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_random_unwatched(chat_id):
    """Получить случайный непросмотренный фильм"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, url FROM movies 
                   WHERE chat_id = %s AND watched = FALSE 
                   ORDER BY RANDOM() LIMIT 1""",
                (chat_id,)
            )
            row = cur.fetchone()
            if row:
                return {"id": row[0], "url": row[1]}
            return None
    except Exception as e:
        print(f"❌ Ошибка при выборе случайного фильма: {e}")
        return None
    finally:
        if conn:
            conn.close()

# ------------------ Переменные состояния ------------------
add_mode = set()
wait_delete_id = set()

# ------------------ UI функции ------------------
def show_screen(call, text, keyboard):
    """Обновление сообщения с клавиатурой"""
    try:
        bot.edit_message_text(
            text=text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Ошибка при обновлении сообщения: {e}")

def main_menu():
    """Главное меню"""
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ Добавить", callback_data="add"),
        types.InlineKeyboardButton("🎲 Выбрать", callback_data="random"),
        types.InlineKeyboardButton("📋 Список", callback_data="list"),
        types.InlineKeyboardButton("🧹 Очистка", callback_data="clear")
    )
    return kb

# ------------------ Команды бота ------------------
@bot.message_handler(commands=["start", "help"])
def start(message):
    """Обработчик команды /start"""
    init_db()  # Инициализируем БД при первом запуске
    bot.send_message(
        message.chat.id,
        "🎬 <b>Бот для выбора фильмов с сохранением в БД</b>\n\n"
        "Фильмы теперь сохраняются в базе данных и не пропадут при перезапуске!\n\n"
        "Выбери действие:",
        reply_markup=main_menu()
    )

@bot.callback_query_handler(func=lambda c: c.data == "menu")
def back(call):
    """Возврат в главное меню"""
    show_screen(call, "🎬 Главное меню:", main_menu())

# ------------------ Добавление фильма ------------------
@bot.callback_query_handler(func=lambda c: c.data == "add")
def add_button(call):
    """Кнопка добавления фильма"""
    add_mode.add(call.message.chat.id)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("↩️ Назад", callback_data="menu"))
    show_screen(call, "➕ Отправь ссылку на фильм (YouTube, Kinopoisk и т.д.):", kb)

@bot.message_handler(func=lambda m: m.chat.id in add_mode)
def add_movie(message):
    """Добавление фильма по ссылке"""
    chat_id = message.chat.id
    add_mode.discard(chat_id)
    
    text = message.text.strip()
    
    if not text.startswith("http"):
        bot.send_message(chat_id, "❌ Это не ссылка. Отправьте корректную ссылку.", reply_markup=main_menu())
        return
    
    # Сохраняем в БД
    new_id = save_movie(chat_id, text)
    
    if new_id is None:
        bot.send_message(chat_id, "⚠️ Этот фильм уже есть в вашем списке!", reply_markup=main_menu())
        return
    
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Добавить ещё", callback_data="add"),
        types.InlineKeyboardButton("🏠 В меню", callback_data="menu")
    )
    
    bot.send_message(chat_id, f"✅ Фильм добавлен под ID {new_id}!", reply_markup=kb)

# ------------------ Список фильмов ------------------
@bot.callback_query_handler(func=lambda c: c.data == "list")
def list_button(call):
    """Показать список фильмов"""
    chat_id = call.message.chat.id
    
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
    films = load_movies(chat_id)
    
    if not films:
        bot.send_message(chat_id, "📭 Список фильмов пуст", reply_markup=main_menu())
        return
    
    # Группируем по просмотренным/непросмотренным
    watched = [f for f in films if f["watched"]]
    unwatched = [f for f in films if not f["watched"]]
    
    text = "📋 <b>Ваш список фильмов</b>\n\n"
    
    if unwatched:
        text += "🎬 <b>Непросмотренные:</b>\n"
        for f in unwatched:
            text += f"{f['id']}. {f['url']}\n"
        text += "\n"
    
    if watched:
        text += "✅ <b>Просмотренные:</b>\n"
        for f in watched:
            text += f"{f['id']}. {f['url']}\n"
    
    text += f"\nВсего: {len(films)} | ✅ {len(watched)} | 🎬 {len(unwatched)}"
    
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🔄 Обновить", callback_data="list"),
        types.InlineKeyboardButton("🏠 В меню", callback_data="menu")
    )
    
    bot.send_message(chat_id, text, reply_markup=kb)

# ------------------ Случайный выбор ------------------
@bot.callback_query_handler(func=lambda c: c.data == "random")
def random_screen(call):
    """Выбор случайного непросмотренного фильма"""
    chat_id = call.message.chat.id
    film = get_random_unwatched(chat_id)
    
    if not film:
        show_screen(call, "❌ Нет доступных непросмотренных фильмов", main_menu())
        return
    
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
    """Отметить фильм как просмотренный"""
    chat_id = call.message.chat.id
    fid = int(call.data.split(":")[1])
    
    if update_watched(fid, chat_id):
        show_screen(call, "✅ Фильм отмечен как просмотренный", main_menu())
    else:
        show_screen(call, "❌ Ошибка при обновлении", main_menu())

@bot.callback_query_handler(func=lambda c: c.data.startswith("delete:"))
def delete(call):
    """Удалить фильм"""
    chat_id = call.message.chat.id
    fid = int(call.data.split(":")[1])
    
    if delete_movie(fid, chat_id):
        show_screen(call, "🗑 Фильм удалён", main_menu())
    else:
        show_screen(call, "❌ Ошибка при удалении", main_menu())

# ------------------ Очистка ------------------
@bot.callback_query_handler(func=lambda c: c.data == "clear")
def clear_menu(call):
    """Меню очистки"""
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🗑 Удалить по ID", callback_data="clear_one"),
        types.InlineKeyboardButton("✅ Удалить просмотренные", callback_data="clear_watched")
    )
    kb.add(
        types.InlineKeyboardButton("💥 Очистить всё", callback_data="clear_all"),
        types.InlineKeyboardButton("↩️ Назад", callback_data="menu")
    )
    show_screen(call, "🧹 <b>Что удалить?</b>", kb)

@bot.callback_query_handler(func=lambda c: c.data == "clear_one")
def clear_one(call):
    """Запрос ID для удаления"""
    wait_delete_id.add(call.message.chat.id)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("↩️ Отмена", callback_data="menu"))
    show_screen(call, "🗑 Введи ID фильма для удаления:", kb)

@bot.message_handler(func=lambda m: m.chat.id in wait_delete_id)
def delete_by_id(message):
    """Удаление по ID"""
    chat_id = message.chat.id
    wait_delete_id.discard(chat_id)
    
    try:
        fid = int(message.text.strip())
    except:
        bot.send_message(chat_id, "❌ Нужно ввести число (ID фильма)", reply_markup=main_menu())
        return
    
    if delete_movie(fid, chat_id):
        bot.send_message(chat_id, f"🗑 Фильм с ID {fid} удалён", reply_markup=main_menu())
    else:
        bot.send_message(chat_id, f"❌ Фильм с ID {fid} не найден", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "clear_watched")
def clear_watched(call):
    """Удалить все просмотренные"""
    chat_id = call.message.chat.id
    deleted = delete_watched(chat_id)
    show_screen(call, f"✅ Удалено просмотренных фильмов: {deleted}", main_menu())

@bot.callback_query_handler(func=lambda c: c.data == "clear_all")
def clear_all_confirm(call):
    """Подтверждение полной очистки"""
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("💥 Да, удалить всё", callback_data="clear_all_yes"),
        types.InlineKeyboardButton("↩️ Отмена", callback_data="menu")
    )
    show_screen(call, "⚠️ <b>Точно удалить ВСЕ фильмы?</b>\nЭто действие нельзя отменить!", kb)

@bot.callback_query_handler(func=lambda c: c.data == "clear_all_yes")
def clear_all_yes(call):
    """Полная очистка"""
    chat_id = call.message.chat.id
    if delete_all(chat_id):
        show_screen(call, "💥 Все фильмы удалены", main_menu())
    else:
        show_screen(call, "❌ Ошибка при очистке", main_menu())

# ------------------ Вебхуки для Render ------------------
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    """Endpoint для вебхуков Telegram"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'OK'

@app.route('/')
def index():
    """Главная страница"""
    return '🎬 Movie Bot is running with PostgreSQL!'

@app.route('/health')
def health():
    """Health check для Render"""
    return 'OK', 200

# ------------------ Запуск приложения ------------------
if __name__ == '__main__':
    # Инициализация БД при запуске
    print("🚀 Инициализация бота...")
    init_db()
    
    # Настройка вебхука
    bot.remove_webhook()
    
    # Получаем URL из переменных окружения Render
    render_url = os.getenv('RENDER_EXTERNAL_URL')
    if render_url:
        webhook_url = f"{render_url}/{TOKEN}"
        bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook установлен: {webhook_url}")
    else:
        print("⚠️ RENDER_EXTERNAL_URL не найден, работаю в режиме polling")
    
    # Запуск Flask сервера
    port = int(os.environ.get('PORT', 10000))
    print(f"🌐 Запуск сервера на порту {port}...")
    app.run(host='0.0.0.0', port=port)