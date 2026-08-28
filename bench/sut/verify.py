"""Does each injected behaviour actually behave as its class says?

Not a corpus run and not a test of the framework — a check on the *fixture*. An
item whose flag does nothing would score as a pass and quietly inflate every
metric built on top of it, so each flag is exercised once, headless, and its
observation compared against what the class claims.

    .venv/Scripts/python bench/sut/verify.py            # needs server.py running

Each case runs against **its own store** (`?run=`). The first version of this file
did not, and a case that created a row moved the baseline for the cases after it.
Isolation is not a nicety here: without it the corpus would be
measuring the order its items ran in.

Each case also states what a naive assertion would conclude, because that is the
whole point of the deceptiveness axis: several of these defects leave a page that
looks entirely healthy.
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8800"
DEBOUNCE_SETTLE_MS = 600


def observe(page) -> dict:
    return page.evaluate("""() => ({
        total: document.querySelector('[data-testid=total]')?.textContent,
        rows: document.querySelectorAll('tbody tr[data-key]').length,
        skeletons: document.querySelectorAll('tbody tr.skeleton').length,
        names: [...document.querySelectorAll('tbody tr[data-key] td:first-child')]
                 .map(td => td.textContent),
    })""")


def open_page(page, run: str, params: str = "") -> None:
    """Open the target in an isolated store."""
    query = f"?run={run}" + (f"&{params}" if params else "")
    page.goto(f"{BASE}/{query}", wait_until="domcontentloaded")
    page.wait_for_selector("tbody tr", state="attached")
    page.wait_for_timeout(300)


def type_search(page, text: str) -> None:
    box = page.get_by_role("searchbox")
    box.click()
    box.fill(text)
    page.wait_for_timeout(DEBOUNCE_SETTLE_MS)


def case(name: str, expectation: str, got: object, ok: bool) -> bool:
    mark = "ok  " if ok else "FAIL"
    print(f"  {mark} {name}\n       expected {expectation}\n       got      {got}")
    return ok


def main() -> int:
    results: list[bool] = []
    with sync_playwright() as p:
        # The system Chrome, not Playwright's bundled build: ADR-0008 puts the
        # framework on a real headed Chrome over CDP, and a fixture verified in a
        # different engine would be verifying the wrong thing.
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page()

        print("healthy baseline")
        open_page(page, "healthy")
        base = observe(page)
        results.append(case("unfiltered list", "total 45, 10 rows, 0 skeletons",
                            base, base["total"] == "45" and base["rows"] == 10
                            and base["skeletons"] == 0))
        type_search(page, "ember")
        filtered = observe(page)
        results.append(case("search applies on the first try", "total 2",
                            filtered, filtered["total"] == "2"))

        print("\nD-40 first interaction after load is swallowed")
        open_page(page, "d40", "defects=D-40")
        type_search(page, "ember")
        first = observe(page)
        results.append(case("first search does nothing", "total still 45",
                            first, first["total"] == "45"))
        # The repeat is the whole point: this is what a retry would do, and it works.
        page.get_by_role("searchbox").press("Enter")
        page.wait_for_timeout(DEBOUNCE_SETTLE_MS)
        second = observe(page)
        results.append(case("the identical repeat works", "total 2",
                            second, second["total"] == "2"))

        print("\nD-15 placeholders satisfy a presence check")
        open_page(page, "d15", "defects=D-15")
        stuck = observe(page)
        results.append(case("skeletons never give way", "10 skeletons, 0 real rows",
                            stuck, stuck["skeletons"] == 10 and stuck["rows"] == 0))

        print("\nD-34 a filter in the URL is ignored on a fresh load")
        open_page(page, "d34a", "search=ember")
        with_filter = observe(page)
        results.append(case("healthy: deep link filters", "total 2",
                            with_filter, with_filter["total"] == "2"))
        open_page(page, "d34b", "search=ember&defects=D-34")
        ignored = observe(page)
        results.append(case("D-34: deep link ignored", "total 45",
                            ignored, ignored["total"] == "45"))

        print("\nD-13 the view does not catch up after a write")
        open_page(page, "d13", "defects=D-13")
        before = observe(page)
        page.get_by_placeholder("new row name").fill("zzz-probe")
        page.get_by_role("button", name="Create").click()
        page.wait_for_timeout(400)
        after = observe(page)
        results.append(case("list unchanged after the write", f"total still {before['total']}",
                            after, after["total"] == before["total"]))
        open_page(page, "d13", "defects=D-13")
        reloaded = observe(page)
        results.append(case("a reload shows it — which is what hides this defect",
                            f"total {int(before['total']) + 1}",
                            reloaded, reloaded["total"] == str(int(before["total"]) + 1)))

        print("\nserver halves, seen through the page")
        for run, flag, label, expected in [
            ("d43c", "D-43-counter", "counter disagrees with the collection", "48"),
            ("d17", "D-17", "deleted rows listed", "47"),
        ]:
            open_page(page, run, f"defects={flag}")
            seen = observe(page)
            results.append(case(f"{flag}: {label}", f"total {expected}",
                                seen, seen["total"] == expected))
        open_page(page, "d43s", "defects=D-43-short-page")
        short = observe(page)
        results.append(case("D-43-short-page: window short, total honest",
                            "total 45 and 9 rows on a page of 10",
                            short, short["total"] == "45" and short["rows"] == 9))
        open_page(page, "d45", "defects=D-45&status=draft")
        unfiltered = observe(page)
        results.append(case("D-45: status filter dropped server-side", "total 45",
                            unfiltered, unfiltered["total"] == "45"))

        print("\nC-13 search commits only on Enter (control: must not read as broken)")
        open_page(page, "c13", "defects=C-13")
        type_search(page, "ember")
        inert = observe(page)
        results.append(case("typing alone is inert by design", "total 45",
                            inert, inert["total"] == "45"))
        page.get_by_role("searchbox").press("Enter")
        page.wait_for_timeout(DEBOUNCE_SETTLE_MS)
        committed = observe(page)
        results.append(case("Enter commits", "total 2",
                            committed, committed["total"] == "2"))

        print("\nC-08 controls: harmless changes that must stay green")
        for flag, expect in [("U-01-renamed-control", "Add"), ("C-08-restyle", "Create"),
                             ("C-08-reorder", "Create"), ("C-08-wrap", "Create")]:
            open_page(page, flag.lower(), f"defects={flag}")
            shape = observe(page)
            label = page.evaluate("() => document.querySelector('.create button').textContent")
            results.append(case(f"{flag}: data unchanged", f"total 45, submit says {expect!r}",
                                {"total": shape["total"], "label": label},
                                shape["total"] == "45" and label == expect))

        print("\nrun isolation")
        open_page(page, "iso-a")
        page.get_by_placeholder("new row name").fill("iso-probe")
        page.get_by_role("button", name="Create").click()
        page.wait_for_timeout(400)
        wrote = observe(page)
        open_page(page, "iso-b")
        neighbour = observe(page)
        results.append(case("a write in one run does not move another's baseline",
                            "46 in the writing run, 45 in the neighbour",
                            {"writer": wrote["total"], "neighbour": neighbour["total"]},
                            wrote["total"] == "46" and neighbour["total"] == "45"))

        print("\nconfiguration guard")
        page.goto(f"{BASE}/?defects=D-99", wait_until="domcontentloaded")
        page.wait_for_timeout(200)
        guarded = page.evaluate("""() => ({
            alert: document.querySelector('[role=alert]')?.textContent,
            hasApp: !!document.querySelector('table'),
        })""")
        results.append(case("an unknown id refuses to render an application",
                            "an alert and no table", guarded,
                            guarded["hasApp"] is False and bool(guarded["alert"])))

        browser.close()

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
