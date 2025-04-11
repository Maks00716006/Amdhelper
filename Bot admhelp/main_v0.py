import random
import sqlite3
from decouple import config
from pyromod import Client, Message
from pyrogram import filters
from pyrogram.enums import ParseMode
from template_v0 import generate_template
from checkTest import checkTest
from PIL import Image
from io import BytesIO
import numpy as np

# Стоп-лист запрещённых слов
stop_list = ["мат", "оскорбление", "спам", "запрещенное_слово"]

# Словарь для хранения количества нарушений каждого пользователя
user_violations = {}

# Лимит нарушений перед удалением пользователя
VIOLATION_LIMIT = 3
# Словарь для хранения состояний пользователей
user_states = {}
teacher_results = {}

api_id = config("API_ID")
api_hash = config("API_HASH")
phone = config("PHONE")
login = config("LOGIN")

database = config("DATABASE")

bot = Client(name=login, api_id=api_id, api_hash=api_hash, phone_number=phone)


async def func(_, __, message: Message):
    user_id = message.from_user.id
    cursor, connection = await create_connection()
    if not is_active_user(user_id, cursor):
        await message.reply_text("У вас нет доступа!")
        return False
    return True


active_user = filters.create(func)


async def add_bot_in_db(client: Client, cursor, connection):
    me = await client.get_me()
    if not is_user_registered(me.id, cursor):
        register_user(me.id, me.username, me.first_name, me.last_name, 0,
                      me.phone_number, 0, 'admin', 1, cursor, connection)


async def create_connection():
    """Подключение к базе данных. Создание таблиц при отсутствии"""
    connection = sqlite3.connect(database)
    cursor = connection.cursor()
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            last_name TEXT,
            first_name TEXT,
            patronymic TEXT,
            number_phone TEXT,
            class_code TEXT,
            role TEXT,
            active INTEGER,
            FOREIGN KEY (class_code) REFERENCES class(class_code)
            )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS list_classes (
            class_code INTEGER PRIMARY KEY CHECK(LENGTH(CAST(class_code AS TEXT)) = 5),
            teacher_id INTEGER NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users(user_id)
            )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS class (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_code TEXT NOT NULL,
            student_id INTEGER NOT NULL,
            FOREIGN KEY (student_id) REFERENCES users(user_id),
            FOREIGN KEY (class_code) REFERENCES list_classes(class_code)
            )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id_request INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
            FOREIGN KEY (role) REFERENCES users(role)
            )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            type TEXT,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
    """)
    connection.commit()
    await add_bot_in_db(bot, cursor, connection)
    return connection, cursor


def is_user_registered(user_id, cursor):
    """Проверка зарегистрирован ли пользователь """
    result = cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone() is not None


def is_teacher(user_id, cursor):
    """Проверка пользователя на принадлежность к роли учителя"""
    result = cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone()[-2] == 'teacher'


def is_admin(user_id, cursor):
    """Проверка пользователя на принадлежность к роли администратора"""
    result = cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone()[-2] == 'admin'


def is_student(user_id, cursor):
    """Проверка пользователя на принадлежность к роли ученика"""
    result = cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone()[-2] == 'student'


def is_parent(user_id, cursor):
    """Проверка пользователя на принадлежность к роли родителя"""
    result = cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone()[-2] == 'parent'


def is_class_registered(class_code, cursor):
    """Проверка существует ли такой класс"""
    result = cursor.execute("SELECT * FROM list_classes WHERE class_code = ?", (class_code,))
    return result.fetchone() is not None


def is_active_user(user_id, cursor):
    """Проверка активации учётной записи пользователя в системе"""
    result = cursor.execute("SELECT active FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone()[-1] == 1


def registration_request(user_id, role, cursor, connection):
    """Зарегистрировать запрос"""
    try:
        cursor.execute(
            "INSERT INTO requests (user_id, role) VALUES (?, ?)",
            (user_id, role))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f'Ошибка при регистрации заявки на подтверждение: {e}')
        return False


def register_user(user_id, username, first_name, last_name, patronymic, number_phone, class_code, role, active, cursor,
                  connection):
    """Зарегистрировать нового пользователя"""
    try:
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, last_name, patronymic, number_phone, class_code, role, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, first_name.upper(), last_name.upper(), str(patronymic).upper(),
             number_phone, class_code, role, active))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f'Ошибка при регистрации пользователя: {e}')
        return False


def add_chat(chat_id, title, chat_type, user_id):
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO chats (chat_id, title, type, user_id) VALUES (?, ?, ?, ?)",
                       (chat_id, title, chat_type, user_id))
        conn.commit()
        print(f"Чат/канал {title} добавлен в базу")
    except sqlite3.IntegrityError:
        print(f"Чат с ID {chat_id} уже существует")
    finally:
        conn.close()


def get_chats():
    conn = sqlite3.connect(database)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM chats")
    chats = cursor.fetchall()
    conn.close()
    return chats


def activate_user(user_id, cursor, connection):
    """Активировать учётную запись пользователя"""
    try:
        cursor.execute("UPDATE users SET active = 1 WHERE user_id = ?", (user_id,))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f'Ошибка при активации пользователя: {e}')
        return False


def deactivate_user(user_id, cursor, connection):
    """Деактивировать (отключить) учётную запись пользователя"""
    try:
        cursor.execute("UPDATE users SET active = 0 WHERE user_id = ?", (user_id,))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f'Ошибка при деактивации пользователя: {e}')
        return False


def register_user_in_class(class_code, student_id, cursor, connection):
    """Добавление нового ученика или родителя в класс"""
    try:
        cursor.execute(
            "INSERT INTO class (class_code, student_id) VALUES (?, ?)",
            (class_code, student_id))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f'Ошибка при регистрации пользователя в классе: {e}')
        return False


def register_class(class_code, teacher_id, cursor, connection):
    """Добавление нового класса в базу данных"""
    try:
        cursor.execute(
            "INSERT INTO list_classes (class_code, teacher_id) VALUES (?, ?)",
            (class_code, teacher_id))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f'Ошибка при создании класса: {e}')
        return False


def get_user_id_request(role, cursor, connection):
    """Возвращаем id отправителя запроса с указанной ролью"""
    try:
        id_user = cursor.execute("SELECT user_id FROM requests WHERE role = ?", (role,)).fetchone()
        connection.commit()
        return id_user[0]
    except sqlite3.Error as e:
        print(f'Ошибка при извлечении ID пользователя на подтверждение: {e}')
        return False


def delete_request(request_id, cursor, connection):
    """Удалить выбранный запрос"""
    try:
        cursor.execute("DELETE FROM requests WHERE id_request = ?", (request_id,))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f'Ошибка при удалении заявки на подтверждение: {e}')
        return False


def generate_class_code():
    """Генерирует случайный пятизначный код класса."""
    return random.randint(10000, 99999)


def get_role(user_id, cursor):
    result = cursor.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone()


def get_full_name(user_id, cursor):
    result = cursor.execute("SELECT last_name, first_name, patronymic FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone()


def get_username(user_id, cursor):
    result = cursor.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone()


def get_number_phone(user_id, cursor):
    result = cursor.execute("SELECT number_phone FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone()


def get_class_code(user_id, cursor):
    result = cursor.execute("SELECT class_code FROM users WHERE user_id = ?", (user_id,))
    return result.fetchone()


def get_list_classes(cursor):
    result = cursor.execute("SELECT * FROM list_classes ORDER BY id_teacher")
    return result.fetchall()


def get_users_by_role(role, cursor):
    result = cursor.execute("SELECT user_id FROM users WHERE role = ?", (role,))
    return result.fetchall()


def get_list_id_user_class(class_code, cursor):
    result = cursor.execute("SELECT student_id FROM class WHERE class_code = ?", (class_code,))
    return result.fetchall()


def get_request_by_role(role, cursor):
    result = cursor.execute("SELECT * FROM requests WHERE role = ?", (role,))
    return result.fetchone()


def get_id_teacher(class_code, cursor):
    result = cursor.execute("SELECT teacher_id FROM list_classes WHERE class_code = ?", (class_code,))
    return result.fetchone()


def set_role_user(user_id, role, cursor, connection):
    try:
        cursor.execute("UPDATE users SET role = ? WHERE user_id = ?", (role, user_id))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f'Ошибка при установке роли: {e}')
        return False


def set_first_name(user_id, first_name, cursor, connection):
    try:
        cursor.execute("UPDATE users SET first_name = ? WHERE user_id = ?", (first_name, user_id))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f"Не удалось установить имя: {e}")
        return False


def set_last_name(user_id, last_name, cursor, connection):
    try:
        cursor.execute("UPDATE users SET last_name = ? WHERE user_id = ?", (last_name, user_id))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f"Не удалось установить фамилию: {e}")
        return False


def set_patronymic(user_id, patronymic, cursor, connection):
    try:
        cursor.execute("UPDATE users SET patronymic = ? WHERE user_id = ?", (patronymic, user_id))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f"Не удалось установить отчество: {e}")
        return False


def set_number_phone(user_id, patronymic, cursor, connection):
    try:
        cursor.execute("UPDATE users SET number_phone = ? WHERE user_id = ?", (patronymic, user_id))
        connection.commit()
        return True
    except sqlite3.Error as e:
        print(f"Не удалось установить номер: {e}")
        return False


async def get_my_id(client: Client):
    info_me = await client.get_me()
    return info_me.id


async def notification_of_request(client, user_id, role, cursor):
    """Сообщение о поступлении новой заявки на активацию учётной записи"""
    if role == 'admin':
        target = ('me',)
    elif role == 'teacher':
        target = get_users_by_role('admin', cursor)[0]
    else:
        code_class = get_class_code(user_id, cursor)[0]
        target = get_id_teacher(code_class, cursor)

    for i in tuple(target):
        await client.send_message(i, 'Поступила навоя заявка! Для просмотра введите /заявки')


async def set_data(chat):
    """Запрос данных пользователя"""
    last_name = await chat.ask("Введите вашу фамилию")
    first_name = await chat.ask("Введите ваше имя")
    patronymic = await chat.ask('Введите ваше отчество(при отсутствии поставить нуль ("0"))')
    number_phone = await chat.ask("Введите номер телефона (без '+')")
    last_name, first_name, patronymic, number_phone = last_name.text, first_name.text, patronymic.text, number_phone.text
    return last_name, first_name, patronymic, number_phone


@bot.on_message(filters.group & filters.incoming)  # Обрабатываем сообщения только в группах
async def moderate_chat(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Проверяем, содержит ли сообщение слова из стоп-листа
    for word in stop_list:
        if word in message.text.lower():
            # Удаляем сообщение
            await message.delete()

            # Увеличиваем счётчик нарушений для пользователя
            if user_id not in user_violations:
                user_violations[user_id] = 0
            user_violations[user_id] += 1

            # Отправляем предупреждение
            if user_violations[user_id] < VIOLATION_LIMIT:
                await client.send_message(
                    chat_id,
                    f"@{message.from_user.username}, ваше сообщение удалено из-за нарушения правил. "
                    f"Количество предупреждений: {user_violations[user_id]}/{VIOLATION_LIMIT}."
                )
            else:
                # Удаляем пользователя из чата при превышении лимита
                await client.ban_chat_member(chat_id, user_id)
                await client.send_message(
                    chat_id,
                    f"@{message.from_user.username} был удалён из чата за повторные нарушения."
                )
                # Сбрасываем счётчик нарушений для этого пользователя
                user_violations[user_id] = 0
            break


async def default_registration(role, client, message):
    """Шаблон сценария регистрации нового пользователя"""
    connection, cursor = await create_connection()
    user_id = message.from_user.id
    username = message.from_user.username
    chat = message.chat
    if is_user_registered(user_id, cursor):
        cursor.close()
        connection.close()
        await message.reply_text("Вы уже зарегистрированы!")
    else:
        request = ''
        while request != "ДА":
            last_name, first_name, patronymic, number_phone = await set_data(chat)
            await message.reply_text(f"""Проверьте верность введённых данных: \n
                                        {last_name} {first_name} {patronymic} \n
                                        {number_phone}""")
            request = await chat.ask("Всё верно? (ДА/НЕТ)", filters=filters.text)
            request = request.text.upper()
        if role in ['student', 'parent']:
            class_code = await chat.ask("Введите код класса, который вам выдал классный руководитель:",
                                        filters=filters.text)

            while not is_class_registered(class_code.text, cursor):
                class_code = await chat.ask("Введите код класса, который вам выдал классный руководитель:",
                                            filters=filters.text)
            class_code = class_code.text
        else:
            class_code = '0'
        if register_user(user_id, username, first_name, last_name, patronymic, number_phone, class_code, role, 0,
                         cursor,
                         connection):
            if role in ['student', 'parent']:
                register_user_in_class(class_code, user_id, cursor, connection)
            await message.reply_text('Вы зарегистрированы! Ожидайте активации.')
            registration_request(user_id, role, cursor, connection)
            await notification_of_request(client, user_id, role, cursor)
        else:
            await message.reply_text("Не удалось зарегистрировать!")
        cursor.close()
        connection.close()


@bot.on_message(filters.command("создатькласс") & filters.incoming & active_user)
async def create_class(client: Client, message: Message):
    """Создание нового класса"""
    connection, cursor = await create_connection()
    user_id = message.from_user.id
    if not (is_teacher(user_id, cursor) or is_admin(user_id, cursor)):
        cursor.close()
        connection.close()
        await message.reply_text("Вы не можете создать класс!")
    else:
        class_code = generate_class_code()
        while is_class_registered(class_code, cursor):
            class_code = generate_class_code()
        if register_class(class_code, message.from_user.id, cursor, connection):
            await message.reply_text(f'Класс зарегистрирован! Код класса: {class_code}')
        else:
            await message.reply_text("Не удалось зарегистрировать!")
        cursor.close()
        connection.close()


@bot.on_message(filters.command("начать") & filters.incoming)
async def start_command(client: Client, message: Message):
    """Стартовая команда"""
    connection, cursor = await create_connection()
    user_id = message.from_user.id
    username = message.from_user.username

    if is_user_registered(user_id, cursor):
        cursor.close()
        connection.close()
        await message.reply_text("Вы уже зарегистрированы!")
    else:
        cursor.close()
        connection.close()
        await message.reply_text(f"""Привет, {username}! Пожалуйста, укажите, кто вы:
        /администратор - Администратор
        /учитель - Учитель
        /ученик - Ученик
        /родитель - Родитель
        """
                                 )


@bot.on_message(filters.command("администратор") & filters.incoming)
async def admin_registration(client: Client, message: Message):
    """Регистрации учётной записи с ролью администратора"""
    role = 'admin'
    await default_registration(role, client, message)


@bot.on_message(filters.command("учитель") & filters.incoming)
async def teacher_registration(client: Client, message: Message):
    """Регистрации учётной записи с ролью учителя"""
    role = 'teacher'
    await default_registration(role, client, message)


@bot.on_message(filters.command("ученик") & filters.incoming)
async def student_registration(client: Client, message: Message):
    """Регистрации учётной записи с ролью ученика"""
    role = 'student'
    await default_registration(role, client, message)


@bot.on_message(filters.command("родитель") & filters.incoming)
async def parent_registration(client: Client, message: Message):
    """Регистрации учётной записи с ролью родителя"""
    role = 'parent'
    await default_registration(role, client, message)


# @bot.on_message((filters.command("создатьканал") | filters.command("создатьчат")) & filters.incoming & active_user)
# async def create_chat_command(client: Client, message: Message):
#     connection, cursor = await create_connection()
#     user_id = message.from_user.id
#     chat = message.chat
#
#     # Определяем роль пользователя
#     role = get_role(user_id, cursor)[0]
#
#     # Список для хранения выбранных участников
#     selected_users = [user_id]
#
#     # Запрашиваем тип чата (чат или канал)
#     chat_type = await chat.ask("Вы хотите создать чат или канал? (напишите 'чат' или 'канал')")
#     while chat_type.text.lower() not in ["чат", "канал"]:
#         await message.reply_text("Пожалуйста, введите 'чат' или 'канал'.")
#         chat_type = await chat.ask("Вы хотите создать чат или канал? (напишите 'чат' или 'канал')")
#
#     # Запрашиваем название чата/канала
#     chat_title = await chat.ask("Введите название чата/канала:")
#
#     # Основной цикл добавления участников
#     while True:
#         search_query = await chat.ask("Введите имя, фамилию или отчество участника (или /готово для завершения):")
#
#         if search_query.text.lower() == "/готово":
#             break
#
#         # Поиск пользователей в зависимости от роли
#         if role in ["admin", "teacher"]:
#             # Поиск по всей базе
#             cursor.execute(
#                 "SELECT user_id, last_name, first_name, patronymic FROM users WHERE last_name LIKE ? OR first_name LIKE ? OR patronymic LIKE ?",
#                 (f"%{search_query.text.upper()}%", f"%{search_query.text.upper()}%", f"%{search_query.text.upper()}%")
#             )
#         else:
#             # Поиск только в своём классе
#             class_code = get_class_code(user_id, cursor)[0]
#             cursor.execute(
#                 "SELECT u.user_id, u.last_name, u.first_name, u.patronymic FROM users u JOIN class c ON u.user_id = c.student_id WHERE c.class_code = ? AND (u.last_name LIKE ? OR u.first_name LIKE ? OR u.patronymic LIKE ?)",
#                 (class_code, f"%{search_query.text.upper()}%", f"%{search_query.text.upper()}%", f"%{search_query.text.upper()}%")
#             )
#
#         users = cursor.fetchall()
#
#         if not users:
#             await message.reply_text("Никого не найдено. Попробуйте ещё раз.")
#             continue
#
#         # Формируем список найденных пользователей
#         user_list = "\n".join([f"{i + 1}. {user[1]} {user[2]} {user[3]}" for i, user in enumerate(users)])
#         await message.reply_text(f"Найдены следующие пользователи:\n{user_list}\n")
#
#         # Запрашиваем выбор пользователя
#         user_choice = await chat.ask("Введите номер пользователя для добавления:")
#         while not user_choice.text.isdigit() or int(user_choice.text) < 1 or int(user_choice.text) > len(users):
#             await message.reply_text("Пожалуйста, введите корректный номер.")
#             user_choice = await chat.ask("Пожалуйста, введите корректный номер. Для выхода напишите /выход.")
#             if user_choice.text == '/выход':
#                 break
#         if user_choice.text == '/выход':
#             continue
#         selected_user = users[int(user_choice.text) - 1]
#         selected_users.append(selected_user[0])  # Добавляем ID пользователя
#         await message.reply_text(f"Пользователь {selected_user[1]} {selected_user[2]} добавлен.")
#
#     # Создаём чат/канал
#     if chat_type.text.lower() == "чат":
#         try:
#             # Создаём группу (чат)
#             created_chat = await client.create_supergroup(chat_title.text, selected_users)
#             await message.reply_text(f"Чат '{chat_title.text}' успешно создан!")
#
#             # Добавляем запись в таблицу chats
#             add_chat(created_chat.id, chat_title.text, "group", user_id)
#         except Exception as e:
#             await message.reply_text(f"Ошибка при создании чата: {e}")
#     else:
#         try:
#             # Создаём канал
#             created_channel = await client.create_channel(chat_title.text, "")
#             for user_id in selected_users:
#                 await client.add_chat_members(created_channel.id, user_id)
#             await message.reply_text(f"Канал '{chat_title.text}' успешно создан! Ссылка: {created_channel.invite_link}")
#
#             # Добавляем запись в таблицу chats
#             add_chat(created_channel.id, chat_title.text, "channel", user_id)
#         except Exception as e:
#             await message.reply_text(f"Ошибка при создании канала: {e}")
#
#     cursor.close()
#     connection.close()

@bot.on_message((filters.command("создатьканал") | filters.command("создатьчат")) & filters.incoming & active_user)
async def create_chat_command(client: Client, message: Message):
    connection, cursor = await create_connection()
    me = await client.get_me()
    user_id = message.from_user.id
    username = message.from_user.username
    chat = message.chat

    # Определяем роль пользователя
    role = get_role(user_id, cursor)[0]


    selected_users = [me.id, user_id]

    # Запрашиваем тип чата (чат или канал)
    chat_type = await chat.ask("❓ Вы хотите создать чат или канал? (напишите 'чат' или 'канал')")
    while chat_type.text.lower() not in ["чат", "канал"]:
        await message.reply_text("⚠️ Пожалуйста, введите 'чат' или 'канал'.")
        chat_type = await chat.ask("❓ Вы хотите создать чат или канал? (напишите 'чат' или 'канал')")

    # Запрашиваем название чата/канала
    chat_title = await chat.ask("📝 Введите название чата/канала:")
    print(*selected_users)

    # Основной цикл добавления участников
    while True:
        search_query = await chat.ask(
            "🔍 Введите имя, фамилию или отчество участника\n"
            "(или /готово для завершения, /список для просмотра выбранных):"
        )

        if search_query.text.lower() == "/готово":
            if len(selected_users) > 1:  # Проверяем, что есть кто-то кроме создателя
                break
            await message.reply_text("⚠️ Вы не добавили ни одного участника!")
            continue

        if search_query.text.lower() == "/список":

            users_list = []
            for uname in selected_users:
                cursor.execute("SELECT last_name, first_name FROM users WHERE user_id = ?", (uname,))  # Изменено
                user = cursor.fetchone()
                users_list.append(f"• {user[0]} {user[1]}")
            await message.reply_text("📋 Выбранные участники:\n" + "\n".join(users_list))
            continue

        # Разбиваем ввод на отдельные слова
        search_terms = search_query.text.upper().split()

        # Создаем условия для поиска
        conditions = []
        params = []

        for term in search_terms:
            conditions.append("(last_name LIKE ? OR first_name LIKE ? OR patronymic LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])

        where_clause = " AND ".join(conditions)

        # Поиск пользователей в зависимости от роли
        if role in ["admin", "teacher"]:
            cursor.execute(
                f"SELECT user_id, last_name, first_name, patronymic FROM users WHERE {where_clause}",  # Изменено
                params
            )
        else:
            class_code = get_class_code(user_id, cursor)[0]
            cursor.execute(
                f"""SELECT u.user_id, u.last_name, u.first_name, u.patronymic
                    FROM users u JOIN class c ON u.user_id = c.student_id
                    WHERE c.class_code = ? AND ({where_clause})""",
                [class_code] + params
            )

        all_users = cursor.fetchall()

        if not all_users:
            await message.reply_text("🔎 Никого не найдено. Попробуйте изменить запрос.")
            continue

        # Пагинация
        page_size = 10
        total_pages = (len(all_users) + page_size - 1) // page_size
        current_page = 0

        while True:
            start_idx = current_page * page_size
            end_idx = start_idx + page_size
            users_page = all_users[start_idx:end_idx]

            # Формируем список найденных пользователей
            user_list = "\n".join([
                f"{i + 1}. {user[1]} {user[2]} {user[3] or ''}"
                for i, user in enumerate(users_page, start=start_idx)
            ])

            # Добавляем информацию о странице
            page_info = f"\n\n📄 Страница {current_page + 1} из {total_pages}"
            controls = "\n\n🔹 Команды:\n/далее - следующая страница\n/назад - предыдущая\n/выбрать [номер] - добавить участника\n/отмена - выйти из поиска"

            await message.reply_text(f"👥 Найдены пользователи:\n{user_list}{page_info}{controls}")

            # Ждем действия пользователя
            action = await chat.ask("↘️ Выберите действие:")
            action_text = action.text.lower()

            if action_text == "/далее":
                if current_page < total_pages - 1:
                    current_page += 1
                else:
                    await message.reply_text("ℹ️ Это последняя страница.")
            elif action_text == "/назад":
                if current_page > 0:
                    current_page -= 1
                else:
                    await message.reply_text("ℹ️ Это первая страница.")
            elif action_text.startswith("/выбрать"):
                try:
                    choice = int(action_text.split()[1]) - 1
                    if 0 <= choice < len(all_users):
                        selected_user = all_users[choice]
                        if selected_user[0] not in selected_users:
                            selected_users.append(selected_user[0])
                            await message.reply_text(f"✅ Добавлен: {selected_user[1]} {selected_user[2]}")
                        else:
                            await message.reply_text("⚠️ Этот пользователь уже добавлен!")
                        break
                    else:
                        await message.reply_text("❌ Неверный номер пользователя.")
                except (IndexError, ValueError):
                    await message.reply_text("❌ Формат: /выбрать [номер]")
            elif action_text == "/отмена":
                await message.reply_text("🔙 Поиск отменен.")
                break
            else:
                await message.reply_text("❌ Неизвестная команда. Используйте /далее, /назад, /выбрать или /отмена.")

    # Создаём чат/канал
    # if chat_type.text.lower() == "чат":
    #     try:
    #
    #         # Создаём группу (чат)
    #         created_chat = await client.create_supergroup(title=chat_title.text)
    #         for uname in selected_users:
    #             try:
    #                 await client.add_chat_members(created_chat.id, uname)
    #             except Exception as e:
    #                 print(f"Ошибка добавления {uname}: {str(e)}")
    #         await message.reply_text(
    #             f"✅ Чат '{chat_title.text}' успешно создан!\n"
    #             f"👥 Участников: {len(selected_users)}\n"
    #             f"🆔 ID чата: {created_chat.id}"
    #         )
    #
    #         # Добавляем запись в таблицу chats
    #         add_chat(created_chat.id, chat_title.text, "group", username)  # Изменено
    #     except Exception as e:
    #         await message.reply_text(f"❌ Ошибка при создании чата: {str(e)}")
    #         print(e)
    # else:
    #     try:
    #         # Создаём канал
    #         created_channel = await client.create_channel(
    #             title=chat_title.text,
    #             description=""
    #         )
    #
    #         # Создаем инвайт-ссылку с настройками
    #         invite_link = await client.create_chat_invite_link(
    #             chat_id=created_channel.id,
    #             name="Основная ссылка",
    #             creates_join_request=False
    #         )
    #
    #         for uname in selected_users:
    #             try:
    #                 await client.add_chat_members(created_channel.id, uname)
    #             except Exception as e:
    #                 print(f"Ошибка добавления {uname}: {str(e)}")
    #
    #         await message.reply_text(
    #             f"✅ Канал '{chat_title.text}' создан!\n\n"
    #             f"🔗 Ссылка для входа: {invite_link.invite_link}\n"
    #             f"👥 Участников: {len(selected_users)}\n"
    #             f"🆔 ID канала: {created_channel.id}"
    #         )
    #
    #         # Добавляем запись в таблицу chats
    #         add_chat(created_channel.id, chat_title.text, "channel", username)  # Изменено
    #     except Exception as e:
    #         await message.reply_text(f"❌ Ошибка создания канала: {str(e)}")

    if chat_type.text.lower() == "чат":
        try:
            # Создаём группу (чат)
            created_chat = await client.create_supergroup(title=chat_title.text)

            # Создаем инвайт-ссылку
            try:
                invite_link = await client.create_chat_invite_link(
                    chat_id=created_chat.id,
                    name="Основная ссылка",
                    creates_join_request=False
                )
                if not invite_link.invite_link:
                    raise Exception("Не удалось создать инвайт-ссылку")
            except Exception as e:
                await message.reply_text(f"❌ Ошибка создания инвайт-ссылки: {str(e)}")
                return

            # Добавляем участников и рассылаем ссылки
            success_count = 0
            failed_users = []

            for uname in selected_users[2:]:
                try:
                    # Добавляем в чат
                    await client.add_chat_members(created_chat.id, uname)

                    # Отправляем ссылку в ЛС
                    try:
                        await client.send_message(
                            uname,
                            f"🔗 Вас добавили в чат '{chat_title.text}'\n"
                            f"Присоединяйтесь: {invite_link.invite_link}"
                        )
                        success_count += 1
                    except Exception as e:
                        failed_users.append(f"{uname} (не отправлено сообщение)")
                except Exception as e:
                    failed_users.append(f"{uname} (не добавлен в чат)")
                    print(f"Ошибка с пользователем {uname}: {str(e)}")

            # Формируем отчет
            report_msg = (
                f"✅ Чат '{chat_title.text}' создан!\n"
                f"👥 Успешно добавлено: {success_count}/{len(selected_users)}\n"
                f"🆔 ID чата: {created_chat.id}\n"
                f"🔗 Ссылка: {invite_link.invite_link}"
            )

            if failed_users:
                report_msg += f"\n\n❌ Проблемы с:\n" + "\n".join(failed_users)

            await message.reply_text(report_msg)
            add_chat(created_chat.id, chat_title.text, "group", username)

        except Exception as e:
            await message.reply_text(f"❌ Ошибка при создании чата: {str(e)}")
            print(e)
    else:
        try:
            # Создаём канал
            created_channel = await client.create_channel(
                title=chat_title.text,
                description=""
            )

            # Создаем инвайт-ссылку
            try:
                invite_link = await client.create_chat_invite_link(
                    chat_id=created_channel.id,
                    name="Основная ссылка",
                    creates_join_request=False
                )
                if not invite_link.invite_link:
                    raise Exception("Не удалось создать инвайт-ссылку")
            except Exception as e:
                await message.reply_text(f"❌ Ошибка создания инвайт-ссылки: {str(e)}")
                return

            # Добавляем участников и рассылаем ссылки
            success_count = 0
            failed_users = []

            for uname in selected_users[2:]:
                try:
                    # Добавляем в канал
                    await client.add_chat_members(created_channel.id, uname)

                    # Отправляем ссылку в ЛС
                    try:
                        await client.send_message(
                            uname,
                            f"🔗 Вас добавили в канал '{chat_title.text}'\n"
                            f"Присоединяйтесь: {invite_link.invite_link}"
                        )
                        success_count += 1
                    except Exception as e:
                        failed_users.append(f"{uname} (не отправлено сообщение)")
                except Exception as e:
                    failed_users.append(f"{uname} (не добавлен в канал)")
                    print(f"Ошибка с пользователем {uname}: {str(e)}")

            # Формируем отчет
            report_msg = (
                f"✅ Канал '{chat_title.text}' создан!\n"
                f"👥 Успешно добавлено: {success_count}/{len(selected_users)}\n"
                f"🆔 ID канала: {created_channel.id}\n"
                f"🔗 Ссылка: {invite_link.invite_link}"
            )

            if failed_users:
                report_msg += f"\n\n❌ Проблемы с:\n" + "\n".join(failed_users)

            await message.reply_text(report_msg)
            add_chat(created_channel.id, chat_title.text, "channel", username)

        except Exception as e:
            await message.reply_text(f"❌ Ошибка создания канала: {str(e)}")
    cursor.close()
    connection.close()

@bot.on_message(filters.command("помощь") & filters.incoming)
async def help_command(client: Client, message: Message):
    connection, cursor = await create_connection()
    user_id = message.from_user.id

    # Определяем роль пользователя
    role = get_role(user_id, cursor)[0] if is_user_registered(user_id, cursor) else "unregistered"

    # Базовые команды для всех пользователей
    help_text = """
**Доступные команды:**
/начать - Начать работу с ботом.
/помощь - Показать это сообщение.
"""

    # Команды для администратора
    if role == "admin":
        help_text += """
**Команды администратора:**
/создатькласс - Создать новый класс.
/заявки - Просмотр и подтверждение заявок.
/создатьчат или /создатьканал - Создать чат или канал.

"""

    # Команды для учителя
    if role == "teacher":
        help_text += """
**Команды учителя:**
/создатькласс - Создать новый класс.
/заявки - Просмотр и подтверждение заявок.
/создатьчат или /создатьканал - Создать чат или канал.
/проверитьтест - Начать проверку тестов.
/создатьшаблонтеста - Создать шаблон теста.
"""

    # Команды для ученика и родителя
    if role in ["student", "parent"]:
        help_text += """
**Команды ученика/родителя:**
/создатьчат или /создатьканал - Создать чат или канал.

"""

    # Если пользователь не зарегистрирован
    if role == "unregistered":
        help_text += """
**Для регистрации используйте одну из команд:**
/администратор - Зарегистрироваться как администратор.
/учитель - Зарегистрироваться как учитель.
/ученик - Зарегистрироваться как ученик.
/родитель - Зарегистрироваться как родитель.
"""

    await message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    cursor.close()
    connection.close()


@bot.on_message(filters.command("заявки") & filters.incoming & active_user)
async def verf(client: Client, message: Message):
    connection, cursor = await create_connection()
    id_user = message.from_user.id
    chat = message.chat
    role = get_role(id_user, cursor)[0]
    me = await client.get_me()
    if chat.id == me.id:
        request = get_request_by_role('admin', cursor)
        if request:
            await message.reply_text(f"""Заявка №{request[0]}

        ФИО\t {get_full_name(request[1], cursor)}
        Номер телефона\t {get_number_phone(request[1], cursor)[0]}
        """)
        else:
            await message.reply_text("Заявок нет!")
            return False

    elif role == 'admin':
        request = get_request_by_role('teacher', cursor)
        if request:
            await message.reply_text(f"""Заявка №{request[0]}

ФИО\t {get_full_name(request[1], cursor)}
Номер телефона\t {get_number_phone(request[1], cursor)[0]}
""")
        else:
            await message.reply_text("Заявок нет!")
            return False
    elif role == 'teacher':
        request = get_request_by_role('parent', cursor) or get_request_by_role('student', cursor)
        if request:
            await message.reply_text(f"""Заявка №{request[0]}

ФИО\t {get_full_name(request[1], cursor)}
Номер телефона\t {get_number_phone(request[1], cursor)[0]}
        """)
        else:
            await message.reply_text("Заявок нет!")
            return False

    delete_request(request[0], cursor, connection)
    result = await chat.ask('Принять или Отклонить?')
    while result.text.upper() not in ("ПРИНЯТЬ", "ОТКЛОНИТЬ"):
        result = await chat.ask('Принять или Отклонить?')

    if result.text.upper() == "ПРИНЯТЬ":
        activate_user(request[1], cursor, connection)
        await client.send_message(chat_id=request[1], text='Ваша заявка одобрена!')
    else:
        await client.send_message(chat_id=request[1], text='Ваша заявка отклонена!')


@bot.on_message(filters.command("отмена") & filters.incoming)
async def cancel_command(client: Client, message: Message):
    # Проверяем, ожидает ли пользователь отправки файла
    if user_states.get(message.from_user.id) is not None:
        # Сбрасываем состояние пользователя
        user_states[message.from_user.id] = None
        await message.reply_text("Действие отменено.")
    else:
        await message.reply_text("Нет активных действий для отмены.")


@bot.on_message(filters.command("создатьшаблонтеста") & filters.incoming)
async def generate_template_command(client: Client, message: Message):
    # Запрашиваем параметры у пользователя
    try:
        # Запрашиваем количество вопросов
        question_count_msg = await message.chat.ask("Введите количество вопросов:")
        question_count = int(question_count_msg.text)

        # Запрашиваем количество вариантов ответов
        option_count_msg = await message.chat.ask("Введите количество вариантов ответов:")
        option_count = int(option_count_msg.text)

        # Запрашиваем количество колонок
        columns_msg = await message.chat.ask("Введите количество колонок:")
        columns = int(columns_msg.text)

        # Генерируем изображение
        image_array = generate_template(question_count=question_count, option_count=option_count, columns=columns)

        # Преобразуем numpy.array в изображение
        image = Image.fromarray(image_array)

        # Сохраняем изображение в байтовый поток
        image_bytes = BytesIO()
        image.save(image_bytes, format="PNG")
        image_bytes.seek(0)

        # Отправляем изображение как документ (без сжатия)
        await client.send_document(
            chat_id=message.chat.id,
            document=image_bytes,
            file_name="template.png",  # Имя файла
            caption="Ваше сгенерированное изображение (без сжатия)!"
        )
    except ValueError:
        # Если пользователь ввел нечисловые данные
        await message.reply_text("Ошибка: все параметры должны быть числами. Попробуйте снова.")
    except Exception as e:
        # Обработка других ошибок
        await message.reply_text(f"Произошла ошибка: {e}")


@bot.on_message(filters.command("распознатьтест") & filters.incoming)
async def check_test_command(client: Client, message: Message):
    # Устанавливаем состояние "ожидание фото" для пользователя

    user_states[message.from_user.id] = "waiting_for_test"

    # Просим пользователя отправить фото как файл
    await message.reply_text(
        "Пожалуйста, отправьте фото своего теста как файл (без сжатия).\n"
        "Чтобы отменить, введите /отмена."
    )


@bot.on_message(filters.document & filters.incoming)
async def handle_document(client: Client, message: Message):
    # Проверяем, ожидает ли пользователь отправки фото

    if user_states.get(message.from_user.id) == "waiting_for_test":
        # Проверяем, является ли документ фото (по MIME-типу)
        if message.document.mime_type.startswith("image/"):
            # Скачиваем файл на диск
            file_byte = BytesIO()
            file_path = await client.download_media(message, in_memory=True)
            file_byte.seek(0)

            # Открываем изображение с помощью Pillow
            image = Image.open(file_path)
            image_array = np.array(image)

            # Передаем изображение в функцию checkTest
            result = checkTest(image_array)

            # Отправляем результат пользователю
            user_states[message.from_user.id] = result
            await message.reply_text(f"Результат проверки: {result}")

        user_states.pop(message.from_user.id, None)
    elif user_states.get(message.from_user.id) == "waiting_for_self_test":
        # Проверяем, является ли документ фото (по MIME-типу)
        if message.document.mime_type.startswith("image/"):
            # Скачиваем файл на диск
            file_byte = BytesIO()
            file_path = await client.download_media(message, in_memory=True)
            file_byte.seek(0)

            # Открываем изображение с помощью Pillow
            image = Image.open(file_path)
            image_array = np.array(image)

            # Передаем изображение в функцию checkTest
            result = checkTest(image_array)
            teacher_results[message.from_user.id] = result

            # Отправляем результат пользователю

            await message.reply_text(f"Результат проверки: {result}")
            await message.reply_text(f"Отправьте фото теста ученика без сжатия (файлом)\n"
                                     "Для прекращения /отмена")

        user_states[message.from_user.id] = "waiting_for_student_test"
    elif user_states.get(message.from_user.id) == "waiting_for_student_test":
        # Проверяем, является ли документ фото (по MIME-типу)
        if message.document.mime_type.startswith("image/"):
            # Скачиваем файл на диск
            file_byte = BytesIO()
            file_path = await client.download_media(message, in_memory=True)
            file_byte.seek(0)

            # Открываем изображение с помощью Pillow
            image = Image.open(file_path)
            image_array = np.array(image)

            # Передаем изображение в функцию checkTest
            student_result = checkTest(image_array)
            print(student_result)
            # Сравниваем результаты
            correct_answers = 0
            wrong_questions = []
            for i, (teacher_ans, student_ans) in enumerate(zip(teacher_results[message.from_user.id], student_result)):
                if teacher_ans == student_ans:
                    correct_answers += 1
                else:
                    wrong_questions.append(i + 1)  # Нумерация заданий с 1

            # Отправляем результат пользователю

            await message.reply_text(f"Результат проверки: \n"
                                     f"Верных заданий {correct_answers} из {len(student_result)}\n"
                                     f"Ошибки в следующих заданиях:{wrong_questions}"
                                     )
            await message.reply_text(f"Отправьте фото теста ученика без сжатия (файлом)\n"
                                     "Для прекращения /отмена")

        user_states[message.from_user.id] = "waiting_for_student_test"
    else:
        # Если состояние не установлено, игнорируем
        return


@bot.on_message(filters.command("проверитьтест") & filters.incoming)
async def start_check_command(client: Client, message: Message):
    """
    Основная функция для проверки тестов.
    """
    user_id = message.from_user.id

    # Проверяем, является ли пользователь учителем или администратором
    connection, cursor = await create_connection()
    if not (is_teacher(user_id, cursor) or is_admin(user_id, cursor)):
        await message.reply_text("У вас нет прав для выполнения этой команды.")
        return

    user_states[message.from_user.id] = "waiting_for_self_test"

    # Просим учителя отправить фото его теста
    await message.reply_text(
        "Пожалуйста, отправьте фото вашего теста (без сжатия).\n"
        "Чтобы выйти, введите /отмена.\n."
    )


bot.run()
