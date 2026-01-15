"""
Сервис для OCR и GPT обработки eBay скриншотов.
"""
import logging
import json
import aiohttp
import openai
import asyncio

from config import OPENAI_API_KEY, OCR_API_KEY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
Ты ассистент по обработке заказов eBay. Извлеки из текста только следующие поля:

1. Имя — имя и фамилия покупателя (если не найдено — оставь пусто).
2. Адрес — только улица, дом, город, штат, zip (только первые 5 цифр), страна не нужна, не указывай суффикс zip-4.
3. Название наушников — выбери из:
- Openrun Pro 2 Black
- Openrun Pro 2 Orange
- Openrun Pro 2 Silver
- Openswim Pro Gray (указывай Gray, даже если написано Black)
- Openswim Pro Red
- 2025 Opencomm 2 UC USB-C

Формат ответа:
{
    "Имя": "",
    "Адрес": "",
    "Товар": ""
}
Если данные не удалось найти, оставь поле пустым. Не добавляй пояснений, только валидный JSON.
"""


class OCRGPTService:
    """Сервис для OCR и GPT обработки."""
    
    def __init__(self):
        self.openai_client = openai.Client(api_key=OPENAI_API_KEY)
    
    async def ocr_space_file(self, file_path: str) -> dict:
        """Отправить файл в OCR.Space и вернуть JSON-ответ."""
        url = "https://api.ocr.space/parse/image"
        try:
            with open(file_path, "rb") as f:
                timeout = aiohttp.ClientTimeout(total=20)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    form = aiohttp.FormData()
                    form.add_field("apikey", OCR_API_KEY)
                    form.add_field("language", "eng")
                    form.add_field("file", f, filename=file_path, content_type="image/jpeg")
                    logger.info(f"Отправляю {file_path} на OCR...")
                    async with session.post(url, data=form) as resp:
                        text = await resp.text()
                        logger.info(f"OCR raw ответ: {text}")
                        try:
                            return json.loads(text)
                        except Exception as e:
                            logger.error(f"Ошибка при разборе JSON OCR: {e}")
                            return {"ParsedResults": [{"ParsedText": ""}]}
        except Exception as e:
            logger.error(f"Ошибка в ocr_space_file: {e}")
            return {"ParsedResults": [{"ParsedText": ""}]}
    
    def gpt_structured_fields(self, text: str) -> dict:
        """Вызов OpenAI для структурирования текста заказа eBay."""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Распознанный текст:\n{text}"}
                ],
                max_tokens=400,
                temperature=0.7,
            )
            content = response.choices[0].message.content
            logger.info(f"Ответ GPT: {content}")
            data = json.loads(content)
            return data
        except Exception as e:
            logger.error(f"Ошибка в gpt_structured_fields: {e}")
            return {"Имя": "", "Адрес": "", "Товар": ""}
    
    async def process_ebay_photo(self, file_path: str) -> dict:
        """
        Обработать фото eBay: OCR -> GPT -> структурированные данные.
        Возвращает словарь с полями: Имя, Адрес, Товар.
        """
        ocr_result = await self.ocr_space_file(file_path)
        parsed_text = ocr_result.get("ParsedResults", [{}])[0].get("ParsedText", "")
        
        if not parsed_text or not parsed_text.strip():
            logger.warning("OCR не вернул текст из изображения")
            return {"Имя": "", "Адрес": "", "Товар": ""}
        
        structured = await asyncio.to_thread(self.gpt_structured_fields, parsed_text)
        logger.info(f"Структурированные данные от GPT: {structured}")
        
        # Нормализуем значения (убираем пробелы, проверяем на None)
        structured_normalized = {
            "Имя": (structured.get("Имя") or "").strip(),
            "Адрес": (structured.get("Адрес") or "").strip(),
            "Товар": (structured.get("Товар") or "").strip(),
        }
        
        logger.info(f"Нормализованные данные: {structured_normalized}")
        
        return structured_normalized


# Глобальный экземпляр сервиса
_ocr_gpt_service = None


def get_ocr_gpt_service() -> OCRGPTService:
    """Получить глобальный экземпляр сервиса OCR/GPT."""
    global _ocr_gpt_service
    if _ocr_gpt_service is None:
        _ocr_gpt_service = OCRGPTService()
    return _ocr_gpt_service

