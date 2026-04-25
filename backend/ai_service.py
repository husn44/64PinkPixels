import json
import re
import asyncio
import logging
import httpx
from backend.config import settings
from backend.models import (
    ExtractedItem,
    MarketBenchmark,
    ReputationResult,
    VendorAnalysis,
    CompetitiveMatrix,
    QuoteRecord,
)

logger = logging.getLogger(__name__)


async def _call_glm(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> str:
    url = f"{settings.GLM_BASE_URL}/chat/completions"
    payload = {
        "model": settings.GLM_MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.GLM_API_KEY}",
        "Content-Type": "application/json",
    }
    backoff = 2
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if content is None:
                    raise ValueError("GLM returned None content (model may have refused or hit a safety filter)")
                return content
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.HTTPStatusError) as e:
            logger.warning(f"GLM attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                await asyncio.sleep(backoff)
                backoff *= 2
            else:
                raise RuntimeError(f"GLM call failed after 3 retries: {e}") from e


def _extract_json(text: str) -> dict:
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences
    fence = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding the outermost JSON object
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
                    continue

    # Handle truncated JSON — try to close open braces/brackets
    if start is not None:
        snippet = text[start:]
        # Count unclosed braces and brackets
        open_braces = snippet.count('{') - snippet.count('}')
        open_brackets = snippet.count('[') - snippet.count(']')
        if open_braces > 0 or open_brackets > 0:
            # Remove trailing incomplete token (e.g., partial string/value)
            # Strip from the last comma or colon
            for cut in range(len(snippet) - 1, max(len(snippet) - 50, 0), -1):
                if snippet[cut] in ',:"':
                    snippet = snippet[:cut]
                    break
            # Close all open structures
            snippet += ']' * max(open_brackets, 0) + '}' * max(open_braces, 0)
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Could not extract JSON from GLM response: {text[:200]}")


async def _call_glm_json(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> dict:
    raw = await _call_glm(messages, temperature, max_tokens)
    return _extract_json(raw)


MAX_TEXT_LEN = 4000
SHORT_TEXT_LEN = 1500

EXTRACTION_SYSTEM = """You are a procurement data extraction specialist.
Extract ALL line items from the vendor quote text below. A quote may contain
multiple products/services — you MUST extract every single one, not just the first.

The PDF filename is provided as a hint for the vendor name (e.g. if the filename
contains a company name, use it as vendor_name). Also look carefully at the
header, letterhead, stamp, or signature area of the quote for the vendor name.
Do NOT return "Unnamed Vendor" or empty — use the filename-derived name if no
name appears in the text body.

Return ONLY valid JSON with this structure:
{
  "vendor_name": "company name (from text or filename hint)",
  "items": [
    {
      "item_name": "product or service name",
      "item_description": "brief description",
      "item_price": numeric total price for this line (no currency symbols),
      "quantity": numeric quantity,
      "unit": "original unit from the quote (e.g., ml, L, cm, m, g, kg, piece, unit, box)",
      "normalized_unit": "standard metric unit (L, m, kg, piece, unit, box)",
      "normalized_quantity": quantity converted to the normalized_unit,
      "delivery_days": estimated delivery time in days (integer or null),
      "payment_terms": "e.g., Net 30, COD, 50% advance",
      "hidden_fees": ["list of any hidden or extra fees"],
      "warranty": "warranty terms if mentioned, else empty string",
      "contact_info": "vendor contact details if found, else empty string",
      "confidence": 0.0 to 1.0
    }
  ]
}

Normalization rules:
- ml → L: divide by 1000 (e.g., 500ml → 0.5L)
- cm → m: divide by 100 (e.g., 150cm → 1.5m)
- g → kg: divide by 1000 (e.g., 750g → 0.75kg)
- mm → m: divide by 1000
- oz → L: multiply by 0.0295735
- ft → m: multiply by 0.3048
- lb → kg: multiply by 0.453592

If a field is not found in the text, use null for optional numeric fields,
empty string for text fields, and empty list for arrays.
Set confidence to 0.0 if the text is garbled or empty.

IMPORTANT: Extract ALL items. Do not stop at the first one.
If the text was trimmed, extract what you can from the available portion."""


def _trim_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n[TEXT TRIMMED — extract what you can from the above]"


def _filename_to_vendor_hint(filename: str) -> str:
    """Derive a vendor name hint from the PDF filename."""
    name = filename.rsplit(".", 1)[0]  # strip extension
    name = name.replace("_", " ").replace("-", " ").strip()
    # Remove common non-vendor words
    for word in ("quote", "quotation", "quatation", "pdf", "test"):
        name = re.sub(rf"\b{word}\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip()
    # If what's left is just numbers or very short, it's not useful
    if len(name) <= 2 or name.replace(" ", "").isdigit():
        return ""
    return name


async def extract_quote_data(raw_text: str, filename: str = "") -> list[ExtractedItem]:
    if not raw_text.strip():
        return [ExtractedItem(
            vendor_name="UNKNOWN",
            item_name="UNKNOWN",
            item_price=0.0,
            unit="unknown",
            normalized_unit="unknown",
            normalized_quantity=0.0,
            confidence=0.0,
            filename=filename,
        )]

    vendor_hint = _filename_to_vendor_hint(filename)
    user_text = _trim_text(raw_text, MAX_TEXT_LEN)
    if vendor_hint:
        user_text = f"[PDF Filename: {filename} — likely vendor: {vendor_hint}]\n\n{user_text}"

    # First attempt: full text (truncated to 4000 chars)
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM},
        {"role": "user", "content": user_text},
    ]
    try:
        data = await _call_glm_json(messages, temperature=0.1, max_tokens=2048)
        return _parse_multi_item_response(data, filename, vendor_hint)
    except Exception as e:
        logger.warning(f"Extraction failed with full text ({len(raw_text)} chars): {e}")

    # Fallback: retry with much shorter text
    short_text = _trim_text(raw_text, SHORT_TEXT_LEN)
    if vendor_hint:
        short_text = f"[PDF Filename: {filename} — likely vendor: {vendor_hint}]\n\n{short_text}"
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM},
        {"role": "user", "content": short_text},
    ]
    try:
        data = await _call_glm_json(messages, temperature=0.1, max_tokens=1024)
        return _parse_multi_item_response(data, filename, vendor_hint)
    except Exception as e:
        logger.error(f"Extraction failed with short text too: {e}")
        return [ExtractedItem(
            vendor_name=vendor_hint or "EXTRACTION_FAILED",
            item_name="EXTRACTION_FAILED",
            item_price=0.0,
            unit="unknown",
            normalized_unit="unknown",
            normalized_quantity=0.0,
            confidence=0.0,
            filename=filename,
        )]


def _parse_multi_item_response(
    data: dict, filename: str, vendor_hint: str
) -> list[ExtractedItem]:
    """Parse the new multi-item response format into a list of ExtractedItems."""
    vendor_name = data.get("vendor_name") or vendor_hint or "UNKNOWN"
    # Clean up unnamed vendor
    if vendor_name.lower().strip() in ("", "unnamed vendor", "unknown"):
        vendor_name = vendor_hint or "UNKNOWN"

    items_raw = data.get("items", [])
    # Backwards compat: if GLM returned old single-item format, wrap it
    if not items_raw and "item_name" in data:
        items_raw = [data]

    results = []
    for item_data in items_raw:
        try:
            item_data.setdefault("vendor_name", vendor_name)
            item_data.setdefault("filename", filename)
            results.append(ExtractedItem(**item_data))
        except Exception as e:
            logger.warning(f"Skipping malformed item: {e}")
            continue

    if not results:
        results.append(ExtractedItem(
            vendor_name=vendor_name,
            item_name="UNKNOWN",
            item_price=0.0,
            unit="unknown",
            normalized_unit="unknown",
            normalized_quantity=0.0,
            confidence=0.0,
            filename=filename,
        ))
    return results


ANALYSIS_SYSTEM = """You are an adversarial procurement analyst.
Your job is to find every reason NOT to choose each vendor.
Be critical, skeptical, and thorough.

You will receive:
1. Current extracted quotes from vendors
2. Market benchmark prices from web research
3. Vendor reputation findings from web research
4. Historical pricing from past quotes

Compare each vendor's quote against:
- Market average (is the price above/below/at market?)
- Historical prices (have we had better prices before?)
- Reputation (any red flags or concerns?)
- Hidden fees (any undisclosed costs?)
- Delivery risk (is the delivery timeline reasonable?)

Return ONLY valid JSON:
{
  "items_compared": ["item1", "item2"],
  "vendors": ["vendor1", "vendor2"],
  "analyses": [
    {
      "vendor_name": "...",
      "price_vs_market": "above|below|at",
      "price_vs_history": "higher|lower|same|no_history",
      "hidden_fee_alert": true/false,
      "reputation_risk": "high|medium|low|unknown",
      "delivery_risk": "high|medium|low|unknown",
      "overall_score": 0.0-10.0,
      "summary": "2-3 sentence critical assessment"
    }
  ],
  "winner": "vendor_name",
  "winner_justification": "3-4 sentence justification considering price, risk, and value"
}

Scoring: 10 = best possible deal, 0 = avoid at all costs.
Consider: price competitiveness, hidden fees, delivery reliability, reputation."""


async def analyze_quotes_vs_research(
    extracted_items: list[ExtractedItem],
    benchmarks: list[MarketBenchmark],
    reputations: list[ReputationResult],
    history_records: list[QuoteRecord],
) -> CompetitiveMatrix:
    user_content = {
        "current_quotes": [item.model_dump() for item in extracted_items],
        "market_benchmarks": [b.model_dump() for b in benchmarks],
        "vendor_reputations": [r.model_dump() for r in reputations],
        "historical_quotes": [h.model_dump(mode="json") for h in history_records],
    }
    messages = [
        {"role": "system", "content": ANALYSIS_SYSTEM},
        {"role": "user", "content": json.dumps(user_content, indent=2)},
    ]
    data = await _call_glm_json(messages, temperature=0.3, max_tokens=2048)
    return CompetitiveMatrix(**data)


EMAIL_SYSTEM = """You are a professional procurement officer writing a formal
vendor acceptance email. Write a clear, professional email that:

1. Formally accepts the vendor's quote
2. References ALL item(s), their price(s), and terms agreed upon — list every line item
3. Confirms the expected delivery timeline
4. Requests confirmation and any next steps
5. Includes appropriate professional closing

Use Malaysian Ringgit (RM) for all prices. Format prices as "RM X.XX".

Do NOT mention other vendors, competitive analysis, or any adversarial findings.
The email should read as if this was the preferred vendor all along."""


async def draft_acceptance_email(
    vendor_name: str,
    extracted_items: list[ExtractedItem],
    competitive_matrix: CompetitiveMatrix,
) -> str:
    items_text = ""
    for i, item in enumerate(extracted_items, 1):
        items_text += (
            f"\n--- Item {i} ---\n"
            f"Name: {item.item_name}\n"
            f"Price: RM {item.item_price:,.2f}\n"
            f"Quantity: {item.normalized_quantity} {item.normalized_unit}\n"
        )
    total_price = sum(item.item_price for item in extracted_items)
    first_item = extracted_items[0]
    user_content = (
        f"Vendor: {vendor_name}\n"
        f"Number of items: {len(extracted_items)}\n"
        f"Items:{items_text}\n"
        f"Total Price: RM {total_price:,.2f}\n"
        f"Delivery: {first_item.delivery_days} days\n"
        f"Payment Terms: {first_item.payment_terms}\n"
        f"Contact: {first_item.contact_info}"
    )
    messages = [
        {"role": "system", "content": EMAIL_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    return await _call_glm(messages, temperature=0.5, max_tokens=2048)
