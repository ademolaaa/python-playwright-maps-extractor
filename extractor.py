"""
Async Playwright Business Directory & Maps Extraction Pipeline.
"""
import argparse
import asyncio
import logging
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote_plus

import pandas as pd
import phonenumbers
from playwright.async_api import async_playwright, Page

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("maps_extractor")


@dataclass
class BusinessRecord:
    business_name: str
    category: str
    address: str
    phone: str
    website: str
    source_url: str


def normalize_phone(raw_phone: str, default_region: str = "US") -> str:
    """Validate and format a phone number into E.164 format."""
    if not raw_phone:
        return ""
    try:
        parsed = phonenumbers.parse(raw_phone, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    digits = re.sub(r"\D+", "", raw_phone)
    return f"+1{digits}" if len(digits) == 10 and default_region == "US" else raw_phone.strip()


class MapsBusinessExtractor:
    """Extracts public business listings using Playwright with polite scrolling."""

    def __init__(self, headless: bool = True, region: str = "US"):
        self.headless = headless
        self.region = region

    async def _extract_card(self, page: Page, href: str, category: str) -> Optional[BusinessRecord]:
        try:
            await page.goto(href, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(1200)
            name = (await page.locator("h1").first.inner_text()).strip() if await page.locator("h1").count() else ""
            if not name:
                return None

            address_el = page.locator('button[data-item-id="address"]')
            phone_el = page.locator('button[data-item-id^="phone:"]')
            web_el = page.locator('a[data-item-id="authority"]')

            address = (await address_el.first.inner_text()).strip() if await address_el.count() else ""
            raw_phone = (await phone_el.first.inner_text()).strip() if await phone_el.count() else ""
            website = (await web_el.first.get_attribute("href") or "").strip() if await web_el.count() else ""

            return BusinessRecord(
                business_name=name,
                category=category,
                address=re.sub(r"\s+", " ", address),
                phone=normalize_phone(raw_phone, self.region),
                website=website,
                source_url=href,
            )
        except Exception as exc:
            logger.debug("Skipped %s: %s", href, exc)
            return None

    async def extract(self, query: str, location: str, limit: int = 50) -> List[BusinessRecord]:
        search_url = f"https://www.google.com/maps/search/{quote_plus(f'{query} in {location}')}"
        records: List[BusinessRecord] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(locale="en-US")
            page = await context.new_page()
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)

            hrefs: List[str] = []
            seen_hrefs = set()
            feed = page.locator('div[role="feed"]')
            for _ in range(15):
                links = await page.locator('a[href*="/maps/place/"]').all()
                for link in links:
                    href = await link.get_attribute("href")
                    if href and href not in seen_hrefs:
                        seen_hrefs.add(href)
                        hrefs.append(href)
                if len(hrefs) >= limit or not await feed.count():
                    break
                await feed.evaluate("el => el.scrollBy(0, 1200)")
                await page.wait_for_timeout(1200)

            detail_page = await context.new_page()
            for href in hrefs[:limit]:
                rec = await self._extract_card(detail_page, href, query)
                if rec:
                    records.append(rec)

            await browser.close()
        return records


def export_clean_dataset(records: List[BusinessRecord], output_path: Path) -> Path:
    """Deduplicate extracted records and write CSV or XLSX output."""
    df = pd.DataFrame([asdict(r) for r in records])
    if not df.empty:
        df = df.drop_duplicates(subset=["business_name", "address"], keep="first")
        df = df.sort_values(by=["business_name"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".xlsx":
        df.to_excel(output_path, index=False)
    else:
        df.to_csv(output_path, index=False, encoding="utf-8")
    logger.info("Exported %d deduplicated records to %s", len(df), output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Extract and normalize business directory records.")
    parser.add_argument("--query", required=True, help="Target business category")
    parser.add_argument("--location", required=True, help="City or region")
    parser.add_argument("--limit", type=int, default=25, help="Max listings to capture")
    parser.add_argument("--out", default="output/extracted_leads.csv", help="Output CSV or XLSX path")
    args = parser.parse_args()

    extractor = MapsBusinessExtractor(headless=True)
    results = asyncio.run(extractor.extract(args.query, args.location, limit=args.limit))
    export_clean_dataset(results, Path(args.out))


if __name__ == "__main__":
    main()
