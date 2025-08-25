document.addEventListener('DOMContentLoaded', function() {
    // --- Логика для входа ---
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            const messageDiv = document.getElementById('message');

            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });

                const data = await response.json();

                if (response.ok) {
                    if (data.redirect_url) {
                        window.location.href = data.redirect_url;
                    }
                } else {
                    if (messageDiv) {
                        messageDiv.textContent = data.message;
                        messageDiv.style.color = 'red';
                    }
                    document.getElementById('username').value = '';
                    document.getElementById('password').value = '';
                }
            } catch (error) {
                console.error('Ошибка:', error);
                if (messageDiv) {
                    messageDiv.textContent = 'Ошибка сервера. Попробуйте снова.';
                    messageDiv.style.color = 'red';
                }
            }
        });
    }

    // --- Логика для дашборда (панели управления) ---
    if (document.getElementById('logout-btn')) {
        const userRank = document.getElementById('user-rank').textContent.trim();
        
        document.getElementById('logout-btn').addEventListener('click', function() {
            fetch('/logout', {
                method: 'POST',
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    window.location.href = '/';
                }
            });
        });

        // Логика переключения вкладок
        window.openTab = function(evt, tabName) {
            var i, tabcontent, tabbuttons;
            tabcontent = document.getElementsByClassName("tab-content");
            for (i = 0; i < tabcontent.length; i++) {
                tabcontent[i].style.display = "none";
            }
            tabbuttons = document.getElementsByClassName("tab-button");
            for (i = 0; i < tabbuttons.length; i++) {
                tabbuttons[i].className = tabbuttons[i].className.replace(" active", "");
            }
            document.getElementById(tabName).style.display = "block";
            evt.currentTarget.className += " active";

            // Загрузка данных при открытии вкладок
            if (tabName === 'admins-tab') {
                loadAllAdmins();
            } else if (tabName === 'file-manager') {
                loadFileTree('');
                loadModifiedFilesList();
            } else if (tabName === 'backups') {
                loadBackupsList();
            }
        }
        
        loadBotList();
        document.getElementById('bot-management').style.display = 'block';
        
        // --- Логика для вкладки "Управление ботами" ---
        function loadBotList() {
            fetch('/get-bot-list')
                .then(response => response.json())
                .then(data => {
                    const botList = document.getElementById('bot-list');
                    botList.innerHTML = '';
                    if (data.bots && data.bots.length > 0) {
                        data.bots.forEach(bot => {
                            const botDiv = document.createElement('div');
                            botDiv.className = 'bot-item';
                            let actionsHtml = `<button onclick="toggleBot('${bot.name}', ${bot.is_running})">${bot.is_running ? 'Остановить' : 'Запустить'}</button>`;
                            
                            if (userRank === 'tech_admin' || userRank === 'admin' || userRank === 'owner') {
                                actionsHtml += `<button onclick="openConsole('${bot.name}')">Консоль</button>`;
                            }
                            
                            botDiv.innerHTML = `
                                <span>${bot.name}</span>
                                <span class="status ${bot.is_running ? 'running' : 'stopped'}">
                                    ${bot.is_running ? 'Запущен' : 'Остановлен'}
                                </span>
                                <div class="bot-actions">
                                    ${actionsHtml}
                                </div>
                            `;
                            botList.appendChild(botDiv);
                        });
                    } else {
                        botList.innerHTML = 'Нет доступных ботов.';
                    }
                })
                .catch(error => console.error('Ошибка при загрузке списка ботов:', error));
        }

        window.toggleBot = function(botName, isRunning) {
            const action = isRunning ? 'stop' : 'run';
            fetch(`/${action}-bot`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bot_name: botName })
            })
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                loadBotList();
            });
        }

        window.addBot = function() {
            const botName = document.getElementById('new-bot-name').value;
            if (botName) {
                fetch('/add-bot', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ bot_name: botName })
                })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    loadBotList();
                });
            }
        }

        // --- Логика для консоли ---
        window.openConsole = function(botName) {
            const consoleContainer = document.getElementById('console-container');
            const consoleOutput = document.getElementById('console-output');
            const consoleBotName = document.getElementById('console-bot-name');
            const consoleInputArea = document.getElementById('console-input-area');
            
            consoleBotName.textContent = botName;
            consoleOutput.textContent = '';
            
            const eventSource = new EventSource(`/bot-logs/${botName}`);
            
            eventSource.onmessage = function(event) {
                consoleOutput.textContent += event.data;
                consoleOutput.scrollTop = consoleOutput.scrollHeight; // Прокрутка вниз
            };
            
            // Если у пользователя ранг тех.админ, добавляем поле ввода для команд
            if (userRank === 'tech_admin' || userRank === 'owner') {
                if (!document.getElementById('console-input')) {
                    const input = document.createElement('input');
                    input.type = 'text';
                    input.id = 'console-input';
                    input.placeholder = 'Введите команду...';
                    input.addEventListener('keydown', function(e) {
                        if (e.key === 'Enter') {
                            sendCommand(botName);
                        }
                    });
                    const button = document.createElement('button');
                    button.textContent = 'Отправить';
                    button.onclick = () => sendCommand(botName);
                    
                    consoleInputArea.appendChild(input);
                    consoleInputArea.appendChild(button);
                }
            } else {
                consoleInputArea.innerHTML = '';
            }

            consoleContainer.classList.remove('hidden');
        };

        window.closeConsole = function() {
            const consoleContainer = document.getElementById('console-container');
            const eventSource = new EventSource('/bot-logs/dummy'); // Заглушка, чтобы отключить
            eventSource.close();
            consoleContainer.classList.add('hidden');
        };

        window.sendCommand = function(botName) {
            const commandInput = document.getElementById('console-input');
            const command = commandInput.value;
            if (!command) return;
            
            fetch('/send-command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bot_name: botName, command: command })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status !== 'success') {
                    alert('Ошибка: ' + data.message);
                }
                commandInput.value = '';
            });
        };
        
        // --- Логика для файлового менеджера ---
        let currentPath = '';

        window.loadFileTree = function(path = '') {
            currentPath = path;
            const displayPath = path === '' ? '/' : '/' + path;
            document.getElementById('current-path').textContent = displayPath;
            fetch('/get-file-list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path })
            })
            .then(response => response.json())
            .then(data => {
                const fileList = document.getElementById('file-list');
                fileList.innerHTML = '';
                if (data.error) {
                     fileList.innerHTML = `<li style="color: red;">${data.error}</li>`;
                     return;
                }
                
                // Добавляем ссылку на родительскую папку
                if (path !== '') {
                    const parentItem = document.createElement('li');
                    parentItem.className = 'folder';
                    parentItem.innerHTML = `<span onclick="goBack()">..</span>`;
                    fileList.appendChild(parentItem);
                }
                
                data.forEach(item => {
                    const listItem = document.createElement('li');
                    if (item.is_dir) {
                        listItem.className = 'folder';
                        listItem.innerHTML = `<span onclick="loadFileTree('${path}/${item.name}')">${item.name}/</span>`;
                    } else {
                        listItem.className = 'file';
                        listItem.innerHTML = `<span onclick="openFile('${item.name}')">${item.name}</span>`;
                        if (item.status === 'modified') {
                            listItem.classList.add('modified');
                        }
                    }
                    fileList.appendChild(listItem);
                });
            });
        };

        window.openFile = function(filename) {
            fetch('/read-file', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: filename, path: currentPath })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    alert('Ошибка: ' + data.error);
                    return;
                }
                document.getElementById('current-file-name').textContent = data.filename;
                document.getElementById('file-content-editor').value = data.content;
            });
        };

        window.saveFileToBuffer = function() {
            const filename = document.getElementById('current-file-name').textContent;
            const content = document.getElementById('file-content-editor').value;
            if (!filename) {
                alert('Сначала выберите файл.');
                return;
            }
            fetch('/save-file-to-buffer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename: filename, content: content, path: currentPath })
            })
            .then(response => response.json())
            .then(data => {
                alert(data.message);
                if (data.status === 'success') {
                    loadFileTree(currentPath);
                    loadModifiedFilesList();
                }
            });
        };
        
        window.applyChanges = function() {
            if (confirm('Вы уверены, что хотите применить все изменения?')) {
                fetch('/apply-changes', {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    if (data.status === 'success') {
                        loadFileTree(currentPath);
                        loadModifiedFilesList();
                    } else {
                        // Если сайт перешел в режим восстановления, перенаправляем пользователя
                        if (data.message.includes('режим восстановления')) {
                            window.location.href = '/';
                        }
                    }
                });
            }
        };
        
        function loadModifiedFilesList() {
            fetch('/get-modified-files')
                .then(response => response.json())
                .then(data => {
                    const list = document.getElementById('modified-files-list');
                    list.innerHTML = '';
                    if (data.files && data.files.length > 0) {
                        data.files.forEach(file => {
                            const li = document.createElement('li');
                            li.textContent = file;
                            list.appendChild(li);
                        });
                    } else {
                        list.innerHTML = '<li>Нет измененных файлов в буфере.</li>';
                    }
                });
        }

        window.goBack = function() {
            const pathParts = currentPath.split('/').filter(p => p !== '');
            pathParts.pop();
            const newPath = pathParts.join('/');
            loadFileTree(newPath);
        };
        
        // --- Логика для бэкапов ---
        window.createManualBackup = function() {
            if (confirm('Создать новую резервную копию? Это может занять несколько секунд.')) {
                fetch('/create-manual-backup', {
                    method: 'POST'
                })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    if (data.status === 'success') {
                        loadBackupsList();
                    }
                });
            }
        };
        
        function loadBackupsList() {
            fetch('/get-backups')
                .then(response => response.json())
                .then(data => {
                    const list = document.getElementById('backups-list');
                    list.innerHTML = '';
                    if (data.backups && data.backups.length > 0) {
                        data.backups.forEach(backup => {
                            const li = document.createElement('li');
                            li.textContent = backup;
                            li.innerHTML = `<span>${backup}</span> <button onclick="restoreBackup('${backup}')">Восстановить</button>`;
                            list.appendChild(li);
                        });
                    } else {
                        list.innerHTML = '<li>Нет доступных бэкапов.</li>';
                    }
                });
        }
        
        window.restoreBackup = function(backupName) {
            if (confirm(`Вы уверены, что хотите восстановить сайт из бэкапа "${backupName}"? Все текущие файлы будут заменены.`)) {
                fetch('/restore-backup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ backup_name: backupName })
                })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    if (data.status === 'success') {
                        // Очищаем буфер измененных файлов после восстановления
                        fetch('/get-modified-files').then(res => res.json()).then(d => {
                             d.files.forEach(f => modified_files[f] = null);
                             loadModifiedFilesList();
                        });
                        loadFileTree(''); // Обновляем файловый менеджер
                    }
                });
            }
        };

        // --- Остальные функции ---
        window.loadAllAdmins = function() {
            fetch('/get-all-users-status')
                .then(response => response.json())
                .then(data => {
                    const tableBody = document.querySelector('#all-admins-table tbody');
                    tableBody.innerHTML = '';
                    data.forEach(user => {
                        const row = tableBody.insertRow();
                        row.innerHTML = `
                            <td>${user.username}</td>
                            <td>${user.rank}</td>
                            <td class="user-status">${user.status}</td>
                            <td>${user.ip_address}</td>
                            <td>${user.last_active ? new Date(user.last_active).toLocaleString() : 'N/A'}</td>
                            <td><button onclick="deleteUser('${user.username}')">Удалить</button></td>
                        `;
                    });
                });
        };

        window.deleteUser = function(username) {
            if (confirm(`Вы уверены, что хотите удалить пользователя ${username}?`)) {
                fetch('/delete-user', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: username })
                })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    if (data.status === 'success') {
                        loadAllAdmins();
                    }
                });
            }
        };
        
        const addUserForm = document.getElementById('add-user-form');
        if (addUserForm) {
            addUserForm.addEventListener('submit', function(e) {
                e.preventDefault();
                const newUserName = document.getElementById('new-user-name').value;
                const newUserPassword = document.getElementById('new-user-password').value;
                const newUserRank = document.getElementById('new-user-rank').value;

                fetch('/add-user', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: newUserName, password: newUserPassword, rank: newUserRank })
                })
                .then(response => response.json())
                .then(data => {
                    alert(data.message);
                    if (data.status === 'success') {
                        document.getElementById('new-user-name').value = '';
                        document.getElementById('new-user-password').value = '';
                        loadAllAdmins();
                    }
                });
            });
        }
        
        window.showUserLogsSelection = function() {
            fetch('/get-user-logs-list')
                .then(response => response.json())
                .then(data => {
                    const logListContainer = document.getElementById('log-list-container');
                    logListContainer.innerHTML = '<h3>Логи пользователей</h3><ul class="log-list"></ul>';
                    const list = logListContainer.querySelector('.log-list');
                    if (data.users && data.users.length > 0) {
                        data.users.forEach(user => {
                            const li = document.createElement('li');
                            li.innerHTML = `<button onclick="getUserLogContent('${user}')">${user}</button>`;
                            list.appendChild(li);
                        });
                    } else {
                        list.innerHTML = '<li>Нет логов пользователей.</li>';
                    }
                    document.getElementById('log-content-container').innerHTML = '';
                });
        };
        
        window.getUserLogContent = function(username) {
            fetch(`/get-user-log-content/${username}`)
                .then(response => response.json())
                .then(data => {
                    const logContentContainer = document.getElementById('log-content-container');
                    logContentContainer.innerHTML = `<h3>Логи для ${username}</h3><div class="log-content-box"></div>`;
                    const logContentBox = logContentContainer.querySelector('.log-content-box');
                    if (data.logs && data.logs.length > 0) {
                        data.logs.forEach(log => {
                            const p = document.createElement('p');
                            p.textContent = `[${new Date(log.timestamp).toLocaleString()}] ${log.action}: ${log.details} (IP: ${log.ip_address})`;
                            logContentBox.appendChild(p);
                        });
                    } else {
                        logContentBox.innerHTML = '<p>Нет логов для этого пользователя.</p>';
                    }
                });
        };
        
        window.showBotLogsSelection = function() {
            fetch('/get-all-bot-logs-list')
                .then(response => response.json())
                .then(data => {
                    const logListContainer = document.getElementById('log-list-container');
                    logListContainer.innerHTML = '<h3>Логи ботов</h3><ul class="log-list"></ul>';
                    const list = logListContainer.querySelector('.log-list');
                    if (data.bots && data.bots.length > 0) {
                        data.bots.forEach(bot => {
                            const li = document.createElement('li');
                            li.innerHTML = `<button onclick="getBotLogsList('${bot}')">${bot}</button>`;
                            list.appendChild(li);
                        });
                    } else {
                        list.innerHTML = '<li>Нет логов ботов.</li>';
                    }
                    document.getElementById('log-content-container').innerHTML = '';
                });
        };
        
        window.getBotLogsList = function(botName) {
            fetch(`/get-log-list/${botName}`)
                .then(response => response.json())
                .then(data => {
                    const logContentContainer = document.getElementById('log-content-container');
                    logContentContainer.innerHTML = `<h3>Логи для ${botName}</h3><ul class="bot-log-files"></ul>`;
                    const list = logContentContainer.querySelector('.bot-log-files');
                    if (data.logs && data.logs.length > 0) {
                        data.logs.forEach(log => {
                            const li = document.createElement('li');
                            li.innerHTML = `<button onclick="getBotLogContent('${botName}', '${log}')">${log}</button>`;
                            list.appendChild(li);
                        });
                    } else {
                        list.innerHTML = '<li>Нет файлов логов для этого бота.</li>';
                    }
                });
        };
        
        window.getBotLogContent = function(botName, logFilename) {
            fetch(`/get-log-content/${botName}/${logFilename}`)
                .then(response => response.json())
                .then(data => {
                    const logContentContainer = document.getElementById('log-content-container');
                    logContentContainer.innerHTML = `<h3>Содержимое файла: ${logFilename}</h3><pre class="log-content-box">${data.content}</pre>`;
                });
        };

        const chatInput = document.getElementById('chat-input');
        const sendChatBtn = document.getElementById('send-chat-btn');
        const chatMessages = document.getElementById('chat-messages');

        if (chatInput && sendChatBtn) {
            sendChatBtn.addEventListener('click', sendMessage);
            chatInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });
        }
        
        function sendMessage() {
            const message = chatInput.value;
            if (message.trim() === '') return;

            fetch('/send-chat-message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    chatInput.value = '';
                } else {
                    alert(data.message);
                }
            });
        }

        function loadChatHistory() {
            fetch('/get-chat-history')
                .then(response => response.json())
                .then(history => {
                    chatMessages.innerHTML = '';
                    history.forEach(msg => {
                        const msgDiv = document.createElement('div');
                        msgDiv.className = 'chat-message';
                        msgDiv.innerHTML = `
                            <span class="chat-meta">[${new Date(msg.timestamp).toLocaleString()}] <strong class="chat-user chat-rank-${msg.rank}">${msg.username}</strong>:</span>
                            <span class="chat-text">${msg.message}</span>
                        `;
                        chatMessages.appendChild(msgDiv);
                    });
                    chatMessages.scrollTop = chatMessages.scrollHeight;
                });
        }
        
        if (document.getElementById('admin-chat')) {
            loadChatHistory();
            const chatEventSource = new EventSource('/admin-chat');
            chatEventSource.onmessage = function(event) {
                const msg = JSON.parse(event.data);
                const msgDiv = document.createElement('div');
                msgDiv.className = 'chat-message';
                msgDiv.innerHTML = `
                    <span class="chat-meta">[${new Date(msg.timestamp).toLocaleString()}] <strong class="chat-user chat-rank-${msg.rank}">${msg.username}</strong>:</span>
                    <span class="chat-text">${msg.message}</span>
                `;
                chatMessages.appendChild(msgDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            };
        }
    }
});