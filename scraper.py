"""Парсер каталога книг с сайта Books to Scrape (http://books.toscrape.com).

Скрипт умеет:
* собирать данные об одной книге (``get_book_data``);
* обходить все страницы каталога и собирать данные обо всех книгах
  (``scrape_books``) с опциональным сохранением в ``books_data.txt``;
* запускать сбор по расписанию каждый день в заданное время
  (``run_scheduler``).

Примеры запуска из терминала::

    python scraper.py --once              # один сбор прямо сейчас
    python scraper.py --at 19:00          # ежедневный сбор в 19:00
"""

import argparse
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import requests
import schedule
from bs4 import BeautifulSoup

BASE_URL = "http://books.toscrape.com/"
CATALOGUE_PAGE_URL = BASE_URL + "catalogue/page-{}.html"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "artifacts" / "books_data.txt"
REQUEST_TIMEOUT_SEC = 15
DEFAULT_WORKERS = 10
SCHEDULER_CHECK_INTERVAL_SEC = 60
DEFAULT_RUN_TIME = "19:00"

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

logger = logging.getLogger(__name__)


def fetch_soup(url: str, session: requests.Session | None = None) -> BeautifulSoup:
    """Скачать страницу и вернуть её разобранное HTML-дерево.

    Args:
        url: адрес страницы.
        session: необязательная сессия ``requests`` для переиспользования
            соединений; если не передана, используется ``requests.get``.

    Returns:
        Объект ``BeautifulSoup`` со страницей.

    Raises:
        requests.HTTPError: если сервер вернул код ошибки (4xx/5xx).
        requests.RequestException: при сетевых ошибках.
    """
    client = session or requests
    response = client.get(url, timeout=REQUEST_TIMEOUT_SEC)
    response.raise_for_status()
    # Берём байты, а не response.text: сайт не указывает кодировку,
    # и requests иначе ломает символ фунта «£».
    return BeautifulSoup(response.content, "html.parser")


def parse_price(text: str) -> float:
    """Преобразовать строку цены вида ``'£51.77'`` в число ``51.77``."""
    return float(re.sub(r"[^\d.]", "", text))


def parse_availability(text: str) -> int:
    """Достать количество экземпляров из строки ``'In stock (22 available)'``.

    Returns:
        Количество книг в наличии, либо 0, если число в строке не найдено.
    """
    match = re.search(r"\d+", text)
    return int(match.group()) if match else 0


def parse_book_page(soup: BeautifulSoup, book_url: str = "") -> dict:
    """Извлечь данные о книге из уже скачанной страницы товара.

    Args:
        soup: HTML-дерево страницы книги.
        book_url: адрес страницы (сохраняется в результат для справки).

    Returns:
        Словарь с ключами ``url``, ``title``, ``price``, ``rating``,
        ``available``, ``description``, ``category`` и ``product_info``
        (все строки таблицы Product Information как ``{заголовок: значение}``).
    """
    main = soup.select_one("div.product_main")
    rating_tag = main.select_one("p.star-rating")
    rating_word = next(
        (cls for cls in rating_tag["class"] if cls in RATING_WORDS), None
    )
    description_tag = soup.select_one("#product_description + p")
    breadcrumbs = soup.select("ul.breadcrumb li a")
    product_info = {
        row.th.get_text(strip=True): row.td.get_text(strip=True)
        for row in soup.select("table.table-striped tr")
    }

    return {
        "url": book_url,
        "title": main.h1.get_text(strip=True),
        "price": parse_price(main.select_one("p.price_color").get_text()),
        "rating": RATING_WORDS.get(rating_word, 0),
        "available": parse_availability(
            main.select_one("p.availability").get_text()
        ),
        "description": (
            description_tag.get_text(strip=True) if description_tag else ""
        ),
        "category": breadcrumbs[-1].get_text(strip=True) if breadcrumbs else "",
        "product_info": product_info,
    }


def get_book_data(book_url: str, session: requests.Session | None = None) -> dict:
    """Собрать всю информацию об одной книге по ссылке на её страницу.

    Args:
        book_url: полный адрес страницы книги, например
            ``http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html``.
        session: необязательная сессия ``requests``.

    Returns:
        Словарь с названием, ценой (float, в фунтах), рейтингом (1–5),
        количеством в наличии, описанием, категорией и таблицей
        Product Information. Формат — см. ``parse_book_page``.
    """
    return parse_book_page(fetch_soup(book_url, session), book_url)


def get_book_links(page_soup: BeautifulSoup, page_url: str) -> list[str]:
    """Вернуть абсолютные ссылки на все книги со страницы каталога.

    Args:
        page_soup: HTML-дерево страницы каталога.
        page_url: адрес этой страницы (нужен для превращения
            относительных ссылок в абсолютные).

    Returns:
        Список URL страниц книг в порядке их следования на странице.
    """
    return [
        urljoin(page_url, link["href"])
        for link in page_soup.select("article.product_pod h3 a")
    ]


def collect_all_book_links(session: requests.Session) -> list[str]:
    """Пройти по страницам каталога ``page-1``, ``page-2``, ... и собрать ссылки.

    Обход идёт, пока на странице есть кнопка «next», поэтому число страниц
    не зашито в код.

    Args:
        session: сессия ``requests``.

    Returns:
        Список ссылок на все книги каталога.
    """
    links = []
    page_number = 1
    while True:
        page_url = CATALOGUE_PAGE_URL.format(page_number)
        page_soup = fetch_soup(page_url, session)
        links = links + get_book_links(page_soup, page_url)
        logger.debug("Страница %d: всего ссылок %d", page_number, len(links))
        if page_soup.select_one("li.next a") is None:
            return links
        page_number += 1


def save_books(books: list[dict], output_path: Path) -> None:
    """Сохранить список книг в текстовый файл (одна книга — одна JSON-строка).

    Args:
        books: список словарей, полученных из ``get_book_data``.
        output_path: путь к файлу; недостающие папки будут созданы.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        for book in books:
            file.write(json.dumps(book, ensure_ascii=False) + "\n")
    logger.info("Сохранено %d книг в %s", len(books), output_path)


def scrape_books(
    is_save: bool = False,
    output_path: Path | str = DEFAULT_OUTPUT,
    max_workers: int = DEFAULT_WORKERS,
) -> list[dict]:
    """Собрать данные обо всех книгах каталога Books to Scrape.

    Сначала обходит все страницы каталога и собирает ссылки на книги,
    затем параллельно скачивает страницы книг через ``get_book_data``.

    Args:
        is_save: если ``True``, результат сохраняется в ``output_path``;
            если ``False``, шаг сохранения пропускается.
        output_path: путь к файлу для сохранения
            (по умолчанию ``artifacts/books_data.txt`` рядом со скриптом).
        max_workers: число потоков для параллельной загрузки книг.

    Returns:
        Список словарей с данными о книгах (порядок как в каталоге).
    """
    with requests.Session() as session:
        links = collect_all_book_links(session)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            books = list(pool.map(lambda url: get_book_data(url, session), links))

    if is_save:
        save_books(books, Path(output_path))
    return books


def scheduled_job(output_path: Path | str = DEFAULT_OUTPUT) -> None:
    """Задача для планировщика: собрать все книги и сохранить в файл.

    Ошибки сети логируются, а не прерывают планировщик — следующая
    попытка будет в следующий запланированный момент.
    """
    logger.info("Запуск планового сбора данных")
    try:
        books = scrape_books(is_save=True, output_path=output_path)
    except requests.RequestException:
        logger.exception("Сбор данных не удался")
        return
    logger.info("Плановый сбор завершён: %d книг", len(books))


def run_scheduler(
    run_at: str = DEFAULT_RUN_TIME,
    check_interval: int = SCHEDULER_CHECK_INTERVAL_SEC,
    output_path: Path | str = DEFAULT_OUTPUT,
) -> None:
    """Запускать сбор данных каждый день в заданное время (бесконечный цикл).

    Чтобы не нагружать систему, наступление времени проверяется
    не постоянно, а раз в ``check_interval`` секунд.

    Args:
        run_at: время запуска в формате ``"ЧЧ:ММ"``.
        check_interval: пауза между проверками расписания, в секундах.
        output_path: куда сохранять результат.
    """
    schedule.every().day.at(run_at).do(scheduled_job, output_path=output_path)
    logger.info("Планировщик запущен: ежедневно в %s", run_at)
    while True:
        schedule.run_pending()
        time.sleep(check_interval)


def parse_args() -> argparse.Namespace:
    """Разобрать аргументы командной строки."""
    parser = argparse.ArgumentParser(description="Парсер books.toscrape.com")
    parser.add_argument(
        "--once", action="store_true", help="выполнить один сбор и выйти"
    )
    parser.add_argument(
        "--at", default=DEFAULT_RUN_TIME, help="время ежедневного запуска ЧЧ:ММ"
    )
    parser.add_argument(
        "--output", default=str(DEFAULT_OUTPUT), help="путь к файлу результата"
    )
    return parser.parse_args()


def main() -> None:
    """Точка входа: один сбор (``--once``) или ежедневный запуск по расписанию."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = parse_args()
    if args.once:
        books = scrape_books(is_save=True, output_path=args.output)
        print(f"Собрано книг: {len(books)}")
        return
    run_scheduler(run_at=args.at, output_path=args.output)


if __name__ == "__main__":
    main()
