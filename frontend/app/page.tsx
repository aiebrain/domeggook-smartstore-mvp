"use client";

import { FormEvent, useMemo, useState } from "react";
import { sampleHtml, sampleUrl } from "../lib/sampleHtml";
import type { AnalyzeResponse, BrowserPreviewResponse, RegistrationStatus } from "../lib/types";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type FieldStatus = "ready" | "review" | "blocked";

type RegistrationField = {
  section: string;
  smartstoreField: string;
  value: string;
  status: FieldStatus;
  source: string;
  action: string;
};

function formatValue(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "예" : "아니오/확인 필요";
  return String(value);
}

function formatWon(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return `${value.toLocaleString()}원`;
}

function formatListValue(values: string[]): string {
  return values.length ? values.join(", ") : "-";
}

function statusLabel(status: RegistrationStatus): string {
  if (status === "READY") return "브라우저 등록 준비 가능";
  if (status === "BLOCKED") return "올리기 차단";
  return "올리기 전 검수 필요";
}

function statusClass(status: RegistrationStatus): string {
  if (status === "READY") return "status-ready";
  if (status === "BLOCKED") return "status-blocked";
  return "status-review";
}

function fieldStatusLabel(status: FieldStatus): string {
  if (status === "ready") return "준비됨";
  if (status === "blocked") return "차단";
  return "검수 필요";
}

function ImageCard({ url, label }: { url: string; label: string }) {
  return (
    <figure className="image-card">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={url} alt={label} loading="lazy" onError={(event) => event.currentTarget.classList.add("image-error")} />
      <figcaption>{url}</figcaption>
    </figure>
  );
}

function ListBlock({ items, emptyText, tone }: { items: string[]; emptyText: string; tone?: "warning" | "ok" }) {
  if (!items.length) return <p className={tone === "ok" ? "ok" : "hint"}>{emptyText}</p>;
  return (
    <ul className={tone === "warning" ? "warning-list" : "check-list"}>
      {items.map((item) => <li key={item}>{item}</li>)}
    </ul>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string | number; tone?: "ok" | "warning" | "danger" }) {
  return (
    <div className={`metric-card ${tone ? `metric-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FieldStatusBadge({ status }: { status: FieldStatus }) {
  return <span className={`field-badge field-${status}`}>{fieldStatusLabel(status)}</span>;
}

function RegistrationFieldTable({ rows, onCopy }: { rows: RegistrationField[]; onCopy: (text: string, successMessage: string) => void }) {
  return (
    <div className="table-wrap">
      <table className="registration-table">
        <thead>
          <tr>
            <th>스마트스토어 입력 위치</th>
            <th>현재 입력값</th>
            <th>상태</th>
            <th>출처</th>
            <th>올리기 전 액션</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.section}-${row.smartstoreField}`}>
              <td>
                <span className="table-section">{row.section}</span>
                <strong>{row.smartstoreField}</strong>
              </td>
              <td className="value-cell">{row.value}</td>
              <td><FieldStatusBadge status={row.status} /></td>
              <td>{row.source}</td>
              <td>
                <span>{row.action}</span>
                {row.value !== "-" ? (
                  <button
                    type="button"
                    className="tiny-button"
                    onClick={() => onCopy(row.value, `${row.smartstoreField} 값을 복사했습니다.`)}
                  >
                    복사
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Home() {
  const [url, setUrl] = useState(sampleUrl);
  const [html, setHtml] = useState("");
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copyMessage, setCopyMessage] = useState("");
  const [isHarnessLoading, setIsHarnessLoading] = useState(false);
  const [harnessResult, setHarnessResult] = useState<BrowserPreviewResponse | null>(null);

  const draftJsonExport = useMemo(
    () => (result?.smartstore_package ? JSON.stringify(result.smartstore_package.registration_draft, null, 2) : ""),
    [result],
  );
  const responseJsonExport = useMemo(() => (result ? JSON.stringify(result, null, 2) : ""), [result]);

  async function analyze(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setIsLoading(true);
    setError(null);
    setCopyMessage("");

    try {
      const response = await fetch(`${apiBaseUrl}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, html: html.trim() || undefined }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail ?? `API 오류: HTTP ${response.status}`);
      }
      setResult(payload as AnalyzeResponse);
      setHarnessResult(null);
    } catch (caught) {
      setResult(null);
      setError(caught instanceof Error ? caught.message : "알 수 없는 분석 오류가 발생했습니다.");
    } finally {
      setIsLoading(false);
    }
  }

  async function copyJson(text: string, successMessage: string) {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopyMessage(successMessage);
    } catch {
      setCopyMessage("브라우저 권한 문제로 자동 복사하지 못했습니다. 아래 텍스트를 직접 복사하세요.");
    }
  }

  async function openSmartStoreRegistration() {
    if (!pkg) return;
    setIsHarnessLoading(true);
    setHarnessResult(null);
    setError(null);
    if (browserCopyPackage) {
      await copyJson(
        browserCopyPackage,
        "스마트스토어 입력 패키지를 복사했습니다. 브라우저 하네스가 판매자센터 등록 화면을 진행합니다.",
      );
    }
    try {
      const response = await fetch(`${apiBaseUrl}/api/smartstore/browser-preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ package: pkg, timeout_seconds: 120 }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail ?? `브라우저 하네스 API 오류: HTTP ${response.status}`);
      }
      setHarnessResult(payload as BrowserPreviewResponse);
      setCopyMessage((payload as BrowserPreviewResponse).message);
    } catch (caught) {
      setHarnessResult(null);
      setError(caught instanceof Error ? caught.message : "브라우저 하네스 실행 중 알 수 없는 오류가 발생했습니다.");
    } finally {
      setIsHarnessLoading(false);
    }
  }

  function loadDemo() {
    setUrl(sampleUrl);
    setHtml(sampleHtml);
    setError(null);
    setCopyMessage("샘플 HTML을 입력했습니다. 분석 버튼을 누르면 결정적 데모가 실행됩니다.");
  }

  const pkg = result?.smartstore_package;
  const product = result?.product;
  const registrationRows: RegistrationField[] = pkg && product ? [
    {
      section: "상품 기본정보",
      smartstoreField: "상품명",
      value: pkg.individual_product.smartstore_name_candidate,
      status: pkg.individual_product.smartstore_name_candidate ? "ready" : "blocked",
      source: "도매꾹 상품명 정리",
      action: "금칙어/과장어 확인 후 사용",
    },
    {
      section: "상품 기본정보",
      smartstoreField: "카테고리 leafCategoryId",
      value: formatValue(pkg.individual_product.leaf_category_id),
      status: pkg.individual_product.leaf_category_id ? "ready" : "review",
      source: product.category_path.join(" > ") || "도매꾹 카테고리 없음",
      action: "하네스가 카테고리 검색어 입력을 시도하고 최종 선택은 사람이 확인",
    },
    {
      section: "판매가/재고",
      smartstoreField: "판매가",
      value: formatWon(pkg.individual_product.pricing.sale_price_candidate),
      status: pkg.individual_product.pricing.sale_price_candidate ? "review" : "blocked",
      source: `공급가 ${formatWon(pkg.individual_product.pricing.selected_supply_price)} 기준 자동계산`,
      action: "마진·배송비 포함 최종가 확정",
    },
    {
      section: "판매가/재고",
      smartstoreField: "재고수량",
      value: formatValue(pkg.individual_product.stock_quantity_candidate),
      status: "review",
      source: product.stock_qty ? "도매꾹 재고" : "기본값 999",
      action: "품절 리스크 고려해 보수적으로 조정",
    },
    {
      section: "이미지",
      smartstoreField: "대표이미지 URL",
      value: formatValue(pkg.individual_product.image_preparation.representative_url),
      status: pkg.individual_product.image_preparation.representative_url ? "ready" : "blocked",
      source: "도매꾹 썸네일",
      action: "하네스가 파일 다운로드 후 업로드 입력칸 설정 시도",
    },
    {
      section: "이미지",
      smartstoreField: "추가이미지 업로드 후보",
      value: pkg.individual_product.image_preparation.optional_image_urls.length ? `${pkg.individual_product.image_preparation.optional_image_urls.length}개` : "-",
      status: pkg.individual_product.image_preparation.optional_image_urls.length ? "ready" : "review",
      source: "도매꾹 상세 이미지 상위 9개",
      action: "하네스가 파일 다운로드 후 추가이미지 입력칸 설정 시도",
    },
    {
      section: "상세설명",
      smartstoreField: "상세 HTML",
      value: pkg.detailContent ? `생성됨 · 상세 이미지 ${pkg.individual_product.image_preparation.detail_image_urls.length}개 포함` : "-",
      status: pkg.detailContent ? "ready" : "blocked",
      source: "도매꾹 상세 이미지 + 핵심정보 자동 구성",
      action: "문구/이미지 사용권 최종 확인",
    },
    {
      section: "검색설정",
      smartstoreField: "검색태그",
      value: formatListValue(pkg.individual_product.search_tags),
      status: pkg.individual_product.search_tags.length ? "ready" : "review",
      source: "상품명 + 카테고리 + 옵션 조합 자동생성",
      action: "불필요/과장 키워드 제거 후 사용",
    },
    {
      section: "검색설정",
      smartstoreField: "태그",
      value: formatListValue(pkg.individual_product.tags),
      status: pkg.individual_product.tags.length ? "ready" : "review",
      source: "상품명 꼬리어 + 카테고리 + 옵션값 자동생성",
      action: "중복/의미 없는 태그 정리 후 사용",
    },
    {
      section: "원산지/인증",
      smartstoreField: "원산지",
      value: formatValue(pkg.individual_product.origin),
      status: pkg.individual_product.origin ? "ready" : "review",
      source: "도매꾹 원천값",
      action: "스마트스토어 원산지 코드 매핑 필요",
    },
    {
      section: "원산지/인증",
      smartstoreField: "인증정보",
      value: pkg.individual_product.certification_review_required ? "인증 검수 필요" : "인증 없음",
      status: "review",
      source: "상품군 자동판단 미완료",
      action: "KC/어린이/전기용품 등 해당 여부 확인",
    },
    {
      section: "상품정보제공고시",
      smartstoreField: "상품군/고시 항목",
      value: formatValue(pkg.individual_product.product_notice_group),
      status: pkg.individual_product.product_notice_group ? "ready" : "review",
      source: "판매자 입력 필요",
      action: "상품군 선택 및 필수 고시값 입력",
    },
    {
      section: "배송/반품/A/S",
      smartstoreField: "배송 정책",
      value: pkg.common_operation_info.delivery_policy,
      status: "review",
      source: "도매꾹 배송 참고 + 판매자 공통 정책",
      action: "택배사/배송비/제주산간비 확정",
    },
    {
      section: "배송/반품/A/S",
      smartstoreField: "반품·교환·A/S",
      value: `${pkg.common_operation_info.return_exchange_policy} / ${pkg.common_operation_info.after_service_policy}`,
      status: "review",
      source: "판매자 공통 운영값",
      action: "반품지·반품비·A/S 연락처 입력",
    },
  ] : [];

  const readyCount = pkg ? pkg.registration_gate.ready_items.length : 0;
  const reviewCount = pkg ? pkg.registration_gate.review_flags.length + pkg.registration_gate.missing_fields.length : 0;
  const blockerCount = pkg ? pkg.registration_gate.blockers.length : 0;
  const browserCopyPackage = pkg && product ? [
    "[스마트스토어 브라우저 등록 준비 패키지]",
    `원천 URL: ${pkg.source_url}`,
    `상품번호: ${product.product_no}`,
    "",
    "1) 상품 기본정보",
    `상품명: ${pkg.individual_product.smartstore_name_candidate}`,
    `카테고리 힌트: ${product.category_path.join(" > ") || "직접 선택 필요"}`,
    `원산지: ${formatValue(pkg.individual_product.origin)}`,
    "",
    "2) 가격/재고",
    `판매가 후보: ${formatWon(pkg.individual_product.pricing.sale_price_candidate)}`,
    `공급가 참고: ${formatWon(pkg.individual_product.pricing.selected_supply_price)}`,
    `재고 후보: ${formatValue(pkg.individual_product.stock_quantity_candidate)}`,
    `최소주문수량 참고: ${formatValue(pkg.individual_product.pricing.selected_min_order_quantity)}`,
    "",
    "3) 이미지",
    `대표이미지 URL: ${formatValue(pkg.individual_product.image_preparation.representative_url)}`,
    `추가이미지 업로드 후보: ${pkg.individual_product.image_preparation.optional_image_urls.length}개`,
    ...pkg.individual_product.image_preparation.optional_image_urls.map((imageUrl, index) => `추가이미지 ${index + 1}: ${imageUrl}`),
    `상세이미지 수: ${pkg.individual_product.image_preparation.detail_image_urls.length}개`,
    ...pkg.individual_product.image_preparation.detail_image_urls.map((imageUrl, index) => `상세이미지 ${index + 1}: ${imageUrl}`),
    "",
    "4) 검색설정",
    `검색태그: ${formatListValue(pkg.individual_product.search_tags)}`,
    `태그: ${formatListValue(pkg.individual_product.tags)}`,
    "",
    "5) 상세설명",
    "상세 HTML은 화면의 상세 HTML 소스 영역에서 복사",
    "",
    "6) 올리기 전 사람 검수",
    "- 카테고리 leafCategoryId 직접 선택",
    "- 상품정보제공고시 상품군/필수값 입력",
    "- KC/인증 대상 여부 확인",
    "- 배송비/택배사/반품지/반품비/교환비/A/S 연락처 확정",
    "- 미리보기 확인 후 저장하기/임시저장은 사용자가 직접 클릭",
  ].join("\n") : "";

  return (
    <main className="page-shell">
      <section className="hero card">
        <div>
          <p className="eyebrow">Domeggook → SmartStore 브라우저 등록 준비</p>
          <h1>스마트스토어 판매자센터에 붙여넣을 자료를 정리합니다</h1>
          <p>
            도매꾹에서 가져온 상품명·가격·썸네일·상세 이미지를 스마트스토어 판매자센터 브라우저 화면 순서에 맞춰 재배치합니다.
            자동 API 등록이 아니라, 사람이 로그인한 브라우저에서 붙여넣고 저장 직전까지 검토하는 방식입니다.
          </p>
        </div>
        <button type="button" className="secondary" onClick={loadDemo}>
          샘플 HTML 불러오기
        </button>
      </section>

      <form className="card form-grid" onSubmit={analyze}>
        <label>
          도매꾹 URL
          <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://domeggook.com/54804743" required suppressHydrationWarning />
        </label>
        <label>
          HTML 직접 붙여넣기 (선택, 라이브 fetch 없이 결정적 데모 가능)
          <textarea value={html} onChange={(event) => setHtml(event.target.value)} rows={10} placeholder="<html>...</html>" suppressHydrationWarning />
        </label>
        <div className="actions">
          <button type="submit" disabled={isLoading}>{isLoading ? "분석 중..." : "브라우저 등록자료 만들기"}</button>
          <span className="hint">분석 서버: {apiBaseUrl} · 스마트스토어에는 직접 접속해서 입력</span>
        </div>
      </form>

      {error ? <div className="card error" role="alert">{error}</div> : null}
      {copyMessage ? <div className="card notice">{copyMessage}</div> : null}

      {result && pkg && product ? (
        <div className="results">
          <section className={`card status-card ${statusClass(pkg.registration_status)}`}>
            <div className="section-header">
              <div>
                <p className="eyebrow">브라우저 등록 준비 상태</p>
                <h2>{pkg.registration_status} · {statusLabel(pkg.registration_status)}</h2>
              </div>
              <div className="header-actions">
                <button
                  type="button"
                  className="smartstore-open-button"
                  onClick={openSmartStoreRegistration}
                  disabled={pkg.registration_status === "BLOCKED" || isHarnessLoading}
                  title={pkg.registration_status === "BLOCKED" ? "차단 항목을 먼저 해결한 뒤 하네스 등록을 시작하세요." : "브라우저 하네스로 스마트스토어 등록 화면 입력을 진행하고 미리보기까지 시도합니다."}
                >
                  {isHarnessLoading ? "하네스 진행 중..." : "하네스로 등록 진행/미리보기"}
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => copyJson(browserCopyPackage, "브라우저 등록용 복사 패키지를 클립보드에 복사했습니다.")}
                >
                  브라우저 입력값 복사
                </button>
              </div>
            </div>
            <p>
              스마트스토어 판매자센터에는 사용자가 직접 로그인합니다. 이 화면은 붙여넣을 자료를 준비하고, 저장하기/임시저장 버튼을 누르기 직전 검수 지점까지만 안내합니다.
            </p>
            <div className="metrics-grid">
              <MetricCard label="준비 완료" value={`${readyCount}개`} tone="ok" />
              <MetricCard label="검수/입력 필요" value={`${reviewCount}개`} tone="warning" />
              <MetricCard label="올리기 차단" value={`${blockerCount}개`} tone={blockerCount ? "danger" : "ok"} />
              <MetricCard label="상세 이미지" value={`${pkg.individual_product.image_preparation.detail_image_urls.length}개`} />
            </div>
          </section>

          {harnessResult ? (
            <section className={`card harness-result-card harness-${harnessResult.status.toLowerCase().replace("_", "-")}`}>
              <div className="section-header">
                <div>
                  <p className="eyebrow">브라우저 하네스 실행 결과</p>
                  <h2>{harnessResult.status}</h2>
                </div>
                <span className="field-badge field-ready">저장/임시저장 미클릭: {harnessResult.stopped_before_save ? "예" : "확인 필요"}</span>
              </div>
              <p>{harnessResult.message}</p>
              <dl className="summary-grid">
                <div><dt>현재 SmartStore URL</dt><dd>{harnessResult.current_url || "-"}</dd></div>
                <div><dt>브라우저 제목</dt><dd>{harnessResult.page_title || "-"}</dd></div>
                <div><dt>미리보기 실행</dt><dd>{harnessResult.preview_opened ? "성공" : "미완료/확인 필요"}</dd></div>
                <div><dt>스크린샷 경로</dt><dd>{harnessResult.screenshot_path || "-"}</dd></div>
              </dl>
              <div className="two-columns">
                <div>
                  <h3>자동 입력/설정 성공</h3>
                  <ListBlock items={harnessResult.filled_fields} emptyText="자동 입력된 필드 없음" tone="ok" />
                </div>
                <div>
                  <h3>사람 확인/수동 처리 필요</h3>
                  <ListBlock items={harnessResult.missing_fields} emptyText="추가 확인 항목 없음" tone="warning" />
                </div>
              </div>
              <p className="hint">로그인, 카테고리, 고시, 인증, 배송/반품/A/S처럼 화면 구조와 판매자 계정 설정에 따라 달라지는 항목은 자동 저장하지 않고 미리보기/검수 지점에서 멈춥니다.</p>
            </section>
          ) : null}

          <section className="card browser-prep-card">
            <div className="section-header">
              <div>
                <p className="eyebrow">저장 직전까지 준비</p>
                <h2>스마트스토어 브라우저 등록 방식</h2>
                <p className="hint">판매자센터에 직접 접속해서 아래 순서대로 붙여넣습니다. 자동 저장/임시저장은 하지 않습니다.</p>
              </div>
              <div className="header-actions">
                <button type="button" className="smartstore-open-button" onClick={openSmartStoreRegistration} disabled={pkg.registration_status === "BLOCKED" || isHarnessLoading}>
                  {isHarnessLoading ? "하네스 진행 중..." : "하네스로 등록 진행/미리보기"}
                </button>
                <button type="button" className="secondary" onClick={() => copyJson(browserCopyPackage, "브라우저 등록용 복사 패키지를 클립보드에 복사했습니다.")}>
                  전체 입력 패키지 복사
                </button>
              </div>
            </div>
            <ol className="manual-steps">
              <li><strong>판매자센터 접속</strong><span>https://sell.smartstore.naver.com/#/products/create 를 사용자가 로그인한 브라우저에서 엽니다.</span></li>
              <li><strong>필드별 붙여넣기</strong><span>아래 표의 상품명·판매가·재고·상세 HTML을 복사해 해당 섹션에 넣습니다.</span></li>
              <li><strong>이미지 처리</strong><span>하네스가 대표/추가 이미지 파일 입력을 시도하고, 실패한 항목만 사람이 직접 업로드합니다.</span></li>
              <li><strong>검수 후 정지</strong><span>카테고리, 고시, 인증, 배송/반품/A/S를 확인한 뒤 미리보기까지만 진행합니다.</span></li>
            </ol>
          </section>

          <section className="card smartstore-priority">
            <div className="section-header">
              <div>
                <p className="eyebrow">브라우저 등록 준비 패키지</p>
                <h2>스마트스토어 판매자센터에서 직접 입력할 값</h2>
                <p className="hint">API JSON이 아니라 브라우저 입력 순서 기준입니다. 복사 버튼으로 하나씩 붙여넣고, 검수 필요 항목은 판매자가 직접 확정합니다.</p>
              </div>
            </div>
            <RegistrationFieldTable rows={registrationRows} onCopy={copyJson} />
          </section>

          <section className="card">
            <h2>올리기 전 체크리스트</h2>
            <div className="three-columns">
              <div>
                <h3>준비 완료</h3>
                <ListBlock items={pkg.registration_gate.ready_items} emptyText="아직 준비 완료 항목 없음" tone="ok" />
              </div>
              <div>
                <h3>검수 필요</h3>
                <ListBlock items={pkg.registration_gate.review_flags} emptyText="검수 플래그 없음" tone="warning" />
              </div>
              <div>
                <h3>차단/누락</h3>
                <ListBlock items={[...pkg.registration_gate.blockers, ...pkg.registration_gate.missing_fields]} emptyText="차단 항목 없음" tone="warning" />
              </div>
            </div>
          </section>

          <section className="card registration-flow">
            <h2>스마트스토어 판매자센터 입력 순서</h2>
            <ol className="flow-list">
              <li><strong>상품 기본정보</strong><span>상품명, 카테고리, 판매상태, 원산지</span></li>
              <li><strong>가격/재고</strong><span>판매가, 공급가 참고, 재고수량, 최소주문수량</span></li>
              <li><strong>이미지</strong><span>대표 이미지 1개, 추가 이미지 최대 9개, 상세 이미지 URL</span></li>
              <li><strong>상세설명</strong><span>상세 HTML 미리보기 후 권리/문구 확인</span></li>
              <li><strong>검색설정</strong><span>검색태그/태그 자동생성값 검수</span></li>
              <li><strong>배송/반품/A/S</strong><span>판매자 공통 정책 입력</span></li>
              <li><strong>고시/인증</strong><span>상품정보제공고시와 KC 등 인증 여부 확인</span></li>
            </ol>
          </section>

          <section className="card">
            <h2>상품 기본정보</h2>
            <dl className="summary-grid">
              <div><dt>스마트스토어 상품명 후보</dt><dd>{pkg.individual_product.smartstore_name_candidate}</dd></div>
              <div><dt>도매꾹 상품번호</dt><dd>{product.product_no}</dd></div>
              <div><dt>원상품명</dt><dd>{product.original_name}</dd></div>
              <div><dt>판매자명</dt><dd>{formatValue(product.seller_name)}</dd></div>
              <div><dt>도매꾹 카테고리 힌트</dt><dd>{product.category_path.join(" > ") || "-"}</dd></div>
              <div><dt>leafCategoryId</dt><dd>{formatValue(pkg.individual_product.leaf_category_id)}</dd></div>
              <div><dt>원산지</dt><dd>{formatValue(product.origin)}</dd></div>
              <div><dt>옵션 후보</dt><dd>{pkg.individual_product.options.join(", ") || "옵션 없음 또는 추출 필요"}</dd></div>
              <div><dt>검색태그</dt><dd>{formatListValue(pkg.individual_product.search_tags)}</dd></div>
              <div><dt>태그</dt><dd>{formatListValue(pkg.individual_product.tags)}</dd></div>
            </dl>
          </section>

          <section className="card">
            <h2>가격/재고 등록값</h2>
            <dl className="summary-grid">
              <div><dt>판매가 후보</dt><dd>{formatWon(pkg.individual_product.pricing.sale_price_candidate)}</dd></div>
              <div><dt>선택 공급가</dt><dd>{formatWon(pkg.individual_product.pricing.selected_supply_price)}</dd></div>
              <div><dt>최소 주문 수량</dt><dd>{formatValue(pkg.individual_product.pricing.selected_min_order_quantity)}</dd></div>
              <div><dt>재고 후보</dt><dd>{formatValue(pkg.individual_product.stock_quantity_candidate)}</dd></div>
              <div><dt>마진 검수</dt><dd>{pkg.individual_product.pricing.margin_review_required ? "필요" : "불필요"}</dd></div>
              <div><dt>배송비 참고</dt><dd>{formatValue(product.shipping_summary)}</dd></div>
            </dl>
            <p className="hint">{pkg.individual_product.pricing.margin_policy_note}</p>
            <h3>도매꾹 가격 구간</h3>
            <table>
              <thead><tr><th>최소 수량</th><th>단가</th></tr></thead>
              <tbody>
                {product.price_tiers.map((tier) => (
                  <tr key={`${tier.min_qty}-${tier.unit_price}`}><td>{tier.min_qty.toLocaleString()}개</td><td>{tier.unit_price.toLocaleString()}원</td></tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="card">
            <h2>이미지 등록 준비</h2>
            <p className="hint">
              대표/추가 이미지는 하네스가 원격 URL을 임시 파일로 내려받아 업로드 입력칸 설정을 시도합니다. 상세 이미지는 상세 HTML에 자동 포함했습니다.
              스마트스토어 이미지 기준: 최대 {pkg.individual_product.image_preparation.image_upload_limit}개 · 허용 형식 {pkg.individual_product.image_preparation.allowed_formats.join("/")}
            </p>
            <h3>대표 이미지</h3>
            {pkg.individual_product.image_preparation.representative_url ? <ImageCard url={pkg.individual_product.image_preparation.representative_url} label="대표 이미지" /> : <p>대표 이미지 없음</p>}
            <h3>추가 이미지 업로드 후보</h3>
            <div className="gallery">
              {pkg.individual_product.image_preparation.optional_image_urls.map((imageUrl, index) => <ImageCard key={`${imageUrl}-optional`} url={imageUrl} label={`추가 이미지 ${index + 1}`} />)}
            </div>
            <h3>상세 이미지 URL</h3>
            <div className="gallery">
              {pkg.individual_product.image_preparation.detail_image_urls.map((imageUrl, index) => <ImageCard key={imageUrl} url={imageUrl} label={`상세 이미지 ${index + 1}`} />)}
            </div>
          </section>

          <section className="card">
            <h2>배송/반품/A/S 공통 운영 정보</h2>
            <dl className="summary-grid">
              <div><dt>배송 정책</dt><dd>{pkg.common_operation_info.delivery_policy}</dd></div>
              <div><dt>반품/교환 정책</dt><dd>{pkg.common_operation_info.return_exchange_policy}</dd></div>
              <div><dt>A/S 정책</dt><dd>{pkg.common_operation_info.after_service_policy}</dd></div>
              <div><dt>클레임 정책</dt><dd>{pkg.common_operation_info.claim_policy}</dd></div>
            </dl>
            <h3>판매자 공통 입력 필요값</h3>
            <ListBlock items={pkg.common_operation_info.requires_seller_input} emptyText="공통 입력 필요값 없음" tone="warning" />
            <p className="hint">{pkg.common_operation_info.common_notice}</p>
          </section>

          <section className="card">
            <h2>상품정보제공고시/인증</h2>
            <dl className="summary-grid">
              <div><dt>상품정보제공고시 상품군</dt><dd>{formatValue(pkg.individual_product.product_notice_group)}</dd></div>
              <div><dt>인증 검수 필요</dt><dd>{formatValue(pkg.individual_product.certification_review_required)}</dd></div>
              <div><dt>이미지 사용 권한</dt><dd>{formatValue(product.detail_image_use_allowed)}</dd></div>
              <div><dt>최종 사람 승인</dt><dd>{formatValue(pkg.registration_gate.final_human_approval)}</dd></div>
            </dl>
          </section>

          <section className="card">
            <h2>상세 HTML 미리보기</h2>
            <iframe className="preview" title="SmartStore detail HTML preview" srcDoc={pkg.detailContent} />
            <h3>상세 HTML 소스</h3>
            <textarea className="code-area" readOnly rows={8} value={pkg.detailContent} />
          </section>

          <section className="card final-stop-card">
            <h2>저장 직전 최종 확인</h2>
            <p className="hint">아래 항목 중 하나라도 미확정이면 스마트스토어에서 저장하기/임시저장을 누르지 않습니다.</p>
            <ul className="stop-checklist">
              <li>카테고리 leafCategoryId를 스마트스토어 화면에서 직접 선택했다.</li>
              <li>상품명 100자 제한, 금칙어, 과장 표현을 확인했다.</li>
              <li>판매가에 공급가, 배송비, 수수료, 광고비, 부가세, 목표마진을 반영했다.</li>
              <li>대표이미지와 상세이미지 사용 권한을 확인했다.</li>
              <li>상품정보제공고시 상품군과 필수 항목을 직접 입력했다.</li>
              <li>KC/어린이/전기용품/식품 등 인증 대상 여부를 확인했다.</li>
              <li>배송비, 택배사, 반품지, 반품비, 교환비, A/S 연락처를 확정했다.</li>
              <li>미리보기에서 모바일 상세설명과 이미지 깨짐 여부를 확인했다.</li>
            </ul>
          </section>

          <section className="card">
            <div className="section-header">
              <div>
                <h2>개발용 Draft JSON</h2>
                <p className="hint">브라우저 등록이 기본 방식입니다. 이 JSON은 개발/자동화 후보 검토용으로만 사용합니다.</p>
              </div>
              <button
                type="button"
                className="secondary"
                onClick={() => copyJson(browserCopyPackage, "브라우저 등록용 복사 패키지를 클립보드에 복사했습니다.")}
              >
                Draft JSON 복사
              </button>
            </div>
            <textarea className="code-area" readOnly rows={18} value={draftJsonExport} />
          </section>

          <section className="card raw-data-card">
            <div className="section-header">
              <h2>원천 분석 응답 JSON</h2>
              <button
                type="button"
                className="secondary"
                onClick={() => copyJson(responseJsonExport, "전체 API 응답 JSON을 클립보드에 복사했습니다.")}
              >
                응답 JSON 복사
              </button>
            </div>
            <p className="hint">개발/디버깅용 원천 데이터입니다. 실제 운영 화면에서는 접어둘 영역입니다.</p>
            <textarea className="code-area" readOnly rows={14} value={responseJsonExport} />
          </section>
        </div>
      ) : null}
    </main>
  );
}
