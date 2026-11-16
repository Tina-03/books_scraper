# Books Scraper

Парсер каталога книг с учебного сайта [Books to Scrape](http://books.toscrape.com) — домашнее задание 3 по Python для Data Science (парсинг, Git, тестирование).

## Цель

Автоматически собирать данные обо всех книгах каталога (название, цена, рейтинг, наличие, описание, категория, таблица Product Information), сохранять их в текстовый файл и обновлять выгрузку ежедневно по расписанию.

## Структура проекта

```
books_scraper/
├── artifacts/
│   └── books_data.txt        # результат парсинга: 1000 книг, по одной JSON-строке на книгу
├── notebooks/
│   └── HW_03_python_ds.ipynb # заполненный ноутбук с выводами ячеек
├── tests/
│   └── test_scraper.py       # автотесты pytest
├── scraper.py                # основной скрипт парсера
├── pytest.ini                # настройки pytest
├── requirements.txt
├── .gitignore
└── README.md
```

## Установка

```bash
git clone <ссылка на репозиторий>
cd books_scraper
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Запуск

```bash
# один сбор данных прямо сейчас -> artifacts/books_data.txt
python scraper.py --once

# ежедневный автоматический сбор в 19:00 (бесконечный цикл, остановка Ctrl+C)
python scraper.py --at 19:00

# свой путь к файлу результата
python scraper.py --once --output my_books.txt
```

Использование из Python:

```python
from scraper import get_book_data, scrape_books

book = get_book_data("http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html")
books = scrape_books(is_save=True)   # список из 1000 словарей + сохранение в файл
```

## Тесты

```bash
pytest -v                 # все тесты (2 из них обращаются к сайту)
pytest -m "not network"   # только офлайн-тесты
```

## Формат данных

Каждая строка `artifacts/books_data.txt` — JSON-объект:

```json
{"url": "...", "title": "A Light in the Attic", "price": 51.77, "rating": 3,
 "available": 22, "description": "...", "category": "Poetry",
 "product_info": {"UPC": "a897fe39b1053632", "Product Type": "Books", "...": "..."}}
```

## Используемые библиотеки

- `requests` — HTTP-запросы к сайту;
- `beautifulsoup4` — разбор HTML;
- `schedule` — ежедневный запуск по расписанию;
- `pytest` — автотесты;
- стандартная библиотека: `concurrent.futures` (параллельная загрузка страниц), `json`, `re`, `argparse`, `logging`.
