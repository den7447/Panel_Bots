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
BASE_FOLDER = os.path.join(os.path.dirname(__file__))
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
    
# --- Логика файлового менеджера ---
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

# --- Логика бэкапов ---
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

# --- Прочие маршруты (без изменений) ---
# ... (Остальной код, как в предыдущей версии)
#   get_bot_list
#   read_file
#   run_bot
#   stop_bot
#   bot_logs
#   send_command
#   get_log_list
#   get_log_content
#   add_bot
#   get_all_users_status
#   add_user
#   delete_user
#   get_user_logs_list
#   get_user_log_content
#   get_all_bot_logs_list
#   admin_chat
#   send_chat_message
#   get_chat_history
#   ...

if __name__ == '__main__':
    if not os.path.exists(LOGS_FOLDER):
        os.makedirs(LOGS_FOLDER)
    if not os.path.exists(BACKUPS_FOLDER):
        os.makedirs(BACKUPS_FOLDER)
    create_initial_user()
    app.run(host='0.0.0.0', debug=True)