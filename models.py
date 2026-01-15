"""
Модели данных для бота Shokz.
Используются для передачи данных между слоями приложения.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class AddressParts:
    """Компоненты адреса для генерации URL квитанций."""
    addr1: str  # Улица (Line 1)
    addr2: str  # Line 2 (квартира, unit и т.д.)
    city: str
    state: str
    zip_code: str


@dataclass
class AccountData:
    """Данные созданного аккаунта."""
    row_idx: int
    order_no: str
    email: str
    name: str
    address: str  # Адрес для записи в GS (может быть искаженным)
    phone: str
    product: str
    serial: str
    issue: str
    date: str  # Дата для квитанции (в прошлом)
    # Чистые компоненты адреса для URL (если нужны)
    address_parts: Optional[AddressParts] = None


@dataclass
class ReceiptData:
    """Данные для генерации ссылки на квитанцию."""
    product_name: str
    date: str  # ISO формат YYYY-MM-DD
    name: str
    address_parts: AddressParts


@dataclass
class eBayParsedData:
    """Данные, извлеченные из eBay скриншота."""
    name: str
    address_raw: str  # Адрес как строка от GPT
    product: str
    address_parts: AddressParts  # Разобранные компоненты для URL

