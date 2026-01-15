# receipts_config.py

"""
Конфиг для всех квитанций (макеты на Тильде).
Сюда добавляем новые магазины: URL + CSS-селектор блока.
"""

RECEIPT_LAYOUTS = {
    "amazon": {
        # Базовый URL страницы макета на Тильде
        "base_url": "https://amzrcpt.tilda.ws/amazon",
        # CSS-селектор блока, который нужно скриншотить
        "block_selector": "div.t396__group.tn-group.tn-group__1032321626175370363792646060.t396__group-flex",
    },

    "bestbuy": {
        "base_url": "https://amzrcpt.tilda.ws/bestbuy2",
        # ИСПРАВЛЕНО: Используем новый ID, который появился в вашем последнем скриншоте.
        "block_selector": "div.t396__group.tn-group.tn-group__1032528881175388348417022430.t396__group-flex",
    },

    # Можно добавить Target, Walmart и т.д. просто дописав новые ключи.
}