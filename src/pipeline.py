import argparse
import json
import time
from pathlib import Path

from openpyxl import Workbook

from src.extractor import extract_listing


URLS_FILE = Path("data/raw/listing_urls.json")
RECORDS_FILE = Path("data/processed/listings.jsonl")
FAILURES_FILE = Path("data/processed/extraction_failures.jsonl")
XLSX_FILE = Path("output/bayut_listings.xlsx")
TRANSIENT_RETRIES = 3
TRANSIENT_RETRY_DELAY = 5

FIELDS = [
	"listing_id", "url", "purpose", "property_type", "price",
	"price_period", "currency", "bedrooms", "bathrooms", "area_sqm",
	"location_raw", "agency_name", "is_verified", "date_listed",
	"description_raw", "language", "compound_name", "developer_name",
	"governorate", "city", "district", "finishing_level",
	"delivery_status", "delivery_date", "sale_type", "payment_type",
	"down_payment_amount", "down_payment_pct", "installment_years",
	"installment_amount", "installment_frequency", "cash_discount_pct",
	"amenities", "floor_number", "garden_area_sqm", "roof_area_sqm",
	"is_negotiable", "price_per_sqm", "total_installment_cost",
]

def load_records() -> dict[str, dict]:
	if not RECORDS_FILE.exists():
		return {}
	records = {}
	with RECORDS_FILE.open(encoding="utf-8") as file:
		for line in file:
			if line.strip():
				record = json.loads(line)
				if record.get("listing_id") and record.get("_extraction_status") == "complete":
					records[record["listing_id"]] = record
	return records


def load_failed_urls() -> list[str]:
	if not FAILURES_FILE.exists():
		return []
	failed_urls = []
	seen = set()
	with FAILURES_FILE.open(encoding="utf-8") as file:
		for line in file:
			if not line.strip():
				continue
			failure = json.loads(line)
			url = failure.get("url")
			if url and url not in seen:
				seen.add(url)
				failed_urls.append(url)
	return failed_urls


def append_jsonl(path: Path, record: dict) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("a", encoding="utf-8") as file:
		file.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_xlsx(records: list[dict]) -> None:
	XLSX_FILE.parent.mkdir(parents=True, exist_ok=True)
	workbook = Workbook()
	sheet = workbook.active
	sheet.title = "listings"
	sheet.append(FIELDS)
	for record in records:
		row = []
		for field in FIELDS:
			value = record.get(field)
			row.append(json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value)
		sheet.append(row)
	sheet.freeze_panes = "A2"
	sheet.auto_filter.ref = sheet.dimensions
	workbook.save(XLSX_FILE)


def is_transient_error(error_message: str) -> bool:
	return any(
		marker in error_message
		for marker in ("DNSError", "Could not resolve host", "Timeout", "timed out")
	)


def main() -> None:
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"--failed-only",
		action="store_true",
		help="retry URLs recorded in extraction_failures.jsonl only",
	)
	args = parser.parse_args()

	if args.failed_only:
		urls = load_failed_urls()
	else:
		with URLS_FILE.open(encoding="utf-8") as file:
			targets = json.load(file)
		urls = list(dict.fromkeys(url for group in targets.values() for url in group))
	records = load_records()
	mode = "failed URLs" if args.failed_only else "all URLs"
	print(f"Mode: {mode} | URLs: {len(urls)} | already extracted: {len(records)}")

	for index, url in enumerate(urls, start=1):
		listing_id = url.rsplit("details-", 1)[-1].split(".", 1)[0]
		if listing_id in records:
			continue
		try:
			for attempt in range(1, TRANSIENT_RETRIES + 1):
				try:
					record = extract_listing(url)
					break
				except Exception as exc:
					error_message = f"{type(exc).__name__}: {exc}"
					if not is_transient_error(error_message) or attempt == TRANSIENT_RETRIES:
						raise
					print(
						f"[{index}/{len(urls)}] retrying ({attempt}/{TRANSIENT_RETRIES - 1}) "
						f"after temporary network error"
					)
					time.sleep(TRANSIENT_RETRY_DELAY)

			record["_extraction_status"] = "complete"
			records[record["listing_id"]] = record
			append_jsonl(RECORDS_FILE, record)
			print(f"[{index}/{len(urls)}] extracted {record['listing_id']}")
		except Exception as exc:
			error_message = f"{type(exc).__name__}: {exc}"
			append_jsonl(FAILURES_FILE, {"url": url, "error": error_message})
			print(f"[{index}/{len(urls)}] failed {url}: {error_message}")
			if "429" in error_message or "RESOURCE_EXHAUSTED" in error_message:
				print("API quota exhausted; stopping so the run can resume later.")
				break

	write_xlsx(list(records.values()))
	print(f"Saved {len(records)} records to {XLSX_FILE}")


if __name__ == "__main__":
	main()
