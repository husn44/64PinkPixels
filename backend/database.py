import httpx
import asyncio
from backend.config import settings
from backend.models import QuoteRecord


def _headers() -> dict[str, str]:
    return {
        "X-Master-Key": settings.JSONBIN_API_KEY,
        "Content-Type": "application/json",
    }


async def _request_with_retry(
    method: str, url: str, *, json_data: dict | None = None, max_retries: int = 3
) -> httpx.Response:
    backoff = 1
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    resp = await client.get(url, headers=_headers())
                elif method == "POST":
                    resp = await client.post(url, headers=_headers(), json=json_data)
                elif method == "PUT":
                    resp = await client.put(url, headers=_headers(), json=json_data)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                resp.raise_for_status()
                return resp
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.HTTPStatusError) as e:
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                raise
            if attempt < max_retries - 1:
                await asyncio.sleep(backoff)
                backoff *= 2
            else:
                raise


async def ensure_bin_exists() -> str:
    if settings.JSONBIN_BIN_ID:
        try:
            await _request_with_retry(
                "GET", f"{settings.JSONBIN_BASE_URL}/b/{settings.JSONBIN_BIN_ID}/latest"
            )
            return settings.JSONBIN_BIN_ID
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                raise

    data = {"quote_history": []}
    resp = await _request_with_retry(
        "POST", f"{settings.JSONBIN_BASE_URL}/b", json_data=data
    )
    bin_id = resp.json()["metadata"]["id"]

    env_path = settings.DATA_DIR.parent / ".env"
    lines = []
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("JSONBIN_BIN_ID="):
                lines.append(f'JSONBIN_BIN_ID="{bin_id}"')
            else:
                lines.append(line)
        if not any(l.startswith("JSONBIN_BIN_ID=") for l in lines):
            lines.append(f'JSONBIN_BIN_ID="{bin_id}"')
    else:
        lines = [f'JSONBIN_BIN_ID="{bin_id}"']

    env_path.write_text("\n".join(lines) + "\n")
    settings.JSONBIN_BIN_ID = bin_id
    return bin_id


async def read_bin() -> dict:
    bin_id = await ensure_bin_exists()
    resp = await _request_with_retry(
        "GET", f"{settings.JSONBIN_BASE_URL}/b/{bin_id}/latest"
    )
    record = resp.json().get("record", resp.json())
    # Handle legacy bins that stored a flat list instead of {"quote_history": [...]}
    if isinstance(record, list):
        return {"quote_history": record}
    if isinstance(record, dict) and "quote_history" not in record:
        return {"quote_history": []}
    return record


async def write_bin(data: dict) -> None:
    bin_id = await ensure_bin_exists()
    await _request_with_retry(
        "PUT", f"{settings.JSONBIN_BASE_URL}/b/{bin_id}", json_data=data
    )


async def append_quote(record: QuoteRecord) -> None:
    data = await read_bin()
    if "quote_history" not in data:
        data["quote_history"] = []
    data["quote_history"].append(record.model_dump(mode="json"))
    await asyncio.sleep(1)  # JSONBin rate limit: 1 write/sec
    await write_bin(data)


async def query_history(
    item_name: str | None = None, vendor_name: str | None = None
) -> list[QuoteRecord]:
    data = await read_bin()
    records = data.get("quote_history", [])
    results = []
    for r in records:
        try:
            parsed = QuoteRecord(**r)
        except Exception:
            continue
        if item_name and item_name.lower() not in r.get("item_name", "").lower():
            continue
        if vendor_name and vendor_name.lower() not in r.get("vendor_name", "").lower():
            continue
        results.append(parsed)
    return results


async def get_all_history() -> list[QuoteRecord]:
    data = await read_bin()
    results = []
    for r in data.get("quote_history", []):
        try:
            results.append(QuoteRecord(**r))
        except Exception:
            continue
    return results


async def delete_quote(record_id: str) -> bool:
    data = await read_bin()
    original_len = len(data.get("quote_history", []))
    data["quote_history"] = [
        r for r in data.get("quote_history", [])
        if r.get("id") != record_id
    ]
    if len(data["quote_history"]) == original_len:
        return False
    await asyncio.sleep(1)  # JSONBin rate limit
    await write_bin(data)
    return True
