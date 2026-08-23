# Failure Summary

- **Final result:** 700 unique URLs were collected; 696 listings were
  extracted successfully and 4 remained unresolved.
- **Deleted listings:** the four final failures returned HTTP 404, indicating
  that Bayut no longer served those detail pages. They remain in
  `data/processed/extraction_failures.jsonl` with one entry each.
- **Temporary DNS failures:** some requests returned `DNSError` / `Could not
  resolve host`. The pipeline retries transient DNS and timeout errors three
  times before logging the URL and continuing.
- **OpenRouter provider overload:** the free Nvidia route sometimes returned
  HTTP 502 with an upstream-overloaded message or a response without
  `choices`. For each listing, the extractor makes one initial request and up
  to two additional retry requests, three attempts total. The log labels these
  as `retrying (1/2)` and `retrying (2/2)`, making the retry count visible per
  listing. It records the failure only after all three attempts fail.
- **LLM timeout:** some requests returned curl error 28 after approximately
  120 seconds with bytes received. These are treated as transient and receive
  the same two-retry policy before the listing is logged as failed.
- **Usage limits:** repeated runs reached provider usage limits, so the
  extraction was resumed with additional API keys. The pipeline's append-only
  records and ID-based skip logic prevented duplicate completed listings.
- **Cost reporting:** early attempts used a paid OpenRouter route until its
  available credit was exhausted. The final extraction used
  `nvidia/nemotron-3-ultra-550b-a55b:free`, so its model cost was `$0`. Exact
  token usage and paid spend were not recorded by the original pipeline, so
  they are intentionally not estimated.
- **Recovery outcome:** reruns continue from `listings.jsonl`; completed IDs
  are skipped, while unresolved URLs can be retried with
  `python -m src.pipeline --failed-only`.