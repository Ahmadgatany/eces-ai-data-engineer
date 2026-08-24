# Short Analysis: Geographic and Property-Type Price Differences

## Research question

How different are advertised sale prices per square meter across governorates,
and is property type a larger source of variation than geography?

## Evidence

The dataset contains 696 complete listings: 486 for sale and 210 for rent.
Coverage is geographically balanced by the configured collection targets:
Cairo 346 listings, Giza 210, and Alexandria 140. All 696 records have a
positive advertised area and a computed `price_per_sqm`.

For sale listings, median advertised price per square meter is 59,296 EGP in
Cairo (n=276), 60,000 EGP in Giza (n=140), and 42,829 EGP in Alexandria
(n=70). Alexandria is therefore about 28% below Cairo on this measure:
`1 - 42,829 / 59,296 = 27.8%`. The gap is large enough to be a useful
descriptive signal, but it is not a causal estimate because the sample is not
weighted and property mix differs by governorate.

Property type shows an even stronger contrast in the sale sample. Apartments
have a median of 45,802 EGP per square meter (n=263), while villas have
75,000 EGP (n=143), about 64% higher. Townhouses are also high at 77,755 EGP
(n=37). This suggests that controlling for property type is essential before
interpreting geographic price differences.

For rent listings, the corresponding median price per square meter is 389 EGP
in Cairo (n=70), 297 EGP in Giza (n=70), and 126 EGP in Alexandria (n=70).
Rent per-square-meter is not a yield measure because sale and rent records are
different advertisements and are not matched on the same units.

## Interpretation

The useful finding is that property type appears to explain more variation than
the broad geography in this snapshot: the apartment-to-villa median gap is
29,198 EGP per square meter, while the Cairo-to-Alexandria geographic gap is
16,467 EGP per square meter. This is why the dataset stores both normalized
location and property type rather than relying on a raw location string.

The result also shows why the extracted Group B fields matter. A raw price and
area can produce `price_per_sqm`, but comparing listings fairly requires the
compound, normalized location, finishing, delivery status, and payment-plan
fields. Only 4 of 696 listings have a non-null total installment cost because
the calculation requires down payment, installment amount, duration, and
frequency all to be explicitly available. Treating incomplete plans as zero
would create a misleading analysis, so the pipeline correctly returns null.

## Caveats

This is a snapshot of Bayut advertisements, not transaction data. Advertised
prices may differ from negotiated prices, rent periods are not always directly
comparable, and the four deleted/unavailable listings are excluded from the
complete-record analysis. The 25-listing evaluation reports 87.43% field-level
accuracy and a 2.86% hallucination rate; those metrics describe the sampled
extraction quality, not market uncertainty. The reference labels were reviewed
against the opened listing pages, with conservative nulls where no explicit
evidence was available.
