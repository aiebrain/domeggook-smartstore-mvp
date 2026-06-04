from app.extractor.domeggook import parse_product_html
from app.smartstore.package_builder import build_smartstore_package
from tests.test_extractor import SAMPLE_HTML


def test_build_smartstore_package_recommends_price_and_html():
    product = parse_product_html(SAMPLE_HTML, "https://domeggook.com/54804743")
    package = build_smartstore_package(product, margin_rate=0.3)

    assert package.source_url == "https://domeggook.com/54804743"
    assert package.generated_name_suggestion == "국산 튼튼한 스테인리스 집게"
    # ceil((5900 + 3000) * 1.3) rounded to next 100 = 11600
    assert package.sale_price_recommendation == 11600
    assert package.images.thumbnail_url == product.thumbnail_url
    assert package.images.detail_image_urls == product.detail_image_urls
    assert '<img src="https://cdn.example.com/upload/item/54804743/54804743_stt_001.jpg"' in package.detailContent
    assert package.registration_status == "NEED_REVIEW"
    assert package.registration_gate.blockers == []
    assert "NEED_CATEGORY" in package.registration_gate.review_flags
    assert "NEED_PRODUCT_NOTICE" in package.registration_gate.review_flags
    assert package.registration_gate.final_human_approval is False
    assert package.registration_draft.source_raw.product_no == "54804743"
    assert package.registration_draft.smartstore_draft.origin_product["name"] == "국산 튼튼한 스테인리스 집게"
    assert package.registration_draft.smartstore_draft.smartstore_channel_product["naver_shopping_registration"] is False
    assert package.registration_draft.qa.status == "NEED_REVIEW"


def test_build_smartstore_package_prefers_original_supplier_detail_html():
    product = parse_product_html(SAMPLE_HTML, "https://domeggook.com/54804743")
    product.detail_html = '<div class="original-supplier-detail"><iframe src="https://www.youtube.com/embed/example"></iframe><img src="https://example.com/original.jpg" /></div>'

    package = build_smartstore_package(product, margin_rate=0.3)

    assert package.detailContent == product.detail_html
    assert package.individual_product.detail_content == product.detail_html
    assert package.registration_draft.smartstore_draft.origin_product["detail_content"] == product.detail_html


def test_build_smartstore_package_splits_individual_and_common_registration_info():
    product = parse_product_html(SAMPLE_HTML, "https://domeggook.com/54804743")
    package = build_smartstore_package(product, margin_rate=0.3)

    individual = package.individual_product
    common = package.common_operation_info

    assert individual.product_no == "54804743"
    assert individual.source_product_name == "국산 튼튼한 스테인리스 집게"
    assert individual.smartstore_name_candidate == "국산 튼튼한 스테인리스 집게"
    assert individual.leaf_category_id is None
    assert individual.pricing.selected_supply_price == 5900
    assert individual.pricing.sale_price_candidate == 11600
    assert individual.pricing.margin_review_required is True
    assert individual.stock_quantity_candidate == 123
    assert individual.origin == "대한민국"
    assert "집게" in individual.tags
    assert "국산 튼튼한 스테인리스 집게" in individual.search_tags
    assert individual.image_preparation.representative_url == product.thumbnail_url
    assert individual.image_preparation.optional_image_urls == []
    assert individual.image_preparation.detail_image_urls == product.detail_image_urls
    assert individual.certification_review_required is True

    assert "도매꾹 참고 배송 정보" in common.delivery_policy
    assert "배송비 3,000원" in common.delivery_policy
    assert "반품/교환" in common.return_exchange_policy
    assert "A/S" in common.after_service_policy
    assert "반품비" in common.requires_seller_input
    draft = package.registration_draft.smartstore_draft
    assert draft.registration_mode == "draft"
    assert draft.origin_product["delivery_info"]["seller_input_required"] == common.requires_seller_input
    assert draft.category["search_hint"] == "주방용품 > 조리도구 > 집게"
    assert "집게" in draft.seo["tags"]
    assert "국산 튼튼한 스테인리스 집게" in draft.seo["search_tags"]
    assert draft.common_operation_info["claim_policy"] == common.claim_policy
    assert draft.compliance["human_review_required"] is True


def test_build_smartstore_package_blocks_missing_thumbnail_and_detail():
    product = parse_product_html(SAMPLE_HTML, "https://domeggook.com/54804743")
    product.thumbnail_url = None
    product.detail_image_urls = []
    package = build_smartstore_package(product, margin_rate=0.3)

    assert package.registration_status == "BLOCKED"
    assert "BLOCKED_NO_THUMBNAIL" in package.registration_gate.blockers
    assert "BLOCKED_NO_DETAIL_CONTENT" in package.registration_gate.blockers
    assert "대표 이미지" in package.registration_gate.missing_fields
    assert "상세설명" in package.registration_gate.missing_fields
    assert package.registration_draft.qa.blockers == package.registration_gate.blockers
