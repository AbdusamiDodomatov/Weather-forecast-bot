import os
import requests
import telebot
from telebot import types
from dotenv import load_dotenv

BOT_TOKEN = os.getenv("BOT_TOKEN")
API = os.getenv("WEATHER_API")

if not BOT_TOKEN or not API:
    raise ValueError("Missing BOT_TOKEN or WEATHER_API in .env file.")

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    location_button = types.KeyboardButton('📍 Send Location', request_location=True)
    city_button = types.KeyboardButton('🏙 Choose City')
    markup.add(location_button, city_button)

    welcome_text = (
        "👋 Hi! I'm your weather bot!\n\n"
        "🌍 Send your **location** or choose a **city** to get the weather forecast."
    )

    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(content_types=['location'])
def handle_location(message):
    if message.location:
        lat, lon = message.location.latitude, message.location.longitude
        city = get_city_by_location(lat, lon)

        if city:
            bot.send_message(message.chat.id, f"📍 You're near **{city}**. Fetching weather…", parse_mode="Markdown")
            fetch_weather(message.chat.id, city)
            recommend_nearby_cities(message.chat.id, lat, lon)
        else:
            bot.send_message(message.chat.id, "⚠️ I couldn't determine your city. Try again later.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == "🏙 Choose City":
        recommend_cities(message.chat.id)
    else:
        city = message.text.strip().title()  
        fetch_weather(message.chat.id, city)

def recommend_cities(chat_id):
    popular_cities = ['Tashkent', 'Moscow', 'New York', 'London', 'Tokyo', 'Berlin', 'Paris', 'Dubai']
    markup = types.InlineKeyboardMarkup(row_width=2)

    for city in popular_cities:
        markup.add(types.InlineKeyboardButton(city, callback_data=city))
    
    bot.send_message(chat_id, "🌎 Choose a city:", reply_markup=markup)

def recommend_nearby_cities(chat_id, lat, lon):
    try:
        url = f'https://api.openweathermap.org/data/2.5/find?lat={lat}&lon={lon}&cnt=5&appid={API}&units=metric'
        res = requests.get(url)
        data = res.json()

        if not data.get("list"):
            bot.send_message(chat_id, "⚠️ Couldn't find nearby cities.")
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        for city_data in data["list"][:3]: 
            city_name = city_data["name"]
            markup.add(types.InlineKeyboardButton(city_name, callback_data=city_name))
        
        bot.send_message(chat_id, "🌍 Nearby cities:", reply_markup=markup)
    except Exception as e:
        bot.send_message(chat_id, "❌ Error fetching nearby cities.")
        print(f"Error: {e}")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        fetch_weather(call.message.chat.id, call.data)
    except Exception as e:
        bot.send_message(call.message.chat.id, "❌ An error occurred while processing your request.")
        print(f"Error: {e}")

def fetch_weather(chat_id, city):
    try:
        url = f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API}&units=metric'
        res = requests.get(url)
        data = res.json()

        if data.get("cod") != 200:
            bot.send_message(chat_id, f"⚠️ Sorry, I couldn't find weather data for **{city}**.")
            return

        weather_condition = data["weather"][0]["main"]
        temp = round(data["main"]["temp"])
        description = data["weather"][0]["description"].capitalize()
        icon_code = data["weather"][0]["icon"]
        icon_url = f"https://openweathermap.org/img/wn/{icon_code}@4x.png"

        response = (
            f"🌤 **Weather in {city}**\n"
            f"📌 Condition: *{weather_condition}*\n"
            f"🌡 Temperature: *{temp}°C*\n"
            f"📖 Description: *{description}*"
        )

        bot.send_photo(chat_id, icon_url, caption=response, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, "❌ An error occurred while fetching the weather. Try again later.")
        print(f"Error: {e}")

def get_city_by_location(lat, lon):
    try:
        url = f'http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API}'
        res = requests.get(url)
        data = res.json()

        if data.get("cod") == 200:
            return data.get("name")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

bot.infinity_polling(none_stop=True)
