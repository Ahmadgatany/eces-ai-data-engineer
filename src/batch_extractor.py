import json
import time
from pathlib import Path

from src.extractor import extract_listing


TEST_LISTINGS = [
    {
        "name": "Apartment Sale - Compound",
        "url": "https://www.bayut.eg/en/property/details-503809479.html",
    },
    {
        "name": "Villa Sale - Fully Finished",
        "url": "https://www.bayut.eg/en/property/details-503337955.html",
    },
    {
        "name": "Villa Sale - Payment Plan",
        "url": "https://www.bayut.eg/en/property/details-503878516.html",
    },
    {
        "name": "Villa Sale - Resale / Furnished",
        "url": "https://www.bayut.eg/en/property/details-503853495.html",
    },
    {
        "name": "Villa Sale - Semi Finished",
        "url": "https://www.bayut.eg/en/property/details-503477250.html",
    },
    {
        "name": "Apartment Rent - Furnished",
        "url": "https://www.bayut.eg/en/property/details-503749655.html",
    },
    {
        "name": "Apartment Rent - Compound",
        "url": "https://www.bayut.eg/en/property/details-503230515.html",
    },
    {
        "name": "Villa Sale - Resale",
        "url": "https://www.bayut.eg/en/property/details-503824211.html",
    },
]


OUTPUT_FILE = Path(
    "data/processed/extraction_test_results.json"
)

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


DISPLAY_FIELDS = [
    "listing_id",
    "purpose",
    "property_type",
    "price",
    "price_period",
    "currency",
    "bedrooms",
    "bathrooms",
    "area_sqm",
    "location_raw",
    "agency_name",
    "is_verified",
    "date_listed",
    "language",
    "compound_name",
    "developer_name",
    "governorate",
    "city",
    "district",
    "finishing_level",
    "delivery_status",
    "delivery_date",
    "sale_type",
    "payment_type",
    "down_payment_amount",
    "down_payment_pct",
    "installment_years",
    "installment_amount",
    "installment_frequency",
    "cash_discount_pct",
    "amenities",
    "floor_number",
    "garden_area_sqm",
    "roof_area_sqm",
    "is_negotiable",
]


def print_result(data: dict) -> None:
    """Print extracted fields for manual inspection."""

    for field in DISPLAY_FIELDS:
        print(f"{field:25}: {data.get(field)}")


def save_results(results: list[dict]) -> None:
    """Save raw extractor results without modifying them."""

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=2,
        )


def main() -> None:

    print("=" * 80)
    print("BAYUT BATCH EXTRACTOR TEST")
    print("=" * 80)

    print(f"\nListings to test: {len(TEST_LISTINGS)}")
    print(f"Output: {OUTPUT_FILE}")

    results = []
    success_count = 0
    failed_count = 0

    for index, listing in enumerate(TEST_LISTINGS, start=1):

        print("\n" + "-" * 80)
        print(
            f"[{index}/{len(TEST_LISTINGS)}] "
            f"{listing['name']}"
        )
        print(f"URL: {listing['url']}")
        print("-" * 80)

        try:
            data = extract_listing(listing["url"])

            result = {
                **data,
                "_test_name": listing["name"],
                "_test_status": "success",
            }

            results.append(result)
            success_count += 1

            print("\nSUCCESS")
            print_result(data)

        except Exception as exc:

            failed_count += 1

            print("\nFAILED")
            print(
                f"Error: {type(exc).__name__}: {exc}"
            )

            results.append(
                {
                    "url": listing["url"],
                    "_test_name": listing["name"],
                    "_test_status": "failed",
                    "_error": (
                        f"{type(exc).__name__}: {exc}"
                    ),
                }
            )

        if index < len(TEST_LISTINGS):
            time.sleep(2)

    save_results(results)

    print("\n")
    print("=" * 80)
    print("BATCH EXTRACTION SUMMARY")
    print("=" * 80)

    print(f"Total listings : {len(TEST_LISTINGS)}")
    print(f"Successful     : {success_count}")
    print(f"Failed         : {failed_count}")

    print("-" * 80)

    if failed_count == 0:
        print("STATUS: ALL TEST LISTINGS EXTRACTED SUCCESSFULLY")
    else:
        print("STATUS: SOME LISTINGS FAILED")

    print(f"\nResults saved to: {OUTPUT_FILE}")
    print("=" * 80)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()