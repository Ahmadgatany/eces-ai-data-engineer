import json
import os
import re
import time
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests
from dotenv import load_dotenv
from pydantic import BaseModel, Field


load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")
MODEL = os.getenv(
    "OPENROUTER_MODEL",
    os.getenv("GEMINI_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"),
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_RETRIES = 3
LLM_RETRY_DELAY = 5

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is missing from environment variables."
    )

class GroupB(BaseModel):
    compound_name: Optional[str] = None
    developer_name: Optional[str] = None

    governorate: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

    finishing_level: Optional[str] = None

    delivery_status: Optional[str] = None
    delivery_date: Optional[str] = None

    sale_type: Optional[str] = None

    payment_type: Optional[str] = None
    down_payment_amount: Optional[float] = Field(default=None, ge=0)
    down_payment_pct: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
    )

    installment_years: Optional[float] = Field(
        default=None,
        ge=0,
        le=30,
    )

    installment_amount: Optional[float] = Field(
        default=None,
        ge=0,
    )

    installment_frequency: Optional[str] = None

    cash_discount_pct: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
    )

    amenities: Optional[list[str]] = None

    floor_number: Optional[int | str] = None

    garden_area_sqm: Optional[float] = Field(
        default=None,
        ge=0,
    )

    roof_area_sqm: Optional[float] = Field(
        default=None,
        ge=0,
    )

    is_negotiable: Optional[bool] = None


def clean_text(value: Optional[str]) -> str:
    if not value:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()


def number(value: str) -> Optional[float]:
    if not value:
        return None

    value = (
        str(value)
        .replace(",", "")
        .replace("EGP", "")
        .strip()
    )

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def listing_id_from_url(url: str) -> Optional[str]:
    match = re.search(
        r"details-(\d+)\.html",
        url,
        re.I,
    )

    return match.group(1) if match else None


def fetch_page(url: str) -> BeautifulSoup:
    response = requests.get(
        url,
        impersonate="chrome",
        timeout=30,
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "lxml",
    )


def all_text(soup: BeautifulSoup) -> str:
    return clean_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )


def detect_language(value: Optional[str]) -> str:
    """Classify text using the presence of Arabic script."""
    if not value:
        return "en"

    has_arabic = bool(re.search(r"[\u0600-\u06ff]", value))
    has_latin = bool(re.search(r"[A-Za-z]", value))

    if has_arabic and has_latin:
        return "mixed"
    if has_arabic:
        return "ar"
    return "en"


def find_label_value(
    soup: BeautifulSoup,
    label: str,
) -> Optional[str]:
    """
    Find values from Bayut's structured
    Property Information section.

    Example:

        Purpose
        For Sale

    or:

        Published at
        20 August 2026
    """

    label_clean = label.lower()

    # --------------------------------------------------------
    # Look through text-containing elements
    # --------------------------------------------------------

    for element in soup.find_all(
        ["li", "div", "p", "span"]
    ):
        text = clean_text(
            element.get_text(
                " ",
                strip=True,
            )
        )

        if not text:
            continue

        # Exact "Label Value" form
        match = re.match(
            rf"^{re.escape(label)}\s*:?\s*(.+)$",
            text,
            re.I,
        )

        if match:
            value = clean_text(match.group(1))

            if value.lower() != label_clean:
                return value

    # --------------------------------------------------------
    # Fallback: search whole text around label
    # --------------------------------------------------------

    text = all_text(soup)

    match = re.search(
        rf"\b{re.escape(label)}\s+(.+?)(?=\s+(?:"
        r"Type|Purpose|Reference no\.|Completion|"
        r"Furnishing|Published at|Ownership"
        r")\b|$)",
        text,
        re.I,
    )

    if match:
        return clean_text(match.group(1))

    return None


def extract_property_information(
    soup: BeautifulSoup,
) -> dict:
    """
    Extract Bayut's structured Property Information.
    """

    return {
        "type": find_label_value(
            soup,
            "Type",
        ),
        "purpose": find_label_value(
            soup,
            "Purpose",
        ),
        "completion": find_label_value(
            soup,
            "Completion",
        ),
        "furnishing": find_label_value(
            soup,
            "Furnishing",
        ),
        "published_at": find_label_value(
            soup,
            "Published at",
        ),
        "ownership": find_label_value(
            soup,
            "Ownership",
        ),
    }


def extract_description(soup: BeautifulSoup) -> str:
    text = clean_text(soup.get_text(" ", strip=True))

    start_markers = [
        "Property Description",
        "Property description",
        "نظرة عامة",
        "Location & Nearby",
    ]

    end_markers = [
        "Property Information",
        "Trends & Indices",
        "Mortgage",
        "Recommended for you",
        "Similar properties",
        "Useful Links",
        "العقارات الموصى بها",
    ]

    start = 0

    for marker in start_markers:
        idx = text.find(marker)
        if idx != -1:
            start = idx + len(marker)
            break

    description = text[start:]

    if "Location & Nearby" in text:
        description = text[text.find("Location & Nearby") + len("Location & Nearby"):]
        description = re.sub(r"^\s*(?:(?:Email|Call)\s+)+", "", description, flags=re.I)

    if not description.strip() or description.strip() in start_markers:
        description = text

    end = len(description)

    for marker in end_markers:
        idx = description.find(marker)
        if idx != -1:
            end = min(end, idx)

    return clean_text(description[:end])

def extract_location(
    soup: BeautifulSoup,
) -> Optional[str]:
    """
    Extract the listing's raw location as displayed on Bayut.

    Examples:
        EL Patio ORO Compound, 5th Settlement, New Cairo, Cairo
        South Med, North Coast, Matruh
        4th District, 5th Settlement, New Cairo, Cairo

    The function must NOT return:
        - Down payment text
        - Beds / Baths / Area
        - Amenities
        - Recommended-property locations
    """

    # --------------------------------------------------------
    # 1. Look for the listing summary text
    # --------------------------------------------------------

    text = clean_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    # Bayut normally places the location after
    # "Share Save" and before the Beds/Baths summary.
    match = re.search(
        r"(?:Share\s+Save|Save)\s+"
        r"(.+?)"
        r"(?=\s+\d+\s+Beds?\b)",
        text,
        re.I,
    )

    if match:
        location = clean_text(
            match.group(1)
        )

        # ----------------------------------------------------
        # Remove accidental payment information.
        #
        # Example:
        # Down payment: EGP 22,000,000 South Med,
        # North Coast, Matruh
        # ----------------------------------------------------

        location = re.sub(
            r"^Down\s+payment\s*:\s*"
            r"(?:EGP|AED|USD|EUR)?\s*"
            r"[\d,]+(?:\.\d+)?\s*",
            "",
            location,
            flags=re.I,
        )

        # ----------------------------------------------------
        # Remove obvious UI fragments
        # ----------------------------------------------------

        location = re.sub(
            r"^(?:Share|Save)\s+",
            "",
            location,
            flags=re.I,
        )

        location = clean_text(
            location
        )

        # ----------------------------------------------------
        # Reject if this is actually property metadata
        # ----------------------------------------------------

        if location and not re.search(
            r"\b\d+\s+(?:Beds?|Baths?|"
            r"Sq\.?\s*M)\b",
            location,
            re.I,
        ):
            return location

    # --------------------------------------------------------
    # 2. Fallback: search short DOM elements that look like
    #    actual locations.
    # --------------------------------------------------------

    location_pattern = re.compile(
        r"(?:"
        r"Compound|"
        r"Settlement|"
        r"Cairo|"
        r"Giza|"
        r"North Coast|"
        r"Matruh|"
        r"District|"
        r"Madinaty|"
        r"New Cairo|"
        r"Sheikh Zayed|"
        r"6th of October|"
        r"October"
        r")",
        re.I,
    )

    candidates = []

    for element in soup.find_all(
        ["a", "div", "span", "p"]
    ):
        value = clean_text(
            element.get_text(
                " ",
                strip=True,
            )
        )

        if not value:
            continue

        # Avoid huge containers.
        if len(value) > 150:
            continue

        # Must look like a location.
        if not location_pattern.search(value):
            continue

        # Reject property-summary strings.
        if re.search(
            r"\b\d+\s+(?:Beds?|Baths?|"
            r"Sq\.?\s*M)\b",
            value,
            re.I,
        ):
            continue

        # Reject payment strings.
        if re.search(
            r"\b(?:Down\s+payment|"
            r"Payment\s+Plan|"
            r"Total\s+Contract)\b",
            value,
            re.I,
        ):
            continue

        candidates.append(value)

    # --------------------------------------------------------
    # Prefer comma-separated location strings.
    # --------------------------------------------------------

    comma_candidates = [
        value
        for value in candidates
        if "," in value
    ]

    if comma_candidates:
        candidates = comma_candidates

    # --------------------------------------------------------
    # Prefer the shortest meaningful candidate.
    #
    # This avoids selecting a parent container containing
    # the entire page section.
    # --------------------------------------------------------

    if candidates:
        candidates.sort(
            key=len
        )

        return candidates[0]

    return None

def extract_agency(
    soup: BeautifulSoup,
) -> Optional[str]:
    """
    Extract the agency/agent name from the Listing by section.

    Important:
    Bayut may place the listing price immediately after the
    agent name, e.g.:

        Listing by Rejan magdy EGP 29,950,000

    The price must NOT become part of agency_name.
    """

    text = all_text(soup)

    # --------------------------------------------------------
    # Find "Listing by ..."
    # --------------------------------------------------------

    match = re.search(
        r"Listing\s+by\s+(.+?)"
        r"(?=\s+(?:Email|Call|WhatsApp|Contact|Verified|"
        r"Share|Save|Published\s+at|Ownership|Property)\b|$)",
        text,
        re.I,
    )

    if not match:
        return None

    agency = clean_text(match.group(1))

    # --------------------------------------------------------
    # Remove common prefixes
    # --------------------------------------------------------

    agency = re.sub(
        r"^\s*Agent\s*:\s*",
        "",
        agency,
        flags=re.I,
    )


    agency = re.sub(
        r"\s+(?:EGP|LE|جنيه(?:\s+مصري)?)"
        r"\s*[\d,]+(?:\.\d+)?\s*$",
        "",
        agency,
        flags=re.I,
    )

    # Also handle prices without currency if they are clearly
    # attached to the end of the extracted agency.
    agency = re.sub(
        r"\s+[\d,]+(?:\.\d+)?\s*$",
        "",
        agency,
    )

    # --------------------------------------------------------
    # Remove accidental trailing UI labels
    # --------------------------------------------------------

    agency = re.sub(
        r"\s+(?:Email|Call|WhatsApp|Contact|Verified|Share|Save)"
        r"\s*$",
        "",
        agency,
        flags=re.I,
    )

    agency = clean_text(agency)

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    if not agency:
        return None

    if len(agency) > 100:
        return None

    # An agency name should not be just a price.
    if re.fullmatch(
        r"(?:EGP|LE)?\s*[\d,]+(?:\.\d+)?",
        agency,
        flags=re.I,
    ):
        return None

    return agency


def normalize_purpose(
    value: Optional[str],
) -> Optional[str]:

    if not value:
        return None

    value = value.lower()

    if "sale" in value:
        return "sale"

    if "rent" in value:
        return "rent"

    return None


def normalize_property_type(
    value: Optional[str],
) -> Optional[str]:

    if not value:
        return None

    value = value.lower()

    mapping = {
        "apartment": "Apartment",
        "villa": "Villa",
        "chalet": "Chalet",
        "townhouse": "Townhouse",
        "duplex": "Duplex",
        "penthouse": "Penthouse",
        "studio": "Studio",
        "land": "Land",
        "twin house": "other",
        "stand alone villa": "Villa",
    }

    for key, normalized in mapping.items():
        if key in value:
            return normalized

    return "other"


def extract_group_a(
    soup: BeautifulSoup,
    url: str,
) -> dict:

    text = all_text(soup)

    title = clean_text(
        soup.title.get_text()
        if soup.title
        else ""
    )

    info = extract_property_information(
        soup
    )

    data = {
        "listing_id": listing_id_from_url(url),
        "url": url,

        "purpose": None,
        "property_type": None,

        "price": None,
        "price_period": None,
        "currency": None,

        "bedrooms": None,
        "bathrooms": None,
        "area_sqm": None,

        "location_raw": None,
        "agency_name": None,

        "is_verified": None,
        "date_listed": None,

        "description_raw": extract_description(
            soup
        ),

        "language": None,
    }

    # --------------------------------------------------------
    # Purpose
    # --------------------------------------------------------

    data["purpose"] = normalize_purpose(
        info.get("purpose")
    )

    if data["purpose"] is None:

        if re.search(
            r"\bfor sale\b",
            title,
            re.I,
        ):
            data["purpose"] = "sale"

        elif re.search(
            r"\bfor rent\b",
            title,
            re.I,
        ):
            data["purpose"] = "rent"

    # --------------------------------------------------------
    # Property type
    # --------------------------------------------------------

    data["property_type"] = normalize_property_type(
        info.get("type")
    )

    if data["property_type"] is None:

        property_types = [
            "Apartment",
            "Villa",
            "Chalet",
            "Townhouse",
            "Duplex",
            "Penthouse",
            "Studio",
            "Land",
        ]

        for property_type in property_types:

            if re.search(
                rf"\b{re.escape(property_type)}\b",
                title,
                re.I,
            ):
                data["property_type"] = property_type
                break

    # --------------------------------------------------------
    # Price
    # --------------------------------------------------------

    # Prefer the main price displayed near EGP.
    matches = re.findall(
        r"\bEGP\s*([\d,]+(?:\.\d+)?)",
        text,
        re.I,
    )

    if matches:

        values = [
            number(x)
            for x in matches
        ]

        values = [
            x for x in values
            if x is not None
        ]

        if values:
            data["price"] = values[0]
            data["currency"] = "EGP"

    # --------------------------------------------------------
    # Rental period
    # --------------------------------------------------------

    if data["purpose"] == "rent":

        if re.search(
            r"\bmonthly\b",
            text,
            re.I,
        ):
            data["price_period"] = "monthly"

        elif re.search(
            r"\byearly\b|\bannually\b",
            text,
            re.I,
        ):
            data["price_period"] = "yearly"

    # --------------------------------------------------------
    # Bedrooms
    # --------------------------------------------------------

    match = re.search(
        r"(\d+)\s+Beds?\b",
        text,
        re.I,
    )

    if match:
        data["bedrooms"] = int(
            match.group(1)
        )

    elif re.search(
        r"\bStudio\b",
        title,
        re.I,
    ):
        data["bedrooms"] = 0

    # --------------------------------------------------------
    # Bathrooms
    # --------------------------------------------------------

    match = re.search(
        r"(\d+)\s+Baths?\b",
        text,
        re.I,
    )

    if match:
        data["bathrooms"] = int(
            match.group(1)
        )

    # --------------------------------------------------------
    # Area
    # --------------------------------------------------------

    match = re.search(
        r"([\d,]+(?:\.\d+)?)\s*"
        r"Sq\.?\s*M\.?",
        text,
        re.I,
    )

    if match:
        data["area_sqm"] = number(
            match.group(1)
        )

    # --------------------------------------------------------
    # Location
    # --------------------------------------------------------

    data["location_raw"] = extract_location(
        soup
    )

    # --------------------------------------------------------
    # Agency
    # --------------------------------------------------------

    data["agency_name"] = extract_agency(
        soup
    )

    # --------------------------------------------------------
    # Published date
    # --------------------------------------------------------

    published = info.get(
        "published_at"
    )

    if published:
        data["date_listed"] = clean_text(
            published
        )

    # --------------------------------------------------------
    # Verified
    # --------------------------------------------------------

    data["is_verified"] = bool(
        re.search(
            r"\bVerified\b",
            text,
            re.I,
        )
    )

    # --------------------------------------------------------
    # Language
    # --------------------------------------------------------

    html = soup.find("html")

    if html:

        lang = str(
            html.get(
                "lang",
                "",
            )
        ).lower()

        if lang.startswith("ar"):
            data["language"] = "ar"

        elif lang.startswith("en"):
            data["language"] = "en"

        else:
            data["language"] = detect_language(
                data["description_raw"]
            )

    else:
        data["language"] = detect_language(
            data["description_raw"]
        )

    return data


def extract_llm_evidence(soup: BeautifulSoup) -> str:
    """
    Build a compact evidence block for Group B extraction.
    Keep only listing-specific information and exclude recommendations.
    """

    text = clean_text(soup.get_text(" ", strip=True))

    start_markers = [
        "Property Description",
        "نظرة عامة",
        "Location & Nearby",
    ]

    end_markers = [
        "Property Information",
        "Trends & Indices",
        "Mortgage",
        "Recommended for you",
        "Useful Links",
        "العقارات الموصى بها",
    ]

    start = 0

    for marker in start_markers:
        idx = text.find(marker)
        if idx != -1:
            start = idx
            break

    evidence = text[start:]

    end = len(evidence)

    for marker in end_markers:
        idx = evidence.find(marker)
        if idx != -1:
            end = min(end, idx)

    evidence = clean_text(evidence[:end])

    if not evidence or evidence in start_markers:
        evidence = extract_description(soup)

    info = extract_property_information(soup)
    info_lines = [
        f"{label}: {value}"
        for label, value in info.items()
        if value
    ]

    location = extract_location(soup)
    if location:
        info_lines.append(f"Location: {location}")

    if info_lines:
        evidence = f"{evidence} Property Information: {'; '.join(info_lines)}"

    return evidence

SYSTEM_PROMPT = """
You are a high-precision information extraction system for Egyptian real-estate listings from Bayut Egypt.

Your task is to extract Group B research fields from the provided listing evidence.

IMPORTANT:
- Extract facts from the provided listing evidence only.
- Never invent, guess, or use outside knowledge.
- A missing value MUST be null.
- Prefer null over an uncertain value.
- Arabic and English have the same meaning.
- The evidence may contain English, Arabic, or mixed language.
- Numbers must be returned as numeric values, not strings.
- Do not confuse similar concepts.

FIELD RULES:

compound_name:
The project/compound name explicitly stated for this listing.
Use Project Name when available.
A compound name mentioned as the property's location is also valid.
Do not infer it from the developer.

developer_name:
Only when the developer is explicitly stated.
"Developer: X" is strong evidence.
Do not infer a developer from a compound name.

governorate / city / district:
Normalize the property's location hierarchy only when supported by the listing.
Do not invent missing hierarchy levels.
Use the location information belonging to THIS listing, not nearby/recommended properties.

finishing_level:
Normalize explicitly stated finishing:
- core & shell
- semi-finished
- fully finished
- super lux
- furnished
- unknown

Important:
"Furnished" is a valid finishing_level according to the task.
Do not confuse "Unfurnished" with a finishing level.
If the listing only says furnished/unfurnished and gives no actual finishing level, return:
- furnished when Furnishing = Furnished
- null for Unfurnished

delivery_status:
- ready when explicitly stated as Ready / جاهز
- off-plan when explicitly stated as Off-Plan / تحت الإنشاء
- otherwise null

delivery_date:
Extract only an explicitly stated delivery year or year-quarter.
Examples:
2028 -> "2028"
Q4 2027 -> "2027-Q4"
"delivery in 2027" -> "2027"
Never infer a delivery date from Booking Year or other dates.

sale_type:
- primary when explicitly stated as Primary or developer/new sale
- resale when explicitly stated as Resale
- otherwise null

payment_type:
- cash when explicitly described as cash-only/cash payment
- installments when an installment/payment plan is explicitly stated
- both when both cash and installments are explicitly available
- otherwise null

down_payment_amount:
Extract an explicitly stated down payment amount.
"Down payment: EGP 22,000,000" -> 22000000

down_payment_pct:
Extract an explicitly stated percentage.
"10% down payment" -> 10

installment_years:
Extract the duration of an installment/payment plan.
"8 Years" -> 8
"7 year payment plan" -> 7

installment_amount:
Extract the recurring installment amount.
Examples:
"EGP 500,000 monthly" -> 500000
"500,000 EGP per month" -> 500000

installment_frequency:
Normalize:
- monthly
- quarterly
- annual

cash_discount_pct:
Only extract an explicitly advertised cash discount.
"25% cash discount" -> 25
Do NOT treat the existence of a cash discount as proof that payment_type is cash.

amenities:
Return a list of amenities/features explicitly associated with THIS listing.
Do not include nearby-property amenities.
Do not invent amenities from the property description.

floor_number:
Extract only when explicitly stated.
Do not assume ground floor from "Ground Floor" unless it refers to the property's actual floor.

garden_area_sqm:
Extract only an explicitly stated garden area.
Do not confuse land area or built-up area with garden area.

roof_area_sqm:
Extract only an explicitly stated roof area.

is_negotiable:
true only when the listing explicitly says the price is negotiable.
false only when the listing explicitly says it is not negotiable.
Otherwise null.

VERY IMPORTANT:
The evidence may contain:
1. Listing description
2. Property Information
3. Project Information
4. Amenities / Features

Use ALL of them.

Ignore:
- Recommended for you
- Similar properties
- Nearby properties
- Popular searches
- Other listings
- Generic Bayut navigation text

Only extract information belonging to the current listing.

Return ONLY the requested JSON object.
"""



def extract_group_b(evidence: str) -> GroupB:
    if not evidence.strip():
        return GroupB()

    last_error = None
    for attempt in range(1, LLM_RETRIES + 1):
        try:
            response = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/eces-ai-data-engineer",
                    "X-Title": "ECES Bayut Extraction",
                },
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"LISTING EVIDENCE:\n{evidence}"},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                timeout=120,
            )
            response.raise_for_status()
            payload = response.json()
            choices = payload.get("choices")
            if not choices:
                error = payload.get("error", payload)
                raise RuntimeError(f"OpenRouter returned no choices: {error}")
            content = choices[0].get("message", {}).get("content")

            if content:
                parsed = GroupB.model_validate(json.loads(content))
                return validate_group_b(parsed, evidence)

            raise ValueError("OpenRouter returned empty model content")

        except Exception as exc:
            last_error = exc
            if attempt < LLM_RETRIES:
                print(
                    f"LLM extraction retrying ({attempt}/{LLM_RETRIES - 1}): "
                    f"{type(exc).__name__}: {exc}"
                )
                time.sleep(LLM_RETRY_DELAY)

    print(f"LLM extraction failed: {type(last_error).__name__}: {last_error}")
    raise RuntimeError(
        f"Group B extraction failed: {type(last_error).__name__}: {last_error}"
    ) from last_error


def validate_group_b(
    data: GroupB,
    text: str,
) -> GroupB:

    values = data.model_dump()

    if values["floor_number"] is not None:
        floor = str(values["floor_number"]).strip().lower()
        if floor in {"ground floor", "ground", "الأرضي", "الدور الأرضي"}:
            values["floor_number"] = 0
        elif floor.isdigit():
            values["floor_number"] = int(floor)
        else:
            values["floor_number"] = None

    # --------------------------------------------------------
    # Finishing
    # --------------------------------------------------------

    if values["finishing_level"]:

        value = (
            values["finishing_level"]
            .strip()
            .lower()
        )

        mapping = {
            "core and shell": "core & shell",
            "core & shell": "core & shell",
            "core-shell": "core & shell",
            "semi finished": "semi-finished",
            "semi-finished": "semi-finished",
            "fully finished": "fully finished",
            "full finished": "fully finished",
            "superlux": "super lux",
            "super-lux": "super lux",
            "super lux": "super lux",
            "furnished": "furnished",
        }

        values["finishing_level"] = mapping.get(
            value,
            value,
        )

    # --------------------------------------------------------
    # Payment type
    # --------------------------------------------------------

    if values["payment_type"]:

        value = (
            values["payment_type"]
            .strip()
            .lower()
        )

        mapping = {
            "installment": "installments",
            "cash and installments": "both",
            "cash & installments": "both",
            "cash / installments": "both",
            "cash / installment": "both",
            "cash and installment": "both",
        }

        values["payment_type"] = mapping.get(
            value,
            value,
        )

    # --------------------------------------------------------
    # Frequency
    # --------------------------------------------------------

    if values["installment_frequency"]:

        value = (
            values["installment_frequency"]
            .strip()
            .lower()
        )

        mapping = {
            "yearly": "annual",
            "annually": "annual",
            "every year": "annual",
            "per year": "annual",
            "every 3 months": "quarterly",
            "every three months": "quarterly",
        }

        values["installment_frequency"] = mapping.get(
            value,
            value,
        )

    # --------------------------------------------------------
    # Delivery status
    # --------------------------------------------------------

    if values["delivery_status"]:

        value = (
            values["delivery_status"]
            .strip()
            .lower()
        )

        if value not in {
            "ready",
            "off-plan",
        }:
            values["delivery_status"] = None

    # --------------------------------------------------------
    # Sale type
    # --------------------------------------------------------

    if values["sale_type"]:

        value = (
            values["sale_type"]
            .strip()
            .lower()
        )

        if value not in {
            "primary",
            "resale",
        }:
            values["sale_type"] = None

    # --------------------------------------------------------
    # Payment type validation
    # --------------------------------------------------------

    if values["payment_type"]:

        if values["payment_type"] not in {
            "cash",
            "installments",
            "both",
        }:
            values["payment_type"] = None

    # --------------------------------------------------------
    # Cash discount does NOT imply cash payment.
    # --------------------------------------------------------

    if (
        values["payment_type"] == "cash"
        and values["cash_discount_pct"] is not None
    ):

        if not re.search(
            r"\bcash\s+"
            r"(?:payment|only|price|deal)\b",
            text,
            re.I,
        ):

            values["payment_type"] = None

    return GroupB.model_validate(
        values
    )


def merge_results(
    group_a: dict,
    group_b: GroupB,
) -> dict:

    result = dict(group_a)

    result.update(
        group_b.model_dump()
    )

    return result


def add_derived_fields(
    data: dict,
) -> dict:

    # --------------------------------------------------------
    # Price per sqm
    # --------------------------------------------------------

    price = data.get("price")
    area = data.get("area_sqm")

    if (
        price is not None
        and area is not None
        and area > 0
    ):
        data["price_per_sqm"] = (
            price / area
        )
    else:
        data["price_per_sqm"] = None

    # --------------------------------------------------------
    # Total installment cost
    # --------------------------------------------------------

    down = data.get(
        "down_payment_amount"
    )

    amount = data.get(
        "installment_amount"
    )

    years = data.get(
        "installment_years"
    )

    frequency = data.get(
        "installment_frequency"
    )

    multiplier = {
        "monthly": 12,
        "quarterly": 4,
        "annual": 1,
    }.get(frequency)

    if (
        down is not None
        and amount is not None
        and years is not None
        and multiplier is not None
    ):

        data["total_installment_cost"] = (
            down
            + amount
            * multiplier
            * years
        )

    else:
        data["total_installment_cost"] = None

    return data


def extract_listing(
    url: str,
) -> dict:

    soup = fetch_page(url)

    # --------------------------------------------------------
    # Group A — deterministic
    # --------------------------------------------------------

    group_a = extract_group_a(
        soup,
        url,
    )

    # --------------------------------------------------------
    # Group B — Gemini
    #
    # Do NOT send description only.
    # Bayut keeps important Group B information in:
    # - Overview
    # - Property Information
    # - Project Information
    # - Amenities / Features
    # --------------------------------------------------------

    llm_evidence = extract_llm_evidence(soup)

    group_b = extract_group_b(
        llm_evidence
    )

    # Merge
    result = merge_results(
        group_a,
        group_b,
    )

    # Derived
    return add_derived_fields(
        result
    )

if __name__ == "__main__":

    url = (
        "https://www.bayut.eg/en/property/"
        "details-503809479.html"
    )

    result = extract_listing(url)

    print("=" * 80)

    for key, value in result.items():
        print(
            f"{key:30}: {value}"
        )