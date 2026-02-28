"""Tests for scraper.py using mocked HTTP responses."""

import unittest
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

import scraper


# ---------------------------------------------------------------------------
# Sample HTML fixtures
# ---------------------------------------------------------------------------

INDEX_HTML = """
<html><body>
  <a href="/atc_ddd_index/?code=A">A ALIMENTARY TRACT AND METABOLISM</a>
  <a href="/atc_ddd_index/?code=B">B BLOOD AND BLOOD FORMING ORGANS</a>
  <a href="/other-page">Ignore this link</a>
</body></html>
"""

LEVEL2_HTML = """
<html><body>
  <a href="/atc_ddd_index/?code=A01">A01 STOMATOLOGICAL PREPARATIONS</a>
  <a href="/atc_ddd_index/?code=A02">A02 DRUGS FOR ACID RELATED DISORDERS</a>
</body></html>
"""

LEAF_HTML = """
<html><body>
  <table class="atcdetails">
    <tr>
      <th>ATC code</th><th>Name</th><th>DDD</th><th>U</th><th>Adm.R</th><th>Note</th>
    </tr>
    <tr>
      <td>A01AA01</td><td>sodium fluoride</td><td>1.1</td><td>mg F-</td><td>O</td><td></td>
    </tr>
    <tr>
      <td>A01AA02</td><td>sodium monofluorophosphate</td><td></td><td></td><td></td><td></td>
    </tr>
  </table>
</body></html>
"""

LEAF_NO_NOTE_HTML = """
<html><body>
  <table class="atcdetails">
    <tr>
      <th>ATC code</th><th>Name</th><th>DDD</th><th>U</th><th>Adm.R</th>
    </tr>
    <tr>
      <td>B01AA03</td><td>warfarin</td><td>7.5</td><td>mg</td><td>O</td>
    </tr>
  </table>
</body></html>
"""


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestGetAtcLinks(unittest.TestCase):
    def test_returns_atc_links_only(self):
        links = scraper.get_atc_links(_soup(INDEX_HTML))
        urls = [u for u, _ in links]
        self.assertEqual(len(links), 2)
        self.assertTrue(all("/atc_ddd_index/?code=" in u for u in urls))

    def test_returns_full_urls(self):
        links = scraper.get_atc_links(_soup(INDEX_HTML))
        for url, _ in links:
            self.assertTrue(url.startswith("https://"), url)

    def test_link_text_captured(self):
        links = scraper.get_atc_links(_soup(INDEX_HTML))
        texts = [t for _, t in links]
        self.assertIn("A ALIMENTARY TRACT AND METABOLISM", texts)


class TestIsLeafPage(unittest.TestCase):
    def test_leaf_page_detected(self):
        self.assertTrue(scraper.is_leaf_page(_soup(LEAF_HTML)))

    def test_non_leaf_page(self):
        self.assertFalse(scraper.is_leaf_page(_soup(INDEX_HTML)))


class TestParseDDDTable(unittest.TestCase):
    def test_parses_two_rows(self):
        records = scraper.parse_ddd_table(_soup(LEAF_HTML))
        self.assertEqual(len(records), 2)

    def test_first_record_fields(self):
        records = scraper.parse_ddd_table(_soup(LEAF_HTML))
        r = records[0]
        self.assertEqual(r["atc_code"], "A01AA01")
        self.assertEqual(r["drug_name"], "sodium fluoride")
        self.assertEqual(r["ddd_value"], "1.1")
        self.assertEqual(r["ddd_unit"], "mg F-")
        self.assertEqual(r["adm_route"], "O")
        self.assertEqual(r["note"], "")

    def test_skips_header_row(self):
        records = scraper.parse_ddd_table(_soup(LEAF_HTML))
        atc_codes = [r["atc_code"] for r in records]
        self.assertNotIn("ATC code", atc_codes)

    def test_no_table_returns_empty(self):
        records = scraper.parse_ddd_table(_soup(INDEX_HTML))
        self.assertEqual(records, [])

    def test_table_without_note_column(self):
        records = scraper.parse_ddd_table(_soup(LEAF_NO_NOTE_HTML))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["note"], "")


class TestGetPage(unittest.TestCase):
    def test_returns_soup_on_success(self):
        mock_resp = MagicMock()
        mock_resp.text = INDEX_HTML
        mock_resp.raise_for_status = MagicMock()
        session = MagicMock()
        session.get.return_value = mock_resp

        soup = scraper.get_page("http://example.com", session)
        self.assertIsNotNone(soup)
        self.assertIsInstance(soup, BeautifulSoup)

    def test_returns_none_on_request_error(self):
        import requests as req
        session = MagicMock()
        session.get.side_effect = req.RequestException("timeout")

        soup = scraper.get_page("http://example.com", session)
        self.assertIsNone(soup)


class TestScrapeLevel(unittest.TestCase):
    def _make_session(self, pages: dict):
        """Return a mock session that maps URL -> HTML string."""
        def fake_get(url, **kwargs):
            resp = MagicMock()
            resp.text = pages.get(url, "<html><body></body></html>")
            resp.raise_for_status = MagicMock()
            return resp

        session = MagicMock()
        session.get.side_effect = fake_get
        return session

    @patch("scraper.time.sleep")
    def test_recurses_into_sub_levels(self, _mock_sleep):
        leaf_url = f"{scraper.BASE_URL}/atc_ddd_index/?code=A01AA"
        level2_url = f"{scraper.BASE_URL}/atc_ddd_index/?code=A01"
        level2_html = f"""
        <html><body>
          <a href="/atc_ddd_index/?code=A01AA">A01AA Caries prophylactic agents</a>
        </body></html>
        """
        pages = {
            level2_url: level2_html,
            leaf_url: LEAF_HTML,
        }
        session = self._make_session(pages)
        records = scraper.scrape_level(level2_url, session, set())
        self.assertEqual(len(records), 2)

    @patch("scraper.time.sleep")
    def test_visited_urls_not_repeated(self, _mock_sleep):
        url = f"{scraper.BASE_URL}/atc_ddd_index/?code=A01AA"
        pages = {url: LEAF_HTML}
        session = self._make_session(pages)
        visited: set = {url}
        records = scraper.scrape_level(url, session, visited)
        self.assertEqual(records, [])
        session.get.assert_not_called()

    @patch("scraper.time.sleep")
    def test_returns_empty_on_fetch_failure(self, _mock_sleep):
        import requests as req
        session = MagicMock()
        session.get.side_effect = req.RequestException("error")
        records = scraper.scrape_level(
            f"{scraper.BASE_URL}/atc_ddd_index/?code=A01", session, set()
        )
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
