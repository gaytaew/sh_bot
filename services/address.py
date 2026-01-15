"""
Сервис для работы с адресами: искажение, парсинг, генерация телефонов.
"""
import logging
import re
import random
import string
from typing import Tuple

from constants import STREET_SYNONYMS, DIRECTION_SYNONYMS
from models import AddressParts

logger = logging.getLogger(__name__)


def col_to_letter(col: int) -> str:
    """Конвертировать номер колонки в букву: 1 -> A, 2 -> B, ..."""
    result = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        result = chr(65 + rem) + result
    return result


def _perturb_word_letters(word: str, max_changes: int = 1) -> str:
    """
    Слегка коверкать буквы в слове (макс. 1 изменение) или добавлять лишнюю букву (50/50).
    """
    if not word or len(word) < 4:
        return word

    if any(char.isdigit() for char in word):
        return word  # НЕ ТРОГАЕМ СЛОВА С ЦИФРАМИ (НОМЕРА ДОМОВ/КВАРТИР)

    chars = list(word)
    letter_positions = [i for i, c in enumerate(chars) if c.isalpha()]
    
    if not letter_positions:
        return word

    # 50% шанс изменить букву, 50% шанс добавить букву
    if random.random() < 0.5:
        # СЛУЧАЙ 1: Изменение существующей буквы (макс. 1)
        pos = random.choice(letter_positions)
        old = chars[pos]
        if old.isupper():
            alphabet = string.ascii_uppercase
        else:
            alphabet = string.ascii_lowercase
        candidates = [ch for ch in alphabet if ch != old]
        if candidates:
            chars[pos] = random.choice(candidates)
    else:
        # СЛУЧАЙ 2: Добавление лишней буквы
        insert_pos = random.randint(1, len(chars)) 
        
        if insert_pos > 0 and chars[insert_pos - 1].isupper():
            new_char = random.choice(string.ascii_uppercase)
        else:
            new_char = random.choice(string.ascii_lowercase)
            
        chars.insert(insert_pos, new_char)

    return "".join(chars)


def perturb_name(full_name: str) -> str:
    """
    Правила:
    - Максимум 1 изменение (буква/добавление) в каждом слове.
    - 50% шанс поменять местами имя и фамилию.
    """
    if not full_name:
        return full_name

    words = full_name.split()
    
    # 50% шанс поменять местами имя/фамилию (если минимум 2 слова)
    if len(words) >= 2 and random.random() < 0.5:
        words[0], words[1] = words[1], words[0]

    # Коверкаем каждое слово с макс. 1 изменением
    mutated = [_perturb_word_letters(w, max_changes=1) for w in words]
    return " ".join(mutated)


def _perturb_city(city: str) -> str:
    """
    Город: максимум 1 изменение (буква/добавление) и не первая буква,
    только в 50% случаев.
    """
    if not city or len(city) < 4:
        return city
        
    if any(char.isdigit() for char in city):
        return city  # НЕ ТРОГАЕМ СЛОВА С ЦИФРАМИ

    # Новое правило: Коверкаем только в 50% случаев
    if random.random() < 0.5:
        return city
        
    chars = list(city)
    letter_positions = [i for i, c in enumerate(chars) if c.isalpha()]

    # Убираем первую букву из кандидатов на изменение
    change_positions = [i for i in letter_positions if i != 0]
    
    if not change_positions:
        return city
        
    # 50% шанс изменить букву, 50% шанс добавить букву
    if random.random() < 0.5:
        # СЛУЧАЙ 1: Изменение существующей буквы
        pos = random.choice(change_positions)
        old = chars[pos]
        if old.isupper():
            alphabet = string.ascii_uppercase
        else:
            alphabet = string.ascii_lowercase
        candidates = [ch for ch in alphabet if ch != old]
        if candidates:
            chars[pos] = random.choice(candidates)
    else:
        # СЛУЧАЙ 2: Добавление лишней буквы
        insert_pos = random.randint(1, len(chars)) 
        
        if insert_pos > 0 and chars[insert_pos - 1].isupper():
            new_char = random.choice(string.ascii_uppercase)
        else:
            new_char = random.choice(string.ascii_lowercase)
            
        chars.insert(insert_pos, new_char)

    return "".join(chars)


def replace_with_synonym(word, synonym_map):
    """
    Заменяет слово на синоним из карты, если слово найдено в карте (без учета регистра/точек).
    """
    upper_word = word.upper().strip().replace('.', '')
    # Объединяем все глобальные карты синонимов
    full_map = {
        **STREET_SYNONYMS,
        **DIRECTION_SYNONYMS,
    }

    if upper_word in full_map:
        return random.choice(full_map[upper_word])
    return word


def perturb_address(
    addr1: str, addr2: str, city: str, state: str, zip_code: str
) -> str:
    """
    Коверкает адрес, собирает его в одну строку для записи в GS (COL_ADDRESS).
    """
    mutated_parts = []

    # 1. КОВЕРКАНИЕ УЛИЦЫ (addr1)
    street_parts = addr1.split()
    new_street_parts = []
    
    for word in street_parts:
        if any(char.isdigit() for char in word):
            new_street_parts.append(word)  # Сохраняем номера домов/Line 1
            continue
        
        upper_word = word.upper().replace('.', '')
        
        # Замена синонимов (Rd, St, N, S, APT и т.д.)
        if upper_word in STREET_SYNONYMS or upper_word in DIRECTION_SYNONYMS:
            new_street_parts.append(replace_with_synonym(word, {})) 
        else:
            # Коверкаем только основные слова в названии улицы
            new_street_parts.append(_perturb_word_letters(word, max_changes=1))

    mutated_parts.append(" ".join(new_street_parts))

    # 2. КОВЕРКАНИЕ LINE 2 (addr2)
    if addr2:
        line2_parts = addr2.split()
        new_line2_parts = []
        for word in line2_parts:
             if any(char.isdigit() for char in word):
                new_line2_parts.append(word)  # Сохраняем номера квартир
             else:
                # Замена синонимов (Apt, Unit и т.д.)
                upper_word = word.upper().replace('.', '')
                if upper_word in STREET_SYNONYMS: 
                    new_line2_parts.append(replace_with_synonym(word, {}))
                else:
                    new_line2_parts.append(_perturb_city(word)) 
        mutated_parts.append(" ".join(new_line2_parts)) 

    # 3. КОВЕРКАНИЕ ГОРОДА
    city_words = city.split()
    # Коверкаем только ПЕРВОЕ слово города, в 50% случаев
    if city_words:
        city_words[0] = _perturb_city(city_words[0])
    mutated_parts.append(" ".join(city_words))

    # 4. Добавляем неискаженные State/Zip
    mutated_parts.append(f"{state} {zip_code}")

    return ", ".join([p.strip() for p in mutated_parts if p.strip()])


def parse_zip_and_city(address: str) -> Tuple[str, str]:
    """
    Выделить ZIP (5 цифр) и город из адреса.
    Ищем паттерн: City, ST ZIP или ZIP в конце строки.
    """
    address = address or ""
    
    # Паттерн 1: City, ST ZIP (наиболее распространенный)
    # Пример: "Brownsville, OR 97327"
    pattern1 = r'([A-Za-z\s]+),\s*([A-Z]{2})\s+(\d{5})\b'
    match1 = re.search(pattern1, address)
    if match1:
        city = match1.group(1).strip()
        zip_code = match1.group(3)
        return zip_code, city
    
    # Паттерн 2: ZIP в конце строки (5 цифр)
    zip_match = re.search(r'(\b\d{5})\b', address)
    zip_code = zip_match.group(1) if zip_match else "00000"
    
    # Ищем город перед штатом и ZIP
    # Пример: "Brownsville, OR 97327"
    city_match = re.search(r'([A-Za-z\s]+),\s*([A-Z]{2})\s*' + re.escape(zip_code), address)
    if city_match:
        city = city_match.group(1).strip()
        return zip_code, city
    
    return zip_code, ""


def random_digits(n: int) -> str:
    """Сгенерировать n цифр без слишком простых последовательностей."""
    while True:
        digits = ''.join(random.choices('0123456789', k=n))
        if not re.match(r'(123456|654321|000000|111111|222222|333333|444444|555555|666666|777777|888888|999999)', digits):
            return digits


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


def parse_ebay_address(address_raw: str) -> AddressParts:
    """
    Парсит адрес из строки (от GPT) на компоненты для eBay flow.
    Используется только для eBay, где адрес приходит как одна строка.
    
    Пример: "29160 Sheep Head Rd, Brownsville, OR 97327"
    Результат: addr1="29160 Sheep Head Rd", city="Brownsville", state="OR", zip="97327"
    """
    address_raw = address_raw or ""
    
    # Извлекаем ZIP и город
    zip_code, city_name = parse_zip_and_city(address_raw)
    
    # Извлекаем штат (2 заглавные буквы перед ZIP)
    state_pattern = r'\b([A-Z]{2})\s+' + re.escape(zip_code)
    state_match = re.search(state_pattern, address_raw)
    state_code = state_match.group(1) if state_match else ""
    
    # Если не нашли через паттерн, ищем любой штат в адресе
    if not state_code:
        state_match = re.search(r'\b([A-Z]{2})\b', address_raw)
        state_code = state_match.group(1) if state_match else ""
    
    # Формируем addr1: все что до города, штата и ZIP
    # Удаляем паттерн "City, ST ZIP" или "City ST ZIP"
    addr1_url = address_raw
    
    # Удаляем паттерн с городом, штатом и ZIP
    if city_name and state_code and zip_code:
        # Удаляем "City, ST ZIP" или "City ST ZIP"
        pattern_to_remove = rf'{re.escape(city_name)}\s*,\s*{re.escape(state_code)}\s+{re.escape(zip_code)}'
        addr1_url = re.sub(pattern_to_remove, '', addr1_url, flags=re.IGNORECASE).strip()
    else:
        # Если не нашли все компоненты, удаляем по отдельности
        if zip_code and zip_code != "00000":
            addr1_url = re.sub(r'\b' + re.escape(zip_code) + r'\b', '', addr1_url).strip()
        if state_code:
            addr1_url = re.sub(r'\b' + re.escape(state_code) + r'\b', '', addr1_url, flags=re.IGNORECASE).strip()
        if city_name:
            addr1_url = re.sub(r'\b' + re.escape(city_name) + r'\b', '', addr1_url, flags=re.IGNORECASE).strip()
    
    # Очищаем лишние символы
    addr1_url = addr1_url.replace('United States', '').replace(',', ' ').replace('  ', ' ').strip()
    
    addr2_url = ""  # Line 2 остается пустым для eBay
    
    return AddressParts(
        addr1=addr1_url,
        addr2=addr2_url,
        city=city_name,
        state=state_code,
        zip_code=zip_code,
    )

