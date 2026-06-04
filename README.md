# Domeggook to SmartStore MVP

도매꾹 상품 URL을 분석해 네이버 스마트스토어 등록 준비 패키지를 만들고, 판매자센터 브라우저 하네스로 등록 화면 입력/미리보기 직전 검증까지 수행하는 MVP입니다.

> Safety boundary: 이 프로젝트의 브라우저 하네스는 스마트스토어 `저장` / `임시저장` 버튼을 누르지 않고, 미리보기 또는 검수 지점에서 멈추도록 설계했습니다.

## 주요 기능

- Domeggook 상품 URL 정규화 및 상품번호 추출
- 저장된 HTML 또는 라이브 HTTP fetch 기반 상품 정보 추출
- 추출 필드
  - 상품번호, 원상품명, 판매자명, 카테고리
  - 가격 구간, 최소구매수량, 재고, 원산지
  - 배송 요약, 옵션, 대표 이미지, 상세 이미지, 이미지 사용 허용 여부, 경고
- 스마트스토어 등록 준비 패키지 생성
  - 상품명 후보
  - 판매가 후보
  - 재고수량 후보
  - 대표이미지 / 상세 HTML
  - 태그 / 검색설정 태그
  - QA 플래그 / 사람 확인 항목
- 브라우저 하네스 기반 스마트스토어 입력 검증
  - 판매가 / 재고수량 DOM 최종 확인
  - 상세설명은 SmartEditor ONE 대신 `HTML 작성` 탭 직접 입력
  - 추가이미지는 업로드하지 않고 대표이미지만 사용
  - 원산지 국산/수입산/아시아/중국 Selectize 자동 선택
  - 미리보기 전 저장/임시저장 미클릭 보장

## API

- `GET /health`
- `POST /api/analyze`
  - body: `{ "url": "https://domeggook.com/...", "html": "optional saved html" }`
- `POST /api/browser-preview`
  - 분석 패키지를 바탕으로 스마트스토어 판매자센터 브라우저 화면에 입력하고, 저장하지 않은 채 미리보기/검수 단계에서 멈춥니다.

## 백엔드 설치 및 테스트

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

Hermes/uv 환경에서는 다음처럼도 실행할 수 있습니다.

```bash
cd backend
uv run --with-requirements requirements.txt pytest -q
```

## 백엔드 실행

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 프론트엔드 설치, 테스트, 실행

```bash
cd frontend
npm install
npm run typecheck
npm run dev
```

프론트엔드는 기본적으로 `http://localhost:8000` 백엔드에 연결합니다. 다른 주소를 쓰려면 실행 전에 환경 변수를 설정하세요.

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

브라우저에서 `http://localhost:3000`을 열고 `샘플 HTML 불러오기`를 누르면 라이브 크롤링 없이 데모 분석을 실행할 수 있습니다.

## API 예시

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://domeggook.com/54804743"}'
```

결정적 테스트나 크롤링 차단 회피를 위해 HTML을 직접 전달할 수 있습니다.

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://domeggook.com/54804743", "html":"<html>...</html>"}'
```

## 브라우저 하네스 검증 요약

브라우저 하네스를 실행하려면 `browser-harness-win`이 `PATH`에 있거나 다음 환경변수를 지정해야 합니다.

```bash
export BROWSER_HARNESS_WIN_BIN=/path/to/browser-harness-win
export BU_CDP_URL=http://<windows-host-or-localhost>:9223
```

최근 5개 상품 반복 검증 결과, 판매가/재고수량/상세 HTML 입력과 SmartEditor ONE 미실행, 저장/임시저장 미클릭 경계가 통과했습니다.

| 상품번호 | 상태 | 판매가 | 재고수량 | 상세 HTML | SmartEditor ONE | 저장/임시저장 |
|---|---|---:|---:|---|---|---|
| 23824901 | PREVIEW_OPENED | 300 | 158282 | OK | 미실행 | 미클릭 |
| 58088773 | PREVIEW_OPENED | 7200 | 45914 | OK | 미실행 | 미클릭 |
| 54804743 | PREVIEW_OPENED | 7700 | 12440 | OK | 미실행 | 미클릭 |
| 35444818 | PARTIAL | 8500 | 981 | OK | 미실행 | 미클릭 |
| 65197944 | PREVIEW_OPENED | 15100 | 3992 | OK | 미실행 | 미클릭 |

`35444818`은 화장품 카테고리 권한 신청 모달 때문에 미리보기만 차단되었고, 판매가/재고/HTML 입력 자체는 통과했습니다.

## 주의사항

- 이 코드는 판매자센터 UI 자동화를 포함하므로 실제 계정/정책/권한 상태에 따라 동작이 달라질 수 있습니다.
- 저장/임시저장은 자동 클릭하지 않도록 설계되어 있지만, 운영 전에는 반드시 테스트 계정/검수 환경에서 확인하세요.
- 수입산 상품의 `원산지 수입사`는 원문 또는 사용자가 확인한 값이 없으면 자동 생성하지 않고 확인 항목으로 남깁니다.
- 라이브 도매꾹 DOM은 변경될 수 있으므로 파서는 보수적으로 추출하고 누락 필드는 warnings/QA flags로 전달합니다.

## 공개 저장소 제외 항목

다음 항목은 `.gitignore`로 제외합니다.

- 로컬 실행 결과 `artifacts/`
- 판매자센터 스크린샷/결과 JSON
- 로그 `logs/`, `*.log`
- `.env`, `.env.*`
- `.next/`, `.pytest_cache/`, `__pycache__/`, `node_modules/`
