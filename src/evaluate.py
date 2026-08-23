import csv
import json
from pathlib import Path


RECORDS_FILE = Path("data/processed/listings.jsonl")
GOLD_FILE = Path("data/processed/gold_set_25.csv")
RESULTS_FILE = Path("data/processed/evaluation_results.json")

GROUP_B_FIELDS = [
    "compound_name", "developer_name", "governorate", "city", "district",
    "finishing_level", "delivery_status", "delivery_date", "sale_type",
    "payment_type", "down_payment_amount", "down_payment_pct",
    "installment_years", "installment_amount", "installment_frequency",
    "cash_discount_pct", "amenities", "floor_number", "garden_area_sqm",
    "roof_area_sqm", "is_negotiable",
]
GOLD_FIELDS = ["listing_id", "url", "purpose"] + GROUP_B_FIELDS + ["evidence_note"]

SAMPLE_IDS = [
    "503641035", "503952478", "503956008", "503676096", "503962919",
    "503913663", "503966142", "503914496", "503588414", "503934901",
    "503480700", "503398534", "503967685", "503967027", "503962707",
    "503716753", "503956939", "503971825", "503943339", "503949272",
    "503933760", "503945831", "503946688", "503974269", "503577282",
]


def load_records() -> dict[str, dict]:
    records = {}
    with RECORDS_FILE.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                records[str(record["listing_id"])] = record
    return records


def normalize(value):
    if isinstance(value, list):
        return sorted(str(item).strip().lower() for item in value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        value = value.strip().lower()
        return value if value else None
    return value


def load_gold() -> dict[str, dict]:
    with GOLD_FILE.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != GOLD_FIELDS:
            raise RuntimeError(f"Gold CSV columns must be: {', '.join(GOLD_FIELDS)}")
        rows = {row["listing_id"]: row for row in reader}
        if set(rows) != set(SAMPLE_IDS):
            raise RuntimeError("Gold CSV must contain exactly the fixed 25-listing sample")
        return rows


def parse_gold(value: str):
    if value is None or value.strip() == "" or value.lower() == "none":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def evaluate(records: dict[str, dict], gold: dict[str, dict]) -> dict:
    correct = {field: 0 for field in GROUP_B_FIELDS}
    total = len(SAMPLE_IDS)
    hallucinations = {field: 0 for field in GROUP_B_FIELDS}

    for listing_id in SAMPLE_IDS:
        prediction = records[listing_id]
        reference = gold[listing_id]
        for field in GROUP_B_FIELDS:
            predicted_value = prediction.get(field)
            gold_value = parse_gold(reference[field])
            if normalize(predicted_value) == normalize(gold_value):
                correct[field] += 1
            if predicted_value is not None and gold_value is None:
                hallucinations[field] += 1

    total_cells = total * len(GROUP_B_FIELDS)
    correct_cells = sum(correct.values())
    hallucinated_cells = sum(hallucinations.values())
    results = {
        "sample_size": total,
        "fields_evaluated": len(GROUP_B_FIELDS),
        "field_level_accuracy_pct": round(100 * correct_cells / total_cells, 2),
        "hallucination_rate_pct": round(100 * hallucinated_cells / total_cells, 2),
        "accuracy_by_field_pct": {
            field: round(100 * correct[field] / total, 2)
            for field in GROUP_B_FIELDS
        },
        "hallucinations_by_field": hallucinations,
    }
    RESULTS_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def main() -> None:
    records = load_records()
    missing = [listing_id for listing_id in SAMPLE_IDS if listing_id not in records]
    if missing:
        raise RuntimeError(f"Missing sample records: {', '.join(missing)}")
    results = evaluate(records, load_gold())
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
