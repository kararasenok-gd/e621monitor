# Translations

This folder holds the bot's language files. Each language is a separate YAML
file named after its Telegram language code (`language_code`), e.g. `en.yaml`,
`ru.yaml`.

## File structure

```yaml
display: "🇷🇺 Русский"

strings:
  start:
    greetings: "Привет!"
  add:
    missing_args: "Пропущены теги! Правильное использование: /add <теги>"
```

- `display` — the language name shown to the user (usually a flag + the name in that language).
- `strings` — the tree of strings. The nesting and key names must **exactly**
  match `en.yaml` — that's the default language the bot falls back to when a
  string is missing from a translation (see `utils/i18n.py`).

## Adding a new language

1. Copy `en.yaml` into a new file named after the target language code (e.g. `de.yaml`).
2. Translate the `display` value and all strings inside `strings`, without changing the keys.
3. If you want, you can also add a `translators` field with your username.
4. Don't translate command names (`/add`, `/addbl`, `/rem`, `/list`) — they're fixed in code.
5. That's it: `utils/i18n.py` picks up every `*.yaml` file in this folder
   automatically, nothing else needs to be registered.

A user's language is set automatically from their Telegram `language_code` on
first contact with the bot (see `utils/funcs/db.py`). If no translation exists
for that language, `en` is used instead.

## Pull Request

Pull requests are welcome! Please keep the following things in mind:

- Make sure your translation is 100% accurate.
- No need to update the `display` value — it's ok to keep it in English.
- Don't change the key names under `strings`.
- Make sure your language code is correct and not already in use.

## Plural forms

Some strings (`add.tags`, `add.success`, `addbl.success`) aren't a single
value but a set of forms:

```yaml
tags:
  one: "Тег"
  few: "Теги"
```

The form is picked by the `pluralize()` function in `utils/funcs/txt.py`
following Russian pluralization rules (`one` / `few` / `many` / `other`). When
adding a language with a different plural system (e.g. English, which only
has one form), just duplicate the same value across all the needed keys:

```yaml
success:
  one: "added"
  few: "added"
```

## HTML and data substitution

Translations can contain Telegram HTML tags (`<b>`, `<tg-emoji>`, etc.) — they
get inserted into the message text as-is. `i18n.get()` escapes HTML in values
by default, so tags inside the translation string itself aren't escaped, but
dynamic data (user tags, etc.) that the calling code wraps around the
translation is escaped separately at the call site.

## Testing

After adding a translation, run the bot (`python main.py` from `src/`) and
check the main commands (`/start`, `/add`, `/addbl`, `/rem`, `/list`) with an
account whose Telegram `language_code` matches it.