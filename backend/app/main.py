from __future__ import annotations

from time import perf_counter

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.extractor.domeggook import DomeggookParseError, fetch_product_html, parse_product_html
from app.logging_utils import LOG_FILE, configure_logging, write_json_log
from app.models import AnalyzeRequest, AnalyzeResponse, BrowserHarnessStatusResponse, BrowserPreviewRequest, BrowserPreviewResponse
from app.smartstore.browser_harness_registration import check_browser_harness_readiness, run_browser_preview
from app.smartstore.package_builder import build_smartstore_package

logger = configure_logging()

app = FastAPI(title="Domeggook to SmartStore MVP", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ],
    # Windows Chrome accesses WSL-hosted apps through the WSL private IP
    # (for example http://192.168.168.150:3001), not through localhost.
    # Keep this scoped to local development frontend ports instead of using "*"
    # because credentials support is enabled.
    allow_origin_regex=r"http://192\.168\.\d{1,3}\.\d{1,3}:(3000|3001)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/log-path")
def log_path() -> dict[str, str]:
    return {"log_file": str(LOG_FILE)}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    started = perf_counter()
    has_html = bool(request.html)
    write_json_log(logger, "analyze_start", url=request.url, has_pasted_html=has_html)
    try:
        html = request.html if request.html is not None else await fetch_product_html(request.url)
        product = parse_product_html(html, request.url)
        package = build_smartstore_package(product)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        write_json_log(
            logger,
            "analyze_success",
            url=request.url,
            normalized_url=product.source_url,
            product_no=product.product_no,
            name=product.original_name,
            category_path=product.category_path,
            price_tier_count=len(product.price_tiers),
            thumbnail_found=bool(product.thumbnail_url),
            detail_image_count=len(product.detail_image_urls),
            detail_image_use_allowed=product.detail_image_use_allowed,
            warning_count=len(product.warnings),
            warnings=product.warnings,
            qa_flags=package.qa_flags,
            recommended_sale_price=package.sale_price_recommendation,
            duration_ms=duration_ms,
        )
        return AnalyzeResponse(product=product, smartstore_package=package)
    except DomeggookParseError as exc:
        write_json_log(logger, "analyze_error", url=request.url, error_type="DomeggookParseError", detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        write_json_log(logger, "analyze_error", url=request.url, error_type="RuntimeError", detail=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        write_json_log(logger, "analyze_error", url=request.url, error_type=type(exc).__name__, detail=str(exc))
        raise HTTPException(status_code=502, detail=f"Extraction failed: {exc}") from exc


@app.get("/api/smartstore/browser-harness/status", response_model=BrowserHarnessStatusResponse)
def smartstore_browser_harness_status() -> BrowserHarnessStatusResponse:
    result = check_browser_harness_readiness()
    write_json_log(
        logger,
        "smartstore_browser_harness_status",
        status=result.status,
        harness_bin=result.harness_bin,
        cdp_url=result.cdp_url,
        browser=result.browser,
        current_url=result.current_url,
        page_title=result.page_title,
    )
    return result


@app.post("/api/smartstore/browser-preview", response_model=BrowserPreviewResponse)
async def smartstore_browser_preview(request: BrowserPreviewRequest) -> BrowserPreviewResponse:
    write_json_log(
        logger,
        "smartstore_browser_preview_start",
        url=request.package.source_url,
        product_no=request.package.individual_product.product_no,
        registration_status=request.package.registration_status,
    )
    try:
        result = await run_browser_preview(request)
        write_json_log(
            logger,
            "smartstore_browser_preview_result",
            status=result.status,
            current_url=result.current_url,
            page_title=result.page_title,
            filled_fields=result.filled_fields,
            missing_fields=result.missing_fields,
            preview_opened=result.preview_opened,
            stopped_before_save=result.stopped_before_save,
        )
        return result
    except Exception as exc:
        write_json_log(logger, "smartstore_browser_preview_error", error_type=type(exc).__name__, detail=str(exc))
        raise HTTPException(status_code=502, detail=f"Browser harness preview failed: {exc}") from exc
