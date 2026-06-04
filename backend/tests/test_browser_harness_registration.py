from pathlib import Path

from app.extractor.domeggook import parse_product_html
from app.smartstore.browser_harness_registration import (
    HARNESS_SETUP_STEPS,
    _browser_payload,
    _harness_script,
    _prepare_upload_payload,
    _resolve_image_suffix,
    _to_browser_upload_path,
    check_browser_harness_readiness,
)
from app.smartstore.package_builder import build_smartstore_package
from tests.test_extractor import SAMPLE_HTML


def sample_package():
    product = parse_product_html(SAMPLE_HTML, "https://domeggook.com/54804743")
    return build_smartstore_package(product, margin_rate=0.3)


def test_browser_payload_carries_tags_category_and_upload_paths():
    package = sample_package()

    payload = _browser_payload(
        package,
        upload_payload={
            "representative_upload_path": r"C:\\Temp\\smartstore-harness\\rep.jpg",
            "optional_upload_paths": [r"C:\\Temp\\smartstore-harness\\opt-1.jpg"],
            "detail_upload_paths": [r"C:\\Temp\\smartstore-harness\\detail-1.jpg"],
        },
    )

    assert payload["category_hint"] == "주방용품 > 조리도구 > 집게"
    assert payload["category_search_hint"] == "조리도구 집게"
    assert payload["representative_upload_path"].endswith("rep.jpg")
    assert payload["optional_upload_paths"] == [r"C:\\Temp\\smartstore-harness\\opt-1.jpg"]
    assert payload["detail_upload_paths"] == [r"C:\\Temp\\smartstore-harness\\detail-1.jpg"]
    assert "집게" in payload["tags"]
    assert len(payload["tags"]) <= 10
    assert all(len(tag) <= 10 and " " not in tag for tag in payload["tags"])
    assert "국산 튼튼한 스테인리스 집게" in payload["search_tags"]


def test_to_browser_upload_path_converts_wsl_drive_paths():
    assert _to_browser_upload_path(Path("/mnt/c/Temp/smartstore-harness/test.jpg")) == r"C:\Temp\smartstore-harness\test.jpg"


def test_prepare_upload_payload_collects_download_failures(monkeypatch, tmp_path: Path):
    package = sample_package()

    def fake_download(url: str | None, destination_dir: Path, prefix: str):
        if prefix == "representative-image":
            return r"C:\\Temp\\smartstore-harness\\rep.jpg", None
        return None, f"{prefix}: 다운로드 실패"

    monkeypatch.setattr(
        "app.smartstore.browser_harness_registration._download_image_to_temp",
        fake_download,
    )

    upload_payload, missing_fields = _prepare_upload_payload(package, tmp_path)

    assert upload_payload["representative_upload_path"].endswith("rep.jpg")
    assert upload_payload["optional_upload_paths"] == []
    assert upload_payload["detail_upload_paths"] == []
    assert missing_fields == []


def test_resolve_image_suffix_accepts_octet_stream_jpeg_signature():
    class FakeResponse:
        headers = {"content-type": "application/octet-stream"}
        url = "https://cdn1.domeggook.com/upload/item/image_without_extension?hash=abc"
        content = b"\xff\xd8\xff\xe0" + b"jpeg-bytes"

    assert _resolve_image_suffix("https://example.com/no-extension", FakeResponse()) == ".jpg"


def test_harness_script_targets_collected_registration_fields():
    script = _harness_script("/tmp/payload.json")

    assert 'input[name="category"][placeholder="카테고리명 입력"]' in script
    assert 'textarea[name="editorContent"]' in script
    assert 'textarea[ng-model="vm.editorContent"]' in script
    assert 'vm.func.changeEditorType(vm.CONSTANTS.EDITOR_TYPE.NONE)' in script
    assert "실제 키보드 입력 완료" in script
    assert "click_at_xy" in script
    assert "type_text(str(detail_html))" in script
    assert "open_image_registration('대표이미지')" in script
    assert "사용자 요청으로 등록 생략" in script
    assert "upload_detail_images_to_smarteditor()" in script
    assert "상세설명 SmartEditor ONE 작성 버튼" in script
    assert "상세설명 SmartEditor 이미지 파일 입력" in script
    assert "inject_detail_html_into_smarteditor_body()" in script
    assert "상세설명 SmartEditor 본문 HTML" in script
    assert "카테고리 최종선택" in script
    assert "verify_sale_price()" in script
    assert "verify_stock_quantity()" in script
    assert "set_sale_price_and_stock()" in script
    assert "판매가 최종 DOM 확인" in script
    assert "재고수량 최종 DOM 확인" in script
    assert "stockQuantity" in script
    assert "handle_origin()" in script
    assert 'originAreaInfo.originAreaExposureType' in script
    assert 'originAreaInfo.firstSubOriginAreaType' in script
    assert 'originAreaInfo.secondSubOriginAreaType' in script
    assert "0200037" in script
    assert "원산지 수입사" in script
    assert "set_detail_html()" in script
    assert "set_search_tags()" in script
    assert 'select[ng-model="vm.directInputTag"]' in script
    assert "selectize.createItem" in script
    assert "검색설정 태그" in script
    assert "HTML 작성 탭 직접 입력 사용; SmartEditor ONE 전환/작성 버튼 생략" in script
    assert "HTML 작성 탭 입력 실패; SmartEditor ONE은 사용자 요청으로 실행하지 않음" in script
    assert "상세설명 원문 확인" in script
    assert "상세설명 HTML DOM/Angular 동기화" in script
    assert "상세설명 최종 HTML 작성 탭 재확인" in script
    assert "iframe" in script
    assert "상품 등록권한 신청이 필요합니다" in script
    assert "구매대행 판매" in script


def test_browser_harness_readiness_reports_missing_executable(monkeypatch):
    monkeypatch.delenv("BROWSER_HARNESS_WIN_BIN", raising=False)
    monkeypatch.setattr("app.smartstore.browser_harness_registration.shutil.which", lambda _name: None)

    result = check_browser_harness_readiness()

    assert result.status == "NOT_CONFIGURED"
    assert result.harness_bin is None
    assert result.setup_steps == HARNESS_SETUP_STEPS


def test_browser_harness_readiness_reports_ready(monkeypatch):
    class FakeVersionResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Browser": "Chrome/120.0.0.0"}

    class FakeCompletedProcess:
        returncode = 0
        stdout = "{'url': 'https://sell.smartstore.naver.com/#/products/create', 'title': '네이버 스마트스토어센터', 'w': 1200, 'h': 800}\n"
        stderr = ""

    monkeypatch.setenv("BROWSER_HARNESS_WIN_BIN", "/usr/local/bin/browser-harness-win")
    monkeypatch.setenv("BU_CDP_URL", "http://127.0.0.1:9223")
    monkeypatch.setattr("app.smartstore.browser_harness_registration.httpx.get", lambda *_args, **_kwargs: FakeVersionResponse())
    monkeypatch.setattr("app.smartstore.browser_harness_registration.subprocess.run", lambda *_args, **_kwargs: FakeCompletedProcess())

    result = check_browser_harness_readiness()

    assert result.status == "READY"
    assert result.browser == "Chrome/120.0.0.0"
    assert result.current_url == "https://sell.smartstore.naver.com/#/products/create"
    assert result.page_title == "네이버 스마트스토어센터"
    assert result.setup_steps == []


def test_browser_harness_readiness_reports_cdp_unreachable(monkeypatch):
    def fake_get(*_args, **_kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setenv("BROWSER_HARNESS_WIN_BIN", "/usr/local/bin/browser-harness-win")
    monkeypatch.setenv("BU_CDP_URL", "http://127.0.0.1:9223")
    monkeypatch.setattr("app.smartstore.browser_harness_registration.httpx.get", fake_get)

    result = check_browser_harness_readiness()

    assert result.status == "CDP_UNREACHABLE"
    assert "connection refused" in result.message
    assert result.setup_steps == HARNESS_SETUP_STEPS
