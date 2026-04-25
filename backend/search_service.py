import asyncio
import re
import httpx
from bs4 import BeautifulSoup
from backend.models import ExtractedItem, MarketBenchmark, ReputationResult
from backend.ai_service import _call_glm_json

DDG_HTML_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


async def _scrape_search(query: str, num_results: int = 8) -> list[dict]:
    results = []
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.post(
                DDG_HTML_URL,
                data={"q": query},
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for result_div in soup.find_all("div", class_="result", limit=num_results):
                title_tag = result_div.find("a", class_="result__a")
                snippet_tag = result_div.find("a", class_="result__snippet")
                if title_tag:
                    results.append({
                        "title": title_tag.get_text(strip=True),
                        "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
                        "url": title_tag.get("href", ""),
                    })
    except httpx.HTTPError:
        pass
    return results


def _extract_rm_prices(text: str) -> list[float]:
    """Extract Malaysian Ringgit prices from text — handles RM, MYR, RM$ patterns."""
    patterns = [
        r"(?:RM|MYR)\s?(\d+(?:,\d{3})*(?:\.\d{1,2}))",
        r"(\d+(?:,\d{3})*(?:\.\d{2}))\s?(?:RM|MYR)",
    ]
    prices = []
    for pattern in patterns:
        for m in re.findall(pattern, text, re.IGNORECASE):
            try:
                prices.append(float(m.replace(",", "")))
            except ValueError:
                continue
    return prices


async def research_market_price(item_name: str) -> MarketBenchmark:
    # Search across multiple Malaysian marketplaces + general
    shopee_results, lazada_results, general_results = await asyncio.gather(
        _scrape_search(f"site:shopee.com.my {item_name} price"),
        _scrape_search(f"site:lazada.com.my {item_name} price"),
        _scrape_search(f"{item_name} price Malaysia RM"),
    )

    # Combine results from all sources
    all_results = shopee_results + lazada_results + general_results
    all_text = " ".join(r["snippet"] for r in all_results)
    snippets = [f"{r['title']}: {r['snippet']}" for r in all_results if r["snippet"]]

    prices = _extract_rm_prices(all_text)

    if len(prices) >= 2:
        return MarketBenchmark(
            item_name=item_name,
            market_price_low=min(prices),
            market_price_high=max(prices),
            market_price_avg=round(sum(prices) / len(prices), 2),
            source_snippets=snippets[:5],
        )

    # Fallback: ask GLM to estimate Malaysian market price
    try:
        data = await _call_glm_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a Malaysian market pricing expert. Estimate the current "
                        "market price range in Malaysian Ringgit (RM) for the given item. "
                        "Consider Shopee Malaysia, local suppliers, and wholesale prices. "
                        "You MUST provide price estimates — never return null. "
                        "Return JSON: "
                        '{"market_price_low": float, "market_price_high": float, '
                        '"market_price_avg": float}. '
                        "All prices in RM."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Item: {item_name}\nSearch context:\n"
                    + ("\n".join(snippets[:5]) if snippets else "No search results — estimate from your knowledge of Malaysian market prices."),
                },
            ],
            temperature=0.3,
            max_tokens=256,
        )
        if data.get("market_price_avg") is not None:
            return MarketBenchmark(
                item_name=item_name,
                market_price_low=data.get("market_price_low"),
                market_price_high=data.get("market_price_high"),
                market_price_avg=data.get("market_price_avg"),
                source_snippets=snippets[:5] or ["GLM estimated — based on Malaysian market knowledge"],
            )
    except Exception:
        pass

    return MarketBenchmark(item_name=item_name, source_snippets=snippets)


async def research_vendor_reputation(vendor_name: str) -> ReputationResult:
    results = await _scrape_search(f"{vendor_name} reviews complaints Malaysia")

    snippets = [f"{r['title']}: {r['snippet']}" for r in results if r["snippet"]]

    if not snippets:
        # Fallback: ask GLM about the vendor
        try:
            data = await _call_glm_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Based on your knowledge about this vendor/company in Malaysia, "
                            "identify red flags and positive notes. If you don't know the vendor, "
                            "say so. Return JSON: "
                            '{"red_flags": ["..."], "positive_notes": ["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Vendor: {vendor_name}",
                    },
                ],
                temperature=0.3,
                max_tokens=512,
            )
            return ReputationResult(
                vendor_name=vendor_name,
                red_flags=data.get("red_flags", []),
                positive_notes=data.get("positive_notes", []),
                source_snippets=["GLM knowledge-based assessment"],
            )
        except Exception:
            return ReputationResult(vendor_name=vendor_name)

    try:
        data = await _call_glm_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Based on these search results about a vendor, identify "
                        "red flags and positive notes. Return JSON: "
                        '{"red_flags": ["..."], "positive_notes": ["..."]}'
                    ),
                },
                {
                    "role": "user",
                    "content": f"Vendor: {vendor_name}\nSearch results:\n"
                    + "\n".join(snippets),
                },
            ],
            temperature=0.3,
            max_tokens=512,
        )
        return ReputationResult(
            vendor_name=vendor_name,
            red_flags=data.get("red_flags", []),
            positive_notes=data.get("positive_notes", []),
            source_snippets=snippets,
        )
    except Exception:
        return ReputationResult(vendor_name=vendor_name, source_snippets=snippets)


async def research_all(
    items: list[ExtractedItem],
) -> tuple[list[MarketBenchmark], list[ReputationResult]]:
    unique_items = list({item.item_name for item in items})
    unique_vendors = list({item.vendor_name for item in items})

    # Run all research tasks with small stagger to avoid rate limiting
    async def staggered(task, delay):
        if delay > 0:
            await asyncio.sleep(delay)
        return await task

    all_tasks = (
        [research_market_price(name) for name in unique_items]
        + [research_vendor_reputation(name) for name in unique_vendors]
    )

    results = await asyncio.gather(
        *[staggered(task, i * 0.5) for i, task in enumerate(all_tasks)]
    )

    benchmark_results = results[:len(unique_items)]
    reputation_results = results[len(unique_items):]

    return benchmark_results, reputation_results
