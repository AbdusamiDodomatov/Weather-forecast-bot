import requests
import telebot
from telebot import types

bot = telebot.TeleBot('7664050350:AAE4vCX_LskuJn211y7jUTxCUBPFIGbEQrI')
API = 'cbd25e18a1bb35797ac80c002232c1ad'

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    location_button = types.KeyboardButton('Send Location', request_location=True)
    city_button = types.KeyboardButton('Choose City')
    markup.add(location_button, city_button)
    bot.send_message(message.chat.id, "Hi! Send your location or choose a city.", reply_markup=markup)

@bot.message_handler(content_types=['location'])
def handle_location(message):
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        city = get_city_by_location(lat, lon)
        if city:
            bot.send_message(message.chat.id, f"You're near {city}. Fetching weather for {city}...")
            fetch_weather(message.chat.id, city)
            recommend_nearby_cities(message.chat.id, lat, lon)
        else:
            bot.send_message(message.chat.id, "Sorry, I couldn't determine your city. Please try again.")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == 'Choose City':
        recommend_cities(message.chat.id)
    else:
        city = message.text.strip().capitalize()
        fetch_weather(message.chat.id, city)

def recommend_cities(chat_id):
    recommended_cities = ['Tashkent', 'Moscow', 'New York', 'London', 'Canberra', 'Berlin']
    markup = types.InlineKeyboardMarkup(row_width=2)
    for city in recommended_cities:
        markup.add(types.InlineKeyboardButton(city, callback_data=city))
    bot.send_message(chat_id, "Here are some recommended cities:", reply_markup=markup)

def recommend_nearby_cities(chat_id, lat, lon):
    try:
        res = requests.get(f'https://api.openweathermap.org/data/2.5/find?lat={lat}&lon={lon}&cnt=5&appid={API}')
        data = res.json()
        if data.get("list"):
            markup = types.InlineKeyboardMarkup(row_width=2)
            for city_data in data["list"]:
                city_name = city_data["name"]
                markup.add(types.InlineKeyboardButton(city_name, callback_data=city_name))
            bot.send_message(chat_id, "Here are some nearby cities:", reply_markup=markup)
        else:
            bot.send_message(chat_id, "Sorry, I couldn't find nearby cities.")
    except Exception as e:
        bot.send_message(chat_id, "An error occurred while fetching nearby cities.")
        print(f"Error: {e}")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    city = call.data
    fetch_weather(call.message.chat.id, city)

def fetch_weather(chat_id, city):
    try:
        res = requests.get(f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API}&units=metric')
        data = res.json()
        if data.get("cod") != 200:
            bot.send_message(chat_id, f"Sorry, I couldn't find weather data for {city}.")
        else:
            weather_condition = data["weather"][0]["main"]
            temp = round(data["main"]["temp"])
            description = data["weather"][0]["description"]
            icon_code = data["weather"][0]["icon"]
            icon_url = f"https://openweathermap.org/img/wn/{icon_code}@4x.png"

            response = (
                f"Weather in {city}:\n"
                f"- Condition: {weather_condition}\n"
                f"- Temperature: {temp}°C\n"
                f"- Description: {description}"
            )
            bot.send_photo(chat_id, icon_url)
            bot.send_message(chat_id, response)
    except Exception as e:
        bot.send_message(chat_id, "An error occurred while fetching the weather. Please try again later.")
        print(f"Error: {e}")

def get_city_by_location(lat, lon):
    try:
        res = requests.get(f'http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API}')
        data = res.json()
        if data.get("cod") == 200:
            return data.get("name")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None



bot.infinity_polling(none_stop=True)
