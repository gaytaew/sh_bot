import logging
import json
import re
import random
import aiohttp
import openai
import string # Добавлен импорт, так как используется в новой логике

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


def random_digits(n: int) -> str:
    """Сгенерировать n цифр без слишком простых последовательностей."""
    while True:
        digits = ''.join(random.choices('0123456789', k=n))
        if not re.match(r'(123456|654321|000000|111111|222222|333333|444444|555555|666666|777777|888888|999999)', digits):
            return digits


# Файл ebay_utils.py (замените функцию parse_zip_and_city)

def parse_zip_and_city(address: str):
    """
    Выделить ZIP (5 цифр) и город из адреса, ища ZIP в конце строки.
    Это более надежно, чем поиск первого 5-значного числа.
    """
    # Ищем 5 цифр в конце адреса (наиболее вероятно ZIP)
    zip_match = re.search(r'(\b\d{5})\b', address or "")
    zip_code = zip_match.group(1) if zip_match else "00000"
    
    # Ищем Город/Штат, связанный с этим ZIP
    # ([A-Za-z\s]+) — Город
    # \s?[A-Z]{2}\s? — Штат
    city_match = re.search(r'([A-Za-z\s]+),\s?([A-Z]{2})\s?' + re.escape(zip_code), address or "")
    
    city = city_match.group(1).strip() if city_match else ""
    return zip_code, city


def fake_phone(zip_code: str) -> str:
    """
    Сгенерировать фейковый 10-значный телефон на основе ZIP.
    Номер должен быть 10-значным и не начинаться с '1'.
    """
    # 1. Генерация кода города (Area Code - 3 цифры)
    if zip_code and zip_code[0] not in ["0", "1"]:
        # Используем первые 3 цифры ZIP, если они не 0 или 1
        area = zip_code[:3]
    else:
        # Генерируем случайный код города, не начиная с 0 или 1
        area = str(random.randint(200, 999))
        
    # 2. Генерация оставшихся 7 цифр
    rest = random_digits(7)
    
    # 3. Форматирование (Area Code + 7 digits = 10 digits)
    return f"{area}{rest}"


def gpt_structured_fields(text: str) -> dict:
    """Вызов OpenAI для структурирования текста заказа eBay."""
    try:
        client = openai.Client(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
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


async def ocr_space_file(file_path: str) -> dict:
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