"""
Сервис для работы с Google Sheets.
Инкапсулирует всю логику подключения и работы с таблицами.
"""
import logging
import json as _json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config import (
    GOOGLE_SHEETS_KEY,
    GSERVICE_JSON,
    SHOKZ_ACCOUNTS_SHEET,
    CARRIERS_SHEET,
    TYPES_SHEET,
    MEDIATORS_SHEET,
    PRODUCTS_SHEET,
)

logger = logging.getLogger(__name__)

# --- Google Sheets init ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


class GoogleSheetsService:
    """Сервис для работы с Google Sheets."""
    
    def __init__(self):
        """Инициализация подключения к Google Sheets."""
        try:
            creds_dict = _json.loads(GSERVICE_JSON)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
            self.client = gspread.authorize(creds)
            
            self.spreadsheet = self.client.open_by_key(GOOGLE_SHEETS_KEY)
            self.sheet_accounts = self.spreadsheet.worksheet(SHOKZ_ACCOUNTS_SHEET)
            self.sheet_carriers = self.spreadsheet.worksheet(CARRIERS_SHEET)
            self.sheet_types = self.spreadsheet.worksheet(TYPES_SHEET)
            self.sheet_mediators = self.spreadsheet.worksheet(MEDIATORS_SHEET)
            self.sheet_products = self.spreadsheet.worksheet(PRODUCTS_SHEET)
            self.sheet_emails = self.spreadsheet.worksheet("Emails")
            
            # Лист для записи eBay адресов (может не существовать, создастся при первой записи)
            try:
                self.sheet_ebay_addresses = self.spreadsheet.worksheet("eBay_Addresses")
            except Exception:
                # Лист не существует, будет создан при первой записи
                self.sheet_ebay_addresses = None
            
            logger.info("Google Sheets подключен успешно")
        except Exception as e:
            logger.error(f"Ошибка при инициализации Google Sheets: {e}")
            raise
    
    def get_sheet_by_category(self, category_key: str):
        """Получить лист по ключу категории."""
        sheet_map = {
            "carriers": self.sheet_carriers,
            "types": self.sheet_types,
            "mediators": self.sheet_mediators,
        }
        return sheet_map.get(category_key)
    
    def get_recipient_data(self, category_key: str, row_idx: int) -> list:
        """Получить данные получателя из листа категории."""
        sheet = self.get_sheet_by_category(category_key)
        if not sheet:
            raise ValueError(f"Неизвестная категория: {category_key}")
        return sheet.row_values(row_idx)
    
    def append_ebay_address(self, name: str, addr1: str, addr2: str, city: str, state: str, zip_code: str, product: str):
        """
        Добавить запись в лист eBay_Addresses.
        Если лист не существует, создаст его.
        """
        try:
            # Если лист не существует, создаем его
            if self.sheet_ebay_addresses is None:
                try:
                    self.sheet_ebay_addresses = self.spreadsheet.add_worksheet(
                        title="eBay_Addresses",
                        rows=1000,
                        cols=7
                    )
                    # Добавляем заголовки
                    self.sheet_ebay_addresses.append_row([
                        "Имя", "Улица", "Линия 2", "Город", "Штат (ST)", "ZIP", "Товар"
                    ])
                    logger.info("Создан лист eBay_Addresses")
                except Exception as e:
                    logger.error(f"Ошибка создания листа eBay_Addresses: {e}")
                    return
            
            # Добавляем строку данных
            self.sheet_ebay_addresses.append_row([
                name or "[нет имени]",
                addr1 or "",
                addr2 or "",
                city or "",
                state or "",
                zip_code or "",
                product or "[нет товара]",
            ])
            logger.info(f"Запись добавлена в eBay_Addresses: {name}")
        except Exception as e:
            logger.error(f"Ошибка записи в eBay_Addresses: {e}")


# Глобальный экземпляр сервиса (инициализируется при импорте)
_sheets_service = None


def get_sheets_service() -> GoogleSheetsService:
    """Получить глобальный экземпляр сервиса Google Sheets."""
    global _sheets_service
    if _sheets_service is None:
        _sheets_service = GoogleSheetsService()
    return _sheets_service

