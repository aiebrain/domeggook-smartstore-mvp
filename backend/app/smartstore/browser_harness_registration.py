from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.models import BrowserHarnessStatusResponse, BrowserPreviewRequest, BrowserPreviewResponse, SmartStorePackage

SMARTSTORE_CREATE_URL = "https://sell.smartstore.naver.com/#/products/create"
DEFAULT_CDP_URL = "http://127.0.0.1:9223"
HARNESS_SETUP_STEPS = [
    "Install browser-harness and make browser-harness-win available on PATH, or set BROWSER_HARNESS_WIN_BIN=/absolute/path/to/browser-harness-win.",
    "Start Chrome/Edge with a reachable Chrome DevTools Protocol endpoint.",
    "Set BU_CDP_URL to that endpoint, for example http://127.0.0.1:9223 or a WSL-to-Windows proxy URL.",
    "Log in to Naver SmartStore seller-center in that browser before running browser preview.",
    "Verify with: browser-harness-win <<'PY' then print(page_info()) then PY.",
]
RESULT_MARKER = "__SMARTSTORE_HARNESS_RESULT__"
WINDOWS_TEMP_ROOT = Path("/mnt/c/Temp/smartstore-harness")
IMAGE_SUFFIX_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}
IMAGE_SUFFIX_BY_EXTENSION = {
    ".jpeg": ".jpg",
    ".jpg": ".jpg",
    ".png": ".png",
    ".gif": ".gif",
    ".bmp": ".bmp",
}


def _category_search_hint(category_path: list[str]) -> str:
    if not category_path:
        return ""
    if len(category_path) >= 2:
        return " ".join(category_path[-2:])
    return category_path[-1]


def _preferred_harness_tmp_dir() -> Path:
    WINDOWS_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    return WINDOWS_TEMP_ROOT


def _to_browser_upload_path(local_path: Path) -> str:
    parts = local_path.parts
    if len(parts) >= 4 and parts[1] == "mnt" and len(parts[2]) == 1:
        drive = parts[2].upper()
        remainder = "\\".join(parts[3:])
        return f"{drive}:\\{remainder}"
    return str(local_path)


def _safe_filename_stem(prefix: str, url: str) -> str:
    stem = Path(urlparse(url).path).stem or prefix
    return re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or prefix


def _resolve_image_suffix(url: str, response: httpx.Response) -> str | None:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type in IMAGE_SUFFIX_BY_CONTENT_TYPE:
        return IMAGE_SUFFIX_BY_CONTENT_TYPE[content_type]
    extension = Path(urlparse(str(response.url)).path).suffix.lower() or Path(urlparse(url).path).suffix.lower()
    if extension in IMAGE_SUFFIX_BY_EXTENSION:
        return IMAGE_SUFFIX_BY_EXTENSION[extension]
    content = response.content[:16]
    if content.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if content.startswith(b"BM"):
        return ".bmp"
    return None


def _download_image_to_temp(url: str | None, destination_dir: Path, prefix: str) -> tuple[str | None, str | None]:
    if not url:
        return None, f"{prefix}: 원본 이미지 URL 없음"
    try:
        response = httpx.get(url, follow_redirects=True, timeout=20.0)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network exception text depends on runtime
        return None, f"{prefix}: 이미지 다운로드 실패 ({type(exc).__name__}: {exc})"

    suffix = _resolve_image_suffix(url, response)
    if not suffix:
        content_type = response.headers.get("content-type", "알 수 없음")
        return None, f"{prefix}: 지원하지 않는 이미지 형식 ({content_type})"

    local_path = destination_dir / f"{_safe_filename_stem(prefix, url)}{suffix}"
    local_path.write_bytes(response.content)
    if not response.content:
        return None, f"{prefix}: 다운로드한 이미지 파일이 비어 있음"
    return _to_browser_upload_path(local_path), None


def _prepare_upload_payload(package: SmartStorePackage, destination_dir: Path) -> tuple[dict[str, Any], list[str]]:
    product = package.individual_product
    image_preparation = product.image_preparation
    missing_fields: list[str] = []

    representative_upload_path, rep_error = _download_image_to_temp(
        image_preparation.representative_url,
        destination_dir,
        "representative-image",
    )
    if rep_error:
        missing_fields.append(f"대표이미지 파일 준비: {rep_error.split(': ', 1)[-1]}")

    # 사용자 요청: 추가이미지는 등록하지 않고, 상세설명 이미지는 SmartEditor 업로드가 아니라
    # HTML 작성 탭의 원문 <img src="https://...">로만 등록한다. 따라서 브라우저 업로드용
    # 파일은 대표이미지만 준비한다.
    return {
        "representative_upload_path": representative_upload_path,
        "optional_upload_paths": [],
        "detail_upload_paths": [],
    }, missing_fields


def _browser_payload(
    package: SmartStorePackage,
    upload_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    product = package.individual_product
    pricing = product.pricing
    upload_payload = upload_payload or {}
    return {
        "create_url": SMARTSTORE_CREATE_URL,
        "product_name": product.smartstore_name_candidate,
        "sale_price": pricing.sale_price_candidate,
        "stock_quantity": product.stock_quantity_candidate,
        "origin": product.origin,
        "detail_html": package.detailContent,
        "representative_url": product.image_preparation.representative_url,
        "representative_upload_path": upload_payload.get("representative_upload_path"),
        "optional_image_urls": product.image_preparation.optional_image_urls,
        "optional_upload_paths": upload_payload.get("optional_upload_paths", []),
        "detail_image_urls": product.image_preparation.detail_image_urls,
        "detail_upload_paths": upload_payload.get("detail_upload_paths", []),
        "category_hint": " > ".join(product.category_path_hint),
        "category_search_hint": _category_search_hint(product.category_path_hint),
        "leaf_category_id": product.leaf_category_id,
        "tags": product.tags,
        "search_tags": product.search_tags,
        "review_flags": package.registration_gate.review_flags,
        "missing_fields": package.registration_gate.missing_fields,
        "blockers": package.registration_gate.blockers,
        "registration_status": package.registration_status,
    }


def _resolve_harness_bin() -> str | None:
    return os.environ.get("BROWSER_HARNESS_WIN_BIN") or shutil.which("browser-harness-win")


def _resolve_cdp_url() -> str:
    return os.environ.get("BU_CDP_URL", DEFAULT_CDP_URL)


def check_browser_harness_readiness(timeout_seconds: int = 12) -> BrowserHarnessStatusResponse:
    cdp_url = _resolve_cdp_url()
    harness_bin = _resolve_harness_bin()
    if not harness_bin:
        return BrowserHarnessStatusResponse(
            status="NOT_CONFIGURED",
            message="browser-harness-win 실행 파일을 찾지 못했습니다. PATH에 추가하거나 BROWSER_HARNESS_WIN_BIN 환경변수를 설정하세요.",
            harness_bin=None,
            cdp_url=cdp_url,
            setup_steps=HARNESS_SETUP_STEPS,
        )

    try:
        version_response = httpx.get(f"{cdp_url.rstrip('/')}/json/version", timeout=3.0)
        version_response.raise_for_status()
        version_payload = version_response.json()
    except Exception as exc:
        return BrowserHarnessStatusResponse(
            status="CDP_UNREACHABLE",
            message=f"Chrome DevTools endpoint에 연결하지 못했습니다: {type(exc).__name__}: {exc}",
            harness_bin=harness_bin,
            cdp_url=cdp_url,
            setup_steps=HARNESS_SETUP_STEPS,
        )

    env = os.environ.copy()
    env.setdefault("BU_CDP_URL", cdp_url)
    smoke_script = "print(page_info())\n"
    try:
        proc = subprocess.run(
            [harness_bin],
            input=smoke_script,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return BrowserHarnessStatusResponse(
            status="HARNESS_ERROR",
            message=f"browser-harness smoke test가 {timeout_seconds}초 안에 끝나지 않았습니다.",
            harness_bin=harness_bin,
            cdp_url=cdp_url,
            browser=version_payload.get("Browser"),
            setup_steps=HARNESS_SETUP_STEPS,
        )
    except Exception as exc:
        return BrowserHarnessStatusResponse(
            status="HARNESS_ERROR",
            message=f"browser-harness 실행에 실패했습니다: {type(exc).__name__}: {exc}",
            harness_bin=harness_bin,
            cdp_url=cdp_url,
            browser=version_payload.get("Browser"),
            setup_steps=HARNESS_SETUP_STEPS,
        )

    output = (proc.stdout + "\n" + proc.stderr).strip()
    if proc.returncode != 0:
        return BrowserHarnessStatusResponse(
            status="HARNESS_ERROR",
            message=f"browser-harness smoke test가 실패했습니다. exit={proc.returncode}, output={output[-1000:]}",
            harness_bin=harness_bin,
            cdp_url=cdp_url,
            browser=version_payload.get("Browser"),
            setup_steps=HARNESS_SETUP_STEPS,
        )

    page_info_line = next((line for line in output.splitlines() if line.strip().startswith("{") and "'url'" in line), "")
    current_url = None
    page_title = None
    if page_info_line:
        current_url_match = re.search(r"'url': '([^']*)'", page_info_line)
        page_title_match = re.search(r"'title': '([^']*)'", page_info_line)
        current_url = current_url_match.group(1) if current_url_match else None
        page_title = page_title_match.group(1) if page_title_match else None

    return BrowserHarnessStatusResponse(
        status="READY",
        message="browser-harness와 Chrome DevTools endpoint가 정상 동작합니다. 스마트스토어 preview 기능을 사용할 수 있습니다.",
        harness_bin=harness_bin,
        cdp_url=cdp_url,
        browser=version_payload.get("Browser"),
        current_url=current_url,
        page_title=page_title,
        setup_steps=[],
    )


def _harness_script(payload_path: str) -> str:
    # This script runs inside browser-harness-win. It intentionally never clicks
    # 저장하기/임시저장/등록완료/삭제. It only opens seller center, tries safe
    # field entry/upload helpers, then clicks 미리보기 if that control is available.
    script = textwrap.dedent(
        """
        import json, time, traceback

        payload_path = __PAYLOAD_PATH__
        data = json.load(open(payload_path, 'r', encoding='utf-8'))
        result = {
            'status': 'ERROR',
            'message': '',
            'current_url': '',
            'page_title': '',
            'filled_fields': [],
            'missing_fields': [],
            'preview_opened': False,
            'screenshot_path': None,
            'stopped_before_save': True,
        }
        banned_button_words = ['저장', '임시저장', '등록완료', '삭제']

        def emit():
            print(__RESULT_MARKER__ + json.dumps(result, ensure_ascii=False))

        def add_filled(label, detail=''):
            item = f"{label}: {detail}" if detail else label
            if item not in result['filled_fields']:
                result['filled_fields'].append(item)

        def add_missing(label, reason):
            item = f"{label}: {reason}" if reason else label
            if item not in result['missing_fields']:
                result['missing_fields'].append(item)

        def safe_eval(expr):
            try:
                return js(expr)
            except Exception as exc:
                return {'__error__': str(exc)}

        def set_by_keywords(label, value, keywords):
            if value is None or value == '':
                add_missing(label, '값 없음')
                return False
            expr = '''(() => {
              const value = %s;
              const keywords = %s;
              const controls = Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]'))
                .filter(el => !el.disabled && el.offsetParent !== null && el.type !== 'file');
              function textOf(el) {
                const attrs = [el.name, el.id, el.placeholder, el.getAttribute('aria-label'), el.getAttribute('title')]
                  .filter(Boolean).join(' ');
                const label = el.id ? (document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText || '') : '';
                const parent = el.closest('div, li, section, tr, label, td, th')?.innerText || '';
                return (attrs + ' ' + label + ' ' + parent).toLowerCase();
              }
              function setValue(target, nextValue) {
                target.scrollIntoView({block:'center'});
                if (target.isContentEditable) {
                  target.focus();
                  target.innerHTML = nextValue;
                  target.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:nextValue}));
                  return;
                }
                const proto = target.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (setter) setter.call(target, nextValue); else target.value = nextValue;
                target.dispatchEvent(new Event('input', {bubbles:true}));
                target.dispatchEvent(new Event('change', {bubbles:true}));
              }
              const scored = controls
                .map(el => ({ el, text: textOf(el) }))
                .map(item => ({
                  ...item,
                  score: keywords.reduce((sum, keyword) => sum + (item.text.includes(String(keyword).toLowerCase()) ? 1 : 0), 0),
                }))
                .filter(item => item.score > 0)
                .sort((a, b) => b.score - a.score);
              const target = scored[0]?.el;
              if (!target) return {ok:false, reason:'selector-not-found'};
              setValue(target, value);
              return {ok:true, detail:(scored[0].text || '').slice(0, 160)};
            })()''' % (json.dumps(str(value), ensure_ascii=False), json.dumps(keywords, ensure_ascii=False))
            outcome = safe_eval(expr)
            if isinstance(outcome, dict) and outcome.get('ok'):
                add_filled(label, '입력 완료')
                return True
            add_missing(label, '화면 입력칸 자동탐색 실패')
            return False

        def set_by_selectors(label, value, selectors):
            if value is None or value == '':
                add_missing(label, '값 없음')
                return False
            expr = '''(() => {
              const value = %s;
              const selectors = %s;
              function setValue(target, nextValue) {
                target.scrollIntoView({block:'center'});
                target.focus();
                if (target.isContentEditable) {
                  target.innerHTML = nextValue;
                  target.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:nextValue}));
                  target.dispatchEvent(new Event('change', {bubbles:true}));
                  target.dispatchEvent(new Event('blur', {bubbles:true}));
                  return;
                }
                const proto = target.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (setter) setter.call(target, nextValue); else target.value = nextValue;
                target.dispatchEvent(new Event('input', {bubbles:true}));
                target.dispatchEvent(new Event('change', {bubbles:true}));
                target.dispatchEvent(new Event('blur', {bubbles:true}));
              }
              for (const selector of selectors) {
                const candidates = Array.from(document.querySelectorAll(selector)).filter(el => !el.disabled);
                const target = candidates.find(el => el.offsetParent !== null) || candidates[0];
                if (target) {
                  setValue(target, value);
                  return {ok:true, selector};
                }
              }
              return {ok:false, reason:'selector-not-found'};
            })()''' % (json.dumps(str(value), ensure_ascii=False), json.dumps(selectors, ensure_ascii=False))
            outcome = safe_eval(expr)
            if isinstance(outcome, dict) and outcome.get('ok'):
                add_filled(label, f"입력 완료 ({outcome.get('selector')})")
                return True
            return False

        def click_by_keywords(label, keywords, scope_keywords=None):
            expr = '''(() => {
              const keywords = %s;
              const scopeKeywords = %s;
              const banned = %s;
              const candidates = Array.from(document.querySelectorAll('button, a, [role="button"], label, div, span'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                  el,
                  text: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim(),
                  scope: (el.closest('section, div, li, tr')?.innerText || '').replace(/\s+/g, ' ').trim(),
                }))
                .filter(item => item.text || item.scope)
                .filter(item => keywords.some(keyword => (item.text + ' ' + item.scope).includes(keyword)))
                .filter(item => scopeKeywords.length === 0 || scopeKeywords.some(keyword => item.scope.includes(keyword)))
                .filter(item => !banned.some(word => item.text.includes(word)))
                .sort((a, b) => {
                  const aExact = keywords.some(keyword => a.text === keyword) ? 1 : 0;
                  const bExact = keywords.some(keyword => b.text === keyword) ? 1 : 0;
                  if (aExact !== bExact) return bExact - aExact;
                  return (a.text.length || 9999) - (b.text.length || 9999);
                });
              const target = candidates[0]?.el;
              if (!target) return {ok:false, reason:'selector-not-found'};
              target.scrollIntoView({block:'center'});
              target.click();
              return {ok:true, detail:(candidates[0].text || candidates[0].scope || '').slice(0, 120)};
            })()''' % (json.dumps(keywords, ensure_ascii=False), json.dumps(scope_keywords or [], ensure_ascii=False), json.dumps(banned_button_words, ensure_ascii=False))
            outcome = safe_eval(expr)
            if isinstance(outcome, dict) and outcome.get('ok'):
                add_filled(label, outcome.get('detail') or '클릭 완료')
                return True
            return False

        def dismiss_resume_modal():
            outcome = safe_eval('''(() => {
              const bodyText = document.body.innerText || '';
              if (!bodyText.includes('이전에 작성하던 내용')) return {ok:false, reason:'modal-not-found'};
              const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({el, text:(el.innerText || '').trim()}));
              const cancel = buttons.find(item => item.text === '취소') || buttons.find(item => item.text.includes('취소'));
              if (!cancel) return {ok:false, reason:'cancel-button-not-found'};
              cancel.el.click();
              return {ok:true};
            })()''')
            if isinstance(outcome, dict) and outcome.get('ok'):
                add_filled('이전 작성내용 불러오기 팝업', '취소 클릭 후 새 입력 진행')
                time.sleep(1)
                return True
            return False

        def dismiss_permission_modal_if_present():
            outcome = safe_eval('''(() => {
              const bodyText = document.body.innerText || '';
              const hasPermissionModal = bodyText.includes('상품 등록권한 신청이 필요합니다') || bodyText.includes('권한: 구매대행 판매') || bodyText.includes('상품판매권한 신청 페이지');
              if (!hasPermissionModal) return {ok:false, reason:'modal-not-found'};
              const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({el, text:(el.innerText || '').trim()}));
              const cancel = buttons.find(item => item.text === '취소') || buttons.find(item => item.text.includes('취소'));
              if (!cancel) return {ok:false, reason:'cancel-button-not-found'};
              cancel.el.click();
              return {ok:true};
            })()''')
            if isinstance(outcome, dict) and outcome.get('ok'):
                add_filled('권한 신청 모달', '이전 실행에서 남은 모달을 취소로 닫고 새 입력 진행')
                time.sleep(1)
                return True
            return False

        def scroll_to_text(label, keywords):
            outcome = safe_eval('''(() => {
              const keywords = %s;
              const candidates = Array.from(document.querySelectorAll('section, div, li, tr, label, strong, span, h2, h3'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({el, text:(el.innerText || '').replace(/\s+/g, ' ').trim()}))
                .filter(item => item.text && keywords.some(keyword => item.text.includes(keyword)))
                .sort((a, b) => a.text.length - b.text.length);
              const target = candidates[0]?.el;
              if (!target) return {ok:false};
              target.scrollIntoView({block:'center'});
              return {ok:true, detail:candidates[0].text.slice(0, 120)};
            })()''' % (json.dumps(keywords, ensure_ascii=False)))
            if isinstance(outcome, dict) and outcome.get('ok'):
                time.sleep(0.8)
                return True
            return False

        def discover_file_input(keywords, excluded_keywords=None):
            expr = '''(() => {
              const keywords = %s;
              const excluded = %s;
              const inputs = Array.from(document.querySelectorAll('input[type="file"]')).filter(el => !el.disabled);
              function textOf(el) {
                const attrs = [el.name, el.id, el.accept, el.getAttribute('aria-label'), el.getAttribute('title')]
                  .filter(Boolean).join(' ');
                const label = el.id ? (document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText || '') : '';
                const parent = el.closest('div, li, section, tr, td, label')?.innerText || '';
                return (attrs + ' ' + label + ' ' + parent).replace(/\s+/g, ' ').trim().toLowerCase();
              }
              let fallback = null;
              const scored = inputs.map((el, index) => {
                el.setAttribute('data-smartstore-upload-index', String(index));
                const text = textOf(el);
                const score = keywords.reduce((sum, keyword) => sum + (text.includes(String(keyword).toLowerCase()) ? 3 : 0), 0)
                  - excluded.reduce((sum, keyword) => sum + (text.includes(String(keyword).toLowerCase()) ? 2 : 0), 0)
                  + ((el.accept || '').toLowerCase().includes('image') ? 1 : 0);
                const candidate = {
                  selector: `input[type="file"][data-smartstore-upload-index="${index}"]`,
                  text,
                  multiple: !!el.multiple,
                  score,
                };
                if (!fallback && (candidate.score > 0 || text.includes('이미지') || (el.accept || '').toLowerCase().includes('image'))) {
                  fallback = candidate;
                }
                return candidate;
              }).sort((a, b) => b.score - a.score);
              const best = scored.find(item => item.score > 0) || fallback;
              if (!best) return {ok:false, reason:'file-input-not-found', count:inputs.length};
              return {ok:true, selector:best.selector, detail:best.text.slice(0, 160), multiple:best.multiple, count:inputs.length};
            })()''' % (json.dumps(keywords, ensure_ascii=False), json.dumps(excluded_keywords or [], ensure_ascii=False))
            return safe_eval(expr)

        def upload_to_selector(label, selector, paths, detail=''):
            try:
                upload_file(selector, paths if len(paths) != 1 else paths[0])
                add_filled(label, detail or f'{len(paths)}개 파일 입력 설정')
                return True
            except Exception as exc:
                add_missing(label, f'파일 입력 설정 실패 ({type(exc).__name__}: {exc})')
                return False

        def open_image_registration(scope_label):
            code = 'image.repre' if scope_label == '대표이미지' else 'image.add'
            outcome = safe_eval('''(() => {
              const code = %s;
              const target = document.querySelector(`a.btn-add-img[data-nclicks-code="${code}"]`);
              if (!target) return {ok:false, reason:'image-button-not-found'};
              target.scrollIntoView({block:'center'});
              target.click();
              return {ok:true, text:(target.innerText || target.getAttribute('aria-label') || '이미지 등록').trim(), code};
            })()''' % json.dumps(code, ensure_ascii=False))
            if isinstance(outcome, dict) and outcome.get('ok'):
                add_filled(f'{scope_label} 이미지 등록 열기', outcome.get('text') or '이미지 등록')
                return True
            return click_by_keywords(
                f'{scope_label} 이미지 등록 열기',
                ['이미지 등록', '등록'],
                [scope_label, '상품이미지', '이미지'],
            )

        def upload_images():
            representative_path = data.get('representative_upload_path')
            optional_paths = list(data.get('optional_upload_paths') or [])
            if representative_path:
                scroll_to_text('대표이미지 영역', ['대표이미지', '대표 이미지', '상품이미지'])
                open_image_registration('대표이미지')
                time.sleep(1)
                rep_candidate = discover_file_input(['대표이미지', '대표 이미지', '대표', '메인 이미지', '기본 이미지', '이미지'], ['추가', '동영상'])
            else:
                rep_candidate = None
                add_missing('대표이미지 파일 준비', '업로드 경로 없음')

            if representative_path:
                if isinstance(rep_candidate, dict) and rep_candidate.get('ok'):
                    upload_to_selector('대표이미지 파일 입력', rep_candidate['selector'], [representative_path], '대표 파일 입력 설정')
                    time.sleep(1)
                else:
                    add_missing('대표이미지 파일 입력', '파일 입력칸 자동탐색 실패')

            if data.get('optional_image_urls') or optional_paths:
                add_filled('추가이미지', '사용자 요청으로 등록 생략')

        def open_smarteditor_one_for_detail():
            scroll_to_text('상세설명 영역', ['상세설명', 'SmartEditor', '스마트에디터', 'HTML 작성'])
            safe_eval('''(() => {
              const section = Array.from(document.querySelectorAll('.form-section')).find(el => (el.innerText || '').includes('상세설명'));
              const tab = section?.querySelector('a[ng-click*="EDITOR_TYPE.SEONE"]');
              if (!tab || tab.offsetParent === null) return {ok:false};
              tab.scrollIntoView({block:'center'});
              tab.click();
              return {ok:true};
            })()''')
            time.sleep(0.5)
            exact = safe_eval('''(() => {
              const target = document.querySelector('button[data-nclicks-code="descrip.sebtn"]');
              if (!target || target.offsetParent === null) return {ok:false, reason:'smarteditor-button-not-found'};
              target.scrollIntoView({block:'center'});
              target.click();
              return {ok:true, detail:(target.innerText || '스마트 에디터 ONE 으로 작성').replace(/\s+/g, ' ').trim()};
            })()''')
            if isinstance(exact, dict) and exact.get('ok'):
                add_filled('상세설명 SmartEditor ONE 작성 버튼', exact.get('detail') or '클릭 완료')
                time.sleep(1.2)
                return True
            clicked = click_by_keywords(
                '상세설명 SmartEditor ONE 작성 버튼',
                ['SmartEditor ONE으로 작성', 'SmartEditor ONE', '스마트 에디터 ONE 으로 작성', '스마트 에디터 ONE으로 작성', '스마트 에디터 ONE', '스마트 에디터', '스마트에디터 ONE', '스마트에디터', 'Editor ONE'],
                ['상세설명', '상품상세', '직접 작성'],
            )
            if clicked:
                time.sleep(1.2)
                return True
            add_missing('상세설명 SmartEditor ONE 작성 버튼', '자동탐색 실패')
            return False

        def open_editor_image_dialog():
            outcome = safe_eval('''(() => {
              const keywords = ['사진', '이미지', 'image', 'photo'];
              const candidates = Array.from(document.querySelectorAll('button, a, [role="button"], label, span'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                  el,
                  text: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim(),
                  scope: (el.closest('section, div, li, tr')?.innerText || '').replace(/\s+/g, ' ').trim(),
                  klass: el.className || '',
                  own: (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || el.className || '').replace(/\s+/g, ' ').trim(),
                }))
                .filter(item => keywords.some(keyword => (item.own + ' ' + item.klass).toLowerCase().includes(keyword.toLowerCase())))
                .filter(item => !['사진 보관함', '상품관리', '도움말', '대표이미지', '추가이미지', '상품이미지', '동영상', '저장', '임시저장', '삭제'].some(word => (item.text + ' ' + item.scope).includes(word)))
                .sort((a, b) => {
                  const aExact = ['사진', '이미지'].some(keyword => a.text === keyword) ? 1 : 0;
                  const bExact = ['사진', '이미지'].some(keyword => b.text === keyword) ? 1 : 0;
                  if (aExact !== bExact) return bExact - aExact;
                  return (a.text.length || 9999) - (b.text.length || 9999);
                });
              const target = candidates[0]?.el;
              if (!target) return {ok:false, reason:'editor-image-button-not-found'};
              target.scrollIntoView({block:'center'});
              target.click();
              return {ok:true, detail:(candidates[0].text || candidates[0].klass || '이미지 버튼').slice(0, 120)};
            })()''')
            if isinstance(outcome, dict) and outcome.get('ok'):
                add_filled('상세설명 SmartEditor 이미지 버튼', outcome.get('detail') or '클릭 완료')
                time.sleep(1)
                return True
            return False

        def inject_detail_html_into_smarteditor_body():
            detail_html = data.get('detail_html') or ''
            if not detail_html:
                add_missing('상세설명 SmartEditor 본문 HTML', '원본 상세 HTML 없음')
                return False
            outcome = safe_eval('''(() => {
              const html = %s;
              const expectedImgCount = (String(html || '').match(/<img\\b/gi) || []).length;
              const mutationEvents = ['input', 'change', 'keyup', 'blur'];
              function isVisible(el) {
                return !!el && (el.offsetParent !== null || el.isContentEditable || el.tagName === 'TEXTAREA');
              }
              function descriptor(el) {
                return (el.tagName || 'node')
                  + (el.id ? '#' + el.id : '')
                  + (el.className ? '.' + String(el.className).replace(/\\s+/g,'.').slice(0,80) : '');
              }
              function storedHtml(target) {
                return target.value !== undefined ? String(target.value || '') : String(target.innerHTML || '');
              }
              function notify(target, doc, insertedHtml) {
                try { target.dispatchEvent(new InputEvent('beforeinput', {bubbles:true, inputType:'insertHTML', data:insertedHtml})); } catch (_) {}
                try { target.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertHTML', data:insertedHtml})); } catch (_) {}
                for (const type of mutationEvents) {
                  try { target.dispatchEvent(new Event(type, {bubbles:true})); } catch (_) {}
                }
                try { doc.dispatchEvent(new Event('selectionchange', {bubbles:true})); } catch (_) {}
              }
              function selectExisting(target, doc) {
                try {
                  target.focus?.();
                  const selection = doc.getSelection?.();
                  const range = doc.createRange?.();
                  if (!selection || !range || target.tagName === 'TEXTAREA' || target.tagName === 'INPUT') return false;
                  range.selectNodeContents(target);
                  selection.removeAllRanges();
                  selection.addRange(range);
                  return true;
                } catch (_) { return false; }
              }
              function pasteInto(target, doc) {
                if (!target.isContentEditable && target.getAttribute?.('role') !== 'textbox') return false;
                try {
                  target.focus?.();
                  selectExisting(target, doc);
                  const clipboard = new DataTransfer();
                  clipboard.setData('text/html', html);
                  clipboard.setData('text/plain', String(html).replace(/<[^>]+>/g, ' '));
                  const event = new ClipboardEvent('paste', {bubbles:true, cancelable:true, clipboardData: clipboard});
                  const notCancelled = target.dispatchEvent(event);
                  notify(target, doc, html);
                  return !notCancelled || storedHtml(target).includes('<img') || storedHtml(target).length > 0;
                } catch (_) { return false; }
              }
              function execCommandInto(target, doc) {
                if (!target.isContentEditable && target.getAttribute?.('role') !== 'textbox') return false;
                try {
                  target.focus?.();
                  selectExisting(target, doc);
                  const ok = doc.execCommand?.('insertHTML', false, html);
                  notify(target, doc, html);
                  return !!ok || storedHtml(target).includes('<img');
                } catch (_) { return false; }
              }
              function directSet(target, doc) {
                target.scrollIntoView?.({block:'center'});
                target.focus?.();
                if (target.tagName === 'TEXTAREA' || target.tagName === 'INPUT') {
                  const proto = target.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                  if (setter) setter.call(target, html); else target.value = html;
                } else {
                  target.innerHTML = html;
                }
                notify(target, doc, html);
                return true;
              }
              function writeTarget(target, doc) {
                const methods = [];
                target.scrollIntoView?.({block:'center'});
                if (pasteInto(target, doc)) methods.push('paste-event');
                if (storedHtml(target).match(/<img\\b/i)) return result(target, methods);
                if (execCommandInto(target, doc)) methods.push('execCommand-insertHTML');
                if (storedHtml(target).match(/<img\\b/i)) return result(target, methods);
                if (directSet(target, doc)) methods.push('direct-set');
                return result(target, methods);
              }
              function result(target, methods) {
                const stored = storedHtml(target);
                const storedImgCount = (stored.match(/<img\\b/gi) || []).length;
                return {
                  ok: expectedImgCount === 0 ? stored.length > 0 : storedImgCount >= Math.min(expectedImgCount, 1),
                  imgCount: expectedImgCount,
                  storedImgCount,
                  method: methods.join(' > ') || 'none',
                  text:(target.innerText || target.value || '').slice(0, 120),
                  target:descriptor(target),
                };
              }
              function candidatesFrom(doc, allowIframeBody) {
                const selectors = [
                  '[contenteditable="true"]',
                  '[role="textbox"]',
                  '.se-component-content',
                  '.se-section-document',
                  '.se_editable',
                  '.se2_inputarea',
                  '.se-placeholder',
                  '.ProseMirror',
                  '.CodeMirror-code',
                  'textarea[name="editorContent"]',
                  'textarea[ng-model*="content"]',
                  'textarea[ng-model*="editor"]'
                ];
                if (allowIframeBody) selectors.push('body[contenteditable="true"]');
                const all = [];
                for (const selector of selectors) {
                  try { all.push(...Array.from(doc.querySelectorAll(selector))); } catch (_) {}
                }
                return Array.from(new Set(all)).filter(isVisible).map(el => ({el, doc, allowIframeBody}));
              }
              // Never write to the top-level SmartStore page body; that can replace the whole seller-center UI.
              const pools = candidatesFrom(document, false);
              for (const iframe of Array.from(document.querySelectorAll('iframe'))) {
                try {
                  const doc = iframe.contentDocument || iframe.contentWindow?.document;
                  if (doc) pools.push(...candidatesFrom(doc, true));
                } catch (_) {}
              }
              const scored = pools.map(item => {
                const el = item.el;
                const text = [el.getAttribute?.('aria-label'), el.getAttribute?.('placeholder'), el.className, el.id, el.innerText, el.name]
                  .filter(Boolean).join(' ');
                const rect = el.getBoundingClientRect?.();
                let score = 0;
                if (el.isContentEditable) score += 100;
                if (el.getAttribute?.('role') === 'textbox') score += 70;
                if (el.tagName === 'TEXTAREA') score += 55;
                if (String(text).includes('내용을 입력')) score += 50;
                if (/se-|SmartEditor|smarteditor|editor|inputarea|editable|ProseMirror/i.test(String(text))) score += 45;
                if (/editorContent/i.test(String(text))) score += 40;
                if (el.tagName === 'BODY') score -= item.allowIframeBody ? 5 : 500;
                if (rect && rect.width > 300 && rect.height > 120) score += 20;
                if (rect && rect.width < 80) score -= 50;
                return {...item, score, label:String(text).slice(0, 120)};
              }).sort((a, b) => b.score - a.score);
              const best = scored.find(item => item.score > 0);
              if (!best) return {ok:false, reason:'smarteditor-body-not-found', count:pools.length, topScore:scored[0]?.score};
              return writeTarget(best.el, best.doc);
            })()''' % json.dumps(detail_html, ensure_ascii=False))
            if isinstance(outcome, dict) and outcome.get('ok'):
                add_filled('상세설명 SmartEditor 본문 HTML', f"원본 HTML 직접삽입 완료, 원본 img {outcome.get('imgCount')}개/저장 img {outcome.get('storedImgCount')}개, 방식 {outcome.get('method')} ({outcome.get('target')})")
                return True
            if isinstance(outcome, dict):
                add_missing('상세설명 SmartEditor 본문 HTML', f"본문 직접삽입 실패 ({outcome.get('reason') or 'img 검증 실패'}, target={outcome.get('target')}, storedImg={outcome.get('storedImgCount')})")
            else:
                add_missing('상세설명 SmartEditor 본문 HTML', '본문 직접삽입 실패 (unknown)')
            return False

        def upload_detail_images_to_smarteditor():
            detail_paths = list(data.get('detail_upload_paths') or [])
            has_detail_images = bool(data.get('detail_image_urls'))
            if not detail_paths and has_detail_images:
                add_missing('상세설명 SmartEditor 이미지 업로드', '업로드 경로 없음')
            if not open_smarteditor_one_for_detail():
                return False

            # First preserve the supplier's existing detail page inside SmartEditor itself.
            # This covers the common SmartEditor ONE screen where the toolbar shows a 사진
            # button but no discoverable file input exists until deeper modal state changes.
            injected = inject_detail_html_into_smarteditor_body()

            if not detail_paths:
                return injected
            candidate = discover_file_input(['상세설명', 'SmartEditor', '스마트에디터', '본문', '사진', '이미지'], ['대표', '추가', '상품이미지', '동영상'])
            if not (isinstance(candidate, dict) and candidate.get('ok')):
                open_editor_image_dialog()
                time.sleep(1)
                candidate = discover_file_input(['상세설명', 'SmartEditor', '스마트에디터', '본문', '사진', '이미지'], ['대표', '추가', '상품이미지', '동영상'])
            if isinstance(candidate, dict) and candidate.get('ok'):
                if candidate.get('multiple'):
                    return upload_to_selector('상세설명 SmartEditor 이미지 파일 입력', candidate['selector'], detail_paths, f"{len(detail_paths)}개 본문 이미지 파일 입력 설정") or injected
                uploaded = upload_to_selector('상세설명 SmartEditor 이미지 파일 입력', candidate['selector'], [detail_paths[0]], '첫 본문 이미지 파일 입력 설정')
                if len(detail_paths) > 1:
                    add_missing('상세설명 SmartEditor 나머지 이미지 업로드', f'입력칸이 단일 파일만 허용하여 {len(detail_paths) - 1}개는 사람 업로드 필요')
                return uploaded or injected
            add_missing('상세설명 SmartEditor 이미지 파일 입력', '파일 입력칸 자동탐색 실패; 원본 상세 HTML 이미지 태그는 본문에 주입 시도함')
            return injected

        def set_numeric_product_field(label, value, field_name, selectors):
            expected = ''.join(ch for ch in str(value or '') if ch.isdigit())
            if not expected:
                add_missing(label, '값 없음')
                return False
            state = safe_eval('''(() => {
              const expected = %s;
              const fieldName = %s;
              const selectors = %s;
              const selector = selectors.find(sel => document.querySelector(sel));
              const input = selector ? document.querySelector(selector) : null;
              if (!input) return {ok:false, reason:'input-not-found', fieldName};
              function setDom(el, value) {
                el.scrollIntoView({block:'center'});
                el.focus();
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
                if (setter) setter.call(el, value); else el.value = value;
                for (const type of ['keydown','input','keyup','change','blur']) {
                  try { el.dispatchEvent(new Event(type, {bubbles:true})); } catch (_) {}
                }
              }
              function setScope(el, value) {
                try {
                  const ng = window.angular;
                  if (!ng) return {scope:false, reason:'angular-not-found'};
                  let node = el;
                  while (node) {
                    const scope = ng.element(node).scope?.() || ng.element(node).isolateScope?.();
                    if (scope) {
                      const holders = [scope.vm, scope.$ctrl, scope];
                      for (const holder of holders) {
                        if (holder?.product && fieldName in holder.product) {
                          holder.product[fieldName] = Number(value);
                          try { scope.$applyAsync?.(); } catch (_) {}
                          try { scope.$apply?.(); } catch (_) {}
                          return {scope:true, holder:'product'};
                        }
                      }
                    }
                    node = node.parentElement;
                  }
                  return {scope:false, reason:'product-scope-not-found'};
                } catch (e) { return {scope:false, reason:String(e)}; }
              }
              setDom(input, expected);
              const scopeResult = setScope(input, expected);
              setDom(input, expected);
              const actual = String(input.value || '').replace(/[^0-9]/g, '');
              return {ok: actual === expected, value:actual, expected, selector, scopeResult};
            })()''' % (json.dumps(expected, ensure_ascii=False), json.dumps(field_name, ensure_ascii=False), json.dumps(selectors, ensure_ascii=False)))
            if isinstance(state, dict) and state.get('ok'):
                add_filled(label, f"입력 완료 ({state.get('selector')}, {state.get('value')})")
                return True
            add_missing(label, str(state))
            return False

        def verify_numeric_product_field(label, value, selectors):
            expected = ''.join(ch for ch in str(value or '') if ch.isdigit())
            if not expected:
                return False
            state = safe_eval('''(() => {
              const expected = %s;
              const selectors = %s;
              const selector = selectors.find(sel => document.querySelector(sel));
              const input = selector ? document.querySelector(selector) : null;
              const value = String(input?.value || '').replace(/[^0-9]/g, '');
              return {ok: !!input && value === expected, value, expected, found: !!input, selector};
            })()''' % (json.dumps(expected, ensure_ascii=False), json.dumps(selectors, ensure_ascii=False)))
            if isinstance(state, dict) and state.get('ok'):
                add_filled(label, f"{state.get('value')}")
                return True
            add_missing(label, str(state))
            return False

        def verify_sale_price():
            return verify_numeric_product_field('판매가 최종 DOM 확인', data.get('sale_price'), ['input[name="product.salePrice"]', '#prd_price2'])

        def verify_stock_quantity():
            return verify_numeric_product_field('재고수량 최종 DOM 확인', data.get('stock_quantity'), ['input[name="product.stockQuantity"]', '#stock'])

        def set_sale_price_and_stock():
            set_numeric_product_field('판매가', data.get('sale_price'), 'salePrice', ['input[name="product.salePrice"]', '#prd_price2'])
            verify_sale_price()
            set_numeric_product_field('재고수량', data.get('stock_quantity'), 'stockQuantity', ['input[name="product.stockQuantity"]', '#stock'])
            verify_stock_quantity()

        def handle_origin():
            origin = str(data.get('origin') or '').strip()
            if not origin:
                add_missing('원산지', '원산지 정보 없음')
                return
            scroll_to_text('상품 주요정보 영역', ['상품 주요정보', '원산지'])
            opened = safe_eval('''(() => {
              const title = Array.from(document.querySelectorAll('.title-line[role="button"], div[role="button"], .title-line')).find(el => (el.innerText || '').includes('상품 주요정보'));
              if (!title) return {ok:false, reason:'상품 주요정보 섹션 없음'};
              title.scrollIntoView({block:'center'});
              if (!((document.body.innerText || '').includes('원산지 다른 상품 함께 등록'))) title.click();
              return {ok:true, text:(title.innerText || '').slice(0,160)};
            })()''')
            time.sleep(1.5)
            normalized = origin.replace(' ', '')
            is_import = ('수입' in origin) or ('중국' in origin) or ('아시아' in origin)
            country = '중국' if '중국' in origin else ''
            if not is_import:
                outcome = safe_eval('''(() => {
                  const exposure = document.querySelector('select[ng-model="vm.viewData.originAreaInfo.originAreaExposureType"]');
                  if (!exposure?.selectize) return {ok:false, reason:'origin-exposure-not-found'};
                  exposure.selectize.setValue('LOCAL', false);
                  exposure.dispatchEvent(new Event('input', {bubbles:true}));
                  exposure.dispatchEvent(new Event('change', {bubbles:true}));
                  return {ok:true, text: exposure.closest('.form-sub-wrap')?.innerText || ''};
                })()''')
                if isinstance(outcome, dict) and outcome.get('ok'):
                    add_filled('원산지', '국산')
                else:
                    add_missing('원산지', str(outcome))
                return
            outcome = safe_eval('''(() => {
              function dispatch(el) {
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
              }
              function pickByName(select, wantedName, fallbackCode) {
                if (!select?.selectize) return {ok:false, reason:'selectize-not-found'};
                const opts = Object.values(select.selectize.options || {});
                const found = opts.find(o => String(o.name || o.text || '').includes(wantedName)) || opts.find(o => String(o.code || o.value || '') === fallbackCode);
                const value = String(found?.code || found?.value || fallbackCode || '');
                if (!value) return {ok:false, reason:'option-not-found', wantedName, optionCount:opts.length};
                select.selectize.setValue(value, false);
                dispatch(select);
                return {ok:true, value, text:String(found?.name || found?.text || value)};
              }
              const exposure = document.querySelector('select[ng-model="vm.viewData.originAreaInfo.originAreaExposureType"]');
              if (!exposure?.selectize) return {ok:false, reason:'origin-exposure-not-found'};
              exposure.selectize.setValue('IMPORT', false);
              dispatch(exposure);
              return {ok:true, exposure:exposure.selectize.getValue()};
            })()''')
            time.sleep(1.5)
            continent = safe_eval('''(() => {
              function dispatch(el) { el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }
              const first = document.querySelector('select[ng-model="vm.viewData.originAreaInfo.firstSubOriginAreaType"]');
              if (!first?.selectize) return {ok:false, reason:'origin-first-not-found'};
              const opts = Object.values(first.selectize.options || {});
              const found = opts.find(o => String(o.name || o.text || '').includes('아시아')) || opts.find(o => String(o.code || o.value || '') === '0200');
              const value = String(found?.code || found?.value || '0200');
              first.selectize.setValue(value, false);
              dispatch(first);
              return {ok:true, value, text:String(found?.name || found?.text || value)};
            })()''')
            time.sleep(1.5)
            country_out = safe_eval('''(() => {
              function dispatch(el) { el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }
              const second = document.querySelector('select[ng-model="vm.viewData.originAreaInfo.secondSubOriginAreaType"]');
              if (!second?.selectize) return {ok:false, reason:'origin-second-not-found'};
              const opts = Object.values(second.selectize.options || {});
              const found = opts.find(o => String(o.name || o.text || '').includes('중국')) || opts.find(o => String(o.code || o.value || '') === '0200037');
              const value = String(found?.code || found?.value || '0200037');
              second.selectize.setValue(value, false);
              dispatch(second);
              return {ok:true, value, text:String(found?.name || found?.text || value), section: second.closest('.form-sub-wrap')?.innerText || ''};
            })()''')
            if isinstance(country_out, dict) and country_out.get('ok'):
                add_filled('원산지', f"수입산 / 아시아 / {country or country_out.get('text')}")
                importer = safe_eval('''(() => {
                  const el = document.querySelector('input[ng-model="vm.viewData.originAreaInfo.importer"]');
                  return {found:!!el, visible:!!el?.offsetParent, value:String(el?.value || '')};
                })()''')
                if isinstance(importer, dict) and importer.get('visible') and not importer.get('value'):
                    add_missing('원산지 수입사', '도매꾹 원문에 수입사명이 없어 판매자 확인 필요')
            else:
                add_missing('원산지', f"수입산/아시아/중국 자동 선택 실패 ({outcome}, {continent}, {country_out})")

        def handle_category():
            category_hint = data.get('category_hint') or ''
            search_hint = data.get('category_search_hint') or category_hint
            leaf_text = category_hint.split(' > ')[-1] if category_hint else search_hint
            if not category_hint:
                add_missing('카테고리', '카테고리 힌트 없음')
                return
            scroll_to_text('카테고리 영역', ['카테고리명 검색', '카테고리명 선택', '카테고리'])
            selectize_selected = safe_eval('''(async () => {
              const categoryHint = %s;
              const searchHint = %s;
              const leafText = %s;
              const leafCategoryId = %s;
              const input = Array.from(document.querySelectorAll('input[name="category"]')).find(el => el.selectize);
              if (!input || !input.selectize) return {ok:false, reason:'selectize-not-found'};
              const s = input.selectize;
              function optionEntries() {
                return Object.entries(s.options || {}).map(([id, value]) => ({id, value}));
              }
              function score(value) {
                const whole = String(value.wholeCategoryName || value.name || '');
                const name = String(value.name || '');
                let score = 0;
                if (leafCategoryId && String(value.id) === String(leafCategoryId)) score += 1000;
                if (whole.includes(categoryHint)) score += 200;
                if (whole.includes(searchHint)) score += 80;
                if (whole.includes(leafText) || name.includes(leafText)) score += 50;
                for (const part of categoryHint.split('>').map(s => s.trim()).filter(Boolean)) {
                  if (whole.includes(part) || name.includes(part)) score += 10;
                }
                if (value.lastLevel) score += 5;
                if (value.deleted || String(name).includes('사용N')) score -= 100;
                return score;
              }
              async function loadQuery(query) {
                if (!s.settings || !s.settings.load) return [];
                return await new Promise(resolve => {
                  let done = false;
                  const finish = items => { if (!done) { done = true; resolve(Array.isArray(items) ? items : []); } };
                  try {
                    s.settings.load.call(s, query, finish);
                    setTimeout(() => finish([]), 5000);
                  } catch (e) {
                    finish([]);
                  }
                });
              }
              const queries = [leafCategoryId, categoryHint, searchHint, leafText].filter(Boolean);
              for (const query of queries) {
                const loaded = await loadQuery(String(query));
                if (loaded.length) {
                  s.addOption(loaded);
                  s.refreshOptions(false);
                }
              }
              const best = optionEntries()
                .map(item => ({...item, score: score(item.value)}))
                .filter(item => item.score > 0)
                .sort((a, b) => b.score - a.score)[0];
              if (!best) return {ok:false, reason:'category-option-not-found', optionCount:Object.keys(s.options || {}).length};
              s.setValue(best.id, false);
              input.dispatchEvent(new Event('input', {bubbles:true}));
              input.dispatchEvent(new Event('change', {bubbles:true}));
              return {ok:true, id:best.id, text:(best.value.wholeCategoryName || best.value.name || best.id), score:best.score};
            })()''' % (
                json.dumps(category_hint, ensure_ascii=False),
                json.dumps(search_hint, ensure_ascii=False),
                json.dumps(leaf_text, ensure_ascii=False),
                json.dumps(data.get('leaf_category_id'), ensure_ascii=False),
            ))
            if isinstance(selectize_selected, dict) and selectize_selected.get('ok'):
                add_filled('카테고리 최종선택', f"{selectize_selected.get('text')} ({selectize_selected.get('id')})")
                return
            search_selected = safe_eval('''(() => {
              const radios = Array.from(document.querySelectorAll('input[type="radio"][name="category"]'));
              const target = radios.find(el => (el.closest('label, div, li')?.innerText || '').includes('카테고리명 검색')) || radios[0];
              if (!target) return {ok:false};
              target.click();
              target.dispatchEvent(new Event('change', {bubbles:true}));
              return {ok:true};
            })()''')
            field_filled = set_by_selectors(
                '카테고리 검색어',
                search_hint,
                ['input[name="category"][placeholder="카테고리명 입력"]', 'input[placeholder="카테고리명 입력"]'],
            )
            if not field_filled:
                field_filled = set_by_keywords('카테고리 검색어', search_hint, ['카테고리명 입력', '카테고리', 'category'])
            if not field_filled:
                add_missing('카테고리', f'힌트 "{category_hint}" 자동 입력/검색 실패')
                return
            time.sleep(0.5)
            safe_eval('''(() => {
              const input = Array.from(document.querySelectorAll('input')).find(el => el.name === 'category' || el.placeholder === '카테고리명 입력');
              if (!input) return {ok:false};
              input.focus();
              input.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
              input.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
              return {ok:true};
            })()''')
            time.sleep(1.5)
            clicked = safe_eval('''(() => {
              const leafText = %s;
              const categoryHint = %s;
              const candidates = Array.from(document.querySelectorAll('button, a, li, tr, div, span'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({el, text:(el.innerText || '').replace(/\s+/g, ' ').trim()}))
                .filter(item => item.text && (item.text.includes(leafText) || item.text.includes(categoryHint)))
                .filter(item => !['저장', '임시저장', '삭제', '도움말'].some(word => item.text.includes(word)))
                .sort((a, b) => a.text.length - b.text.length);
              const target = candidates[0]?.el;
              if (!target) return {ok:false, reason:'category-result-not-found'};
              target.scrollIntoView({block:'center'});
              target.click();
              return {ok:true, text:candidates[0].text.slice(0,160)};
            })()''' % (json.dumps(leaf_text, ensure_ascii=False), json.dumps(category_hint, ensure_ascii=False)))
            if isinstance(clicked, dict) and clicked.get('ok'):
                add_filled('카테고리 최종선택', clicked.get('text') or category_hint)
                return
            selected_check = safe_eval('''(() => {
              const bodyText = document.body.innerText || '';
              const input = document.querySelector('input[name="category"][placeholder="카테고리명 입력"], input[name="category"]');
              const value = String(input?.value || '');
              const selectedLine = (bodyText.split(String.fromCharCode(10)).find(line => line.includes('선택한 카테고리')) || '').trim();
              if (selectedLine && !bodyText.includes('최종 카테고리까지 선택해 주세요')) return {ok:true, text:selectedLine, value};
              if (value && /^\d{6,}$/.test(value) && !bodyText.includes('최종 카테고리까지 선택해 주세요')) return {ok:true, text:value, value};
              return {ok:false, selectedLine, value, needsFinal:bodyText.includes('최종 카테고리까지 선택해 주세요')};
            })()''')
            if isinstance(selected_check, dict) and selected_check.get('ok'):
                add_filled('카테고리 최종선택', selected_check.get('text') or category_hint)
                return
            add_missing('카테고리 최종선택', f'검색어 "{search_hint}" 입력 완료, 최종 선택은 사람 확인 필요')

        def set_search_tags():
            raw_tags = [
                str(tag).strip()
                for tag in [*(data.get('tags') or []), *(data.get('search_tags') or [])]
                if str(tag).strip()
            ]
            tags = []
            seen = set()
            for tag in raw_tags:
                compact = ''.join(ch for ch in tag if ch.isalnum() or ('가' <= ch <= '힣'))
                if not compact or len(compact) > 10:
                    continue
                key = compact.lower()
                if key in seen:
                    continue
                seen.add(key)
                tags.append(compact)
                if len(tags) >= 20:
                    break
            if not tags:
                add_missing('검색설정 태그', '입력할 태그 없음')
                return False
            scroll_to_text('검색설정 영역', ['검색설정', '태그', 'Page Title'])
            opened = safe_eval('''(() => {
              const existing = document.querySelector('select[ng-model="vm.directInputTag"], input[placeholder="태그를 입력해주세요."]');
              if (existing && existing.offsetParent !== null) return {ok:true, alreadyOpen:true};
              const target = Array.from(document.querySelectorAll('.title-line[role="button"], div[role="button"]'))
                .find(el => (el.innerText || '').includes('검색설정'));
              if (!target) return {ok:false, reason:'search-settings-title-not-found'};
              target.scrollIntoView({block:'center'});
              target.click();
              return {ok:true, clicked:true};
            })()''')
            time.sleep(1.0)
            if not (isinstance(opened, dict) and opened.get('ok')):
                add_missing('검색설정 열기', str(opened))
                return False
            direct_ready = None
            for _ in range(8):
                direct_ready = safe_eval('''(() => {
                  const select = document.querySelector('select[ng-model="vm.directInputTag"]');
                  if (select && select.selectize) return {ok:true, hasSelect:true, hasSelectize:true};
                  const input = document.querySelector('input[placeholder="태그를 입력해주세요."]');
                  if (input) return {ok:true, hasInput:true};
                  const checkbox = document.querySelector('input[ng-model="vm.viewData.isDirectInput"]');
                  if (checkbox) {
                    checkbox.scrollIntoView({block:'center'});
                    if (!checkbox.checked) checkbox.click();
                    return {ok:false, clickedCheckbox:true, checked:checkbox.checked};
                  }
                  return {ok:false, reason:'direct-input-checkbox-not-found'};
                })()''')
                if isinstance(direct_ready, dict) and (direct_ready.get('hasSelectize') or direct_ready.get('hasInput')):
                    break
                time.sleep(0.5)
            create_outcome = safe_eval('''(() => {
              const tags = %s;
              const checkbox = document.querySelector('input[ng-model="vm.viewData.isDirectInput"]');
              if (checkbox && !checkbox.checked) {
                checkbox.scrollIntoView({block:'center'});
                checkbox.click();
              }
              const select = document.querySelector('select[ng-model="vm.directInputTag"]');
              const selectize = select && select.selectize;
              if (!selectize) return {ok:false, reason:'direct-tag-selectize-not-found', hasSelect: !!select};
              try { selectize.clear(true); } catch (_) {}
              const beforeText = select.closest('.form-sub-wrap')?.innerText || '';
              for (const tag of tags) {
                const section = select.closest('.form-sub-wrap') || document;
                const currentText = section.innerText || '';
                const currentCount = (currentText.match(new RegExp('#\\\\s*[^×\\\\n]+', 'g')) || []).length;
                if (currentCount >= 10) break;
                try {
                  selectize.createItem(tag, false);
                } catch (_) {
                  // Some Selectize builds return through Angular callbacks and still create labels.
                }
              }
              select.dispatchEvent(new Event('input', {bubbles:true}));
              select.dispatchEvent(new Event('change', {bubbles:true}));
              try { window.angular?.element(select).triggerHandler('change'); } catch (_) {}
              return {ok:true, requested:tags, beforeText:beforeText.slice(0,400)};
            })()''' % json.dumps(tags, ensure_ascii=False))
            if not (isinstance(create_outcome, dict) and create_outcome.get('ok')):
                add_missing('검색설정 태그', str(create_outcome))
                return False
            time.sleep(1.0)
            outcome = safe_eval('''(() => {
              const tags = %s;
              const select = document.querySelector('select[ng-model="vm.directInputTag"]');
              if (!select) return {ok:false, reason:'direct-tag-select-not-found'};
              const section = select.closest('.form-sub-wrap') || document;
              const text = section.innerText || '';
              const labels = Array.from(section.querySelectorAll('.choice-label strong, .choice-label'))
                .map(el => (el.innerText || '').replace(/^#\s*/, '').replace(/×$/, '').trim())
                .filter(Boolean);
              const created = [];
              for (const label of labels) {
                if (!created.includes(label)) created.push(label);
              }
              if (!created.length) {
                for (const tag of tags) {
                  if (text.includes('# ' + tag) || text.includes('#' + tag)) created.push(tag);
                }
              }
              return {ok:created.length > 0, requested:tags, created:created.slice(0,10), count:created.length, text:text.slice(0,1200)};
            })()''' % json.dumps(tags, ensure_ascii=False))
            if isinstance(outcome, dict) and outcome.get('ok'):
                add_filled('검색설정 태그', f"{outcome.get('count')}개 입력: {', '.join(outcome.get('created') or [])}")
                if int(outcome.get('count') or 0) < min(10, len(tags)):
                    add_missing('검색설정 태그 일부', f"요청 {len(tags)}개 중 {outcome.get('count')}개만 화면 반영")
                return True
            add_missing('검색설정 태그', str(outcome))
            return False

        def set_detail_html():
            detail_html = data.get('detail_html')
            if not detail_html:
                add_missing('상세설명 HTML', '원본 상세 HTML 없음')
                return False
            scroll_to_text('상세설명 영역', ['상세설명', 'HTML 작성', '상세'])
            exact_tab = safe_eval('''(() => {
              const target = document.querySelector('a[ng-click="vm.func.changeEditorType(vm.CONSTANTS.EDITOR_TYPE.NONE)"]');
              if (!target || target.offsetParent === null) return {ok:false, reason:'html-tab-not-found'};
              target.scrollIntoView({block:'center'});
              target.click();
              return {ok:true, detail:(target.innerText || 'HTML 작성').replace(/\s+/g, ' ').trim()};
            })()''')
            if isinstance(exact_tab, dict) and exact_tab.get('ok'):
                add_filled('상세설명 HTML 작성 탭', exact_tab.get('detail') or 'HTML 작성')
            else:
                click_by_keywords('상세설명 HTML 작성 탭', ['HTML 작성'], ['상세설명', '직접 작성'])
            time.sleep(1.0)
            detail_meta = f"원문 HTML {len(detail_html or '')}자, iframe {str(detail_html or '').count('<iframe')}개, img {str(detail_html or '').count('<img')}개"
            html_selectors = [
                'textarea[ng-model="vm.editorContent"]',
                'textarea[ng-model*="editorContent"]',
                'textarea[name="editorContent"]',
            ]
            filled = False
            editor_rect = safe_eval('''(() => {
              const candidates = Array.from(document.querySelectorAll('textarea[ng-model="vm.editorContent"], textarea[ng-model*="editorContent"], textarea[name="editorContent"]'));
              const target = candidates.find(el => el.offsetParent !== null && el.getAttribute('ng-model') === 'vm.editorContent')
                || candidates.find(el => el.offsetParent !== null)
                || candidates[0];
              if (!target) return {ok:false, reason:'html-textarea-not-found'};
              target.scrollIntoView({block:'center'});
              const r = target.getBoundingClientRect();
              return {ok:true, x:r.x, y:r.y, width:r.width, height:r.height, selector:target.getAttribute('ng-model') || target.name || ''};
            })()''')
            if isinstance(editor_rect, dict) and editor_rect.get('ok'):
                try:
                    click_at_xy(editor_rect['x'] + 20, editor_rect['y'] + 20)
                    press_key('Control+A')
                    type_text(str(detail_html))
                    add_filled('상세설명 HTML', f"실제 키보드 입력 완료 ({editor_rect.get('selector')})")
                    filled = True
                except Exception as exc:
                    add_missing('상세설명 HTML 키보드 입력', f"실패 ({type(exc).__name__}: {exc}); DOM 입력 fallback 시도")
            if not filled:
                filled = set_by_selectors('상세설명 HTML', detail_html, html_selectors)
            if not filled:
                filled = set_by_keywords('상세설명 HTML', detail_html, ['상세설명', '상세', 'description', 'content'])
            if not filled:
                add_missing('상세설명 HTML', 'HTML 입력칸 자동탐색 실패')
                return False
            def force_set_detail_html():
                return safe_eval('''(() => {
                  const html = %s;
                  const candidates = Array.from(document.querySelectorAll('textarea[ng-model="vm.editorContent"], textarea[ng-model*="editorContent"], textarea[name="editorContent"]'));
                  const target = candidates.find(el => el.offsetParent !== null && el.getAttribute('ng-model') === 'vm.editorContent')
                    || candidates.find(el => el.offsetParent !== null)
                    || candidates[0];
                  if (!target) return {ok:false, reason:'html-textarea-not-found'};
                  function setDom(el, value) {
                    el.scrollIntoView({block:'center'});
                    el.focus();
                    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
                    if (setter) setter.call(el, value); else el.value = value;
                    for (const type of ['keydown','beforeinput','input','keyup','change','blur']) {
                      try { el.dispatchEvent(new Event(type, {bubbles:true})); } catch (_) {}
                    }
                  }
                  function setScope(el, value) {
                    try {
                      const ng = window.angular;
                      if (!ng) return {scope:false, reason:'angular-not-found'};
                      let node = el;
                      while (node) {
                        const scope = ng.element(node).scope?.() || ng.element(node).isolateScope?.();
                        if (scope) {
                          const holders = [scope.vm, scope.$ctrl, scope];
                          for (const holder of holders) {
                            if (!holder) continue;
                            if ('editorContent' in holder) {
                              holder.editorContent = value;
                              try { scope.$applyAsync?.(); } catch (_) {}
                              try { scope.$apply?.(); } catch (_) {}
                              return {scope:true, holder:'editorContent'};
                            }
                          }
                        }
                        node = node.parentElement;
                      }
                      return {scope:false, reason:'editor-scope-not-found'};
                    } catch (e) { return {scope:false, reason:String(e)}; }
                  }
                  setDom(target, html);
                  const scopeResult = setScope(target, html);
                  setDom(target, html);
                  const value = String(target.value || '');
                  return {ok:value.toLowerCase().includes('<img') || value.length > 0, valueLen:value.length, imgCount:value.toLowerCase().split('<img').length - 1, selector:target.getAttribute('ng-model') || target.name || '', scopeResult};
                })()''' % json.dumps(str(detail_html), ensure_ascii=False))

            def verify_detail_html():
                return safe_eval('''(() => {
                  const expectedImgCount = %s;
                  const candidates = Array.from(document.querySelectorAll('textarea[ng-model="vm.editorContent"], textarea[ng-model*="editorContent"], textarea[name="editorContent"]'));
                  const scored = candidates.map(el => {
                    const value = String(el.value || '');
                    const lowerValue = value.toLowerCase();
                    const rect = el.getBoundingClientRect?.();
                    return {
                      valueLen: value.length,
                      imgCount: lowerValue.split('<img').length - 1,
                      hasImg: lowerValue.includes('<img'),
                      visible: el.offsetParent !== null,
                      selector: el.getAttribute('ng-model') || el.name || '',
                      valueHead: value.slice(0, 160),
                      area: rect ? rect.width * rect.height : 0,
                    };
                  }).sort((a, b) => (b.visible - a.visible) || b.imgCount - a.imgCount || b.valueLen - a.valueLen || b.area - a.area);
                  const best = scored[0];
                  if (!best) return {ok:false, reason:'html-textarea-not-found'};
                  return {ok: expectedImgCount === 0 ? best.valueLen > 0 : best.hasImg, ...best};
                })()''' % json.dumps(str(detail_html or '').count('<img'), ensure_ascii=False))

            force = force_set_detail_html()
            if isinstance(force, dict) and force.get('ok'):
                add_filled('상세설명 HTML DOM/Angular 동기화', f"입력칸 {force.get('selector')}, HTML {force.get('valueLen')}자, img {force.get('imgCount')}개")
            verify = None
            for _ in range(3):
                time.sleep(0.7)
                verify = verify_detail_html()
                if isinstance(verify, dict) and verify.get('ok'):
                    add_filled('상세설명 원문 확인', f"{detail_meta}, 입력칸 {verify.get('selector')}, 입력 img {verify.get('imgCount')}개")
                    return True
            force = force_set_detail_html()
            time.sleep(1.0)
            verify = verify_detail_html()
            if isinstance(verify, dict) and verify.get('ok'):
                add_filled('상세설명 원문 확인', f"{detail_meta}, 입력칸 {verify.get('selector')}, 입력 img {verify.get('imgCount')}개, HTML 전용 재동기화 후 확인")
                return True
            time.sleep(3.0)
            verify = verify_detail_html()
            if isinstance(verify, dict) and verify.get('ok'):
                add_filled('상세설명 원문 확인', f"{detail_meta}, 입력칸 {verify.get('selector')}, 입력 img {verify.get('imgCount')}개, 지연 확인")
                return True
            add_missing('상세설명 HTML 검증', f"입력 후 HTML 입력칸에 이미지가 남지 않음 ({verify})")
            return False

        def reconcile_final_state():
            state = safe_eval('''(() => {
              const bodyText = document.body.innerText || '';
              const htmlEditor = document.querySelector('textarea[ng-model="vm.editorContent"], textarea[ng-model*="editorContent"], textarea[name="editorContent"]');
              const detailValue = String(htmlEditor?.value || '');
              const tagSection = Array.from(document.querySelectorAll('.form-sub-wrap, div')).find(el => (el.innerText || '').includes('태그 직접 입력') && (el.innerText || '').includes('#'));
              const tagText = tagSection ? tagSection.innerText : '';
              const categoryInput = document.querySelector('input[name="category"][placeholder="카테고리명 입력"], input[name="category"]');
              const categoryValue = String(categoryInput?.value || '');
              const priceInput = document.querySelector('input[name="product.salePrice"], #prd_price2');
              const priceValue = String(priceInput?.value || '').replace(/[^0-9]/g, '');
              const stockInput = document.querySelector('input[name="product.stockQuantity"], #stock');
              const stockValue = String(stockInput?.value || '').replace(/[^0-9]/g, '');
              const originExposure = document.querySelector('select[ng-model="vm.viewData.originAreaInfo.originAreaExposureType"]');
              const originFirst = document.querySelector('select[ng-model="vm.viewData.originAreaInfo.firstSubOriginAreaType"]');
              const originSecond = document.querySelector('select[ng-model="vm.viewData.originAreaInfo.secondSubOriginAreaType"]');
              return {
                detailOk: detailValue.toLowerCase().includes('<img'),
                detailImg: detailValue.toLowerCase().split('<img').length - 1,
                detailLen: detailValue.length,
                tagCount: (tagText.match(new RegExp('#\\\\s*[^×\\\\n]+', 'g')) || []).length,
                categoryOk: bodyText.includes('선택한 카테고리 :') && !bodyText.includes('최종 카테고리까지 선택해 주세요'),
                categoryValue,
                priceValue,
                stockValue,
                originExposure: originExposure?.selectize?.getValue() || originExposure?.value || '',
                originFirst: originFirst?.selectize?.getValue() || originFirst?.value || '',
                originSecond: originSecond?.selectize?.getValue() || originSecond?.value || '',
              };
            })()''')
            if not isinstance(state, dict):
                return
            if state.get('detailOk'):
                result['missing_fields'] = [item for item in result['missing_fields'] if not item.startswith('상세설명 HTML 검증') and not item.startswith('상세설명 등록 방식') and not item.startswith('상세설명 SmartEditor')]
                add_filled('상세설명 최종 DOM 확인', f"HTML {state.get('detailLen')}자, img {state.get('detailImg')}개")
            if state.get('categoryOk'):
                result['missing_fields'] = [item for item in result['missing_fields'] if not item.startswith('카테고리 최종선택')]
                add_filled('카테고리 최종 DOM 확인', state.get('categoryValue') or '선택됨')
            if (state.get('tagCount') or 0) >= 10:
                result['missing_fields'] = [item for item in result['missing_fields'] if not item.startswith('검색설정 태그')]
            expected_price = ''.join(ch for ch in str(data.get('sale_price') or '') if ch.isdigit())
            if expected_price and state.get('priceValue') == expected_price:
                result['missing_fields'] = [item for item in result['missing_fields'] if not item.startswith('판매가 최종 DOM 확인')]
                add_filled('판매가 최종 DOM 확인', f"{state.get('priceValue')}원")
            expected_stock = ''.join(ch for ch in str(data.get('stock_quantity') or '') if ch.isdigit())
            if expected_stock and state.get('stockValue') == expected_stock:
                result['missing_fields'] = [item for item in result['missing_fields'] if not item.startswith('재고수량 최종 DOM 확인')]
                add_filled('재고수량 최종 DOM 확인', f"{state.get('stockValue')}개")
            if state.get('originExposure') == 'IMPORT' and state.get('originFirst') == '0200' and state.get('originSecond') == '0200037':
                result['missing_fields'] = [item for item in result['missing_fields'] if not item.startswith('원산지:')]
                add_filled('원산지 최종 DOM 확인', '수입산 / 아시아 / 중국')

        try:
            new_tab(data['create_url'])
            wait_for_load(timeout=20)
            for _ in range(20):
                time.sleep(1)
                info = page_info()
                if 'accounts.commerce.naver.com/login' not in info.get('url', ''):
                    break
            time.sleep(2)
            info = page_info()
            result['current_url'] = info.get('url', '')
            result['page_title'] = info.get('title', '')
            body_text = safe_eval('document.body.innerText.slice(0, 5000)') or ''
            if any(word in str(body_text) for word in ['로그인', '아이디', '비밀번호']) and '상품' not in str(body_text):
                result['status'] = 'NEED_LOGIN'
                result['message'] = '스마트스토어 판매자센터 로그인이 필요합니다. 로그인 후 버튼을 다시 누르세요.'
                try:
                    result['screenshot_path'] = capture_screenshot()
                except Exception:
                    pass
                emit()
            else:
                dismiss_resume_modal()
                dismiss_permission_modal_if_present()
                scroll_to_text('상품 기본정보 영역', ['상품 기본정보', '상품명'])
                set_by_selectors('상품명', data.get('product_name'), ['input[name="product.name"]']) or set_by_keywords('상품명', data.get('product_name'), ['상품명', 'product name', 'name'])
                set_sale_price_and_stock()
                handle_category()
                handle_origin()
                set_search_tags()
                scroll_to_text('이미지 영역', ['상품이미지', '대표이미지', '추가이미지', '이미지'])
                upload_images()
                detail_html_ok = set_detail_html()
                if detail_html_ok:
                    add_filled('상세설명 등록 방식', 'HTML 작성 탭 직접 입력 사용; SmartEditor ONE 전환/작성 버튼 생략')
                else:
                    add_missing('상세설명 등록 방식', 'HTML 작성 탭 입력 실패; SmartEditor ONE은 사용자 요청으로 실행하지 않음')

                dismiss_resume_modal()
                set_sale_price_and_stock()
                final_detail_html_ok = set_detail_html()
                if final_detail_html_ok:
                    add_filled('상세설명 최종 HTML 작성 탭 재확인', '미리보기 직전 HTML 작성 탭 값 유지')
                clicked_preview = safe_eval('''(() => {
                  if ((document.body.innerText || '').includes('이전에 작성하던 내용')) {
                    return {ok:false, reason:'resume-modal-open'};
                  }
                  const banned = ['저장', '임시저장', '삭제', '등록완료'];
                  const candidates = Array.from(document.querySelectorAll('button, a'))
                    .filter(el => el.offsetParent !== null)
                    .filter(el => (el.innerText || '').includes('미리보기'))
                    .filter(el => !banned.some(word => (el.innerText || '').includes(word)));
                  const target = candidates[0];
                  if (!target) return {ok:false, reason:'preview-button-not-found'};
                  target.scrollIntoView({block:'center'});
                  target.click();
                  return {ok:true, text: target.innerText};
                })()''')
                result['preview_opened'] = bool(isinstance(clicked_preview, dict) and clicked_preview.get('ok'))
                time.sleep(2)
                permission_modal = safe_eval('''(() => {
                  const text = document.body.innerText || '';
                  const hasPermissionModal = text.includes('상품 등록권한 신청이 필요합니다') || text.includes('권한: 구매대행 판매') || text.includes('상품판매권한 신청 페이지');
                  if (!hasPermissionModal) return {ok:false};
                  return {ok:true, text:text.slice(0, 500)};
                })()''')
                if isinstance(permission_modal, dict) and permission_modal.get('ok'):
                    result['preview_opened'] = False
                    add_missing('미리보기', '카테고리 상품등록 권한 신청 모달로 차단됨: 구매대행 판매(화장품) 권한 확인 필요')
                info = page_info()
                result['current_url'] = info.get('url', '')
                result['page_title'] = info.get('title', '')
                time.sleep(4)
                reconcile_final_state()
                try:
                    result['screenshot_path'] = capture_screenshot()
                except Exception:
                    pass
                result['status'] = 'PREVIEW_OPENED' if result['preview_opened'] else 'PARTIAL'
                if result['preview_opened']:
                    result['message'] = '스마트스토어 입력/이미지 파일 설정을 시도했고 미리보기 버튼까지 눌렀습니다. 저장하기/임시저장은 누르지 않았습니다.'
                else:
                    result['message'] = '스마트스토어 화면을 열고 입력/이미지 파일 설정을 시도했지만 미리보기 버튼은 찾지 못했습니다. 저장하기/임시저장은 누르지 않았습니다.'
                emit()
        except Exception as exc:
            result['status'] = 'ERROR'
            result['message'] = f'브라우저 하네스 실행 오류: {type(exc).__name__}: {exc}'
            result['traceback'] = traceback.format_exc()[-2000:]
            try:
                info = page_info()
                result['current_url'] = info.get('url', '')
                result['page_title'] = info.get('title', '')
            except Exception:
                pass
            emit()
        """
    )
    return script.replace("__PAYLOAD_PATH__", repr(payload_path)).replace("__RESULT_MARKER__", repr(RESULT_MARKER))


async def run_browser_preview(request: BrowserPreviewRequest) -> BrowserPreviewResponse:
    if request.package.registration_status == "BLOCKED":
        return BrowserPreviewResponse(
            status="BLOCKED",
            message="차단 항목이 있어 브라우저 하네스 등록을 시작하지 않았습니다.",
            current_url="",
            page_title="",
            filled_fields=[],
            missing_fields=request.package.registration_gate.blockers + request.package.registration_gate.missing_fields,
            preview_opened=False,
            screenshot_path=None,
            stopped_before_save=True,
        )

    with tempfile.TemporaryDirectory(prefix="smartstore-harness-", dir=_preferred_harness_tmp_dir()) as tmpdir:
        working_dir = Path(tmpdir)
        upload_payload, preflight_missing_fields = _prepare_upload_payload(request.package, working_dir)
        payload = _browser_payload(request.package, upload_payload=upload_payload)
        payload_path = working_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        script = _harness_script(str(payload_path))
        env = os.environ.copy()
        env.setdefault("BU_CDP_URL", _resolve_cdp_url())
        harness_bin = _resolve_harness_bin()
        if not harness_bin:
            return BrowserPreviewResponse(
                status="ERROR",
                message="browser-harness-win 실행 파일을 찾지 못했습니다. PATH에 추가하거나 BROWSER_HARNESS_WIN_BIN 환경변수를 설정하세요.",
                current_url="",
                page_title="",
                filled_fields=[],
                missing_fields=preflight_missing_fields,
                preview_opened=False,
                screenshot_path=None,
                stopped_before_save=True,
            )
        proc = subprocess.run(
            [harness_bin],
            input=script,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=request.timeout_seconds,
            env=env,
        )
        output = proc.stdout + "\n" + proc.stderr
        parsed: dict[str, Any] | None = None
        for line in output.splitlines()[::-1]:
            if line.startswith(RESULT_MARKER):
                parsed = json.loads(line[len(RESULT_MARKER) :])
                break
        if parsed is None:
            return BrowserPreviewResponse(
                status="ERROR",
                message=f"브라우저 하네스 결과를 해석하지 못했습니다. exit={proc.returncode}, output={output[-1500:]}",
                current_url="",
                page_title="",
                filled_fields=[],
                missing_fields=preflight_missing_fields,
                preview_opened=False,
                screenshot_path=None,
                stopped_before_save=True,
            )
        parsed["missing_fields"] = list(dict.fromkeys([*preflight_missing_fields, *parsed.get("missing_fields", [])]))
        return BrowserPreviewResponse(**parsed)
