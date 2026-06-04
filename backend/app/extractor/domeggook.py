from __future__ import annotations

import re
from html import unescape
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from app.models import DomeggookProduct, PriceTier


class DomeggookParseError(ValueError):
    """Raised for invalid Domeggook input or unsupported HTML."""


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


def normalize_domeggook_url(raw_url: str) -> str:
    candidate = raw_url.strip()
    if not candidate:
        raise DomeggookParseError("Domeggook URL is empty")
    if "://" not in candidate:
        candidate = "https://" + candidate
    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "domeggook.com":
        raise DomeggookParseError("Only Domeggook product URLs are supported")
    product_no = extract_product_no_from_url(candidate)
    if not product_no:
        raise DomeggookParseError("Could not find Domeggook product number in URL")
    return urlunparse(("https", "domeggook.com", f"/{product_no}", "", "", ""))


def extract_product_no_from_url(url: str) -> Optional[str]:
    parsed = urlparse(url if "://" in url else "https://" + url)
    match = re.search(r"/(\d{5,})(?:/)?$", parsed.path)
    return match.group(1) if match else None


def parse_price_tiers(text: str) -> list[dict[str, int]]:
    compact = _collapse_ws(text)
    qty_match = re.search(r"수량\s*\(?개\)?\s*(.*?)\s*단가\s*\(?원\)?", compact)
    price_match = re.search(r"단가\s*\(?원\)?\s*(.*)", compact)
    if not qty_match or not price_match:
        return []
    qtys = [int(n.replace(",", "")) for n in re.findall(r"(\d[\d,]*)\s*~", qty_match.group(1))]
    prices = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", price_match.group(1))]
    return [
        {"min_qty": qty, "unit_price": price}
        for qty, price in zip(qtys, prices)
    ]


def parse_product_html(html: str, source_url: str) -> DomeggookProduct:
    normalized_url = normalize_domeggook_url(source_url)
    soup = BeautifulSoup(html, "html.parser")
    visible_text = _collapse_ws(soup.get_text(" "))
    warnings: list[str] = []

    product_no = _first_match(visible_text, r"상품번호\s*[:：]\s*(\d+)") or extract_product_no_from_url(normalized_url)
    if not product_no:
        raise DomeggookParseError("Could not determine product number")

    original_name = _extract_name(soup)
    if not original_name:
        original_name = f"Domeggook product {product_no}"
        warnings.append("상품명을 찾지 못해 기본 상품명을 사용했습니다.")

    seller_name = _first_match(visible_text, r"판매자(?:명)?\s*[:：]\s*([^:：]+?)(?:\s+상품번호|\s+카테고리|$)")
    if seller_name:
        seller_name = _clean_label_value(seller_name)

    category_path = _extract_category_path(soup, visible_text)
    min_order_qty = _extract_int_after_label(visible_text, ["최소구매수량", "최소주문수량", "최소 주문 수량"])
    parsed_price_tiers = (
        _extract_price_tiers_from_tables(soup)
        or parse_price_tiers(visible_text)
        or _extract_price_tiers_from_js_state(html, min_order_qty=min_order_qty)
    )
    price_tiers = [PriceTier(**item) for item in parsed_price_tiers]
    if not price_tiers:
        warnings.append("가격 구간을 찾지 못했습니다.")

    stock_qty = _extract_int_after_label(visible_text, ["재고수량", "재고 수량"])
    origin = _extract_origin(soup, visible_text)
    shipping_summary = _extract_shipping_summary(soup, visible_text)
    options = _extract_options(soup)
    thumbnail_url = _extract_thumbnail(soup, normalized_url)
    detail_html = _extract_detail_html(soup, normalized_url)
    detail_image_urls = _extract_detail_images(soup, normalized_url, product_no, thumbnail_url)
    detail_image_use_allowed = _extract_detail_permission(visible_text)

    if not thumbnail_url:
        warnings.append("대표 이미지를 찾지 못했습니다.")
    if not detail_image_urls:
        warnings.append("상세 이미지를 찾지 못했습니다.")
    if detail_image_use_allowed is False:
        warnings.append("상세설명 이미지 사용이 허용되지 않았을 수 있습니다.")

    return DomeggookProduct(
        source_url=normalized_url,
        product_no=product_no,
        original_name=original_name,
        seller_name=seller_name,
        category_path=category_path,
        price_tiers=price_tiers,
        min_order_qty=min_order_qty,
        stock_qty=stock_qty,
        origin=origin,
        shipping_summary=shipping_summary,
        options=options,
        thumbnail_url=thumbnail_url,
        detail_image_urls=detail_image_urls,
        detail_html=detail_html,
        detail_image_use_allowed=detail_image_use_allowed,
        warnings=warnings,
    )


async def fetch_product_html(url: str) -> str:
    normalized_url = normalize_domeggook_url(url)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=8.0),
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"},
            follow_redirects=True,
        ) as client:
            response = await client.get(normalized_url)
            response.raise_for_status()
            if "text/html" not in response.headers.get("content-type", ""):
                raise DomeggookParseError("Domeggook response was not HTML")
            return response.text
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Domeggook returned HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not fetch Domeggook page: {exc}") from exc


async def fetch_product_html_with_playwright(url: str) -> str:
    """Optional dynamic fallback; requires installed Playwright browser binaries."""
    normalized_url = normalize_domeggook_url(url)
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError("Playwright is not available") from exc

    try:  # pragma: no cover - not used in deterministic tests
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(user_agent=USER_AGENT)
            await page.goto(normalized_url, wait_until="networkidle", timeout=20000)
            content = await page.content()
            await browser.close()
            return content
    except Exception as exc:
        raise RuntimeError(f"Playwright extraction failed: {exc}") from exc


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def _first_match(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def _clean_label_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :-：")


def _extract_name(soup: BeautifulSoup) -> Optional[str]:
    candidates: list[str] = []
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        candidates.append(str(og["content"]))
    if soup.title and soup.title.string:
        candidates.append(soup.title.string)
    h1 = soup.find("h1")
    if h1:
        candidates.append(h1.get_text(" "))
    for candidate in candidates:
        cleaned = _collapse_ws(candidate)
        cleaned = re.sub(r"^\[도매꾹\]\s*", "", cleaned)
        cleaned = re.sub(r"\s*-\s*도매꾹$", "", cleaned)
        if cleaned:
            return cleaned
    return None


def _extract_category_path(soup: BeautifulSoup, visible_text: str) -> list[str]:
    live_path = _extract_live_domeggook_breadcrumb(soup)
    if live_path:
        return live_path
    for selector in [".category", "#category", ".cate", ".breadcrumb"]:
        node = soup.select_one(selector)
        if node:
            parts = _split_category(node.get_text(" > "))
            if len(parts) > 1:
                return parts
    match = re.search(r"((?:[^>\s]+\s*[>＞]\s*)+[^>\s]+)", visible_text)
    return _split_category(match.group(1)) if match else []


def _extract_live_domeggook_breadcrumb(soup: BeautifulSoup) -> list[str]:
    parts: list[str] = []
    item_view = soup.select_one("#itemView") or soup
    for node in item_view.select('li[id^="lPathCat"]'):
        node_id = str(node.get("id") or "")
        if node_id == "lPathCat1":
            continue
        direct_link = node.find("a", recursive=False)
        if direct_link:
            text = _collapse_ws(direct_link.get_text(" "))
        else:
            clone = BeautifulSoup(str(node), "html.parser")
            for sub in clone.select("ol, ul, .sub"):
                sub.decompose()
            text = _collapse_ws(clone.get_text(" "))
        if text:
            parts.append(text)
    return _dedupe(parts)


def _extract_price_tiers_from_tables(soup: BeautifulSoup) -> list[dict[str, int]]:
    for selector in ["#lBaseAmtTbl", "#lAmtSectionTbl", "table.price"]:
        table = soup.select_one(selector)
        if not table:
            continue
        rows = table.find_all("tr")
        # Domeggook live table: each tbody row is one tier: <th>1 ~</th><td>5,900</td>
        row_tiers: list[dict[str, int]] = []
        for row in rows:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            qty_match = re.search(r"(\d[\d,]*)\s*~", _collapse_ws(cells[0].get_text(" ")))
            price_match = re.search(r"(\d[\d,]*)", _collapse_ws(cells[1].get_text(" ")))
            if qty_match and price_match:
                row_tiers.append(
                    {
                        "min_qty": int(qty_match.group(1).replace(",", "")),
                        "unit_price": int(price_match.group(1).replace(",", "")),
                    }
                )
        if row_tiers:
            return row_tiers

        # Compact table: one row of quantities and one row of unit prices.
        qtys: list[int] = []
        prices: list[int] = []
        for row in rows:
            row_text = _collapse_ws(row.get_text(" "))
            if "수량" in row_text:
                qtys = [int(n.replace(",", "")) for n in re.findall(r"(\d[\d,]*)\s*~", row_text)]
            elif "단가" in row_text:
                prices = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", row_text)]
        if qtys and prices:
            return [{"min_qty": qty, "unit_price": price} for qty, price in zip(qtys, prices)]
    return []


def _extract_price_tiers_from_js_state(html: str, min_order_qty: Optional[int] = None) -> list[dict[str, int]]:
    """Extract Domeggook's JS state fallback price when business-only pages hide the table.

    Some live pages do not render #lBaseAmtTbl/#lAmtSectionTbl in the server HTML, but
    still expose the current wholesale base price in window.lItem.store state as
    `baseAmtDome : 6500`. Use it as a single safe supply-price tier instead of
    treating the product as price-less.
    """
    match = re.search(r"\bbaseAmtDome\s*:\s*['\"]?([0-9][0-9,]*)['\"]?", html)
    if not match:
        return []
    unit_price = int(match.group(1).replace(",", ""))
    if unit_price <= 0:
        return []
    return [{"min_qty": min_order_qty or 1, "unit_price": unit_price}]


def _split_category(text: str) -> list[str]:
    text = text.replace("&gt;", ">").replace("＞", ">")
    return [part.strip() for part in text.split(">") if part.strip()]


def _extract_int_after_label(text: str, labels: Iterable[str]) -> Optional[int]:
    for label in labels:
        match = re.search(re.escape(label) + r"\s*[:：]?\s*(\d[\d,]*)\s*개?", text)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def _extract_short_value(text: str, label: str, stop_labels: list[str]) -> Optional[str]:
    pattern = re.escape(label) + r"\s*[:：]?\s*(.+?)(?:\s+(?:" + "|".join(map(re.escape, stop_labels)) + r")|$)"
    match = re.search(pattern, text)
    if not match:
        return None
    value = _clean_label_value(match.group(1))
    return value or None


def _extract_origin(soup: BeautifulSoup, visible_text: str) -> Optional[str]:
    for selector in [
        "tr.lInfoItemCountry td.lInfoItemCountryContent",
        ".lInfoItemCountryContent",
        "tr.lInfoItemCountry td",
    ]:
        node = soup.select_one(selector)
        if node:
            value = _collapse_ws(node.get_text(" "))
            if value:
                return value
    return _extract_short_value(visible_text, "원산지", stop_labels=["배송", "상세", "옵션", "최소", "재고", "흥정하기", "장바구니"])


def _extract_shipping_summary(soup: BeautifulSoup, visible_text: str) -> Optional[str]:
    for selector in [
        ".lInfoDeli",
        "tr.lInfoDeli td.lInfoItemContent",
        ".shipping",
        "#shipping",
        ".delivery",
        "#delivery",
    ]:
        node = soup.select_one(selector)
        if node:
            return _collapse_ws(node.get_text(" "))
    match = re.search(r"(배송비\s*\d[\d,]*원[^\n]*?)(?:\s+상세|\s+옵션|$)", visible_text)
    return _collapse_ws(match.group(1)) if match else None


def _extract_options(soup: BeautifulSoup) -> list[str]:
    options: list[str] = []
    for option in soup.select("select option"):
        text = _collapse_ws(option.get_text(" "))
        if text and text not in {"선택", "옵션선택"}:
            options.append(text)
    return _dedupe(options)


def _absolute_url(url: str, base_url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return urljoin(base_url, url)


def _extract_thumbnail(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    thumb = soup.select_one("#lThumbImg")
    if thumb and thumb.get("src"):
        return _absolute_url(str(thumb["src"]), base_url)
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return _absolute_url(str(og["content"]), base_url)
    return None


def _extract_detail_images(
    soup: BeautifulSoup,
    base_url: str,
    product_no: str,
    thumbnail_url: Optional[str] = None,
) -> list[str]:
    urls: list[str] = []
    bad_tokens = ["banner", "header", "recommend", "logo", "common", "notice", "arrow"]
    bad_ancestor_selectors = [
        "#lSeller",
        "#AitemsZone",
        "#AitemsRecommend",
        ".recommend-products",
        ".recommend",
        ".related",
        ".tmpl04",
        ".lNoDirectDealingWrap",
        ".lInfoViewNoticeWrap",
    ]
    detail_scopes = soup.select(
        "#detail, #detailView, #itemDetail, #goodsDetail, #lInfoViewItemContents, "
        ".detail, .detail-view, .detail_view, .goods-detail, .goods_detail, .item-detail, .item_detail, .lInfoViewItemContents"
    )
    search_roots = detail_scopes or [soup]
    thumbnail_folder = _upload_item_folder(thumbnail_url or "")
    for root in search_roots:
        for img in root.find_all("img"):
            if any(img.find_parent(selector) for selector in bad_ancestor_selectors):
                continue
            link_parent = img.find_parent("a")
            link_href = str(link_parent.get("href") or "") if link_parent else ""
            if re.search(r"(?:^|/|domeggook\.com/)\d{6,}(?:\D|$)", link_href):
                continue
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            if not src:
                continue
            absolute = _absolute_url(str(src), base_url)
            lowered = absolute.lower()
            if any(token in lowered for token in bad_tokens):
                continue
            same_product_folder = bool(thumbnail_folder and thumbnail_folder in absolute)
            in_explicit_detail_scope = bool(img.find_parent(id="lInfoViewItemContents") or img.find_parent(class_="lInfoViewItemContents"))
            looks_detail = (
                "detail" in lowered
                or product_no in lowered
                or in_explicit_detail_scope
                or (same_product_folder and "_stt_" in lowered)
            )
            if looks_detail and "thumb" not in lowered and "_stt_150" not in lowered:
                urls.append(absolute)
    return _dedupe(urls)


def _extract_detail_html(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Return the supplier's original detail-page HTML when Domeggook embeds it.

    Live Domeggook pages commonly keep the real seller detail in a hidden
    `textarea#contentsBuffer` and then assign it into `#lInfoViewItemContents`
    with JavaScript. Building a new summary from images loses iframes/layout, so
    preserve this source HTML and only normalize URLs.
    """
    for selector in ["textarea#contentsBuffer", "#contentsBuffer"]:
        node = soup.select_one(selector)
        if not node:
            continue
        raw_html = node.string if node.string is not None else node.decode_contents()
        normalized = _normalize_detail_html_urls(raw_html or "", base_url)
        if normalized.strip():
            return normalized.strip()

    container = soup.select_one("#lInfoViewItemContents, .lInfoViewItemContents")
    if not container:
        return None
    clone = BeautifulSoup(str(container), "html.parser")
    for unwanted in clone.select("script, textarea#contentsBuffer, #preloadArea"):
        unwanted.decompose()
    raw_html = clone.decode_contents()
    normalized = _normalize_detail_html_urls(raw_html or "", base_url)
    return normalized.strip() or None


def _normalize_detail_html_urls(raw_html: str, base_url: str) -> str:
    detail_soup = BeautifulSoup(raw_html, "html.parser")
    for tag in detail_soup.find_all(["img", "iframe", "source", "a"]):
        for attr in ["src", "data-src", "data-original", "href"]:
            value = tag.get(attr)
            if value:
                tag[attr] = _absolute_url(str(value), base_url)
    return detail_soup.decode_contents()


def _upload_item_folder(url: str) -> Optional[str]:
    match = re.search(r"(/upload/item/[^?]+/)[^/?]+", url)
    return match.group(1) if match else None


def _extract_detail_permission(text: str) -> Optional[bool]:
    if "상세설명 이미지 사용여부" in text or "상세 이미지 사용" in text:
        if "사용허용" in text or "사용 허용" in text:
            return True
        if "사용불가" in text or "사용 불가" in text or "불허" in text:
            return False
    return None


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
