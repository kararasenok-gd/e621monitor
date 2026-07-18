# e621monitor

A Telegram bot that monitors [e621.net](https://e621.net) for new posts matching your tags and delivers them directly to you.

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Register and get started |
| `/add <tags>` | Add tags to track (e.g. `/add fox solo`) |
| `/addbl <tags>` | Add tags to the blacklist (exclude from results) |
| `/rem <tags>` | Remove tracked or blacklisted tags |
| `/list` | Show all your tracked and blacklisted tags |
| `/lang [code]` | Show a language picker, or set your language directly by code |

> [!NOTE]
> Meta-tags like `score:>=50` are not supported for tracking.

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/kararasenok_gd/e621monitor.git
cd e621monitor
pip install -r requirements.txt
```

### 2. Configure

Copy the example config and fill in your values:

```bash
cp src/config.example.ini src/config.ini
```

Key settings in `config.ini`:

```ini
[bot]
token = YOUR_TELEGRAM_BOT_TOKEN

[art_source]
base_url = https://e621.net
username = YOUR_E621_USERNAME
api_key = YOUR_E621_API_KEY

[database]
driver = sqlite        # sqlite | postgres | mysql

[watch]
check_every_seconds = 90

[autoposting]
channel_id_safe = -100XXXXXXXXXX
channel_id_questionable = -100XXXXXXXXXX
channel_id_explicit = -100XXXXXXXXXX
score_limit = 25
post_limit = 50
```

### 3. Redis Server (for caching)
You can use Redis Cloud or run a local Redis server.

If you want to run a local Redis server, use the following command in the root directory:

```bash
docker compose up -d
```

In that case you don't need to change anything in the config.

### 4. Run

```bash
cd src
python main.py
```

## Configuration Reference

### `[bot]`
| Key | Description |
|-----|-------------|
| `token` | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `debug` | Enable debug logging (`true` / `false`) |

### `[art_source]`
| Key | Description |
|-----|-------------|
| `base_url` | API base URL (default: `https://e621.net`) |
| `username` | Your e621 username |
| `api_key` | Your e621 API key |

### `[database]`
Supports `sqlite`, `postgres`, and `mysql`. Fill in only the section for your chosen driver.

### `[autoposting]`
Posts are forwarded to separate channels based on their rating. Set `channel_id_*` to the Telegram channel ID (must start with `-100`). Posts below `score_limit` are skipped.

### `[redis]`
Used for caching API responses. Run `docker compose up -d` to start a local Redis instance.

## Stack

- [aiogram 3](https://aiogram.dev/) — Telegram bot framework
- [SQLAlchemy](https://www.sqlalchemy.org/) — ORM
- e621api — e621 API client
- [loguru](https://github.com/Delgan/loguru) — logging
- [Redis](https://redis.io/) — Cache

## License

See [LICENSE](LICENSE).