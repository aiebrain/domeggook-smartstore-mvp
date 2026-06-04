from __future__ import annotations

import math
import re
from html import escape

from app.models import (
    CommonOperationInfo,
    DomeggookProduct,
    ImagePreparation,
    IndividualProductPreparation,
    PricingPreparation,
    RegistrationDraftPackage,
    RegistrationDraftQA,
    RegistrationGate,
    RegistrationSourceRaw,
    SmartStoreImages,
    SmartStoreDraftPayload,
    SmartStorePackage,
)


DEFAULT_STOCK_QUANTITY = 999
MAX_TAG_COUNT = 10
MAX_SEARCH_TAG_COUNT = 15
MAX_SMARTSTORE_TAG_CHARS = 10


def build_smartstore_package(product: DomeggookProduct, margin_rate: float = 0.3) -> SmartStorePackage:
    qa_flags = list(product.warnings)
    if product.detail_image_use_allowed is False:
        qa_flags.append("상세 이미지 사용 권한 확인 필요")
    if not product.price_tiers:
        qa_flags.append("판매가 산정을 위한 도매가 확인 필요")

    suggested_name = _suggest_name(product.original_name)
    sale_price = _recommend_sale_price(product, margin_rate)
    detail_content = _build_detail_content(product)
    individual_product = _build_individual_product(product, suggested_name, sale_price, detail_content)
    common_info = _build_common_operation_info(product)
    gate = _build_registration_gate(product, sale_price, detail_content, qa_flags)
    registration_draft = _build_registration_draft(
        product=product,
        suggested_name=suggested_name,
        sale_price=sale_price,
        detail_content=detail_content,
        individual_product=individual_product,
        common_info=common_info,
        gate=gate,
        qa_flags=qa_flags,
    )

    return SmartStorePackage(
        source_url=product.source_url,
        generated_name_suggestion=suggested_name,
        sale_price_recommendation=sale_price,
        images=SmartStoreImages(
            thumbnail_url=product.thumbnail_url,
            detail_image_urls=product.detail_image_urls,
        ),
        detailContent=detail_content,
        qa_flags=qa_flags,
        registration_status=gate.status,
        individual_product=individual_product,
        common_operation_info=common_info,
        registration_gate=gate,
        registration_draft=registration_draft,
    )


def _suggest_name(original_name: str) -> str:
    cleaned = re.sub(r"\s+", " ", original_name).strip()
    banned_terms = ["무료배송", "할인", "쿠폰", "최저가", "도매", "사입", "사업자", "인기", "추천"]
    for term in banned_terms:
        cleaned = cleaned.replace(term, "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _recommend_sale_price(product: DomeggookProduct, margin_rate: float) -> int | None:
    if not product.price_tiers:
        return None
    # MVP recommendation uses the first/default purchase tier rather than the
    # deepest bulk discount, because SmartStore sale price should be safe for
    # the minimum order quantity scenario.
    wholesale_price = product.price_tiers[0].unit_price
    shipping_fee = _extract_shipping_fee(product.shipping_summary or "")
    raw_price = (wholesale_price + shipping_fee) * (1 + margin_rate)
    return int(math.ceil(raw_price / 100.0) * 100)


def _extract_shipping_fee(text: str) -> int:
    match = re.search(r"배송비\s*(\d[\d,]*)\s*원", text)
    return int(match.group(1).replace(",", "")) if match else 0


def _build_detail_content(product: DomeggookProduct) -> str:
    if product.detail_html and product.detail_html.strip():
        return product.detail_html.strip()

    parts = ['<div class="domeggook-detail">']
    parts.append(f"<h2>{escape(_suggest_name(product.original_name))}</h2>")
    parts.append('<section class="summary"><h3>상품 핵심 정보</h3><ul>')
    if product.category_path:
        parts.append(f"<li>카테고리 참고: {escape(' > '.join(product.category_path))}</li>")
    if product.origin:
        parts.append(f"<li>원산지: {escape(product.origin)}</li>")
    if product.options:
        parts.append(f"<li>옵션: {escape(', '.join(product.options[:8]))}</li>")
    if product.shipping_summary:
        parts.append(f"<li>배송 참고: {escape(product.shipping_summary)}</li>")
    parts.append("</ul></section>")
    for url in product.detail_image_urls:
        safe_url = escape(url, quote=True)
        parts.append(f'<img src="{safe_url}" style="max-width:100%;display:block;margin:0 auto;" />')
    parts.append("</div>")
    return "\n".join(parts)


def _infer_leaf_category_id(category_path: list[str]) -> str | None:
    normalized = '>'.join(part.strip() for part in category_path if part.strip())
    known = {
        '건강용품>냉온/찜질용품>찜질팩': '50001932',
    }
    return known.get(normalized)


def _build_individual_product(
    product: DomeggookProduct,
    suggested_name: str,
    sale_price: int | None,
    detail_content: str,
) -> IndividualProductPreparation:
    selected_supply_price = product.price_tiers[0].unit_price if product.price_tiers else None
    selected_min_qty = product.price_tiers[0].min_qty if product.price_tiers else product.min_order_qty
    # 상세페이지 이미지는 상품 추가이미지가 아니라 상세설명 본문 이미지입니다.
    # 하네스가 SmartEditor ONE 본문 영역에 별도로 업로드하도록 두고,
    # 상품이미지/추가이미지 슬롯에는 대표이미지만 자동 처리합니다.
    optional_images: list[str] = []
    tags, search_tags = _build_tags(product, suggested_name)

    return IndividualProductPreparation(
        source_url=product.source_url,
        product_no=product.product_no,
        source_product_name=product.original_name,
        smartstore_name_candidate=suggested_name,
        category_path_hint=product.category_path,
        leaf_category_id=_infer_leaf_category_id(product.category_path),
        pricing=PricingPreparation(
            source_price_tiers=product.price_tiers,
            selected_supply_price=selected_supply_price,
            selected_min_order_quantity=selected_min_qty,
            sale_price_candidate=sale_price,
        ),
        stock_quantity_candidate=product.stock_qty or DEFAULT_STOCK_QUANTITY,
        options=product.options,
        tags=tags,
        search_tags=search_tags,
        origin=product.origin,
        image_preparation=ImagePreparation(
            representative_url=product.thumbnail_url,
            optional_image_urls=optional_images,
            detail_image_urls=product.detail_image_urls,
        ),
        detail_content=detail_content,
        product_notice_group=None,
        certification_review_required=True,
    )


def _build_common_operation_info(product: DomeggookProduct) -> CommonOperationInfo:
    source_delivery = product.shipping_summary or "도매꾹 원천 배송 정보 확인 필요"
    return CommonOperationInfo(
        delivery_policy=(
            f"공통 배송 기본값은 판매자 정책으로 별도 확정. 도매꾹 참고 배송 정보: {source_delivery}"
        ),
        return_exchange_policy=(
            "공통 반품/교환 정책은 스마트스토어 판매자 주소, 택배사, 반품비, 교환비를 기준으로 입력. "
            "공급사 반품 조건은 상품별 원문 확인 필요."
        ),
        after_service_policy="A/S 전화번호와 안내 문구는 판매자 공통값으로 입력. 상품별 제조사 A/S가 있으면 개별상품 메모에 추가.",
        claim_policy="클레임 처리는 스마트스토어 판매자 정책을 우선하고, 공급사 귀책/초기불량 기준은 상품별로 검수.",
        common_notice="실제 등록 전 배송지/반품지/택배사/반품비/교환비/A/S 연락처는 사용자가 확정해야 함.",
        requires_seller_input=["배송비 정책", "반품/교환 주소", "반품비", "교환비", "택배사", "A/S 연락처"],
    )


def _normalize_tag_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[\[\]\(\)\{\}\"'“”‘’]+", " ", value)
    normalized = re.sub(r"[:;,/|]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _extract_option_terms(options: list[str]) -> list[str]:
    terms: list[str] = []
    for option in options:
        normalized = _normalize_tag_text(option)
        if not normalized:
            continue
        parts = [part.strip() for part in normalized.split(":") if part.strip()]
        if len(parts) > 1:
            terms.extend(parts[1:])
        else:
            terms.append(normalized)
    return terms


def _unique_terms(candidates: list[str | None], limit: int) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for candidate in candidates:
        normalized = _normalize_tag_text(candidate)
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        results.append(normalized)
        if len(results) >= limit:
            break
    return results


def _normalize_smartstore_tag(value: str | None) -> str:
    normalized = _normalize_tag_text(value)
    if not normalized:
        return ""
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[^0-9A-Za-z가-힣]+", "", normalized)
    if len(normalized) > MAX_SMARTSTORE_TAG_CHARS:
        return ""
    return normalized


def _smartstore_tag_candidates(product: DomeggookProduct, suggested_name: str) -> list[str]:
    words = [word for word in re.split(r"\s+", _normalize_tag_text(suggested_name)) if word]
    candidates: list[str | None] = []

    name_blob = " ".join([product.original_name, suggested_name])
    if "쿨패치" in name_blob or "쿨링패치" in name_blob:
        candidates.extend([
            "아이스쿨패치",
            "쿨링패치",
            "쿨패치",
            "여름패치",
            "냉감패치",
            "쿨팩",
            "시원한패치",
            "여름용품",
            "붙이는패치",
            "쿨링젤패치",
        ])
    if "아이스" in name_blob:
        candidates.extend(["아이스쿨", "냉감용품", "아이스팩"])
    if "여름" in name_blob:
        candidates.extend(["여름용품", "여름필수품", "폭염대비"])
    if "붙이는" in name_blob:
        candidates.extend(["붙이는패치", "부착형패치"])

    # 상품명 단어는 보조 후보로 사용하되 KC/수량 표기처럼 검색 태그 효용이 낮은 표현은 제외한다.
    low_value_patterns = [r"^\d+팩$", r"^\d+매입$", r"^kc인증$"]
    candidates.extend(
        word for word in words
        if not any(re.match(pattern, word, flags=re.IGNORECASE) for pattern in low_value_patterns)
    )
    candidates.extend(f"{left}{right}" for left, right in zip(words, words[1:]))
    candidates.extend(_extract_option_terms(product.options))

    # 카테고리/판매처명 태그는 네이버 내부 기준에서 제외될 수 있어 후순위로 둔다.
    candidates.extend(reversed(product.category_path))

    return [tag for tag in (_normalize_smartstore_tag(candidate) for candidate in candidates) if tag]


def _build_tags(product: DomeggookProduct, suggested_name: str) -> tuple[list[str], list[str]]:
    leaf_category = product.category_path[-1] if product.category_path else ""
    parent_category = product.category_path[-2] if len(product.category_path) >= 2 else ""
    name_words = suggested_name.split()
    trailing_name = " ".join(name_words[-2:]) if len(name_words) >= 2 else suggested_name
    option_terms = _extract_option_terms(product.options)

    tags = _unique_terms(_smartstore_tag_candidates(product, suggested_name), limit=MAX_TAG_COUNT)
    search_tags = _unique_terms(
        [
            suggested_name,
            product.original_name,
            trailing_name,
            *tags,
            f"{parent_category} {leaf_category}" if parent_category and leaf_category else "",
            f"{product.origin} {leaf_category}" if product.origin and leaf_category else "",
            *[f"{term} {leaf_category}".strip() if leaf_category else term for term in option_terms],
            *product.category_path,
            *option_terms,
        ],
        limit=MAX_SEARCH_TAG_COUNT,
    )
    return tags, search_tags


def _build_registration_draft(
    product: DomeggookProduct,
    suggested_name: str,
    sale_price: int | None,
    detail_content: str,
    individual_product: IndividualProductPreparation,
    common_info: CommonOperationInfo,
    gate: RegistrationGate,
    qa_flags: list[str],
) -> RegistrationDraftPackage:
    representative_url = individual_product.image_preparation.representative_url
    optional_urls = individual_product.image_preparation.optional_image_urls
    category_hint = " > ".join(individual_product.category_path_hint)
    main_keyword = individual_product.tags[0] if individual_product.tags else suggested_name
    detail_attribute = {
        "origin_area_info": {
            "origin_text": product.origin,
        },
        "seller_code_info": {
            "source_site": "domeggook",
            "source_product_no": product.product_no,
        },
        "option_info": {
            "options": product.options,
        },
        "after_service_info": {
            "policy_note": common_info.after_service_policy,
        },
        "product_info_provided_notice": {
            "group": individual_product.product_notice_group,
            "review_required": True,
        },
        "certification_review_required": individual_product.certification_review_required,
    }
    return RegistrationDraftPackage(
        source_raw=RegistrationSourceRaw(
            source_url=product.source_url,
            product_no=product.product_no,
            source_product_name=product.original_name,
            category_path=product.category_path,
            source_price_tiers=product.price_tiers,
            source_min_order_quantity=product.min_order_qty,
            source_stock_quantity=product.stock_qty,
            source_options=product.options,
            source_thumbnail_url=product.thumbnail_url,
            source_detail_image_urls=product.detail_image_urls,
            source_delivery_text=product.shipping_summary,
            source_origin_text=product.origin,
            detail_image_use_allowed=product.detail_image_use_allowed,
            source_warnings=product.warnings,
        ),
        smartstore_draft=SmartStoreDraftPayload(
            origin_product={
                "status_type": "SALE",
                "sale_type": "NEW",
                "leaf_category_id": individual_product.leaf_category_id,
                "name": suggested_name,
                "detail_content": detail_content,
                "images": {
                    "representative_image": {
                        "source_url": representative_url,
                        "upload_url": "",
                    },
                    "optional_images": [{"source_url": url, "upload_url": ""} for url in optional_urls],
                    "detail_image_urls": product.detail_image_urls,
                },
                "sale_price": sale_price,
                "stock_quantity": individual_product.stock_quantity_candidate,
                "delivery_info": {
                    "policy_note": common_info.delivery_policy,
                    "seller_input_required": common_info.requires_seller_input,
                },
                "detail_attribute": detail_attribute,
            },
            smartstore_channel_product={
                "channel_product_name": suggested_name,
                "naver_shopping_registration": False,
                "channel_product_display_status_type": "SUSPENSION",
            },
            category={
                "path_hint": individual_product.category_path_hint,
                "search_hint": category_hint,
                "leaf_category_id": individual_product.leaf_category_id,
            },
            seo={
                "main_keyword": main_keyword,
                "sub_keywords": individual_product.search_tags,
                "tags": individual_product.tags,
                "search_tags": individual_product.search_tags,
            },
            seller_required_inputs=common_info.requires_seller_input,
            common_operation_info=common_info.model_dump(),
            compliance={
                "human_review_required": gate.status != "READY",
                "blockers": gate.blockers,
                "warnings": list(dict.fromkeys([*qa_flags, *gate.review_flags])),
            },
        ),
        qa=RegistrationDraftQA(
            status=gate.status,
            ready_items=gate.ready_items,
            missing_fields=gate.missing_fields,
            review_flags=gate.review_flags,
            blockers=gate.blockers,
            qa_flags=qa_flags,
            final_human_approval=gate.final_human_approval,
        ),
    )


def _build_registration_gate(
    product: DomeggookProduct,
    sale_price: int | None,
    detail_content: str,
    qa_flags: list[str],
) -> RegistrationGate:
    ready_items: list[str] = []
    missing_fields: list[str] = []
    review_flags: list[str] = list(dict.fromkeys(qa_flags))
    blockers: list[str] = []

    if product.original_name:
        ready_items.append("상품명 후보 생성")
    else:
        blockers.append("BLOCKED_NO_PRODUCT_NAME")
        missing_fields.append("상품명")

    if sale_price:
        ready_items.append("판매가 후보 생성")
        review_flags.append("NEED_PRICE_MARGIN")
    else:
        blockers.append("BLOCKED_NO_PRICE")
        missing_fields.append("판매가 후보")

    if product.thumbnail_url:
        ready_items.append("대표 이미지 확보")
    else:
        blockers.append("BLOCKED_NO_THUMBNAIL")
        missing_fields.append("대표 이미지")

    if product.detail_image_urls and detail_content:
        ready_items.append("상세설명 초안 생성")
    else:
        blockers.append("BLOCKED_NO_DETAIL_CONTENT")
        missing_fields.append("상세설명")

    if product.origin:
        ready_items.append("원산지 원천값 확보")
    else:
        review_flags.append("NEED_ORIGIN")
        missing_fields.append("원산지")

    if product.shipping_summary:
        ready_items.append("도매꾹 배송 참고값 확보")
    else:
        review_flags.append("NEED_DELIVERY_INFO")
        missing_fields.append("배송 정보")

    if product.category_path:
        review_flags.append("NEED_CATEGORY")
    else:
        review_flags.append("NEED_CATEGORY")
        missing_fields.append("스마트스토어 leafCategoryId")

    review_flags.append("NEED_PRODUCT_NOTICE")
    review_flags.append("COMPLIANCE_REVIEW")

    if product.detail_image_use_allowed is False:
        blockers.append("BLOCKED_IMAGE_RIGHTS")

    status = "BLOCKED" if blockers else "NEED_REVIEW"
    return RegistrationGate(
        status=status,
        ready_items=list(dict.fromkeys(ready_items)),
        missing_fields=list(dict.fromkeys(missing_fields)),
        review_flags=list(dict.fromkeys(review_flags)),
        blockers=list(dict.fromkeys(blockers)),
        final_human_approval=False,
    )
