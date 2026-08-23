# Short Analysis: Sale Versus Rent in the Collected Sample

## Research question

What does the collected sample say about the scale of advertised sale prices
versus monthly rents, and is the result driven by one governorate?

## Evidence

The dataset contains 696 complete listings: 486 for sale and 210 for rent.
Coverage is geographically balanced by the configured collection targets:
Cairo 346 listings, Giza 210, and Alexandria 140. All 696 records have a
positive advertised area and a computed `price_per_sqm`.

The median advertised sale price is 10,500,000 EGP, while the median advertised
rent is 36,000 EGP per month. These are intentionally reported as medians,
because listing prices are strongly affected by a small number of luxury and
large-unit advertisements. The ratio is not interpreted as a yield: sale and
rent listings are not matched on the same property, and the collection is a
portal sample rather than a probability sample.

## Interpretation

The useful finding is the composition of the sample rather than a claim about
the whole Egyptian market. Sale listings outnumber rent listings by 486 to
210, while the three-governorate coverage prevents the result from being only a
Cairo observation. The dataset can support a stronger follow-up question, such
as comparing median `price_per_sqm` by purpose and governorate, but that should
be done after controlling for property type, bedrooms, and area.

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
