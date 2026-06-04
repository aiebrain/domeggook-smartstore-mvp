export type PriceTier = {
  min_qty: number;
  unit_price: number;
};

export type DomeggookProduct = {
  source_url: string;
  product_no: string;
  original_name: string;
  seller_name: string | null;
  category_path: string[];
  price_tiers: PriceTier[];
  min_order_qty: number | null;
  stock_qty: number | null;
  origin: string | null;
  shipping_summary: string | null;
  options: string[];
  thumbnail_url: string | null;
  detail_image_urls: string[];
  detail_image_use_allowed: boolean | null;
  warnings: string[];
};

export type RegistrationStatus = "READY" | "NEED_REVIEW" | "BLOCKED";

export type ImagePreparation = {
  representative_url: string | null;
  optional_image_urls: string[];
  detail_image_urls: string[];
  excluded_image_urls: string[];
  image_upload_limit: number;
  allowed_formats: string[];
};

export type PricingPreparation = {
  source_price_tiers: PriceTier[];
  selected_supply_price: number | null;
  selected_min_order_quantity: number | null;
  sale_price_candidate: number | null;
  margin_review_required: boolean;
  margin_policy_note: string;
};

export type IndividualProductPreparation = {
  source_url: string;
  product_no: string;
  source_product_name: string;
  smartstore_name_candidate: string;
  category_path_hint: string[];
  leaf_category_id: string | null;
  pricing: PricingPreparation;
  stock_quantity_candidate: number;
  options: string[];
  tags: string[];
  search_tags: string[];
  origin: string | null;
  image_preparation: ImagePreparation;
  detail_content: string;
  product_notice_group: string | null;
  certification_review_required: boolean;
};

export type CommonOperationInfo = {
  delivery_policy: string;
  return_exchange_policy: string;
  after_service_policy: string;
  claim_policy: string;
  common_notice: string;
  requires_seller_input: string[];
};

export type RegistrationGate = {
  status: RegistrationStatus;
  ready_items: string[];
  missing_fields: string[];
  review_flags: string[];
  blockers: string[];
  final_human_approval: boolean;
};

export type RegistrationSourceRaw = {
  source_site: "domeggook";
  source_url: string;
  product_no: string;
  source_product_name: string;
  category_path: string[];
  source_price_tiers: PriceTier[];
  source_min_order_quantity: number | null;
  source_stock_quantity: number | null;
  source_options: string[];
  source_thumbnail_url: string | null;
  source_detail_image_urls: string[];
  source_delivery_text: string | null;
  source_origin_text: string | null;
  detail_image_use_allowed: boolean | null;
  source_warnings: string[];
};

export type RegistrationDraftQA = {
  status: RegistrationStatus;
  ready_items: string[];
  missing_fields: string[];
  review_flags: string[];
  blockers: string[];
  qa_flags: string[];
  final_human_approval: boolean;
};

export type SmartStoreDraftPayload = {
  registration_mode: "draft";
  origin_product: Record<string, unknown>;
  smartstore_channel_product: Record<string, unknown>;
  category: Record<string, unknown>;
  seo: Record<string, unknown>;
  seller_required_inputs: string[];
  common_operation_info: Record<string, unknown>;
  compliance: Record<string, unknown>;
};

export type RegistrationDraftPackage = {
  source_raw: RegistrationSourceRaw;
  smartstore_draft: SmartStoreDraftPayload;
  qa: RegistrationDraftQA;
};

export type SmartStorePackage = {
  source_url: string;
  generated_name_suggestion: string;
  sale_price_recommendation: number | null;
  images: {
    thumbnail_url: string | null;
    detail_image_urls: string[];
  };
  detailContent: string;
  qa_flags: string[];
  registration_status: RegistrationStatus;
  individual_product: IndividualProductPreparation;
  common_operation_info: CommonOperationInfo;
  registration_gate: RegistrationGate;
  registration_draft: RegistrationDraftPackage;
};

export type AnalyzeResponse = {
  product: DomeggookProduct;
  smartstore_package: SmartStorePackage;
};

export type AnalyzeRequest = {
  url: string;
  html?: string;
};

export type BrowserPreviewStatus = "PREVIEW_OPENED" | "PARTIAL" | "NEED_LOGIN" | "BLOCKED" | "ERROR";

export type BrowserPreviewResponse = {
  status: BrowserPreviewStatus;
  message: string;
  current_url: string;
  page_title: string;
  filled_fields: string[];
  missing_fields: string[];
  preview_opened: boolean;
  screenshot_path: string | null;
  stopped_before_save: boolean;
};
