"""Config template for Shokz accounts bot.

1. Copy this file as `config.py`.
2. Fill in all required values: tokens, keys, sheet IDs and service account JSON.
3. Do NOT commit your real secrets to any public repo.
"""

TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"

# OpenAI + OCR.Space API keys
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
OCR_API_KEY = "YOUR_OCR_API_KEY"

# Google Sheets
GOOGLE_SHEETS_KEY = "YOUR_SHEET_ID"

# Paste your service account JSON as a raw string.
GSERVICE_JSON = r"""{
  "type": "service_account",
  "project_id": "your-project-id",
  ...
}"""

# Sheet names
SHOKZ_ACCOUNTS_SHEET = "Shokz_accounts"
CARRIERS_SHEET = "Перевозчики"
TYPES_SHEET = "Типы"
MEDIATORS_SHEET = "Посреды"
PRODUCTS_SHEET = "Товары"

# Column indices (1-based) in Shokz_accounts
COL_DATE = 1            # Дата заказа
COL_ORDER_NO = 2        # № п/п
COL_NAME = 3            # Имя
COL_EMAIL = 4           # Почта
COL_ADDRESS = 5         # Адрес
COL_PHONE = 6           # Телефон
COL_PRODUCT = 7         # Товар
COL_SERIAL = 8          # Серийник
COL_STATUS = 9          # Статус
COL_ISSUE = 10          # Причина обращения
COL_RECEIPT_LINK = 11   # Ссылка на квитанцию
