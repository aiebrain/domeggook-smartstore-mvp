from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class PriceTier(BaseModel):
    min_qty: int
    unit_price: int


class DomeggookProduct(BaseModel):
    source_url: str
    product_no: str
    original_name: str
    seller_name: Optional[str] = None
    category_path: list[str] = Field(default_factory=list)
    price_tiers: list[PriceTier] = Field(default_factory=list)
    min_order_qty: Optional[int] = None
    stock_qty: Optional[int] = None
    origin: Optional[str] = None
    shipping_summary: Optional[str] = None
    options: list[str] = Field(default_factory=list)
    thumbnail_url: Optional[str] = None
    detail_image_urls: list[str] = Field(default_factory=list)
    detail_html: Optional[str] = None
    detail_image_use_allowed: Optional[bool] = None
    warnings: list[str] = Field(default_factory=list)


class SmartStoreImages(BaseModel):
    thumbnail_url: Optional[str] = None
    detail_image_urls: list[str] = Field(default_factory=list)


RegistrationStatus = Literal["READY", "NEED_REVIEW", "BLOCKED"]


class ImagePreparation(BaseModel):
    representative_url: Optional[str] = None
    optional_image_urls: list[str] = Field(default_factory=list)
    detail_image_urls: list[str] = Field(default_factory=list)
    excluded_image_urls: list[str] = Field(default_factory=list)
    image_upload_limit: int = 10
    allowed_formats: list[str] = Field(default_factory=lambda: ["JPG", "GIF", "PNG", "BMP"])


class PricingPreparation(BaseModel):
    source_price_tiers: list[PriceTier] = Field(default_factory=list)
    selected_supply_price: Optional[int] = None
    selected_min_order_quantity: Optional[int] = None
    sale_price_candidate: Optional[int] = None
    margin_review_required: bool = True
    margin_policy_note: str = "배송비, 반품비, 스마트스토어 수수료, 광고비, 부가세 반영 후 최종 판매가 확정 필요"


class IndividualProductPreparation(BaseModel):
    source_url: str
    product_no: str
    source_product_name: str
    smartstore_name_candidate: str
    category_path_hint: list[str] = Field(default_factory=list)
    leaf_category_id: Optional[str] = None
    pricing: PricingPreparation
    stock_quantity_candidate: int
    options: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    search_tags: list[str] = Field(default_factory=list)
    origin: Optional[str] = None
    image_preparation: ImagePreparation
    detail_content: str
    product_notice_group: Optional[str] = None
    certification_review_required: bool = True


class CommonOperationInfo(BaseModel):
    delivery_policy: str
    return_exchange_policy: str
    after_service_policy: str
    claim_policy: str
    common_notice: str
    requires_seller_input: list[str] = Field(default_factory=list)


class RegistrationGate(BaseModel):
    status: RegistrationStatus
    ready_items: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    review_flags: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    final_human_approval: bool = False


class RegistrationSourceRaw(BaseModel):
    source_site: Literal["domeggook"] = "domeggook"
    source_url: str
    product_no: str
    source_product_name: str
    category_path: list[str] = Field(default_factory=list)
    source_price_tiers: list[PriceTier] = Field(default_factory=list)
    source_min_order_quantity: Optional[int] = None
    source_stock_quantity: Optional[int] = None
    source_options: list[str] = Field(default_factory=list)
    source_thumbnail_url: Optional[str] = None
    source_detail_image_urls: list[str] = Field(default_factory=list)
    source_delivery_text: Optional[str] = None
    source_origin_text: Optional[str] = None
    detail_image_use_allowed: Optional[bool] = None
    source_warnings: list[str] = Field(default_factory=list)


class RegistrationDraftQA(BaseModel):
    status: RegistrationStatus
    ready_items: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    review_flags: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    qa_flags: list[str] = Field(default_factory=list)
    final_human_approval: bool = False


class SmartStoreDraftPayload(BaseModel):
    registration_mode: Literal["draft"] = "draft"
    origin_product: dict[str, Any] = Field(default_factory=dict)
    smartstore_channel_product: dict[str, Any] = Field(default_factory=dict)
    category: dict[str, Any] = Field(default_factory=dict)
    seo: dict[str, Any] = Field(default_factory=dict)
    seller_required_inputs: list[str] = Field(default_factory=list)
    common_operation_info: dict[str, Any] = Field(default_factory=dict)
    compliance: dict[str, Any] = Field(default_factory=dict)


class RegistrationDraftPackage(BaseModel):
    source_raw: RegistrationSourceRaw
    smartstore_draft: SmartStoreDraftPayload
    qa: RegistrationDraftQA


class SmartStorePackage(BaseModel):
    source_url: str
    generated_name_suggestion: str
    sale_price_recommendation: Optional[int] = None
    images: SmartStoreImages
    detailContent: str
    qa_flags: list[str] = Field(default_factory=list)
    registration_status: RegistrationStatus = "NEED_REVIEW"
    individual_product: IndividualProductPreparation
    common_operation_info: CommonOperationInfo
    registration_gate: RegistrationGate
    registration_draft: RegistrationDraftPackage


class AnalyzeRequest(BaseModel):
    url: str
    html: Optional[str] = None


class AnalyzeResponse(BaseModel):
    product: DomeggookProduct
    smartstore_package: SmartStorePackage


BrowserPreviewStatus = Literal["PREVIEW_OPENED", "PARTIAL", "NEED_LOGIN", "BLOCKED", "ERROR"]


class BrowserPreviewRequest(BaseModel):
    package: SmartStorePackage
    timeout_seconds: int = Field(default=90, ge=20, le=180)


class BrowserPreviewResponse(BaseModel):
    status: BrowserPreviewStatus
    message: str
    current_url: str
    page_title: str
    filled_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    preview_opened: bool = False
    screenshot_path: Optional[str] = None
    stopped_before_save: bool = True
