import os
import requests
import telebot
from telebot import types
from dotenv import load_dotenv
import psycopg2.pool
from urllib.parse import urlparse
import logging
from datetime import datetime, timedelta, timezone
import gettext
from apscheduler.schedulers.background import BackgroundScheduler

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("WEATHER_API")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN or not API_KEY:
    raise ValueError("Missing BOT_TOKEN or WEATHER_API in environment variables.")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in environment variables.")

# Парсим DATABASE_URL
parsed_url = urlparse(DATABASE_URL)

# Настройка пула соединений с базой данных
DB_PARAMS = {
    "dbname": parsed_url.path[1:], 
    "user": parsed_url.username,
    "password": parsed_url.password,
    "host": parsed_url.hostname,
    "port": parsed_url.port,
}

# Попробуем подключиться, сначала без SSL
try:
    conn_pool = psycopg2.pool.SimpleConnectionPool(1, 10, **DB_PARAMS)
    logging.info("Connected to PostgreSQL without SSL.")
except psycopg2.OperationalError as e:
    logging.warning("Connection failed without SSL, retrying with sslmode='require'...")
    DB_PARAMS["sslmode"] = "require"
    conn_pool = psycopg2.pool.SimpleConnectionPool(1, 10, **DB_PARAMS)
    logging.info("Connected to PostgreSQL with sslmode='require'.")

# Подключение к боту
bot = telebot.TeleBot(BOT_TOKEN)
user_selected_city = {}

# Настройка мультиязычности
gettext.bindtextdomain("messages", "locale")
gettext.textdomain("messages")
_ = gettext.gettext  # Функция перевода


def execute_query(query, params=None, fetchone=False, fetchall=False):
    """ Выполнение SQL-запросов с использованием пула соединений """
    conn = conn_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()
            if fetchone:
                return cur.fetchone()
            elif fetchall:
                return cur.fetchall()
    except Exception as e:
        logging.error(f"Ошибка в БД: {e}")
    finally:
        conn_pool.putconn(conn)


def save_user(user):
    """ Сохранение пользователя в базу данных """
    query = """
        INSERT INTO telegram_users (telegram_id, username, first_name, last_name, language_code, is_premium)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (telegram_id) DO UPDATE 
        SET username = EXCLUDED.username, 
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            language_code = EXCLUDED.language_code,
            is_premium = EXCLUDED.is_premium;
    """
    params = (user.id, user.username, user.first_name, user.last_name, user.language_code, getattr(user, "is_premium", False))
    execute_query(query, params)


@bot.message_handler(commands=['start'])
def start(message):
    save_user(message.from_user)
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    location_button = types.KeyboardButton(_('📍 Отправить локацию'), request_location=True)
    city_button = types.KeyboardButton(_('🏙 Выбрать город'))
    
    markup.add(location_button, city_button)

    bot.send_message(
        message.chat.id,
        _("👋 Привет! Я твой погодный бот!\n\n🌍 Отправь свою **локацию** или выбери **город**, чтобы узнать прогноз погоды."),
        reply_markup=markup, parse_mode="Markdown"
    )

def make_weather_request(endpoint, params):
    """ Универсальный метод для запросов к OpenWeatherMap """
    try:
        url = f"https://api.openweathermap.org/data/2.5/{endpoint}"
        params["appid"] = API_KEY
        params["units"] = "metric"
        response = requests.get(url, params=params)
        return response.json()
    except Exception as e:
        logging.error(f"Ошибка запроса к OpenWeatherMap: {e}")
        return None


def fetch_weather(chat_id, city):
    data = make_weather_request("weather", {"q": city})

    if not data or data.get("cod") != 200:
        bot.send_message(chat_id, f"⚠️ Город **{city}** не найден.")
        return

    try:
        temp = round(data["main"]["temp"])
        description = data["weather"][0]["description"].capitalize()
        icon_code = data["weather"][0]["icon"]
        icon_url = f"http://openweathermap.org/img/wn/{icon_code}@4x.png"

        response = (
            f"🌤 **Погода в {city}**\n"
            f"🌡 Температура: *{temp}°C*\n"
            f"📖 Описание: *{description}*"
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📅 Погода на завтра", callback_data=f"forecast_{city}"))
        markup.add(types.InlineKeyboardButton("🔔 Получать уведомления", callback_data=f"notify_{city}"))

        bot.send_photo(chat_id, icon_url, caption=response, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        logging.error(f"Ошибка обработки данных погоды: {e}")
        bot.send_message(chat_id, "❌ Произошла ошибка при обработке данных о погоде.")


@bot.message_handler(content_types=['location'])
def handle_location(message):
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
        data = make_weather_request("weather", {"lat": lat, "lon": lon})

        if data and data.get("cod") == 200:
            city = data.get("name")
            bot.send_message(message.chat.id, _("📍 Вы находитесь в **{}**. Получаем погоду…").format(city), parse_mode="Markdown")
            fetch_weather(message.chat.id, city)
        else:
            bot.send_message(message.chat.id, _("⚠️ Не удалось определить ваш город. Попробуйте снова."))


@bot.message_handler(commands=["users_count"])
def users_count(message):
    admin_id = int(os.getenv("ADMIN_ID", 0))

    if message.chat.id == admin_id:
        count = execute_query("SELECT COUNT(*) FROM telegram_users;", fetchone=True)[0]
        bot.send_message(message.chat.id, _("👥 Всего пользователей: {}").format(count))
    else:
        bot.send_message(message.chat.id, _("🚫 У вас нет доступа к этой информации."))


@bot.callback_query_handler(func=lambda call: call.data.startswith("notify_"))
def subscribe_notifications(call):
    city = call.data.replace("notify_", "")
    user_id = call.message.chat.id

    execute_query(
        "INSERT INTO weather_subscriptions (user_id, city) VALUES (%s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET city = EXCLUDED.city;",
        (user_id, city)
    )
    bot.send_message(user_id, f"✅ Теперь вы будете получать ежедневные уведомления о погоде в **{city}**!")


@bot.message_handler(commands=['unsubscribe'])
def unsubscribe_notifications(message):
    execute_query("DELETE FROM weather_subscriptions WHERE user_id = %s;", (message.chat.id,))
    bot.send_message(message.chat.id, "🚫 Вы отписались от уведомлений о погоде.")


def send_weather_notifications():
    subscriptions = execute_query("SELECT user_id, city FROM weather_subscriptions;", fetchall=True)
    for user_id, city in subscriptions:
        fetch_weather(user_id, city)

@bot.callback_query_handler(func=lambda call: call.data.startswith("forecast_"))

def forecast_weather(call):
    city = call.data.replace("forecast_", "")
    user_id = call.message.chat.id

    # Запрашиваем прогноз погоды на 1 день вперёд
    data = make_weather_request("forecast", {"q": city, "cnt": 8})  # 8 временных отметок (24 часа)

    if not data or data.get("cod") != "200":
        bot.send_message(user_id, f"⚠️ Не удалось получить прогноз погоды для **{city}**.")
        return

        # Получаем данные о погоде на следующий день
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    next_day_data = [entry for entry in data["list"] if datetime.fromtimestamp(entry["dt"], timezone.utc).date() == tomorrow.date()]



    if not next_day_data:
        bot.send_message(user_id, f"⚠️ Прогноз на завтра для **{city}** не найден.")
        return

    # Рассчитываем среднюю температуру и общее описание погоды
    avg_temp = sum(entry["main"]["temp"] for entry in next_day_data) / len(next_day_data)
    descriptions = {entry["weather"][0]["description"] for entry in next_day_data}
    weather_description = ", ".join(descriptions).capitalize()

    # Берём иконку погоды из первой записи
    icon_code = next_day_data[0]["weather"][0]["icon"]
    icon_url = f"http://openweathermap.org/img/wn/{icon_code}@4x.png"

    response = (
        f"📅 **Прогноз погоды на завтра в {city}**\n"
        f"🌡 Средняя температура: *{round(avg_temp)}°C*\n"
        f"📖 Описание: *{weather_description}*"
    )

    bot.send_photo(user_id, icon_url, caption=response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == _('🏙 Выбрать город'))
def ask_city(message):
    bot.send_message(message.chat.id, "Введите название города, для которого хотите узнать погоду:")
    bot.register_next_step_handler(message, handle_city_input)


def handle_city_input(message):
    city = message.text.strip()
    if not city:
        bot.send_message(message.chat.id, "⚠️ Пожалуйста, введите корректное название города.")
        return
    
    fetch_weather(message.chat.id, city)


scheduler = BackgroundScheduler()
scheduler.add_job(send_weather_notifications, "interval", hours=24, next_run_time=datetime.now() + timedelta(seconds=10))
scheduler.start()

# Запуск бота
bot.infinity_polling(none_stop=True)