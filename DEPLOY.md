# GitHub Pages + Tailscale

Основное приложение — `endterm/bridge-test` («Мой AITU»).
Адрес: **http://100.116.195.35:1740/**.
На GitHub Pages публикуется отдельная страница «Куда обращаться» из `pages/`.
Кнопка переводит пользователя на сервер Tailscale, где работают интерфейс,
Python API, Chromium и локальные базы. Сервер должен оставаться включённым.
Посетителю нужны включённый Tailscale и разрешение на доступ к этому серверу.

GitHub Pages раздаёт только статические файлы и не запускает Python
([документация GitHub](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site)).
С HTTPS-страницы не выполняются запросы к HTTP API: браузеры блокируют такой
[mixed content](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Mixed_content).
Обычный переход по ссылке оставляет интерфейс, API и cookie на одном origin;
настройки CORS и защиты сессий менять не требуется.

## Публикация страницы

1. В репозитории `d30mantcoder/ICTProject` открой **Settings → Pages → Build and deployment → Source → GitHub Actions**.
2. Добавь и закоммить файлы публикации:

   ```bash
   git add .github/workflows/pages.yml pages/ DEPLOY.md .gitignore
   git diff --cached --stat
   git commit -m "Prepare GitHub Pages entry point for Tailscale"
   git push origin main
   ```

   Проверь состав коммита: в рабочем дереве есть и другие незавершённые изменения.
   При подготовке также убраны из индекса ранее отслеживаемые Python-кэш и
   SQL-бэкапы; сами файлы остаются на диске. Новые `.env`, виртуальные окружения,
   SQLite-базы, ключи и бэкапы исключены через `.gitignore`.
   Удаление из текущей версии не удаляет старые файлы из истории Git.

3. Дождись успешного workflow **Deploy access page to GitHub Pages** на вкладке Actions.
   Его можно запустить вручную через **Run workflow**.
4. Открой `https://d30mantcoder.github.io/ICTProject/` и проверь переход
   с устройства, подключённого к Tailscale. Это ожидаемый URL после публикации;
   окончательный URL также отображается в результате workflow.

Workflow загружает **только `pages/`**, а не весь репозиторий.
Корневой `index.html` — старая LMS; для Pages нужно выбрать именно GitHub Actions,
а не публикацию из корня ветки. Публикация страницы не обновляет Python-сервер.

## Сервер

Текущий сервер уже отвечает на `http://100.116.195.35:1740/api/health`.
Для ручного запуска из корня проекта:

```bash
cd endterm
python3 -m venv venv
venv/bin/python -m pip install -r bridge-test/requirements.txt
venv/bin/python -m playwright install chromium --only-shell
BRIDGE_HOST=0.0.0.0 BRIDGE_PORT=1740 BRIDGE_HEADLESS=1 venv/bin/python bridge-test/app.py
```

`0.0.0.0` сохраняет доступ и через Tailscale, и через localhost: внутренний
демо-экран браузера использует `127.0.0.1:1740`. Сетевые разрешения Tailscale
и firewall должны разрешать нужным устройствам TCP-порт 1740.
MariaDB и порт Ollama не нужны клиентским устройствам.

Для автозапуска на текущей машине есть пользовательский systemd unit
`endterm/bridge-test/aitu-bridge.service`:

```bash
mkdir -p ~/.config/systemd/user
install -m 644 endterm/bridge-test/aitu-bridge.service ~/.config/systemd/user/aitu-bridge.service
systemctl --user daemon-reload
systemctl --user enable --now aitu-bridge.service
```

Команды systemd выполняются из корня проекта. При переносе исправь абсолютные
пути в unit; для запуска до входа пользователя администратор может включить
`sudo loginctl enable-linger "$USER"`. Запускай один процесс приложения.
Подробности зависимостей, SQLite и локального AI — в `endterm/bridge-test/README.md`.

Проверка с устройства в Tailscale:

```bash
curl --noproxy '*' http://100.116.195.35:1740/api/health
```

Ожидается JSON со `"status":"ok"`. Затем проверь открытие кабинета и вход.
При смене адреса или порта обнови ссылку и видимый адрес в `pages/index.html`.
Прежняя демонстрационная LMS остаётся на `http://100.116.195.35:1734/app`.
