#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "live_urls.json"
DEFAULT_OUTPUT = ROOT / "logs" / "live_test_latest.json"
DEFAULT_API = "http://127.0.0.1:8000"


@dataclass
class CaseResult:
    label: str
    url: str
    status: str
    product_no: str = "-"
    name: str = "-"
    price_tier_count: int = 0
    thumbnail_found: bool = False
    detail_image_count: int = 0
    qa_flags: list[str] | None = None
    warnings: list[str] | None = None
    registration_status: str = "-"
    review_flags: list[str] | None = None
    blockers: list[str] | None = None
    error: str | None = None
    duration_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "url": self.url,
            "status": self.status,
            "product_no": self.product_no,
            "name": self.name,
            "price_tier_count": self.price_tier_count,
            "thumbnail_found": self.thumbnail_found,
            "detail_image_count": self.detail_image_count,
            "qa_flags": self.qa_flags or [],
            "warnings": self.warnings or [],
            "registration_status": self.registration_status,
            "review_flags": self.review_flags or [],
            "blockers": self.blockers or [],
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("urls", [])
    if not isinstance(cases, list) or not cases:
        raise SystemExit(f"No live test URLs found in {path}")
    return cases


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def classify(payload: dict[str, Any], expect: dict[str, Any]) -> tuple[str, list[str]]:
    product = payload["product"]
    package = payload["smartstore_package"]
    issues: list[str] = []

    price_tier_count = len(product.get("price_tiers", []))
    detail_image_count = len(product.get("detail_image_urls", []))
    thumbnail_found = bool(product.get("thumbnail_url"))
    qa_flags = list(package.get("qa_flags", []))
    warnings = list(product.get("warnings", []))

    if expect.get("thumbnail_required", True) and not thumbnail_found:
        issues.append("대표 이미지 없음")
    if price_tier_count < int(expect.get("min_price_tiers", 1)):
        issues.append(f"가격 구간 부족({price_tier_count})")
    if detail_image_count < int(expect.get("min_detail_images", 1)):
        issues.append(f"상세 이미지 부족({detail_image_count})")
    if qa_flags:
        issues.extend(qa_flags)
    if warnings:
        issues.extend(warnings)

    if not product.get("original_name") or not price_tier_count or not thumbnail_found:
        return "BLOCKED", issues
    if issues:
        return "NEED_REVIEW", issues
    return "READY", []


def run_case(api_base: str, case: dict[str, Any], timeout: int) -> CaseResult:
    label = str(case.get("label") or "-")
    source_url = str(case["url"])
    started = time.perf_counter()
    try:
        payload = post_json(f"{api_base.rstrip('/')}/api/analyze", {"url": source_url}, timeout)
        status, issues = classify(payload, case.get("expect", {}))
        product = payload["product"]
        package = payload["smartstore_package"]
        gate = package.get("registration_gate", {})
        return CaseResult(
            label=label,
            url=source_url,
            status=status,
            product_no=str(product.get("product_no") or "-"),
            name=str(product.get("original_name") or "-"),
            price_tier_count=len(product.get("price_tiers", [])),
            thumbnail_found=bool(product.get("thumbnail_url")),
            detail_image_count=len(product.get("detail_image_urls", [])),
            qa_flags=issues or list(package.get("qa_flags", [])),
            warnings=list(product.get("warnings", [])),
            registration_status=str(package.get("registration_status") or "-"),
            review_flags=list(gate.get("review_flags", [])),
            blockers=list(gate.get("blockers", [])),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return CaseResult(label=label, url=source_url, status="ERROR", error=f"HTTP {exc.code}: {detail}", duration_ms=round((time.perf_counter() - started) * 1000, 2))
    except (URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        return CaseResult(label=label, url=source_url, status="ERROR", error=str(exc), duration_ms=round((time.perf_counter() - started) * 1000, 2))


def print_table(results: list[CaseResult]) -> None:
    headers = ["FETCH", "REG", "NO", "PRICE", "THUMB", "DETAIL", "NAME"]
    rows = []
    for result in results:
        rows.append([
            result.status,
            result.registration_status,
            result.product_no,
            str(result.price_tier_count),
            "Y" if result.thumbnail_found else "N",
            str(result.detail_image_count),
            result.name[:42],
        ])
    widths = [max(len(str(row[i])) for row in [headers, *rows]) for i in range(len(headers))]
    print(" | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(str(row[i]).ljust(widths[i]) for i in range(len(headers))))

    print("\n확인 필요/에러:")
    noisy = [r for r in results if r.status != "READY" or r.blockers]
    if not noisy:
        print("- 추출 스모크 차단 없음. 등록 전 상태는 REG 열과 review_flags를 확인하세요.")
    for result in noisy:
        print(f"- {result.status} {result.product_no} {result.url}")
        for issue in result.qa_flags or []:
            print(f"  · {issue}")
        for blocker in result.blockers or []:
            print(f"  · {blocker}")
        if result.error:
            print(f"  · {result.error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Domeggook live URL smoke tests through the local analyze API.")
    parser.add_argument("--api", default=DEFAULT_API, help="Analyze API base URL")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Live URL config JSON")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output JSON path")
    parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout seconds")
    args = parser.parse_args()

    cases = load_cases(args.config)
    results = [run_case(args.api, case, args.timeout) for case in cases]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"api": args.api, "results": [r.as_dict() for r in results]}, ensure_ascii=False, indent=2), encoding="utf-8")

    print_table(results)
    print(f"\n결과 JSON: {args.output}")
    return 1 if any(result.status in {"BLOCKED", "ERROR"} for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
