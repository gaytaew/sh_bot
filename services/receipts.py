"""
Сервис для генерации ссылок на квитанции.
"""
import logging
from datetime import datetime
from urllib.parse import urlencode, quote

from receipts_config import RECEIPT_LAYOUTS
from receipt_product_map import PRODUCT_ID_MAP
from models import ReceiptData, AddressParts

logger = logging.getLogger(__name__)


class ReceiptService:
    """Сервис для работы с квитанциями."""
    
    def build_receipt_url(self, shop_key: str, receipt_data: ReceiptData) -> str:
        """
        Генерирует ссылку на макет квитанции, используя shop_key.
        
        ВНИМАНИЕ: Для генерации URL используются ЧИСТЫЕ КОМПОНЕНТЫ АДРЕСА.
        """
        layout = RECEIPT_LAYOUTS.get(shop_key)
        if not layout:
            raise ValueError(f"Неизвестный ключ магазина: {shop_key}")
            
        base_url = layout["base_url"]

        # 1. ПОЛУЧАЕМ ID ТОВАРА ДЛЯ ТИЛЬДЫ
        product_tilda_id = PRODUCT_ID_MAP.get(receipt_data.product_name)
        
        if not product_tilda_id:
             raise ValueError(
                 f"Товар '{receipt_data.product_name}' не найден в маппинге PRODUCT_ID_MAP. "
                 f"Обновите receipt_product_map.py."
             )
        
        # 2. ПАРСИНГ ДАТЫ
        date_iso = ""
        if receipt_data.date:
            try:
                date_obj = datetime.strptime(receipt_data.date, "%d.%m.%Y")
                date_iso = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                date_iso = ""

        # 3. ФОРМИРОВАНИЕ ПАРАМЕТРОВ
        params = {
            "product": product_tilda_id,
            "date": date_iso,
            "name": receipt_data.name,
            "addr1": receipt_data.address_parts.addr1,
            "addr2": receipt_data.address_parts.addr2, 
            "city": receipt_data.address_parts.city, 
            "zip": receipt_data.address_parts.zip_code,
            "state": receipt_data.address_parts.state,
        }

        # Ключевой момент: quote_via=quote, иначе URL будет с +
        query = urlencode(params, quote_via=quote)

        return f"{base_url}?{query}"
    
    def build_receipt_urls_for_all_shops(
        self, receipt_data: ReceiptData
    ) -> dict[str, str]:
        """
        Генерирует ссылки на квитанции для всех доступных магазинов.
        Возвращает словарь {shop_key: url} или пустую строку при ошибке.
        """
        results = {}
        
        for shop_key in RECEIPT_LAYOUTS.keys():
            try:
                url = self.build_receipt_url(shop_key, receipt_data)
                results[shop_key] = url
            except Exception as e:
                logger.error(f"Ошибка генерации URL для {shop_key}: {e}")
                results[shop_key] = ""
        
        return results


# Глобальный экземпляр сервиса
_receipt_service = None


def get_receipt_service() -> ReceiptService:
    """Получить глобальный экземпляр сервиса квитанций."""
    global _receipt_service
    if _receipt_service is None:
        _receipt_service = ReceiptService()
    return _receipt_service

