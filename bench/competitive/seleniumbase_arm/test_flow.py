"""SeleniumBase arm: the same six steps, idiomatic SeleniumBase (pytest mode)."""

import os

from seleniumbase import BaseCase

BASE_URL = os.environ["BENCH_BASE_URL"]


class TestFlow(BaseCase):
    def test_add_a_named_row(self) -> None:
        self.open(f"{BASE_URL}/index.html")
        self.click("#inc")
        self.assert_exact_text("1", "#count")
        self.type('input[placeholder="name"]', "alice")
        self.click("#add")
        self.assert_exact_text("row-alice", "#list li:last-child")
