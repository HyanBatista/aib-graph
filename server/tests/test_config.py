import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings import DEV_SECRET_KEY, resolve_secret_key


def test_debug_falls_back_to_the_dev_key():
    assert resolve_secret_key("", debug=True) == DEV_SECRET_KEY


@pytest.mark.parametrize("value", ["", "change-me"])
def test_production_needs_a_strong_secret_key(value):
    with pytest.raises(ImproperlyConfigured):
        resolve_secret_key(value, debug=False)


def test_production_accepts_a_long_key():
    key = "x" * 50
    assert resolve_secret_key(key, debug=False) == key


def test_uploaded_books_are_not_served(client, settings, tmp_path):
    (tmp_path / "media" / "books").mkdir(parents=True)
    (tmp_path / "media" / "books" / "book.pdf").write_bytes(b"%PDF-1.4")
    assert client.get("/media/books/book.pdf").status_code == 404
