"""Fixtures for the benchmark corpus.

The oracle here sends **the same headers the interface sends** — same run store,
same defect list. That is not a detail, it is the difference between an honest
oracle and a rigged one.

Consider the inflated-counter defect. If the oracle omitted the defect header it
would receive the healthy answer, catch the disagreement instantly, and prove
nothing: no real oracle gets to consult a copy of the product that is known to be
correct. Sending the same headers means the API lies to the oracle exactly as it
lies to the page — so the claim has to be **self-checkable**: "the reported total
equals the number of rows you can actually page through" is a question the API
answers against itself, and no privileged knowledge is involved.

The rule that an oracle must ask the API the question the UI asked is load-bearing
for a second reason: it is also what keeps the benchmark
from measuring the corpus author's access rather than the framework's power.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import pytest

from testence.api import ApiClient

DEFECTS = os.environ.get("TESTENCE_SUT_DEFECTS", "")
RUN = os.environ.get("TESTENCE_SUT_RUN", "canonical")
BASE = os.environ.get("TESTENCE_BASE_URL", "http://127.0.0.1:8800").rstrip("/")


@dataclass
class Sut:
    base: str
    run: str
    defects: str

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Run": self.run, "X-Defects": self.defects}

    def url(self, **params: Any) -> str:
        query = {"run": self.run}
        if self.defects:
            query["defects"] = self.defects
        query.update({k: str(v) for k, v in params.items() if v not in (None, "")})
        return f"{self.base}/?{urlencode(query)}"

    def rows_page(self, client: ApiClient, **params: Any) -> dict:
        query = urlencode({k: str(v) for k, v in params.items() if v not in (None, "")})
        response = client.get(f"/api/rows?{query}", headers=self.headers)
        assert response.ok, f"oracle call failed: {response.status} {response.body[:200]}"
        body = response.json
        assert isinstance(body, dict), f"expected a page object, got {type(body).__name__}"
        return body

    def all_rows(self, client: ApiClient, **params: Any) -> list[dict]:
        """Every row the API will actually hand over, by paging to exhaustion.

        Deliberately not "read the total and trust it": the total is one of the
        things under test. Paging until a page comes back short is what makes the
        counter claim self-checkable.
        """
        collected: list[dict] = []
        page = 1
        while page <= 50:  # a loop bound, not an expectation
            body = self.rows_page(client, page=page, **params)
            collected.extend(body["rows"])
            if len(body["rows"]) < body["pageSize"]:
                break
            page += 1
        return collected


@pytest.fixture(scope="session")
def sut() -> Sut:
    return Sut(BASE, RUN, DEFECTS)


@pytest.fixture(scope="session")
def oracle(testence_settings) -> ApiClient:
    """A plain client against the target; the target has no authentication."""
    return ApiClient(BASE, verify_tls=testence_settings.verify_tls)
