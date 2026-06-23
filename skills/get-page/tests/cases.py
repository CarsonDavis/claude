"""Benchmark cases for get-page — the real difficult URLs from live sessions.

Each case is fixed so we can run the SAME bed against different implementations
(current hand-rolled code now; trafilatura / crawl4ai / MarkItDown later) and
compare exactly which sites each approach wins.

Fields:
  id          short stable name
  url         the real URL
  category    grouping (baseline | pdf | hard_block | http2_crash | js_shell | not_found)
  goal        human description of what should happen
  known_hard  True = we do NOT expect any current approach to pass; this is the
              frontier we're benchmarking improvements against. False/absent =
              this is get-page's core job and a failure is a REGRESSION.
  expect      success criteria, all must hold:
                verdict_in    : final verdict must be one of these
                resolved      : auto's resolved flag must equal this
                min_chars     : extracted text length floor
                contains_any  : at least one of these tokens (case-insensitive)
"""

CASES = [
    # ---- baseline: get-page's bread and butter, must always pass ----
    {
        "id": "example", "url": "https://example.com", "category": "baseline",
        "goal": "trivial static page resolves at rung 0",
        "expect": {"verdict_in": ["usable"], "contains_any": ["Example Domain"]},
    },
    {
        "id": "wikipedia",
        "url": "https://en.wikipedia.org/wiki/Web_scraping", "category": "baseline",
        "goal": "403 on bare UA, clears via TLS impersonation",
        "expect": {"verdict_in": ["usable"], "contains_any": ["web scraping"], "min_chars": 2000},
    },
    {
        "id": "quotes_spa",
        "url": "https://quotes.toscrape.com/js/", "category": "baseline",
        "goal": "JS-rendered, needs the browser rung",
        "expect": {"verdict_in": ["usable"], "contains_any": ["Einstein"]},
    },

    # ---- pdf: should extract text, not choke on binary ----
    {
        "id": "vishay_pdf",
        "url": "https://www.vishay.com/docs/31018/cmfind.pdf", "category": "pdf",
        "goal": "datasheet PDF → extracted text",
        "expect": {"verdict_in": ["pdf"], "contains_any": ["Metal Film Resistors"]},
    },

    # ---- hard anti-bot blocks: success = CORRECTLY FLAGGED, not false-usable ----
    {
        "id": "mouser",
        "url": "https://www.mouser.com/ProductDetail/Vishay-Dale/CMF554K700FKR6",
        "category": "hard_block",
        "goal": "PerimeterX 'access denied' — must be flagged, not reported usable",
        # Requirement is substance, not label: must NOT be passed off as real
        # content (resolved=False). Exact verdict (antibot/js_shell/blocked) is
        # an implementation detail that varies by what the block page renders.
        "expect": {"resolved": False},
    },
    {
        "id": "digikey",
        "url": "https://www.digikey.com/en/products/detail/vishay-dale/CMF5510K000FKEK/3622015",
        "category": "hard_block",
        "goal": "Cloudflare 'just a moment' — must be flagged",
        "expect": {"resolved": False},
    },
    {
        "id": "oemsecrets",
        "url": "https://www.oemsecrets.com/compare/CMF5510K000FKEK",
        "category": "hard_block",
        "goal": "Cloudflare challenge — must be flagged",
        "expect": {"resolved": False},
    },

    # ---- browser HTTP/2 crash: FRONTIER — goal is to get the results ----
    {
        "id": "arrow",
        "url": "https://www.arrow.com/en/products/search?q=CMF55%204K7",
        "category": "http2_crash", "known_hard": True,
        "goal": "ERR_HTTP2_PROTOCOL_ERROR / timeout; want the search results",
        "expect": {"verdict_in": ["usable"], "min_chars": 1500},
    },
    {
        "id": "newark",
        "url": "https://www.newark.com/search?st=CMF55%20vishay",
        "category": "http2_crash", "known_hard": True,
        "goal": "ERR_HTTP2_PROTOCOL_ERROR / timeout; want the search results",
        "expect": {"verdict_in": ["usable"], "min_chars": 1500},
    },

    # ---- false-usable JS shells / title-only: FRONTIER — goal is real data ----
    {
        "id": "octopart",
        "url": "https://octopart.com/search?q=CMF5510K000FKEK",
        "category": "js_shell", "known_hard": True,
        "goal": "price aggregator, client-rendered rows",
        "expect": {"contains_any": ["$", "stock", "distributor", "mouser", "digi"], "min_chars": 1500},
    },
    {
        "id": "findchips",
        "url": "https://www.findchips.com/search/CMF5510K000FKEK",
        "category": "js_shell", "known_hard": True,
        "goal": "distributor rows client-rendered",
        "expect": {"contains_any": ["$", "stock", "distributor"], "min_chars": 1500},
    },
    {
        "id": "lcsc",
        "url": "https://www.lcsc.com/search?q=CMF55",
        "category": "js_shell", "known_hard": True,
        "goal": "results body rendered client-side",
        "expect": {"contains_any": ["cmf55", "$", "stock"], "min_chars": 1500},
    },
    {
        "id": "tme",
        "url": "https://www.tme.com/us/en-us/katalog/?search=CMF55%20vishay",
        "category": "js_shell", "known_hard": True,
        "goal": "title-only; want catalog rows",
        "expect": {"contains_any": ["cmf55", "resistor"], "min_chars": 1500},
    },

    # ---- not_found: success = correctly report 404 (bad guesses, skill OK) ----
    {
        "id": "onlinecomponents_404",
        "url": "https://www.onlinecomponents.com/en/vishay/cmf5510k000fkek-23700541.html",
        "category": "not_found",
        "goal": "dead product URL → 404",
        "expect": {"verdict_in": ["not_found"]},
    },
    {
        "id": "vishay_pdf_404",
        "url": "https://www.vishay.com/docs/31019/cmf.pdf", "category": "not_found",
        "goal": "wrong datasheet number → 404",
        "expect": {"verdict_in": ["not_found"]},
    },
]
