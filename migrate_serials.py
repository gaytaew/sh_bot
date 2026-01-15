"""
Скрипт для массовой замены серийных номеров.
Задачи:
1. Найти товар "Cefaly" (или другой) в листе "Товары".
2. Пройтись по всем серийникам.
3. Если серийник содержит "S", заменить ПЕРВУЮ "S" на "8".
4. Обновить данные в Google Sheets.
"""

import logging
from services.google_sheets import get_sheets_service
from services.address import col_to_letter

# Настройка логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TARGET_PRODUCT = "Cefaly"  # Имя столбца в листе Товары

def main():
    print(f"--- Запуск миграции для товара: {TARGET_PRODUCT} ---")
    
    # 1. Подключаемся
    sheets = get_sheets_service()
    sheet_products = sheets.sheet_products
    
    # 2. Ищем столбец
    headers = sheet_products.row_values(1)
    
    try:
        # Ищем точное совпадение или без учета регистра
        try:
            col_idx = headers.index(TARGET_PRODUCT) + 1
        except ValueError:
            # Попробуем найти без учета регистра
            col_idx = -1
            for i, h in enumerate(headers):
                if h.lower() == TARGET_PRODUCT.lower():
                    col_idx = i + 1
                    break
            if col_idx == -1:
                print(f"ОШИБКА: Столбец '{TARGET_PRODUCT}' не найден в листе 'Товары'.")
                print(f"Доступные столбцы: {headers}")
                return

        print(f"Столбец найден: {col_idx} ({headers[col_idx-1]})")
        
        # 3. Читаем данные столбца
        # col_values вернет список всех значений, включая заголовок
        all_values = sheet_products.col_values(col_idx)
        header = all_values[0]
        serials = all_values[1:] # Данные без заголовка
        
        updates_count = 0
        new_serials = []
        
        # 4. Обрабатываем
        for s in serials:
            s = s.strip()
            if not s:
                new_serials.append("")
                continue
            
            # Логика замены: первая S -> 8
            if 'S' in s:
                # replace(old, new, count) -> count=1 заменит только первое вхождение
                new_s = s.replace('S', '8', 1)
                
                if new_s != s:
                    # логируем изменение
                    print(f"CHANGE: {s} -> {new_s}")
                    updates_count += 1
                    new_serials.append(new_s)
                else:
                    new_serials.append(s)
            else:
                new_serials.append(s)
        
        if updates_count == 0:
            print("Нет серийников для замены.")
            return

        print(f"Найдено {updates_count} серийников для обновления.")
        confirm = input("Применить изменения в Google Sheets? (yes/no): ")
        
        if confirm.lower() != "yes":
            print("Отменено пользователем.")
            return

        # 5. Записываем обратно
        # Формируем диапазон. Данные начинаются со 2-й строки.
        # Например, если данных 10, то пишем в строки 2..11
        start_row = 2
        end_row = start_row + len(new_serials) - 1
        col_letter = col_to_letter(col_idx)
        
        rng = f"{col_letter}{start_row}:{col_letter}{end_row}"
        
        # update принимает список списков (по строкам)
        # нам нужно превратить ['a', 'b'] в [['a'], ['b']]
        values_to_write = [[val] for val in new_serials]
        
        sheet_products.update(rng, values_to_write)
        print("Успешно обновлено!")

    except Exception as e:
        logger.exception("Произошла ошибка:")
        print(f"CRICAL ERROR: {e}")

if __name__ == "__main__":
    main()
