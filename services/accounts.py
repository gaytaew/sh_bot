"""
Сервис для создания и управления аккаунтами Shokz.
Отвечает за выдачу email, серийников, создание записей в Google Sheets.
"""
import logging
import random
from datetime import datetime, timedelta

from config import (
    COL_DATE,
    COL_ORDER_NO,
    COL_NAME,
    COL_EMAIL,
    COL_ADDRESS,
    COL_PHONE,
    COL_PRODUCT,
    COL_SERIAL,
    COL_STATUS,
    COL_ISSUE,
    COL_RECEIPT_LINK,
)
from constants import ISSUE_TEMPLATES, CEFALY_ISSUE_TEMPLATES 
from models import AccountData, AddressParts
from services.google_sheets import get_sheets_service
from services.address import (
    perturb_name,
    perturb_address,
    fake_phone,
    parse_zip_and_city,
    col_to_letter,
)

logger = logging.getLogger(__name__)


class AccountService:
    """Сервис для работы с аккаунтами."""
    
    def __init__(self):
        self.sheets = get_sheets_service()
    
    def get_products_from_header(self):
        """
        Считать список товаров из первой строки листа 'Товары'.
        """
        headers = self.sheets.sheet_products.row_values(1)
        products = []
        for idx, name in enumerate(headers, start=1):
            if not name:
                continue
            if name.strip().upper().endswith("USED"):
                continue
            if name.strip().upper().endswith("MODEL"):
                continue
            products.append((idx, name.strip()))
        return products
    
    def get_serial_for_product(self, product_name: str) -> tuple[str, str | None]:
        """
        Найти свободный серийник.
        Для обычных товаров:
            Структура: [Serial] [Used]
            Возвращает: (serial, None)
            
        Для Oura Ring:
            Структура: [Serial] [Model] [Used]
            Возвращает: (serial, model_info)
            
        Действие: Переносит Serial в Used, основной Serial стирает.
        """
        headers = self.sheets.sheet_products.row_values(1)
        try:
            col_idx = headers.index(product_name) + 1  # 1-based
        except ValueError:
            raise RuntimeError(f"Не найден столбец для товара '{product_name}' в листе 'Товары'.")

        # ОПРЕДЕЛЯЕМ СТРУКТУРУ КОЛОНОК
        is_oura = "oura ring" in product_name.lower()
        
        if is_oura:
            # [Serial] [Model] [Used]
            model_col_idx = col_idx + 1
            used_col_idx = col_idx + 2
        else:
            # [Serial] [Used]
            model_col_idx = None
            used_col_idx = col_idx + 1

        # Читаем данные
        # col_vals - это сами серийники
        col_vals = self.sheets.sheet_products.col_values(col_idx)[1:]
        
        # used_vals - колонка использованных
        used_vals = self.sheets.sheet_products.col_values(used_col_idx)[1:]
        
        # model_vals - колонка моделей (если есть)
        model_vals = []
        if model_col_idx:
            model_vals = self.sheets.sheet_products.col_values(model_col_idx)[1:]

        # i - фактический номер строки в Google Sheets (start=2)
        for i, serial in enumerate(col_vals, start=2): 
            list_index = i - 2
            
            serial = serial.strip()
            # Проверяем used
            used = used_vals[list_index].strip() if list_index < len(used_vals) else ""
            
            if serial and not used:
                # НАШЛИ СВОБОДНЫЙ
                row_idx = i
                
                # Достаем доп. инфо если надо
                extra_info = None
                if is_oura:
                    extra_info = model_vals[list_index].strip() if list_index < len(model_vals) else ""
                    if not extra_info:
                        extra_info = "Unknown Model"

                # ЗАПИСЬ В SHEETS (атомарно, насколько можно)
                # Очищаем Serial, Пишем в Used
                # Для Oura: Used колонка смещена на 1
                
                main_col_letter = col_to_letter(col_idx)
                used_col_letter = col_to_letter(used_col_idx)
                
                # Формируем range: например O2:Q2 (если 3 колонки)
                # Но мы обновляем только Serial и Used.
                # Serial -> ""
                # Used -> serial
                # Model (если есть) -> не трогаем
                
                # Обновляем ячейку Serial -> ""
                self.sheets.sheet_products.update_cell(row_idx, col_idx, "")
                # Обновляем ячейку Used -> serial
                self.sheets.sheet_products.update_cell(row_idx, used_col_idx, serial)
                
                logger.info(f"Выдан серийник {serial} для '{product_name}' (stroka {row_idx}). Extra: {extra_info}")
                return serial, extra_info

        raise RuntimeError(f"Нет доступных серийников для товара '{product_name}'.")
    
    def get_email_from_pool(self) -> str:
        """Получить свободный email из пула."""
        col_emails = self.sheets.sheet_emails.col_values(1)[1:]  # без заголовка
        col_used = self.sheets.sheet_emails.col_values(2)[1:]

        for i, email in enumerate(col_emails, start=2):
            email = email.strip()
            used = col_used[i - 2].strip() if i - 2 < len(col_used) else ""
            if email and not used:
                row_idx = i
                rng = f"A{i}:B{i}"
                
                try:
                    self.sheets.sheet_emails.update(rng, [["", email]], value_input_option='USER_ENTERED')
                except Exception as e:
                    logger.error(f"Ошибка обновления Google Sheets (Emails, строка {row_idx}): {e}")
                    raise RuntimeError(f"Ошибка при блокировке email: {email}")

                logger.info(f"Выдан email {email} (строка {row_idx} листа Emails)")
                return email

        raise RuntimeError("Нет свободных email-ов в листе 'Emails'. Добавь новые Email / очисти USED.")
    
    def generate_random_date_str(self, product_name: str | None = None) -> str:
        """
        Генерирует случайную дату покупки.
        Для Cefaly: не позднее, чем за 1 год и 1 месяц (т.е. старее 13 месяцев).
        Для остальных: 4-9 месяцев назад.
        """
        now = datetime.now()
        
        # По умолчанию (Shokz и др): 4-9 месяцев назад
        min_days_back = 4 * 30.5
        max_days_back = 9 * 30.5
        
        if product_name and product_name.lower() == "cefaly":
            # "Не позднее, чем за 1 год и 1 месяц" -> старее (дальше в прошлое), чем 13 месяцев
            # 1 год 1 месяц = ~395 дней
            # Сделаем диапазон от 13 до 18 месяцев (чтобы не улететь в "слишком старое")
            min_days_back = 395  # 13 месяцев
            max_days_back = 545  # ~18 месяцев

        random_days = random.randint(int(min_days_back), int(max_days_back))
        
        random_date = now - timedelta(days=random_days)
        
        return random_date.strftime("%d.%m.%Y")
    
    def create_account(
        self,
        name: str,
        address: str,  # Адрес для записи в GS (может быть искаженным или чистым)
        phone: str = "",
        product: str | None = None,
        issue_reason: str | None = None,
        address_parts: AddressParts | None = None,  # Чистые компоненты для URL
    ) -> AccountData:
        """
        Создать НОВУЮ строку в Shokz_accounts и вернуть данные аккаунта.
        
        Args:
            name: Имя (может быть искаженным)
            address: Адрес для записи в GS (может быть искаженным или чистым)
            phone: Телефон
            product: Название товара
            issue_reason: Причина обращения (если None - выбирается случайная)
            address_parts: Чистые компоненты адреса для генерации URL (опционально)
        """
        if not product:
            raise RuntimeError("Не указан товар при выдаче аккаунта (product=None).")

        email = self.get_email_from_pool()
        serial, extra_info = self.get_serial_for_product(product)

        all_values = self.sheets.sheet_accounts.get_all_values()
        data_rows = max(0, len(all_values) - 1)
        order_seq = data_rows + 1
        order_no = f"SHKZ{order_seq:03d}"

        row_idx = data_rows + 2

        if issue_reason:
            issue = issue_reason
        else:
            # Если товар "Cefaly" (без учета регистра), берем из спец. списка
            if product.lower() == "cefaly":
                issue = random.choice(CEFALY_ISSUE_TEMPLATES)
            else:
                issue = random.choice(ISSUE_TEMPLATES)
        
        date_receipt = self.generate_random_date_str(product)  # Дата с учетом товара
        date_gs_current = datetime.now().strftime("%d.%m.%Y")  # ТЕКУЩАЯ ДАТА ЗАКАЗА
        
        min_len = COL_RECEIPT_LINK 
        new_row = [""] * min_len
        
        # --- ЯВНОЕ ЗАПОЛНЕНИЕ ПОЛЕЙ ---
        new_row[COL_DATE - 1] = date_gs_current  # ТЕКУЩАЯ ДАТА ЗАКАЗА
        new_row[COL_ORDER_NO - 1] = order_no
        new_row[COL_NAME - 1] = name
        new_row[COL_EMAIL - 1] = email 
        new_row[COL_ADDRESS - 1] = address  # Адрес (может быть искаженным или чистым)
        new_row[COL_PHONE - 1] = phone
        new_row[COL_PRODUCT - 1] = product
        new_row[COL_SERIAL - 1] = serial
        new_row[COL_STATUS - 1] = "Новый"
        new_row[COL_ISSUE - 1] = issue
        # new_row[COL_RECEIPT_LINK - 1] остается пустым, будет обновлен после генерации ссылки

        range_a1 = f"A{row_idx}:{col_to_letter(COL_RECEIPT_LINK)}{row_idx}"
        self.sheets.sheet_accounts.update(range_a1, [new_row])

        return AccountData(
            row_idx=row_idx,
            email=email,
            product=product,
            serial=serial,
            issue=issue,
            name=name,
            address=address,
            phone=phone,
            order_no=order_no,
            date=date_receipt,  # Дата для квитанции (в прошлом)
            address_parts=address_parts,  # Чистые компоненты для URL
            extra_info=extra_info,
        )
    
    def create_account_from_category(
        self,
        base_name: str,
        base_addr1: str,
        base_addr2: str,
        base_city: str,
        base_state: str,
        base_zip: str,
        product: str,
    ) -> AccountData:
        """
        Создать аккаунт из данных категории (Перевозчики/Типы/Посреды).
        Искажает имя и адрес перед записью в GS.
        """
        # Искажаем имя
        name = perturb_name(base_name)
        
        # Искажаем адрес для записи в GS
        address_mutated = perturb_address(
            addr1=base_addr1,
            addr2=base_addr2,
            city=base_city,
            state=base_state,
            zip_code=base_zip
        )
        
        # Генерируем телефон на основе ZIP
        zip_code, _city = parse_zip_and_city(base_zip or "")
        phone = fake_phone(zip_code)
        
        # Чистые компоненты для URL
        address_parts = AddressParts(
            addr1=base_addr1,
            addr2=base_addr2,
            city=base_city,
            state=base_state,
            zip_code=base_zip,
        )
        
        return self.create_account(
            name=name,
            address=address_mutated,  # Искаженный адрес для GS
            phone=phone,
            product=product,
            address_parts=address_parts,  # Чистые компоненты для URL
        )
    
    def create_account_from_ebay(
        self,
        name: str,
        address_raw: str,  # Адрес как строка от GPT
        product: str,
        address_parts: AddressParts,  # Разобранные компоненты для URL
    ) -> AccountData:
        """
        Создать аккаунт из данных eBay (OCR/GPT).
        Адрес НЕ искажается, записывается как есть от GPT.
        """
        # Проверка товара
        if not product or not product.strip():
            raise RuntimeError("Не указан товар при выдаче аккаунта (product=None или пустая строка).")
        
        # Генерируем телефон на основе ZIP
        phone = fake_phone(address_parts.zip_code)
        
        return self.create_account(
            name=name or "[имя не найдено]",
            address=address_raw or "",  # Адрес как есть от GPT (БЕЗ искажения)
            phone=phone,
            product=product.strip(),  # Убираем пробелы
            address_parts=address_parts,  # Разобранные компоненты для URL
        )
    
    def update_status(self, row_idx: int, status_value: str):
        """Обновить статус аккаунта."""
        self.sheets.sheet_accounts.update(f"I{row_idx}", [[status_value]])
        logger.info(f"Статус строки {row_idx} обновлён на {status_value}")
    
    def update_receipt_link(self, row_idx: int, receipt_url: str, shop_key: str):
        """Обновить ссылку на квитанцию в Google Sheets."""
        # Экранируем кавычки в URL для формулы HYPERLINK
        # В Google Sheets нужно удваивать кавычки внутри строки
        escaped_url = receipt_url.replace('"', '""')
        link_for_gs = f'=HYPERLINK("{escaped_url}", "Receipt Link ({shop_key.capitalize()})")'
        self.sheets.sheet_accounts.update_cell(row_idx, COL_RECEIPT_LINK, link_for_gs)
        logger.info(f"Ссылка записана в COL_RECEIPT_LINK: {link_for_gs}")
    
    def find_account_by_email_or_order(self, query: str) -> int | None:
        """
        Найти аккаунт по email или номеру заказа.
        Возвращает row_idx или None.
        """
        query = query.strip()
        
        # Если это email
        if "@" in query:
            target_email = query.lower()
            col_emails = self.sheets.sheet_accounts.col_values(COL_EMAIL)[1:]  # без заголовка
            for idx, val in enumerate(col_emails, start=2):
                if val.strip().lower() == target_email:
                    return idx
        else:
            # Считаем, что это код SHKZ...
            code = query.upper()
            col_order = self.sheets.sheet_accounts.col_values(COL_ORDER_NO)[1:]  # без заголовка
            for idx, val in enumerate(col_order, start=2):
                if val.strip().upper() == code:
                    return idx
        
        return None
    
    def get_account_data(self, row_idx: int) -> dict:
        """Получить данные аккаунта по row_idx."""
        row = self.sheets.sheet_accounts.row_values(row_idx)
        
        def safe(col_idx: int) -> str:
            return row[col_idx - 1] if len(row) >= col_idx else ""
        
        return {
            "name": safe(COL_NAME),
            "email": safe(COL_EMAIL),
            "address": safe(COL_ADDRESS),
            "phone": safe(COL_PHONE),
            "product": safe(COL_PRODUCT),
            "serial": safe(COL_SERIAL),
            "status": safe(COL_STATUS),
            "issue": safe(COL_ISSUE),
            "order_no": safe(COL_ORDER_NO),
        }


# Глобальный экземпляр сервиса
_account_service = None


def get_account_service() -> AccountService:
    """Получить глобальный экземпляр сервиса аккаунтов."""
    global _account_service
    if _account_service is None:
        _account_service = AccountService()
    return _account_service

