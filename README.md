# ECES Bayut Egypt Housing Dataset

## Result

This project collected 700 unique Bayut Egypt listing URLs across Cairo, Giza,
and Alexandria, covering both sale and rent listings. The final run produced
696 complete records and 4 unresolved failures. The deliverable workbook is
`output/bayut_listings.xlsx`; the line-oriented source output is
`data/processed/listings.jsonl`.

Coverage is 486 sale listings and 210 rent listings, distributed as Cairo 346,
Giza 210, and Alexandria 140. The four failures are documented in
`data/processed/extraction_failures.jsonl` and summarized in
`failure_summary.md`.

## Method

`src/scraper.py` fetches Bayut category pages using `curl_cffi` with a Chrome
TLS fingerprint, extracts listing URLs, removes duplicates, and persists the
URL file after every page. The chosen scope is six slices: sale and rent in
Cairo, Giza, and Alexandria. This gives geographic and market-purpose coverage
while exceeding the 500-listing requirement.

`src/extractor.py` fetches each detail page, parses structured Group A fields
with BeautifulSoup, and sends only the listing evidence to OpenRouter for the
description-derived Group B fields. The model is configured through
`OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in a local `.env` file. The API key
must never be committed. The extractor validates categorical values, preserves
explicit nulls, and computes `price_per_sqm` and
`total_installment_cost` only when their inputs are complete.

OpenRouter was selected because it provides a single OpenAI-compatible endpoint
for the multilingual extraction model and exposes provider errors clearly.
For each listing, an OpenRouter request has one initial attempt and up to two
additional retries, three attempts total. The messages `retrying (1/2)` and
`retrying (2/2)` show the retry number for that listing. This handles HTTP 502
responses such as `Upstream error from Nvidia: Service temporarily overloaded`
when the response has no `choices`, as well as curl error 28 timeouts after
approximately 120 seconds.
Bayut was selected because it is the specified source and contains both
structured property information and free-text payment and project details.

## Reliability and Resuming

The stable `listing_id` is the numeric ID in the Bayut URL, for example
`details-503641035.html`. It remains stable across reruns and is used as the
deduplication key. Before extracting a URL, the pipeline loads completed
records and skips IDs already marked `_extraction_status=complete`. Each
successful record is appended immediately, so interruption does not discard
previous work. Failures are appended to JSONL rather than swallowed.

Run only unresolved failures with:

```powershell
python -m src.pipeline --failed-only
```

## Limitations

The detail pages can be deleted or temporarily unavailable. Free-text wording
is inconsistent across agents and languages, so a model can miss an implicit
payment term or normalize a location imperfectly. A free model provider can
also return timeouts, rate limits, or upstream overload responses. The retry
policy limits each listing to two retries after the initial request. Null is
preferred whenever the page does not provide explicit evidence.

## Clean-clone Run

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
# Create a local .env file and set OPENROUTER_API_KEY and OPENROUTER_MODEL
python -m src.scraper
python -m src.pipeline
python -m src.evaluate
```

The current repository uses local generated data for the submission. Do not
include `.env` or any secret value in GitHub. Generated data is currently
ignored by `.gitignore`, so submission files must be explicitly force-added or
the ignore rules should be adjusted in the repository copy.

## Model and Cost

OpenRouter was used throughout the project. During early extraction attempts,
the project used a paid OpenRouter route until its available credit was
exhausted. The final 700-listing run used the free route
`nvidia/nemotron-3-ultra-550b-a55b:free`, so the cost of the final run was
`$0`. The paid route name and exact paid spend were not retained in the local
run logs, so no unsupported token or dollar figure is claimed here. The
pipeline also did not persist OpenRouter `usage` metadata; a future run should
save prompt tokens, completion tokens, request count, and provider cost per
listing for exact accounting.

## Evaluation

The 25-listing stratified evaluation sample and manual reference labels are in
`data/processed/gold_set_25.csv`. Run `python -m src.evaluate` to regenerate
the comparison in `data/processed/evaluation_results.json`. The current result
is 87.43% field-level accuracy and 2.86% hallucination rate across 21 Group B
fields and 25 listings. The gold labels were reviewed against the opened
listing pages and their descriptions. A value is treated as known only when
explicit evidence is present, and each row includes an evidence note.

## Further Work

With six more hours, I would add request caching and exponential backoff,
capture OpenRouter usage metadata and cost per record, improve Arabic number
and payment-plan normalization with deterministic rules, and expand the gold
set beyond 25 listings. I would also add schema/data-quality checks and move
the generated deliverables into versioned release artifacts rather than relying
on force-added ignored files.
