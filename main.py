import sqlite3
from datetime import datetime, timedelta
import telebot
from telebot import types
from apscheduler.schedulers.background import BackgroundScheduler

API_TOKEN = '7138896417:AAFuVZBYn-LLxsJJmxjBCw47sng8OFw4ZFA'
bot = telebot.TeleBot(API_TOKEN)

# Хранение chat_id для уведомлений
user_chat_id = None


# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('syrups.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS syrups (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        production_date DATE NOT NULL,
        expiration_days INTEGER NOT NULL CHECK (expiration_days > 0)
    )
    ''')
    conn.commit()
    conn.close()


def db_connection():
    return sqlite3.connect('syrups.db')


# Функция для добавления сиропа
def add_syrup(name: str, production_date: str, expiration_days: int):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO syrups (name, production_date, expiration_days) 
        VALUES (?, ?, ?)''', (name, production_date, expiration_days))
        conn.commit()


# Функция для получения всех сиропов
def get_all_syrups():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, production_date, expiration_days FROM syrups')
        return cursor.fetchall()


# Функция для удаления сиропа
def delete_syrup(syrup_id: int):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM syrups WHERE id = ?', (syrup_id,))
        conn.commit()


# Функция для перемаркировки сиропа
def relabel_syrup(syrup_id: int, new_date: str):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE syrups SET production_date = ? WHERE id = ?', (new_date, syrup_id))
        conn.commit()


# Уведомление о просроченных сиропах
def notify_expired_syrups(chat_id):
    expired_syrups = []
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, production_date, expiration_days FROM syrups')
        syrups = cursor.fetchall()

        for syrup in syrups:
            name, production_date, expiration_days = syrup
            expiration_date = datetime.strptime(production_date, '%Y-%m-%d').date() + timedelta(days=expiration_days)
            if expiration_date < datetime.now().date():
                expired_syrups.append(name)

    if expired_syrups and chat_id:
        message = "Истекшие сиропы:\n" + "\n".join(expired_syrups)
        bot.send_message(chat_id, message)


# Уведомление о списании сиропа
def notify_syrup_removal(chat_id):
    today = datetime.now().date()
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, production_date, expiration_days FROM syrups')
        syrups = cursor.fetchall()

        for syrup in syrups:
            name, production_date, expiration_days = syrup
            expiration_date = datetime.strptime(production_date, '%Y-%m-%d').date() + timedelta(days=expiration_days)

            if expiration_date == today and chat_id:
                bot.send_message(chat_id, f"Сироп {name} нужно списать или перемаркировать.")


# Создание кнопок
def create_main_buttons():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("Добавить сироп"), types.KeyboardButton("Показать сиропы"))
    keyboard.add(types.KeyboardButton("Удалить сироп"), types.KeyboardButton("Перемаркировать сироп"))
    return keyboard


# Создание инлайн-кнопок для удаления сиропов
def create_delete_buttons(syrups):
    keyboard = types.InlineKeyboardMarkup()
    for syrup in syrups:
        syrup_id, name, production_date, _ = syrup
        keyboard.add(types.InlineKeyboardButton(text=f"Удалить {name}, {production_date}", callback_data=str(syrup_id)))
    keyboard.add(types.InlineKeyboardButton(text="Назад", callback_data="back"))
    return keyboard


# Создание инлайн-кнопок для перемаркировки сиропов
def create_relabel_buttons(syrups):
    keyboard = types.InlineKeyboardMarkup()
    for syrup in syrups:
        syrup_id, name, production_date, _ = syrup
        keyboard.add(types.InlineKeyboardButton(text=f"Перемаркировать {name}, {production_date}", callback_data=f"relabel_{syrup_id}"))
    keyboard.add(types.InlineKeyboardButton(text="Назад", callback_data="back"))
    return keyboard


# Обработчик стартового сообщения
@bot.message_handler(commands=['start'])
def send_welcome(message):
    global user_chat_id
    user_chat_id = message.chat.id  # Сохраняем chat_id пользователя
    bot.reply_to(message, "Привет! Я бот для управления сроками годности сиропов.", reply_markup=create_main_buttons())


@bot.message_handler(func=lambda message: message.text == "Добавить сироп")
def request_add_syrup(message):
    bot.reply_to(message, "Введите данные сиропа в формате: Название, дд.мм.гггг, срок хранения (в днях).")


# Обработчик нажатия кнопки "Показать сиропы"
@bot.message_handler(func=lambda message: message.text == "Показать сиропы")
def list_syrups_handler(message):
    syrups = get_all_syrups()
    if syrups:
        response = "Текущие сиропы:\n"
        for syrup in syrups:
            name, production_date, expiration_days = syrup[1], syrup[2], syrup[3]
            production_date_obj = datetime.strptime(production_date, '%Y-%m-%d').date()
            expiration_date = production_date_obj + timedelta(days=expiration_days)

            # Форматируем даты в нужный вид (дд.мм.гггг)
            formatted_production_date = production_date_obj.strftime('%d.%m.%Y')
            formatted_expiration_date = expiration_date.strftime('%d.%m.%Y')

            response += f"{name} {formatted_production_date} - {formatted_expiration_date}. Хранится {expiration_days} дней.\n"
        bot.reply_to(message, response)
    else:
        bot.reply_to(message, "В базе данных нет сиропов.")


# Обработчик для удаления сиропа
@bot.message_handler(func=lambda message: message.text == "Удалить сироп")
def request_delete_syrup(message):
    syrups = get_all_syrups()
    if syrups:
        bot.reply_to(message, "Выберите сироп для удаления:", reply_markup=create_delete_buttons(syrups))
    else:
        bot.reply_to(message, "В базе данных нет сиропов для удаления.")


# Обработчик для перемаркировки сиропа
@bot.message_handler(func=lambda message: message.text == "Перемаркировать сироп")
def request_relabel_syrup(message):
    syrups = get_all_syrups()
    if syrups:
        bot.reply_to(message, "Выберите сироп для перемаркировки:", reply_markup=create_relabel_buttons(syrups))
    else:
        bot.reply_to(message, "В базе данных нет сиропов для перемаркировки.")


@bot.message_handler(func=lambda message: True)
def handle_add_syrup_input(message):
    try:
        data = message.text.strip().split(", ")
        if len(data) != 3:
            bot.reply_to(message, "Неправильный формат. Введите данные в формате: Название, дд.мм.гггг, срок хранения (в днях).")
            return

        name = data[0]
        production_date = datetime.strptime(data[1], '%d.%m.%Y').strftime('%Y-%m-%d')
        expiration_days = int(data[2])

        add_syrup(name, production_date, expiration_days)
        bot.reply_to(message, f"Сироп '{name}' добавлен с датой производства {data[1]} и сроком хранения {expiration_days} дней.")
    except (ValueError, IndexError):
        bot.reply_to(message, "Ошибка в формате ввода. Убедитесь, что вы ввели данные в формате: Название, дд.мм.гггг, срок хранения (в днях).")


# Обработчик удаления сиропа по нажатию кнопки
@bot.callback_query_handler(func=lambda call: call.data.isdigit())
def confirm_delete(call):
    syrup_id = int(call.data)
    delete_syrup(syrup_id)
    bot.answer_callback_query(call.id, "Сироп удален.")
    bot.send_message(call.message.chat.id, f"Сироп с ID {syrup_id} был удален.")
    bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=create_main_buttons())


# Обработчик выбора сиропа для перемаркировки
@bot.callback_query_handler(func=lambda call: call.data.startswith("relabel_"))
def relabel_syrup_prompt(call):
    syrup_id = int(call.data.split("_")[1])
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, f"Введите новую дату производства для сиропа с ID {syrup_id} (в формате дд.мм.гггг):")
    bot.register_next_step_handler(msg, relabel_syrup_handler, syrup_id)


# Обработчик ввода новой даты для перемаркировки
def relabel_syrup_handler(message, syrup_id):
    try:
        new_production_date = message.text.strip()
        # Проверяем формат даты
        new_production_date_db = datetime.strptime(new_production_date, '%d.%m.%Y').strftime('%Y-%m-%d')

        relabel_syrup(syrup_id, new_production_date_db)
        bot.reply_to(message, f"Дата производства для сиропа с ID {syrup_id} обновлена на {new_production_date}.")
    except ValueError:
        bot.reply_to(message, "Неверный формат даты. Пожалуйста, введите дату в формате дд.мм.гггг.")

# Запуск уведомлений каждый день в 9 утра
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: notify_expired_syrups(user_chat_id), 'cron', hour=9, minute=0)
scheduler.add_job(lambda: notify_syrup_removal(user_chat_id), 'cron', hour=9, minute=0)
scheduler.start()

# Запуск бота
init_db()
bot.infinity_polling()