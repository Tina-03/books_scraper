"""Автотесты для парсера books.toscrape.com (запуск: ``pytest``)."""

import json

import pytest
from bs4 import BeautifulSoup

import scraper

BOOK_URL = (
    "http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
)
EXPECTED_KEYS = {
    "url",
    "title",
    "price",
    "rating",
    "available",
    "description",
    "category",
    "product_info",
}
TOTAL_BOOKS_ON_SITE = 1000

BOOK_HTML = """
<ul class="breadcrumb">
  <li><a href="/">Home</a></li>
  <li><a href="/books">Books</a></li>
  <li><a href="/poetry">Poetry</a></li>
</ul>
<div class="product_main">
  <h1>Test Book</h1>
  <p class="price_color">£12.50</p>
  <p class="instock availability">In stock (7 available)</p>
  <p class="star-rating Four"></p>
</div>
<div id="product_description"><h2>Product Description</h2></div>
<p>Some description.</p>
<table class="table table-striped">
  <tr><th>UPC</th><td>abc123</td></tr>
  <tr><th>Number of reviews</th><td>0</td></tr>
</table>
"""

CATALOGUE_HTML = """
<article class="product_pod"><h3><a href="book-a_1/index.html">A</a></h3></article>
<article class="product_pod"><h3><a href="book-b_2/index.html">B</a></h3></article>
"""


# ---------- офлайн-тесты (без сети) ----------


def test_parse_book_page_returns_expected_fields():
    soup = BeautifulSoup(BOOK_HTML, "html.parser")

    book = scraper.parse_book_page(soup, "http://example/book")

    assert set(book) == EXPECTED_KEYS
    assert book["title"] == "Test Book"
    assert book["price"] == 12.5
    assert book["rating"] == 4
    assert book["available"] == 7
    assert book["description"] == "Some description."
    assert book["category"] == "Poetry"
    assert book["product_info"] == {"UPC": "abc123", "Number of reviews": "0"}


@pytest.mark.parametrize(
    "text, expected",
    [("In stock (22 available)", 22), ("Out of stock", 0)],
)
def test_parse_availability(text, expected):
    assert scraper.parse_availability(text) == expected


def test_get_book_links_makes_absolute_urls():
    soup = BeautifulSoup(CATALOGUE_HTML, "html.parser")
    page_url = "http://books.toscrape.com/catalogue/page-1.html"

    links = scraper.get_book_links(soup, page_url)

    assert links == [
        "http://books.toscrape.com/catalogue/book-a_1/index.html",
        "http://books.toscrape.com/catalogue/book-b_2/index.html",
    ]


def test_scrape_books_saves_file_only_when_flag_set(monkeypatch, tmp_path):
    links = ["http://x/1", "http://x/2"]
    monkeypatch.setattr(scraper, "collect_all_book_links", lambda session: links)
    monkeypatch.setattr(
        scraper, "get_book_data", lambda url, session=None: {"url": url}
    )
    output = tmp_path / "books_data.txt"

    not_saved = scraper.scrape_books(is_save=False, output_path=output)
    assert not_saved == [{"url": "http://x/1"}, {"url": "http://x/2"}]
    assert not output.exists()

    saved = scraper.scrape_books(is_save=True, output_path=output)
    lines = output.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == saved


# ---------- тесты на живом сайте ----------


@pytest.mark.network
def test_get_book_data_real_page():
    book = scraper.get_book_data(BOOK_URL)

    assert isinstance(book, dict)
    assert set(book) == EXPECTED_KEYS
    assert book["title"] == "A Light in the Attic"
    assert book["price"] == 51.77
    assert book["rating"] == 3
    assert book["product_info"]["UPC"] == "a897fe39b1053632"


@pytest.mark.network
def test_catalogue_contains_all_books():
    with scraper.requests.Session() as session:
        links = scraper.collect_all_book_links(session)

    assert len(links) == TOTAL_BOOKS_ON_SITE
    assert len(set(links)) == TOTAL_BOOKS_ON_SITE
