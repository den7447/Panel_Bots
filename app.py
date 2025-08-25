import os
import json
import subprocess
import threading
import queue
import time
import shutil
import io
from flask import Flask, render_template, jsonify, request, Response, session, redirect, url_for, g
from datetime import datetime, timedelta

# Настройки приложения и секретный ключ
app = Flask(__name__)
# Замените 'your_secret_key_here' на длинную, случайную строку
app.secret_key = 'your_secret_key_here' 

# Пути к папкам
BASE_FOLDER = os.path.dirname(__file__)
BOTS_FOLDER = os.path.join(BASE_FOLDER, 'bots')
LOGS_FOLDER = os.path.join(BASE_FOLDER, 'logs')
USERS_FILE = os.path.join(BASE_FOLDER, 'users.json')
USER_LOGS_FILE = os.path.join(BASE_FOLDER, 'user_logs.json')
ADMIN_CHAT_FILE = os.path.join(BASE_FOLDER, 'admin_chat.json')
BACKUPS_FOLDER = os.path.join(BASE_FOLDER, 'backups')
TEMP_BACKUP_FOLDER = os.path.join(BASE_FOLDER, 'temp_backup')

# Глобальные словари для отслеживания процессов, очередей и ввода
processes = {}
bot_queues = {}
log_queues = {}
modified_files = {} # Буфер для измененных файлов

# Глобальный словарь для отслеживания активных сессий и их IP-адресов
active_sessions = {}
session_lock = threading.Lock()

# Очередь для сообщений административного чата
chat_queue = queue.Queue()

# --- Вспомогательные функции ---
def create_initial_user():
    """Создает файл users.json с тех.админом по умолчанию, если он не существует."""
    if not os.path.exists(USERS_FILE):
        initial_users = {
            "tech_admin": {
                "password": "tech_admin_password",
                "rank": "tech_admin",
                "last_active": None,
                "ip_address": None
            }
        }
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(initial_users, f, indent=4, ensure_ascii=False)
        print(f"INFO: Файл '{USERS_FILE}' создан с пользователем по умолчанию 'tech_admin'.")

def get_user_data(username):
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            users = json.load(f)
            return users.get(username)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None
        
def load_all_users():
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    
def save_all_users(users):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"ERROR: Не удалось сохранить файл пользователей: {e}")

def get_user_rank():
    if 'username' in session:
        user_data = get_user_data(session['username'])
        if user_data:
            return user_data.get('rank')
    return None

def is_valid_path(path, base_path):
    abs_path = os.path.abspath(os.path.join(base_path, path))
    return abs_path.startswith(os.path.abspath(base_path))

def get_safe_path(path):
    base_folder_abs = os.path.abspath(BASE_FOLDER)
    path_abs = os.path.abspath(os.path.join(base_folder_abs, path))
    
    if not path_abs.startswith(base_folder_abs):
        return None
    return path_abs

def get_safe_log_path(filename):
    logs_folder_abs = os.path.abspath(LOGS_FOLDER)
    file_path_abs = os.path.abspath(os.path.join(logs_folder_abs, filename))
    if not file_path_abs.startswith(logs_folder_abs):
        return None
    return file_path_abs

def log_user_action(username, action, details):
    """Логирует действия пользователя в user_logs.json."""
    try:
        if not os.path.exists(USER_LOGS_FILE):
            with open(USER_LOGS_FILE, 'w', encoding='utf-8') as f:
                json.dump({}, f)
        
        with open(USER_LOGS_FILE, 'r+', encoding='utf-8') as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = {}
            
            if username not in logs:
                logs[username] = []
            
            logs[username].append({
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "details": details,
                "ip_address": request.remote_addr
            })
            
            f.seek(0)
            json.dump(logs, f, indent=4, ensure_ascii=False)
            f.truncate()
    except Exception as e:
        print(f"ERROR: Ошибка при логировании действия пользователя: {str(e)}")

def get_all_users_status():
    """Возвращает список всех пользователей с их статусом и последней активностью."""
    users = load_all_users()
    online_users = {data['username'] for data in active_sessions.values()}
    current_user_rank = get_user_rank()
    
    user_list = []
    for username, data in users.items():
        status = 'Онлайн' if username in online_users else 'Офлайн'
        
        if current_user_rank == 'tech_admin':
            ip_address = data.get('ip_address')
        else:
            ip_address = 'Для этого вам нужен ранг тех_админ'
            
        user_list.append({
            'username': username,
            'rank': data.get('rank', 'user'),
            'status': status,
            'last_active': data.get('last_active'),
            'ip_address': ip_address
        })
    return user_list

def create_backup(backup_name):
    """Создает резервную копию всей папки сайта."""
    if not os.path.exists(BACKUPS_FOLDER):
        os.makedirs(BACKUPS_FOLDER)
    
    # Игнорируем папки с бэкапами и логами
    ignore_list = shutil.ignore_patterns('backups', 'logs', 'temp_backup')
    
    try:
        shutil.copytree(BASE_FOLDER, os.path.join(BACKUPS_FOLDER, backup_name), ignore=ignore_list)
        return True
    except Exception as e:
        print(f"ERROR: Не удалось создать бэкап: {e}")
        return False

def restore_backup(backup_name):
    """Восстанавливает сайт из резервной копии."""
    backup_path = os.path.join(BACKUPS_FOLDER, backup_name)
    if not os.path.exists(backup_path):
        return False
        
    try:
        # Очищаем текущую папку
        for item in os.listdir(BASE_FOLDER):
            item_path = os.path.join(BASE_FOLDER, item)
            if item not in ['backups', 'logs', 'temp_backup', 'run.sh', 'main.py']: # Исключаем важные файлы и папки
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
        
        # Копируем файлы из бэкапа
        for item in os.listdir(backup_path):
            item_path = os.path.join(backup_path, item)
            if os.path.isdir(item_path):
                shutil.copytree(item_path, os.path.join(BASE_FOLDER, item))
            else:
                shutil.copy2(item_path, BASE_FOLDER)
        return True
    except Exception as e:
        print(f"ERROR: Не удалось восстановить бэкап: {e}")
        return False

# Проверка на режим восстановления при запуске
def check_for_recovery_mode():
    if os.path.exists(os.path.join(BASE_FOLDER, '.recovery_mode')):
        return True
    return False

# --- Middleware для отслеживания сессий и логирования ---
@app.before_request
def track_session_and_log():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Запрос от {request.remote_addr} на {request.path}")
    
    if 'logged_in' in session and session['logged_in']:
        username = session.get('username')
        rank = session.get('rank')
        
        with session_lock:
            session_id = session.sid if hasattr(session, 'sid') else f'temp_{username}_{request.remote_addr}'
            
            active_sessions[session_id] = {
                'username': username,
                'rank': rank,
                'ip_address': request.remote_addr,
                'last_active': datetime.now().isoformat()
            }
            users = load_all_users()
            if username in users:
                users[username]['last_active'] = datetime.now().isoformat()
                users[username]['ip_address'] = request.remote_addr
                save_all_users(users)


@app.teardown_request
def remove_session(exception=None):
    pass

# --- Маршруты ---
@app.route('/')
def index():
    if check_for_recovery_mode():
        return render_template('recovery.html')
    
    if 'logged_in' in session and session['logged_in']:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    if check_for_recovery_mode():
        return jsonify({'status': 'error', 'message': 'Сайт находится в режиме восстановления. Доступ ограничен.'}), 403

    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user_data = get_user_data(username)
    
    if user_data and user_data['password'] == password:
        session['logged_in'] = True
        session['username'] = username
        session['rank'] = user_data['rank']
        log_user_action(username, "login", "Успешный вход в систему.")
        
        users = load_all_users()
        users[username]['last_active'] = datetime.now().isoformat()
        users[username]['ip_address'] = request.remote_addr
        save_all_users(users)

        print(f"INFO: Пользователь '{username}' успешно вошел в систему.")
        return jsonify({'status': 'success', 'message': 'Авторизация успешна!', 'redirect_url': url_for('dashboard')})
    else:
        log_user_action(username, "login_failed", "Неудачная попытка входа.")
        print(f"WARNING: Неудачная попытка входа от пользователя '{username}'.")
        return jsonify({'status': 'error', 'message': 'Неверное имя пользователя или пароль.'}), 401

@app.route('/dashboard')
def dashboard():
    if check_for_recovery_mode():
        return redirect(url_for('index'))
    
    if 'logged_in' in session and session['logged_in']:
        return render_template('dashboard.html', user_rank=session.get('rank', 'guest'), username=session.get('username', 'Guest'))
    return redirect(url_for('index'))

@app.route('/logout', methods=['POST'])
def logout():
    username = session.get('username', 'Неизвестный')
    log_user_action(username, "logout", "Вышел из системы.")
    print(f"INFO: Пользователь '{username}' вышел из системы.")
    with session_lock:
        if hasattr(session, 'sid') and session.sid in active_sessions:
            del active_sessions[session.sid]
        
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('rank', None)
    return jsonify({'status': 'success'})

@app.route('/get-bot-list', methods=['GET'])
def get_bot_list():
    if not session.get('logged_in'):
        return jsonify({'error': 'Не авторизован.'}), 401
    
    try:
        log_user_action(session.get('username'), "view_bot_list", "Просмотр списка ботов.")
        bot_list = []
        if not os.path.exists(BOTS_FOLDER):
            os.makedirs(BOTS_FOLDER)
            
        for name in os.listdir(BOTS_FOLDER):
            bot_path = os.path.join(BOTS_FOLDER, name)
            if os.path.isdir(bot_path):
                is_running = name in processes and processes[name].poll() is None
                bot_list.append({
                    'name': name,
                    'is_running': is_running
                })
        print(f"INFO: Пользователь '{session.get('username')}' запросил список ботов.")
        return jsonify({'status': 'success', 'bots': bot_list})
    except Exception as e:
        print(f"ERROR: Ошибка при получении списка ботов: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/read-file', methods=['POST'])
def read_file():
    if not session.get('logged_in') or get_user_rank() != 'tech_admin':
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    data = request.json
    filename = data.get('filename')
    current_path = data.get('path', '')
    
    file_path = get_safe_path(os.path.join(current_path, filename))
    
    if not file_path or not os.path.isfile(file_path):
        log_user_action(session.get('username'), "read_file_failed", f"Попытка чтения несуществующего файла: {file_path}")
        print(f"WARNING: Неудачная попытка чтения файла '{file_path}' от пользователя '{session.get('username')}'. Файл не найден.")
        return jsonify({'error': 'Файл не найден или небезопасный путь.'}), 404
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        log_user_action(session.get('username'), "read_file", f"Чтение файла: {file_path}")
        print(f"INFO: Пользователь '{session.get('username')}' прочитал файл '{file_path}'.")
        return jsonify({'content': content, 'filename': filename, 'path': current_path})
    except Exception as e:
        print(f"ERROR: Ошибка при чтении файла '{file_path}': {str(e)}")
        return jsonify({'error': f'Не удалось прочитать файл: {str(e)}'}), 500

@app.route('/get-file-list', methods=['POST'])
def get_file_list():
    if not session.get('logged_in') or get_user_rank() != 'tech_admin':
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    data = request.json
    current_path = data.get('path', '')
    
    safe_path = get_safe_path(current_path)
    
    if not safe_path or not os.path.isdir(safe_path):
        log_user_action(session.get('username'), "view_file_list_failed", f"Попытка просмотра несуществующей папки: {safe_path}")
        print(f"WARNING: Неудачная попытка получения списка файлов из '{safe_path}' от пользователя '{session.get('username')}'. Папка не найдена.")
        return jsonify({'error': 'Папка не найдена или небезопасный путь.'}), 404

    files = []
    for item in os.listdir(safe_path):
        item_path = os.path.join(safe_path, item)
        is_dir = os.path.isdir(item_path)
        # Исключаем папки с бэкапами и временными файлами, если они не являются частью текущего пути
        if item in ['backups', 'temp_backup', 'logs'] and os.path.abspath(item_path) != os.path.abspath(os.path.join(BASE_FOLDER, item)):
            continue
        files.append({
            'name': item,
            'is_dir': is_dir,
            'status': 'modified' if os.path.abspath(item_path) in modified_files else 'unmodified'
        })
    log_user_action(session.get('username'), "view_file_list", f"Просмотр файлов в папке: {safe_path}")
    print(f"INFO: Пользователь '{session.get('username')}' запросил список файлов из папки '{safe_path}'.")
    return jsonify(files)

@app.route('/save-file-to-buffer', methods=['POST'])
def save_file_to_buffer():
    if not session.get('logged_in') or get_user_rank() != 'tech_admin':
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    data = request.json
    filename = data.get('filename')
    content = data.get('content')
    current_path = data.get('path', '')
    
    file_path = get_safe_path(os.path.join(current_path, filename))
    
    if not file_path:
        return jsonify({'error': 'Небезопасный путь.'}), 400
    
    modified_files[file_path] = content
    return jsonify({'status': 'success', 'message': f'Изменения в файле "{filename}" сохранены в буфер. Нажмите "Применить изменения" для сохранения.'})

@app.route('/apply-changes', methods=['POST'])
def apply_changes():
    if not session.get('logged_in') or get_user_rank() != 'tech_admin':
        return jsonify({'error': 'Недостаточно прав.'}), 403

    if not modified_files:
        return jsonify({'status': 'error', 'message': 'Нет изменений для применения.'})

    # Создаем временный бэкап перед применением
    temp_backup_name = f"temp_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    if not create_backup(temp_backup_name):
        return jsonify({'status': 'error', 'message': 'Не удалось создать временный бэкап. Изменения не применены.'})
    
    try:
        for file_path, content in modified_files.items():
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        
        modified_files.clear()
        
        log_user_action(session.get('username'), "apply_changes", "Применены отложенные изменения.")
        return jsonify({'status': 'success', 'message': 'Изменения успешно применены.'})
    except Exception as e:
        print(f"ERROR: Ошибка при применении изменений: {e}")
        # В случае ошибки, запускаем режим восстановления
        with open(os.path.join(BASE_FOLDER, '.recovery_mode'), 'w') as f:
            f.write(temp_backup_name)
        log_user_action(session.get('username'), "system_failure", "Ошибка при применении изменений. Система переведена в режим восстановления.")
        return jsonify({'status': 'error', 'message': f'Ошибка при применении изменений. Сайт переведен в режим восстановления. Ошибка: {e}'}), 500

@app.route('/get-modified-files', methods=['GET'])
def get_modified_files():
    if not session.get('logged_in') or get_user_rank() != 'tech_admin':
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    return jsonify({'files': list(modified_files.keys())})

@app.route('/run-bot', methods=['POST'])
def run_bot():
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'admin', 'owner']:
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    data = request.json
    bot_name = data.get('bot_name')
    if not bot_name:
        return jsonify({'error': 'Имя бота не указано.'}), 400
    
    if bot_name in processes and processes[bot_name].poll() is None:
        return jsonify({'status': 'error', 'message': f'Бот "{bot_name}" уже запущен.'}), 409

    bot_path = os.path.join(BOTS_FOLDER, bot_name, 'main.py')
    if not os.path.exists(bot_path):
        return jsonify({'status': 'error', 'message': f'Файл main.py не найден для бота "{bot_name}".'}), 404
        
    try:
        q_stdout = queue.Queue()
        q_stderr = queue.Queue()
        
        bot_logs_dir = os.path.join(LOGS_FOLDER, bot_name)
        if not os.path.exists(bot_logs_dir):
            os.makedirs(bot_logs_dir)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"{bot_name}_{timestamp}.log"
        log_filepath = os.path.join(bot_logs_dir, log_filename)
        log_file = open(log_filepath, 'a', encoding='utf-8')
        
        process = subprocess.Popen(
            ['python', bot_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        processes[bot_name] = process
        bot_queues[bot_name] = q_stdout
        log_queues[bot_name] = q_stderr
        
        def read_and_log_stream(stream, q, log_f):
            while True:
                line_bytes = stream.readline()
                if not line_bytes:
                    break
                try:
                    decoded_line = line_bytes.decode('utf-8').strip()
                except UnicodeDecodeError:
                    try:
                        decoded_line = line_bytes.decode('cp1251').strip()
                    except UnicodeDecodeError:
                        decoded_line = line_bytes.decode('utf-8', 'replace').strip()
                
                q.put(decoded_line + '\n')
                log_f.write(decoded_line + '\n')
                log_f.flush()
                
                print(f"[БОТ {bot_name}]: {decoded_line}")
            stream.close()
            
        threading.Thread(target=read_and_log_stream, args=(process.stdout, q_stdout, log_file), daemon=True).start()
        threading.Thread(target=read_and_log_stream, args=(process.stderr, q_stderr, log_file), daemon=True).start()
        
        log_user_action(session.get('username'), "run_bot", f"Запустил бота: {bot_name}")
        print(f"INFO: Пользователь '{session.get('username')}' запустил бота '{bot_name}'.")
        return jsonify({'status': 'success', 'message': f'Бот "{bot_name}" запущен.'})
    except Exception as e:
        print(f"ERROR: Ошибка при запуске бота '{bot_name}': {str(e)}")
        return jsonify({'status': 'error', 'message': f'Не удалось запустить бота: {str(e)}'}), 500

@app.route('/stop-bot', methods=['POST'])
def stop_bot():
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'admin', 'owner']:
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    data = request.json
    bot_name = data.get('bot_name')
    
    if bot_name in processes and processes[bot_name].poll() is None:
        processes[bot_name].stdin.close()
        processes[bot_name].terminate()
        processes[bot_name].wait(timeout=5)
        if processes[bot_name].poll() is None:
            processes[bot_name].kill()
        del processes[bot_name]
        log_user_action(session.get('username'), "stop_bot", f"Остановил бота: {bot_name}")
        print(f"INFO: Пользователь '{session.get('username')}' остановил бота '{bot_name}'.")
        return jsonify({'status': 'success', 'message': f'Бот "{bot_name}" остановлен.'})
    else:
        return jsonify({'status': 'error', 'message': f'Бот "{bot_name}" не запущен.'}), 404

@app.route('/bot-logs/<bot_name>')
def stream(bot_name):
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'admin', 'owner']:
        return Response('Не авторизован', status=401)

    log_user_action(session.get('username'), "view_bot_console", f"Просмотр консоли бота: {bot_name}")
    q = bot_queues.get(bot_name)
    if not q:
        return Response(f'Нет логов для бота "{bot_name}".', status=404)
        
    def generate():
        while True:
            try:
                line = q.get(timeout=1)
                yield f"data: {line}\n\n"
            except queue.Empty:
                if bot_name in processes and processes[bot_name].poll() is not None:
                    break
                continue
    return Response(generate(), mimetype='text/event-stream')

@app.route('/send-command', methods=['POST'])
def send_command():
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'owner']:
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    data = request.json
    bot_name = data.get('bot_name')
    command = data.get('command')
    
    if bot_name not in processes or processes[bot_name].poll() is not None:
        return jsonify({'status': 'error', 'message': f'Бот "{bot_name}" не запущен.'}), 404
        
    try:
        process = processes[bot_name]
        if process.stdin:
            log_user_action(session.get('username'), "send_command", f"Отправка команды '{command}' боту: {bot_name}")
            print(f"INFO: Пользователь '{session.get('username')}' отправил команду '{command}' боту '{bot_name}'.")
            process.stdin.write((command + '\n').encode('utf-8'))
            process.stdin.flush()
            return jsonify({'status': 'success', 'message': 'Команда отправлена.'})
        else:
            return jsonify({'status': 'error', 'message': 'Невозможно отправить команду. Процесс запущен без stdin.'}), 500
    except Exception as e:
        print(f"ERROR: Ошибка при отправке команды боту '{bot_name}': {str(e)}")
        return jsonify({'status': 'error', 'message': f'Ошибка при отправке команды: {str(e)}'}), 500

@app.route('/get-log-list/<bot_name>', methods=['GET'])
def get_log_list(bot_name):
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'owner']:
        return jsonify({'error': 'Не авторизован.'}), 401
    
    bot_logs_dir = os.path.join(LOGS_FOLDER, bot_name)
    if not os.path.exists(bot_logs_dir):
        return jsonify({'logs': []})
        
    logs = []
    for filename in os.listdir(bot_logs_dir):
        if filename.endswith(".log"):
            logs.append(filename)
    
    logs.sort(reverse=True)
    return jsonify({'logs': logs})

@app.route('/get-log-content/<bot_name>/<log_filename>', methods=['GET'])
def get_log_content(bot_name, log_filename):
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'owner']:
        return jsonify({'error': 'Не авторизован.'}), 401
    
    log_path = os.path.join(LOGS_FOLDER, bot_name, log_filename)
    safe_path = get_safe_log_path(os.path.join(bot_name, log_filename))
    
    if not safe_path or not os.path.exists(safe_path):
        return jsonify({'error': 'Файл лога не найден или небезопасный путь.'}), 404
    
    try:
        with open(safe_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': f'Не удалось прочитать файл: {str(e)}'}), 500

@app.route('/add-bot', methods=['POST'])
def add_bot():
    if not session.get('logged_in') or get_user_rank() != 'tech_admin':
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    data = request.json
    bot_name = data.get('bot_name')
    
    if not bot_name:
        return jsonify({'status': 'error', 'message': 'Имя бота не указано.'}), 400
    
    bot_path = os.path.join(BOTS_FOLDER, bot_name)
    if not is_valid_path(bot_path, BOTS_FOLDER):
         return jsonify({'status': 'error', 'message': 'Небезопасное имя бота.'}), 400
        
    try:
        os.makedirs(bot_path, exist_ok=False)
        default_main_py_content = """# Ваш основной код для бота Discord здесь.
# Замените этот текст на свой код.
print("Бот успешно запущен!")
"""
        with open(os.path.join(bot_path, 'main.py'), 'w', encoding='utf-8') as f:
            f.write(default_main_py_content)
        
        log_user_action(session.get('username'), "add_bot", f"Создал нового бота: {bot_name}")
        print(f"INFO: Пользователь '{session.get('username')}' создал новую папку для бота '{bot_name}'.")
        return jsonify({'status': 'success', 'message': f'Папка для бота "{bot_name}" создана. Добавьте код в файл main.py.'})
    except FileExistsError:
        print(f"WARNING: Неудачная попытка создания бота '{bot_name}'. Папка уже существует.")
        return jsonify({'status': 'error', 'message': f'Папка для бота "{bot_name}" уже существует.'}), 409
    except Exception as e:
        print(f"ERROR: Ошибка при создании бота '{bot_name}': {str(e)}")
        return jsonify({'status': 'error', 'message': f'Не удалось создать бота: {str(e)}'}), 500

@app.route('/get-all-users-status', methods=['GET'])
def get_all_users_route():
    if not session.get('logged_in') or get_user_rank() not in ['tech_admin', 'owner']:
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    users = get_all_users_status()
    return jsonify(users)

@app.route('/add-user', methods=['POST'])
def add_user():
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'owner']:
        return jsonify({'error': 'Недостаточно прав.'}), 403

    data = request.json
    username = data.get('username')
    password = data.get('password')
    rank = data.get('rank', 'admin')

    if current_rank == 'owner' and rank in ['tech_admin', 'owner']:
        return jsonify({'status': 'error', 'message': 'Недостаточно прав для создания пользователя с таким рангом.'}), 403
        
    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Имя пользователя и пароль обязательны.'}), 400

    users = load_all_users()
    if username in users:
        return jsonify({'status': 'error', 'message': f'Пользователь с именем "{username}" уже существует.'}), 409

    users[username] = {
        'password': password,
        'rank': rank,
        'last_active': None,
        'ip_address': None
    }
    try:
        save_all_users(users)
        log_user_action(session.get('username'), "add_user", f"Добавил нового пользователя: {username} с рангом {rank}")
        print(f"INFO: Пользователь '{session.get('username')}' добавил нового пользователя '{username}'.")
        return jsonify({'status': 'success', 'message': f'Пользователь "{username}" добавлен.'})
    except Exception as e:
        print(f"ERROR: Ошибка при добавлении пользователя '{username}': {str(e)}")
        return jsonify({'status': 'error', 'message': f'Ошибка при сохранении пользователя: {str(e)}'}), 500

@app.route('/delete-user', methods=['POST'])
def delete_user():
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank != 'tech_admin':
        return jsonify({'error': 'Недостаточно прав.'}), 403

    data = request.json
    username_to_delete = data.get('username')
    
    if not username_to_delete:
        return jsonify({'status': 'error', 'message': 'Имя пользователя не указано.'}), 400

    if username_to_delete == session.get('username'):
        return jsonify({'status': 'error', 'message': 'Вы не можете удалить свой собственный аккаунт.'}), 403

    users = load_all_users()
    if username_to_delete in users:
        del users[username_to_delete]
        try:
            save_all_users(users)
            log_user_action(session.get('username'), "delete_user", f"Удалил пользователя: {username_to_delete}")
            print(f"INFO: Пользователь '{session.get('username')}' удалил пользователя '{username_to_delete}'.")
            
            if os.path.exists(USER_LOGS_FILE):
                with open(USER_LOGS_FILE, 'r+', encoding='utf-8') as f:
                    try:
                        logs = json.load(f)
                    except json.JSONDecodeError:
                        logs = {}
                    if username_to_delete in logs:
                        del logs[username_to_delete]
                    f.seek(0)
                    json.dump(logs, f, indent=4, ensure_ascii=False)
                    f.truncate()

            return jsonify({'status': 'success', 'message': f'Пользователь "{username_to_delete}" удален.'})
        except Exception as e:
            print(f"ERROR: Ошибка при удалении пользователя '{username_to_delete}': {str(e)}")
            return jsonify({'status': 'error', 'message': f'Ошибка при удалении пользователя: {str(e)}'}), 500
    else:
        return jsonify({'status': 'error', 'message': 'Пользователь не найден.'}), 404

@app.route('/get-user-logs-list', methods=['GET'])
def get_user_logs_list():
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'owner']:
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    try:
        with open(USER_LOGS_FILE, 'r', encoding='utf-8') as f:
            logs = json.load(f)
            users_with_logs = list(logs.keys())
            return jsonify({'status': 'success', 'users': users_with_logs})
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({'status': 'success', 'users': []})
        
@app.route('/get-user-log-content/<username>', methods=['GET'])
def get_user_log_content(username):
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'owner']:
        return jsonify({'error': 'Недостаточно прав.'}), 403

    try:
        with open(USER_LOGS_FILE, 'r', encoding='utf-8') as f:
            logs = json.load(f)
            user_logs = logs.get(username, [])
            return jsonify({'status': 'success', 'logs': user_logs})
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({'status': 'success', 'logs': []})

@app.route('/get-all-bot-logs-list', methods=['GET'])
def get_all_bot_logs_list():
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'owner']:
        return jsonify({'error': 'Недостаточно прав.'}), 403
    
    bots_with_logs = []
    if os.path.exists(LOGS_FOLDER):
        for bot_name in os.listdir(LOGS_FOLDER):
            bot_path = os.path.join(LOGS_FOLDER, bot_name)
            if os.path.isdir(bot_path):
                bots_with_logs.append(bot_name)
    return jsonify({'status': 'success', 'bots': bots_with_logs})

@app.route('/create-manual-backup', methods=['POST'])
def create_manual_backup():
    if not session.get('logged_in') or get_user_rank() != 'tech_admin':
        return jsonify({'error': 'Недостаточно прав.'}), 403
        
    backup_name = f"manual_backup_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    if create_backup(backup_name):
        return jsonify({'status': 'success', 'message': f"Бэкап '{backup_name}' успешно создан."})
    else:
        return jsonify({'status': 'error', 'message': "Не удалось создать бэкап."}), 500

@app.route('/get-backups', methods=['GET'])
def get_backups():
    if not session.get('logged_in') or get_user_rank() != 'tech_admin':
        return jsonify({'error': 'Недостаточно прав.'}), 403
        
    backups = []
    if os.path.exists(BACKUPS_FOLDER):
        for name in os.listdir(BACKUPS_FOLDER):
            backups.append(name)
    return jsonify({'backups': sorted(backups, reverse=True)})
    
@app.route('/restore-backup', methods=['POST'])
def restore_backup_route():
    if not session.get('logged_in') or get_user_rank() != 'tech_admin':
        return jsonify({'error': 'Недостаточно прав.'}), 403
        
    data = request.json
    backup_name = data.get('backup_name')
    
    if restore_backup(backup_name):
        log_user_action(session.get('username'), "restore_backup", f"Восстановление из бэкапа: {backup_name}")
        return jsonify({'status': 'success', 'message': f"Сайт успешно восстановлен из бэкапа '{backup_name}'."})
    else:
        return jsonify({'status': 'error', 'message': "Не удалось восстановить бэкап."}), 500

@app.route('/recovery_mode', methods=['GET', 'POST'])
def recovery_mode():
    if not check_for_recovery_mode():
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        data = request.json
        backup_name = data.get('backup_name')
        if not backup_name:
            return jsonify({'status': 'error', 'message': 'Имя бэкапа не указано.'}), 400
            
        if restore_backup(backup_name):
            os.remove(os.path.join(BASE_FOLDER, '.recovery_mode'))
            return jsonify({'status': 'success', 'message': 'Сайт успешно восстановлен. Перезагрузите страницу.'})
        else:
            return jsonify({'status': 'error', 'message': 'Не удалось восстановить бэкап.'}), 500
            
    backups = []
    if os.path.exists(BACKUPS_FOLDER):
        backups = [f for f in os.listdir(BACKUPS_FOLDER) if os.path.isdir(os.path.join(BACKUPS_FOLDER, f))]
        
    return render_template('recovery.html', backups=sorted(backups, reverse=True))

def read_chat_history():
    """Считывает историю чата из файла."""
    try:
        with open(ADMIN_CHAT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def write_chat_history(history):
    """Записывает историю чата в файл."""
    with open(ADMIN_CHAT_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=4, ensure_ascii=False)

@app.route('/admin-chat')
def admin_chat():
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'admin', 'owner']:
        return jsonify({'error': 'Не авторизован.'}), 401
    
    def generate():
        while True:
            msg = chat_queue.get()
            yield f"data: {msg}\n\n"
            
    return Response(generate(), mimetype='text/event-stream')

@app.route('/send-chat-message', methods=['POST'])
def send_chat_message():
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'admin', 'owner']:
        return jsonify({'error': 'Не авторизован.'}), 401
    
    data = request.json
    message = data.get('message')
    username = session.get('username')
    rank = session.get('rank')
    
    if not message:
        return jsonify({'status': 'error', 'message': 'Сообщение не может быть пустым.'}), 400
    
    new_message = {
        'username': username,
        'rank': rank,
        'timestamp': datetime.now().isoformat(),
        'message': message
    }
    
    history = read_chat_history()
    history.append(new_message)
    write_chat_history(history)
    
    chat_queue.put(json.dumps(new_message))
    
    return jsonify({'status': 'success'})
    
@app.route('/get-chat-history', methods=['GET'])
def get_chat_history():
    current_rank = get_user_rank()
    if not session.get('logged_in') or current_rank not in ['tech_admin', 'admin', 'owner']:
        return jsonify({'error': 'Не авторизован.'}), 401
    
    history = read_chat_history()
    return jsonify(history)

if __name__ == '__main__':
    if not os.path.exists(BOTS_FOLDER):
        os.makedirs(BOTS_FOLDER)
    if not os.path.exists(LOGS_FOLDER):
        os.makedirs(LOGS_FOLDER)
    if not os.path.exists(BACKUPS_FOLDER):
        os.makedirs(BACKUPS_FOLDER)
    create_initial_user()
    app.run(host='0.0.0.0', debug=True)