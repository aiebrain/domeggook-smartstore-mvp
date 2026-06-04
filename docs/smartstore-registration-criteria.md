# 도매꾹 → 스마트스토어 상품등록 데이터 정리 기준

작성일: 2026-05-30
대상: 도매꾹 상품 URL을 분석해 스마트스토어 등록 패키지를 만드는 웹앱
목표: 도매꾹에서 추출한 원천 정보를 스마트스토어 공식 등록 구조에 맞게 정리하고, 자동등록 전에 사람이 판단해야 할 위험 요소를 분리한다.

---

## 1. 참고한 공식 기준

### 네이버 커머스API 상품 등록
- 공식 문서: `POST /external/v2/products`
- 필수 큰 구조:
  - `originProduct`
  - `smartstoreChannelProduct`
- `originProduct` 주요 필수/핵심 필드:
  - `statusType`
  - `saleType`
  - `leafCategoryId`
  - `name`
  - `detailContent`
  - `images`
  - `salePrice`
  - `stockQuantity`
  - `deliveryInfo`
  - `detailAttribute`
- `smartstoreChannelProduct` 주요 필수/핵심 필드:
  - `naverShoppingRegistration`
  - `channelProductDisplayStatusType`
- 공식 문서상 상품 등록 시 `statusType`은 `SALE`만 입력 가능하다. 다만 채널 전시 상태는 `ON` 또는 `SUSPENSION`을 쓸 수 있으므로, MVP 기본값은 안전하게 `SUSPENSION`으로 둔다.
- 재고 수량이 0이면 상품 상태는 품절로 등록된다.
- BAD_REQUEST는 `InvalidInputs`만으로 부족할 수 있으므로 `message`까지 파싱해야 한다.

### 네이버 커머스API 상품 이미지 업로드
- 공식 문서: `POST /external/v1/product-images/upload`
- multipart/form-data 방식
- 필드명: `imageFiles`
- 최대 10개까지 등록 가능
- 허용 형식: JPG, GIF, PNG, BMP
- 응답의 이미지 URL을 상품 등록 payload의 `images.representativeImage`, `images.optionalImages`에 사용한다.

### 스마트스토어 도움말 기준
- 상세설명, 옵션, 추가상품, 상품정보제공고시, 배송/반품/교환/A/S 항목은 상품 등록 전에 필수 확인 대상으로 둔다.
- 옵션은 색상, 사이즈, 용량, 구성처럼 구매 조건을 선택하는 항목으로 정리한다.
- 추가상품은 본상품과 함께 사는 별도 상품이지, 색상/사이즈 변형이 아니다.

---

## 2. 도매꾹 원천 데이터 수집 기준

도매꾹 상품 URL에서 수집하는 정보는 그대로 스마트스토어에 넣지 않는다. 반드시 `source_raw`와 `smartstore_draft`를 분리한다.

### 2-1. 반드시 수집할 원천 필드

```yaml
source_raw:
  source_site: domeggook
  source_url: ""
  product_no: ""
  fetched_at: ""
  source_product_name: ""
  source_price_text: ""
  source_price_tiers: []
  source_min_order_quantity: null
  source_options: []
  source_thumbnail_url: ""
  source_detail_image_urls: []
  source_detail_text_blocks: []
  source_delivery_text: ""
  source_return_exchange_text: ""
  source_origin_text: ""
  source_manufacturer_text: ""
  source_brand_text: ""
  source_certification_text: ""
  source_notice_text: ""
```

### 2-2. 원천 데이터 보존 원칙

1. 도매꾹 원문 상품명은 보존한다.
2. 도매꾹 가격 구간은 모두 보존한다.
3. 대표 이미지와 상세 이미지는 구분해서 보존한다.
4. 추천상품, 연관상품, 광고 블록 이미지는 상세 이미지에서 제외한다.
5. 상세페이지 이미지가 외부 CDN이면 URL과 다운로드 성공 여부를 함께 기록한다.
6. 이미지 사용권/워터마크/공급사 로고/타 플랫폼 문구가 보이면 자동등록 불가로 둔다.
7. 도매꾹에 없는 정보는 추정해서 채우지 않는다. `missing_fields`로 보낸다.

---

## 3. 스마트스토어 등록 패키지 기준

웹앱의 최종 출력은 아래 3단 구조로 만든다.

```yaml
registration_package:
  source_raw: {}
  smartstore_draft: {}
  qa: {}
```

### 3-1. 스마트스토어 draft 기본 구조

```yaml
smartstore_draft:
  registration_mode: draft
  originProduct:
    statusType: SALE
    saleType: NEW
    leafCategoryId: ""
    name: ""
    detailContent: ""
    images:
      representativeImage:
        local_path: ""
        upload_url: ""
      optionalImages: []
    salePrice: 0
    stockQuantity: 999
    deliveryInfo: {}
    detailAttribute:
      naverShoppingSearchInfo: {}
      afterServiceInfo: {}
      originAreaInfo: {}
      sellerCodeInfo: {}
      optionInfo: {}
      productInfoProvidedNotice: {}
      certificationInfo: []
  smartstoreChannelProduct:
    channelProductName: ""
    naverShoppingRegistration: false
    channelProductDisplayStatusType: SUSPENSION
  seo:
    main_keyword: ""
    sub_keywords: []
    tags: []
  compliance:
    human_review_required: true
    blockers: []
    warnings: []
```

---

## 4. 필드별 변환 기준

### 4-1. 상품명

도매꾹 상품명은 원천 정보로만 사용한다. 스마트스토어 상품명은 새로 만든다.

기준:
1. 실제 상품 사실만 사용한다.
2. 브랜드/제조사가 불명확하면 만들지 않는다.
3. `무료배송`, `할인`, `쿠폰`, `최저가`, `도매`, `사입`, `사업자`, `인기`, `추천` 같은 판매조건/과장어는 제거한다.
4. 동일 단어 반복을 제거한다.
5. 프로젝트 기본 길이: 24~32자 권장.
6. 구조: `핵심 상품유형 + 핵심 속성 + 사용처/대상 + 용량/구성 + 차별점`

예시:
- 원문: `1.18리터 대용량 텀블러 스텐 빨대 포함 손잡이 보온 보냉병`
- 등록명 후보: `대용량 스텐 텀블러 1.18L 손잡이 빨대 물병`

상태 판정:
- 핵심 상품유형이 불명확하면 `NEED_REVIEW`
- 상표/캐릭터/브랜드 의심 단어가 있으면 `BLOCKED_UNTIL_REVIEW`

### 4-2. 가격

도매꾹은 수량별 공급가가 있을 수 있으므로 가격을 아래처럼 분리한다.

```yaml
pricing:
  source_price_tiers:
    - min_qty: 1
      supply_price: 0
  selected_supply_price: 0
  selected_min_order_quantity: 1
  smartstore_sale_price: 0
  margin_policy:
    shipping_fee_included: false
    platform_fee_rate: null
    target_margin_rate: null
```

기준:
1. 원가와 판매가는 분리한다.
2. 도매꾹 최저 단가가 대량구매 조건이면, 최소구매수량을 반드시 표시한다.
3. 판매가는 자동 확정하지 않고 `가격 계산 필요` 상태로 둔다.
4. 배송비, 반품비, 플랫폼 수수료, 광고비, 부가세를 반영하기 전에는 `priceMarginChecked=false`.
5. 공급가가 0이거나 파싱 실패하면 등록 불가.

### 4-3. 카테고리

스마트스토어는 `leafCategoryId`가 핵심이다.

기준:
1. 자동 추천은 가능하지만 최종 확정은 사람 검수 대상으로 둔다.
2. 최하위 카테고리만 등록 가능 상태로 본다.
3. 고트래픽이지만 부정확한 카테고리는 금지한다.
4. 카테고리별 필수 속성, 상품정보제공고시, 인증 요구사항을 함께 조회해야 한다.

상태 판정:
- leafCategoryId 없음: `NEED_CATEGORY`
- 규제/인증 가능성 있음: `COMPLIANCE_REVIEW`
- 카테고리 확정 + 필수속성 확인 완료: `CATEGORY_READY`

### 4-4. 이미지

스마트스토어 API 이미지 업로드 기준에 맞춰 대표/추가 이미지를 정리한다.

기준:
1. 대표 이미지는 1장 필수.
2. API 이미지 업로드는 최대 10개, JPG/GIF/PNG/BMP만 허용.
3. `representativeImage` 1장 + `optionalImages` 최대 9장으로 설계한다.
4. 상세페이지 이미지는 `detailContent` 내부 이미지로 별도 사용한다.
5. 도매꾹 추천상품/연관상품/광고 이미지는 제외한다.
6. 워터마크, 타 쇼핑몰명, 공급사 연락처, 도매가 노출, 구매 유도 문구가 있으면 자동등록 불가.
7. 너무 긴 상세 이미지는 모바일 기준으로 분할하거나 HTML 상세 블록으로 재구성한다.

상태 판정:
- 대표 이미지 없음: `BLOCKED_NO_THUMBNAIL`
- 상세 이미지 0개: `NEED_DETAIL_CONTENT`
- 이미지 권리/워터마크 의심: `IMAGE_REVIEW_REQUIRED`

### 4-5. 상세설명

도매꾹 상세 이미지를 그대로 붙이는 방식은 1차 MVP에서는 가능하지만, 최종 등록 전에는 스마트스토어용 상세설명으로 재구성한다.

기준:
1. `detailContent`는 필수다.
2. 이미지 나열만 하지 말고 핵심 텍스트 요약을 포함한다.
3. 첫 화면에 상품 유형, 핵심 장점, 사용 상황, 구성 정보를 넣는다.
4. 스크립트, 추적 코드, 외부 구매 링크, 공급사 연락처는 제거한다.
5. 의료/건강/효능/인증 관련 과장 문구는 제거 또는 검수한다.
6. 모바일 폭 기준 860px 이하 이미지/HTML을 우선한다.

권장 구조:
1. 한 줄 핵심 제안
2. 이런 분에게 적합
3. 핵심 장점 3개
4. 제품 구성/옵션
5. 상세 스펙
6. 사용/관리 방법
7. 배송/교환/반품 안내
8. 상품정보제공고시/인증/원산지

### 4-6. 옵션

도매꾹 옵션을 스마트스토어 옵션으로 변환한다.

기준:
1. 색상, 사이즈, 용량, 구성, 수량 묶음은 옵션으로 둔다.
2. 같은 상품의 변형이 아니면 추가상품으로 분리한다.
3. 최소 1개 옵션은 추가금 0원이어야 한다.
4. 옵션 가격은 스마트스토어 제한 범위에 맞는지 검증한다.
5. 직접입력 옵션으로 개인정보를 받지 않는다.
6. 도매꾹 옵션명이 너무 길면 고객용 짧은 이름으로 정리한다.

### 4-7. 배송/반품/교환/A/S

기준:
1. 도매꾹 배송비와 스마트스토어 판매 배송비는 분리한다.
2. 공급사 반품/교환 조건을 원문 보존한다.
3. 스마트스토어 판매자 기준의 반품 주소, 택배사, 반품비, 교환비는 별도 입력값으로 둔다.
4. 공급사 배송지연/제주도서산간 추가비가 있으면 상세설명과 배송정책에 반영한다.
5. A/S 전화번호와 안내 문구는 판매자 기준으로 별도 설정한다.

### 4-8. 상품정보제공고시/인증/원산지

기준:
1. 카테고리별 상품정보제공고시 상품군을 반드시 매칭한다.
2. 원산지 정보가 없으면 등록 준비 완료로 보지 않는다.
3. KC/어린이제품/전기용품/생활화학/식품/화장품/의료/건강기능/무선/Battery 위험은 자동등록 금지다.
4. 인증이 필요한데 도매꾹 페이지에 증빙이 없으면 `BLOCKED_COMPLIANCE`.
5. 제조사/수입자/브랜드는 확인된 값만 넣고, 불명확하면 공란 또는 검수 요청으로 둔다.

---

## 5. 등록 가능 상태 판정 기준

웹앱은 최종적으로 아래 상태를 보여줘야 한다.

### READY
등록 패키지 생성 가능. 단, 실제 저장/등록은 사람 승인 필요.

조건:
- 상품명 생성 완료
- 판매가 후보 있음
- 대표 이미지 있음
- 상세설명 있음
- leafCategoryId 있음
- 배송/반품/A/S 기본값 있음
- 원산지/상품정보제공고시 확인 완료
- 차단 규제 없음
- 이미지 QA 통과

### NEED_REVIEW
등록 전 사람이 확인해야 함.

예:
- 카테고리 후보가 2개 이상
- 상품명에 브랜드/상표 의심 단어 있음
- 가격 마진 계산 미완료
- 상세 이미지가 너무 적거나 상세설명 텍스트 부족
- 옵션 구조가 애매함
- 배송/반품 조건 일부 누락

### BLOCKED
자동등록 금지.

예:
- 대표 이미지 없음
- 판매가/공급가 파싱 실패
- 원산지/인증 필수 정보 누락
- KC/어린이/식품/화장품/의료/전기/무선/배터리 등 규제 위험
- 이미지에 공급사/도매/타몰/연락처/워터마크 노출
- 상세설명에 금지 문구, 외부 링크, 스크립트 포함

---

## 6. MVP 웹앱에서 우선 구현할 검사 항목

1차 자동 검사:
- 상품번호 추출 여부
- 상품명 추출 여부
- 가격 구간 추출 여부
- 대표 이미지 존재 여부
- 상세 이미지 개수
- 상세 이미지가 추천상품 블록에서 섞였는지 여부
- 옵션 텍스트 추출 여부
- 원산지/인증/배송/반품 키워드 존재 여부

2차 등록 패키지 검사:
- `originProduct.name` 비어 있음 여부
- `originProduct.salePrice` 0 여부
- `originProduct.detailContent` 비어 있음 여부
- `originProduct.images.representativeImage` 존재 여부
- `originProduct.stockQuantity` 존재 여부
- `originProduct.deliveryInfo` 기본값 존재 여부
- `originProduct.detailAttribute.originAreaInfo` 존재 여부
- `smartstoreChannelProduct.channelProductDisplayStatusType=SUSPENSION` 여부
- `qa.finalHumanApproval=false` 기본값 유지 여부

---

## 7. 웹앱 출력 화면 기준

분석 결과 화면은 판매자 판단 순서로 보여준다.

1. 등록 가능 상태
   - READY / NEED_REVIEW / BLOCKED
2. 원천 상품 정보
   - 도매꾹 URL, 상품번호, 원문 상품명, 가격 구간
3. 스마트스토어 등록 초안
   - 새 상품명, 판매가 후보, 카테고리 후보, 재고, 옵션
4. 이미지 검수
   - 대표 이미지
   - 추가 이미지 후보
   - 상세페이지 이미지
   - 제외된 이미지
5. 상세페이지 초안
   - HTML 미리보기
   - 텍스트 요약
6. 필수 누락 정보
   - 원산지
   - 인증
   - 상품정보제공고시
   - 배송/반품/A/S
7. 최종 액션
   - JSON 다운로드
   - HTML 다운로드
   - 이미지 ZIP 다운로드
   - 스마트스토어 등록은 비활성화 상태로 두고, 사람 승인 후에만 진행

---

## 8. 절대 자동 처리하면 안 되는 항목

1. 스마트스토어 최종 저장/등록 버튼 클릭
2. API를 통한 실제 상품 생성
3. 로그인, OTP, CAPTCHA, 본인인증
4. 인증/KC/법적 표시를 추정으로 입력
5. 브랜드/제조사/원산지를 임의 생성
6. 이미지 사용권 문제가 있는 상품 자동 등록
7. 식품, 화장품, 의료, 어린이, 전기, 생활화학, 무선, 배터리 상품 자동 등록

---

## 9. 개발용 상태 enum 제안

```ts
type RegistrationStatus =
  | "READY"
  | "NEED_REVIEW"
  | "BLOCKED";

type ReviewFlag =
  | "NEED_CATEGORY"
  | "NEED_PRICE_MARGIN"
  | "NEED_ORIGIN"
  | "NEED_PRODUCT_NOTICE"
  | "NEED_DELIVERY_INFO"
  | "NEED_OPTION_REVIEW"
  | "IMAGE_REVIEW_REQUIRED"
  | "COMPLIANCE_REVIEW";

type Blocker =
  | "BLOCKED_NO_THUMBNAIL"
  | "BLOCKED_NO_PRICE"
  | "BLOCKED_NO_DETAIL_CONTENT"
  | "BLOCKED_COMPLIANCE"
  | "BLOCKED_IMAGE_RIGHTS"
  | "BLOCKED_FORBIDDEN_DETAIL_HTML";
```

---

## 10. 다음 구현 체크포인트

1. `SmartStorePackage` 모델에 `registration_status`, `review_flags`, `blockers`, `missing_fields` 추가
2. 도매꾹 분석 결과에서 `source_raw`와 `smartstore_draft` 분리
3. 이미지 후보를 `representative`, `optional`, `detail`, `excluded`로 분류
4. 가격 구간에서 판매가 계산 전 상태를 명확히 표시
5. 카테고리/상품정보제공고시/원산지/인증은 자동 추정이 아니라 검수 게이트로 연결
6. 실제 스마트스토어 등록 기능은 `finalHumanApproval=true`가 되기 전까지 비활성화
