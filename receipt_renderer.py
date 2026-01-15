# receipt_renderer.py
import asyncio
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote
from playwright.async_api import async_playwright

from receipts_config import RECEIPT_LAYOUTS


class ReceiptRenderError(Exception):
    """Кастомная ошибка рендера квитанции."""
    pass


async def render_receipt_block(shop_key: str, url: str, timeout_ms: int = 60000) -> bytes:
    """
    Открывает страницу квитанции по URL, принудительно заполняет поля
    через Playwright и делает скриншот ТОЛЬКО нужного блока, используя
    скролл до элемента для избежания обрезки.
    """
    layout = RECEIPT_LAYOUTS.get(shop_key)
    if not layout:
        raise ReceiptRenderError(f"Неизвестный макет: {shop_key}")

    selector = layout.get("block_selector")
    if not selector:
        raise ReceiptRenderError(f"Для макета {shop_key} не задан block_selector")

    # --- Парсинг URL ---
    parsed_url = urlparse(url)
    query_params = {k: unquote(v[0].replace('+', ' ')) for k, v in parse_qs(parsed_url.query).items()}
    
    # Собираем адресную строку
    addr_parts = []
    if query_params.get("addr1"): addr_parts.append(query_params.get("addr1"))
    if query_params.get("addr2"): addr_parts.append(query_params.get("addr2"))
    city_line = ""
    if query_params.get("city"): city_line += query_params.get("city")
    if query_params.get("state"): city_line += (city_line and ", " or "") + query_params.get("state")
    if query_params.get("zip"): city_line += (city_line and " " or "") + query_params.get("zip")
    if city_line: addr_parts.append(city_line)
    if addr_parts: addr_parts.append("United States")
    
    full_address = ", ".join(addr_parts)
    
    # --- Запуск Playwright ---
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, timeout=timeout_ms)
        try:
            # Устанавливаем большой viewport, чтобы минимизировать прокрутку
            page = await browser.new_page(
                viewport={"width": 1400, "height": 1800}, 
                java_script_enabled=True,
            )
            page.set_default_timeout(timeout_ms)

            # Открываем страницу
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            
            # 1. СИНХРОНИЗАЦИЯ И ОБНОВЛЕНИЕ ДАННЫХ
            
            if shop_key == "bestbuy":
                update_button_selector = "#updateAllButton"
                
                # Ждем появления формы
                await page.wait_for_selector(update_button_selector, state="visible", timeout=10000)

                # ПРЯМОЕ ЗАПОЛНЕНИЕ ПОЛЕЙ И КЛИК (логика BestBuy)
                
                # Заполнение SELECT и вызов события 'change'
                if query_params.get("product"):
                    await page.select_option("#productSelect", value=query_params.get("product"))
                    await page.evaluate("document.getElementById('productSelect').dispatchEvent(new Event('change', {bubbles: true}))")

                # Заполнение DATE и вызов события 'change'
                if query_params.get("date"):
                    await page.fill("#dateInput", query_params.get("date"))
                    await page.evaluate("document.getElementById('dateInput').dispatchEvent(new Event('change', {bubbles: true}))")

                # Заполнение NAME и вызов события 'input'
                if query_params.get("name"):
                    await page.fill("#nameInput", query_params.get("name"))
                    await page.evaluate("document.getElementById('nameInput').dispatchEvent(new Event('input', {bubbles: true}))")

                # Заполнение ADDRESS и вызов события 'input'
                if full_address:
                    await page.fill("#addressInput", full_address)
                    await page.evaluate("document.getElementById('addressInput').dispatchEvent(new Event('input', {bubbles: true}))")

                # Заполнение STATE и вызов события 'change'
                if query_params.get("state"):
                    await page.select_option("#stateSelect", value=query_params.get("state"))
                    await page.evaluate("document.getElementById('stateSelect').dispatchEvent(new Event('change', {bubbles: true}))")
                
                # Заполнение SN
                await page.fill("#serialNumberInput", query_params.get("sn", ""))
                await page.evaluate("document.getElementById('serialNumberInput').dispatchEvent(new Event('input', {bubbles: true}))")

                # ПРИНУДИТЕЛЬНЫЙ КЛИК ПО КНОПКАМ:
                await page.click("#generateOrderNumberButton", timeout=5000)
                await page.click(update_button_selector, timeout=5000)

            elif shop_key == "amazon":
                # ЛОГИКА AMAZON: Ждем, пока встроенный JS (который ждет 600 мс) завершит работу
                # Amazon JS запускается на DOMContentLoaded, поэтому просто ждем таймаут
                await page.wait_for_timeout(1500) 
                
            else:
                # Для других магазинов просто ждем
                await page.wait_for_timeout(3000)

            # 3. ФИНАЛЬНОЕ НАДЕЖНОЕ ОЖИДАНИЕ (для обоих магазинов)
            
            # Ждем, пока сеть не станет бездействовать (после загрузки картинки)
            await page.wait_for_load_state("networkidle", timeout=10000) # Увеличиваем таймаут
            
            # Ждем финального рендеринга (длительная пауза для стабилизации DOM)
            await page.wait_for_timeout(3000)

            # 4. Скриншот ТОЛЬКО блока, с принудительной прокруткой
            
            block = page.locator(selector)
            
            # Финальное ожидание видимости и стабильности
            await block.wait_for(state="visible", timeout=5000)
            
            count = await block.count()
            if count == 0:
                 raise ReceiptRenderError(
                    f"Блок по селектору '{selector}' не найден на странице {url}"
                )
            
            # Принудительно прокручиваем окно, чтобы элемент не обрезался при скриншоте
            await block.scroll_into_view_if_needed()
            await page.wait_for_timeout(500) # Короткая пауза для отрисовки после скролла

            # Скриншот блока
            screenshot_bytes = await block.screenshot()

            return screenshot_bytes
        finally:
            await browser.close()


# Утилита для локального теста (запуск из консоли, без бота)
if __name__ == "__main__":
    import sys

    async def _test():
        if len(sys.argv) < 3:
            print("Usage: python receipt_renderer.py <shop_key> <url>")
            sys.exit(1)

        shop_key = sys.argv[1]
        url = sys.argv[2]

        img = await render_receipt_block(shop_key, url)
        out_name = f"test_{shop_key}.png"
        with open(out_name, "wb") as f:
            f.write(img)
        print(f"Saved screenshot to {out_name}")

    asyncio.run(_test())