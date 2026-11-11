# 🎵 Music Bot

[![CI](https://github.com/Madeinkind/music-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Madeinkind/music-bot/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![discord.py](https://img.shields.io/badge/discord.py-2.7-5865F2?logo=discord&logoColor=white)](https://github.com/Rapptz/discord.py)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Музыкальный бот для Discord на **Python 3.11+**: `discord.py` 2.x + `yt-dlp` + `ffmpeg`.
Интерфейс полностью на русском, поддерживаются и слэш-команды (`/play`), и обычные текстовые (`!play`).

> **Коротко:** `/play <название или ссылка>` — бот заходит в ваш канал и играет.
> Очередь, кнопки, повтор, перемотка, громкость и поиск уже в комплекте.

## Возможности

- воспроизведение по названию или ссылке: YouTube, SoundCloud, Bandcamp и всё, что умеет `yt-dlp`;
- плейлисты: ссылка на плейлист добавляет до `MAX_PLAYLIST_ITEMS` треков;
- очередь с постраничным просмотром, удалением, очисткой и перемешиванием;
- пауза/продолжение, пропуск, стоп, перемотка, громкость 0–200 %;
- режимы повтора: выключен / один трек / вся очередь;
- кнопки управления под сообщением «Сейчас играет»;
- поиск с выбором из топ-5 результатов (`/search`);
- автовыход из пустого канала через `IDLE_TIMEOUT` секунд;
- поддержка `cookies.txt` и прокси для обхода проверок YouTube;
- корректное завершение работы и сброс состояния, если бота выгнали из канала.

## Требования

- Python **3.11+**
- `ffmpeg` в `PATH` **или** пакет `imageio-ffmpeg` (он входит в `requirements.txt` и подтянет бинарник сам)
- приложение Discord с ботом и токеном

## Быстрый старт

### 1. Клонирование и зависимости

```bash
git clone https://github.com/Madeinkind/music-bot.git
cd music-bot

python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. ffmpeg

Бот попробует найти `ffmpeg` сам: `FFMPEG_PATH` → `PATH` → бинарник из `imageio-ffmpeg`.
Если хотите системную установку:

```powershell
winget install Gyan.FFmpeg          # Windows
```

```bash
sudo apt install ffmpeg             # Debian / Ubuntu
brew install ffmpeg                 # macOS
```

### 3. Приложение Discord

1. Откройте [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. Вкладка **Bot** → **Reset Token** → скопируйте токен (никому его не показывайте).
3. Там же включите **Message Content Intent** (нужно для текстовых команд `!play`).
4. Вкладка **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`;
   - Bot Permissions: `Connect`, `Speak`, `Send Messages`, `Embed Links`, `Read Message History`, `Use Slash Commands`.
5. Откройте сгенерированную ссылку и добавьте бота на сервер.

### 4. Настройка

```bash
cp .env.example .env
```

Вставьте токен в `.env`:

```env
DISCORD_TOKEN=ваш_токен
DEV_GUILD_ID=123456789012345678   # ID вашего сервера — команды появятся сразу
```

`DEV_GUILD_ID` необязателен, но с ним слэш-команды синхронизируются мгновенно, а не в течение часа.

### 5. Запуск

```bash
python bot.py
```

В логе должно появиться `Бот запущен: …` и `Синхронизировано N команд`.

## Команды

| Слэш | Префикс (алиасы) | Что делает |
| --- | --- | --- |
| `/play <запрос \| ссылка>` | `!play`, `!p`, `!п`, `!играть` | Включает трек или плейлист |
| `/search <запрос>` | `!search`, `!find`, `!поиск` | Ищет и показывает топ-5 для выбора |
| `/pause` | `!pause`, `!пауза` | Пауза |
| `/resume` | `!resume`, `!continue`, `!продолжить` | Продолжить |
| `/skip` | `!skip`, `!next`, `!пропустить`, `!след` | Пропустить трек |
| `/stop` | `!stop`, `!стоп` | Остановить и очистить очередь |
| `/seek <секунды>` | `!seek`, `!перемотка` | Перемотка текущего трека |
| `/queue` | `!queue`, `!q`, `!очередь` | Очередь с кнопками страниц |
| `/nowplaying` | `!nowplaying`, `!np`, `!сейчас` | Текущий трек и кнопки |
| `/remove <номер>` | `!remove`, `!rm`, `!удалить` | Удалить трек из очереди |
| `/clear` | `!clear`, `!очистить` | Очистить очередь |
| `/shuffle` | `!shuffle`, `!mix`, `!перемешать` | Перемешать очередь |
| `/loop [off\|track\|queue]` | `!loop`, `!repeat`, `!повтор` | Режим повтора |
| `/join` | `!join`, `!connect`, `!зайти` | Подключиться к вашему каналу |
| `/leave` | `!leave`, `!dc`, `!disconnect`, `!выйти` | Отключиться и очистить очередь |
| `/volume <0-200>` | `!volume`, `!vol`, `!громкость` | Громкость |
| `/voicecheck` | `!voicecheck`, `!vcheck`, `!диагностика` | Диагностика голоса и звука |
| `/help` | `!help`, `!помощь` | Список команд |

Бот также реагирует на упоминание: `@MusicBot play …`.

## Переменные окружения

| Переменная | По умолчанию | Описание |
| --- | --- | --- |
| `DISCORD_TOKEN` | — | Токен бота (обязательно) |
| `COMMAND_PREFIX` | `!` | Префикс текстовых команд |
| `DEV_GUILD_ID` | — | ID сервера для мгновенной синхронизации слэш-команд |
| `FFMPEG_PATH` | — | Путь к `ffmpeg` |
| `YTDL_COOKIES_FILE` | — | Путь к `cookies.txt` для YouTube |
| `PROXY` | — | Прокси для `yt-dlp` |
| `DEFAULT_VOLUME` | `60` | Стартовая громкость, 0–200 |
| `MAX_QUEUE_SIZE` | `500` | Максимум треков в очереди |
| `MAX_PLAYLIST_ITEMS` | `100` | Сколько треков брать из плейлиста |
| `IDLE_TIMEOUT` | `300` | Секунды тишины до выхода из канала (`0` — не выходить) |
| `SELF_DEAF` | `true` | Самоглушение бота (иконка перечёркнутых наушников); `false` — бот принимает звук канала |
| `EMBED_COLOR` | `0x5865F2` | Цвет эмбедов |
| `LOG_LEVEL` | `INFO` | Уровень логирования |

## Docker

```bash
cp .env.example .env     # заполните DISCORD_TOKEN
docker compose up -d --build
docker compose logs -f
```

`ffmpeg` устанавливается внутрь образа, `logs/` монтируется наружу.
Для cookies положите файл рядом и раскомментируйте строку с `cookies.txt` в `docker-compose.yml`.

## Структура проекта

```
bot.py              — запуск, логирование, MusicBot (хранит yt-dlp и плееры)
config.py           — чтение и валидация .env
cogs/
  music.py          — все команды и обработка ошибок слэш-команд
  events.py         — on_ready, потеря голосового канала, ошибки префиксных команд
music/
  track.py          — модель трека
  queue.py          — очередь с лимитом и страницами
  ytdl.py           — асинхронная обёртка над yt-dlp
  player.py         — воспроизведение, повтор, перемотка, таймауты
  views.py          — кнопки плеера, очередь, выбор из поиска
  voice.py          — проверки канала и создание плеера
utils/
  embeds.py         — эмбеды и тексты
  formatting.py     — время и полоса прогресса
  ffmpeg.py         — поиск рабочего бинарника ffmpeg
tests/              — быстрые тесты логики (без сети)
```

### Как добавить команду

1. Создайте метод в `cogs/music.py` с декоратором `@commands.hybrid_command(...)`.
2. Возьмите плеер через `self._prepare(ctx)` (подключение + проверки) или `self._existing(ctx)`.
3. Ответьте через `_reply(ctx, ...)` — это работает и для `/команд`, и для `!команд`.

## Частые проблемы

### Бот в канале, но нет звука

Сначала выполните `/voicecheck` — команда покажет канал, статус воспроизведения, права `Connect`/`Speak`,
серверный мут/оглушение и версии `PyNaCl`/`davey`.

Если всё зелёное, но звука нет, почти всегда виноваты несовместимые версии голосовых зависимостей:
`discord.py 2.7.x` собран под `davey 0.x` и `PyNaCl < 1.6`. С `davey 0.2.x` или `PyNaCl 1.6+`
бот «играет», но в канал уходит тишина. Проверьте, что установлено ровно это:

```bash
pip install "davey>=0.1.0,<0.2" "PyNaCl>=1.5.0,<1.6"
```

Остальное по мелочи:

- права `Connect` и `Speak` у роли бота в этом канале;
- правый клик по боту → «Громкость пользователя» — не 0 %;
- вы сами не в режиме «Отключить звук»;
- `ffmpeg -version` работает из той же среды, где запущен бот;
- `logs/bot.log` — там будут ошибки yt-dlp и ffmpeg.

### YouTube: «Sign in to confirm you're not a bot»

YouTube всё чаще требует авторизацию. Решение — cookies:

1. Установите в браузере расширение **Get cookies.txt LOCALLY** (или аналог).
2. Зайдите на `youtube.com` под своим аккаунтом и экспортируйте cookies в формате Netscape.
3. Сохраните файл как `cookies.txt` в папке бота.
4. В `.env`: `YTDL_COOKIES_FILE=cookies.txt`.

Файл `cookies.txt` уже в `.gitignore` — не коммитьте его.

### `ffmpeg не найден`

Установите ffmpeg (см. раздел 2) **или** выполните `pip install imageio-ffmpeg`.
Можно указать путь явно: `FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe`.

### Слэш-команды не появились

- Заполните `DEV_GUILD_ID` — синхронизация для сервера мгновенная.
- Глобальные команды Discord может кэшировать до часа.
- Проверьте, что бот приглашён со scope `applications.commands`.

### `yt-dlp` устарел / перестали работать ссылки

`yt-dlp` обновляется очень часто, YouTube меняет защиту. Обновляйте пакет:

```bash
pip install -U yt-dlp
```

## Разработка

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

CI (`.github/workflows/ci.yml`) запускает линтер, компиляцию и тесты на Python 3.11/3.12.

## Лицензия

MIT — см. [LICENSE](LICENSE).
