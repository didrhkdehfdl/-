# 인수인계 문서 — 업무효율화 앱 (경기지사 태양광 사업 관리 SPA)

이 문서는 로컬 Claude Code 세션에서 진행하던 작업을 클라우드(또는 다른) 세션에서 이어받기 위한 인수인계 문서입니다. 작성 시각: 2026-08-31.

## 프로젝트 개요

- **무엇**: 태양광 사업(사급 실적, 영업비 정산, 사업 이윤정산, 법인카드, 차량관리, 계약서, 사용전점검, O&M 등)을 관리하는 단일 페이지 웹앱
- **파일 구조**: `index.html` 딱 한 개 파일 (13,000줄+, 바닐라 HTML/CSS/JS, 프레임워크 없음). 모든 화면·로직·스타일이 이 파일 안에 있음
- **백엔드**: Firebase (Firestore `app_data` 컬렉션에 키-값으로 대부분의 데이터 저장, Firebase Storage에 큰 파일(PDF 등), Firebase Auth로 로그인/승인)
- **배포**: GitHub Pages (`github.com/didrhkdehfdl/-`). 로컬에 PowerShell 감시 스크립트가 있어서 `index.html` 저장할 때마다 자동으로 git add/commit/push함 ("Auto sync: 타임스탬프" 커밋들이 그 흔적)
- **Cloud Functions**: `functions/index.js` — 차량 운행일지 빈칸 알림 등 서버 스케줄 작업. 배포는 프로젝트 루트에서 `./node_modules/.bin/firebase deploy --only functions:X` (firebase-tools가 `functions/`가 아니라 루트에 설치돼 있음)

## 검증 방식 (이 세션에서 계속 써온 방법)

이 앱은 실제 로그인이 필요한 Firebase 백엔드에 의존하기 때문에 브라우저에서 풀 E2E 테스트가 어려움. 대신:
1. 코드 수정 후 `<script>` 내용을 추출해서 `node --check`로 문법만 검사
2. `git log --oneline -3`로 로컬 감시 스크립트가 자동 커밋/푸시했는지 확인
3. 격리된 로직(필터 엔진 등)은 임시 테스트 하네스를 스크래치 디렉토리에 만들어 `python -m http.server`로 띄우고 Browser pane으로 직접 검증한 뒤 삭제

## 이번 세션에서 구현한 것 (최근 것부터 역순 아님, 시간 순)

### 1. 법인카드 6종 분류 + 사람별 화면 필터 (세션 초반, 이후 필터는 되돌림)
- `CORP_CARD_CATEGORY_LAST4/LABELS/ORDER`로 개인불출/공용/안전/소모품/사무실/상계 6종 분류
- `CORP_CARD_ASSIGNED_NAMES`: 카드번호 → 담당자 이름 매핑
- **주의**: 처음엔 "담당자 아닌 사람에겐 카드 안 보이게" 필터를 넣었으나, 나중에 사용자 요청으로 **완전히 제거함** — 지금은 관리자든 일반 사용자든 전체 카드가 다 보임 (`renderCorpCardMain`의 `visibleCards = s.cards`)

### 2. 차량운행일지 월별 분리
- `vehicleState.rowsByVehicle[vehicleId]`가 `{[월]: rows[]}` 형태 (예전엔 flat 배열, 자동 마이그레이션 로직 있음)
- 엑셀 내보내기도 월별로 파일 하나씩 (원본 서식이 한 시트에 25행까지만 들어가는 제약 때문)
- `functions/index.js`의 `checkVehicleBlanksHourly`도 이 새 구조에 맞춰 수정·배포 완료

### 3. 범용 버전 이력 시스템
- `saveWithGenericHistory(key, value)` / `loadGenericHistory` / `openGenericHistoryOverlay` — "변동내역" 탭 하나에 12개 이상 탭의 저장 이력이 다 모여서 보임
- 카드관리(카드별)·차량관리(차량별)는 엔티티별로 세분화된 이력

### 4. 엑셀식 열 필터 (체크박스 드롭다운)
- `columnFilters`, `colFilterProviders`, `registerColFilterProvider`, `rowPassesColumnFilters`, `openColFilterDropdown` 등
- 거의 모든 표에 적용됨 (O&M리스트, 법인카드, 차량관리, 실적리스트, 계약서, 사용전점검, 대행서류, 문의대응, 모듈단가, 회사정보, 입금확인 등)
- **중요 구현 디테일**: 필터 아이콘 클릭 이벤트는 `document.body`에 **capture phase**(`addEventListener('click', fn, true)`)로 걸려있음 — bubble phase면 `<th>`의 정렬 클릭이 먼저 발동해버림

### 5. 법인카드 승인내역 대사 개선
- `reconcileCorpCardWithApproval`: 후보가 여러 개면 장소 유사도까지 요구 (같은 날짜/금액의 무관한 다른 거래를 잘못 매칭하던 버그 수정)
- `excludeCancelledApprovalPairs`: 결제+취소 쌍(동일 금액, 부호 반대)을 승인내역에서 제외
- `recomputeCorpCardMismatches`: 승인내역이 실제로 업로드된 달만 대사 (업로드 안 한 달을 "승인내역 없음"으로 잘못 빨간줄 치던 문제 수정)

### 6. 법인카드 입력 UX 제약 (최근 추가)
- 부서/법인도 성명/직급처럼 "고정값" 모드 지원 (`s.fixedDept`, `s.fixedCorp`)
- 사업분류: 자유 텍스트 → "사무실/사업" 드롭다운 강제
- 사무실 선택 시 발전소명 자동으로 "사무실관리"로 채우고 잠금(readonly)
- 하이패스: 자유 텍스트 → O/X 드롭다운 강제
- 비고: 지출내역이 "식대"/"접대비"일 때만 타이핑 가능. 단, 이미 적힌 내용이 있으면(레거시 데이터) 지울 수 있도록 예외적으로 열어둠 (`noteLocked` 계산 로직 참고)

### 7. 사업 이윤정산 "가로 목록" 대개조
- **삭제 기능** 추가 (`deleteProfitCaseById`, "삭제" 버튼)
- **중복건 안내**: 고객명·시공일자·설치용량·총사업비가 모두 같으면 "⚠ 중복의심" 배지 (`profitCaseDupKey`)
- **체크 시 행 하이라이트**: 선택한 행 배경색 표시
- **가로모드 인라인 편집**: `PROFIT_LIST_COLUMNS`에 `edit`/`pfield`/`options` 메타 추가, 약 29개 컬럼이 표에서 바로 편집 가능 (`applyProfitListFieldChange`). 나머지(부가세·합계·이윤 등 계산값)는 읽기 전용
- **회사입금가가 "정산데이터" 기록에서 누락되던 버그 수정**: `resolveProfitLedgerValues`가 연결된 영업비 건/실적리스트에서만 값을 가져오고 이윤정산 건 자체의 `depositPrice`는 무시하던 문제 → 폴백 추가

### 8. 스크롤 점프 버그 일괄 수정
체크박스나 셀 편집 시 표 전체를 다시 그리는데(`innerHTML` 통째로 교체), 이때 `.table-wrap-frozen`의 스크롤 위치(세로 `scrollTop` + **가로 `scrollLeft`**, 특히 가로가 넓은 표에서 중요)가 초기화되던 문제. 아래 화면 전부에 "그리기 전 저장 → 그린 뒤 복원" 패턴 적용:
- 이윤정산 가로 목록 (`profitListTableWrap`)
- 법인카드 (`corpCardTableWrap`)
- 차량관리 (`vehicleTableWrap`)
- O&M 리스트 (`omListTableWrap`)
- 실적리스트 업로드/직접입력 (`importTableWrap`, `perfTableWrap`)
- 계약서 관리는 표 자체 스크롤이 아니라 페이지 스크롤이라 `window.scrollY` 저장/복원 방식 사용

### 9. 계약서 중복 업로드 확인
파일명이 같은 기존 계약서가 있으면 실제 PDF 내용(base64)까지 비교. 제목만 같고 내용 다르면 그냥 업로드(갱신본일 수 있음), 제목·내용 완전히 같으면 confirm 창으로 물어봄.

### 10. 실적리스트 → 영업비 정산 / 사업 이윤정산 자동 반영 (중요 기능)
- `buildSalesRecordFromRow`/`buildProfitCaseFromRow`가 만든 레코드/건에 `sourceRowId`(원본 실적리스트 행 id)를 저장
- 각 레코드/건에 `touchedFields` 배열 — 건 생성 후 상세화면(또는 이윤정산 가로 목록)에서 사람이 직접 고친 필드명을 기록
- `syncSalesRecordFromRow`/`syncProfitCaseFromRow`: 실적리스트 행이 바뀌면 `SALES_ROW_SYNCED_FIELDS`/`PROFIT_ROW_SYNCED_FIELDS`에 정의된 필드만, **touchedFields에 없는 것만** 새 값으로 갱신 (사람이 이미 고친 값은 절대 덮어쓰지 않음)
- `syncCasesFromImportRows(rows)`: 실적리스트 편집 시 0.6초 debounce 후 전체 케이스를 스캔해서 동기화 (`debouncedSyncFromImportRows`/`debouncedSyncFromManualRows`)
- **주의**: `newRecord()`/`newProfitCase()`의 기본값 중 `draftDate`처럼 "지금 시각" 기준으로 매번 새로 계산되는 값은 SYNCED_FIELDS 목록에 절대 넣으면 안 됨 (동기화할 때마다 오늘 날짜로 덮어써지는 버그가 남)

### 11. 실시간 협업 기능 (가장 최근 작업, 핵심 3개 탭: 법인카드/차량관리/실적리스트)
사용자가 "다른 사람이 실시간으로 보이고, 누가 어느 칸 클릭 중인지 색으로 표시, 상단에 OO 사용중 표시"를 요청. AskUserQuestion으로 범위(핵심 탭부터)와 정밀도(칸 단위)를 확정받고 구현:

**실시간 데이터 반영**:
- 기존에 이미 `subscribeListToStorage`(Firestore `onSnapshot` 기반) 패턴이 계약서/사용전점검/입금확인/O&M리스트/대행서류/문의대응 6개 탭에 있었음 — 이 패턴을 재사용
- 법인카드: `ensureCorpCardRowsSubscribed(cardId)` — 지금 보는 카드의 `corp-card-rows:{cardId}` 문서만 구독, 카드 전환 시 재구독
- 차량관리: `ensureVehicleRowsSubscribed(vehicleId)` — 동일한 방식
- 실적리스트: `init()`에서 `IMPORT_DATA_KEY`/`PERF_ROWS_KEY`를 `subscribeListToStorage`로 전환 (기존 `loadImportData`/`loadPerfRows` 함수는 삭제됨 — 더 이상 안 씀)

**프레즌스(접속 현황) — 새 기능, 완전히 새로 만든 서브시스템**:
- Firestore에 **새 컬렉션 `presence`** 사용 (세션마다 별도 문서, `presenceSessionId`로 구분 — 동시 편집 시 서로 덮어쓸 위험 없음)
- 20초마다 heartbeat, `updatedAt`이 45초 넘으면 "끊긴 세션"으로 필터링 (브라우저를 그냥 닫아버려도 정리됨)
- `wirePresenceCells(elements, keyFn)`: 기존 표의 `data-id`/`data-field`(법인카드·차량관리) 또는 `data-perf`+상위 `<tr>`(실적리스트, `importCellKey` 헬퍼) 속성에서 cellKey를 계산 — **표 템플릿 HTML 자체는 거의 안 건드리고** 렌더링 후 한 번 훑어서 focus/blur 이벤트와 하이라이트 스타일을 붙이는 방식
- 상단 배너(`#presenceBanner`, `<main>` 바로 위에 새로 추가된 wrapper div 안에 위치)에 "OO님이 사용 중" 표시
- `PRESENCE_ENABLED_TABS = ['corpCard','vehicle','import']` — 이 3개 탭에서만 동작

**⚠️ 확인 필요 (미검증)**:
1. **Firestore 보안 규칙**: `presence`는 이번에 처음 만든 컬렉션. 기존에 `users` 컬렉션에 대한 `.where()` 쿼리가 이미 동작 중인 걸로 봐서 규칙이 인증된 사용자에게 전반적으로 열려있을 가능성이 높지만, 실제로 새 컬렉션에 대한 읽기/쓰기가 막혀있을 수도 있음. **화면에 프레즌스 배너/하이라이트가 전혀 안 뜨면 제일 먼저 이걸 의심할 것.** Firebase 콘솔 → Firestore → 규칙에서 `match /presence/{doc}` 허용 여부 확인
2. **실사용자 2명 이상 동시 테스트를 못 해봄** — 브라우저 두 개(또는 시크릿 창)로 서로 다른 계정 로그인해서 실제로 색칠·배너가 뜨는지 확인 필요
3. HTML 구조가 바뀜: `<main id="main">`가 이제 `<aside>`와 직접 형제가 아니라, `<div style="display:flex; flex-direction:column;...">` 래퍼 안에 `#presenceBanner`와 함께 들어있음 (레이아웃 CSS는 확인했지만 실제 브라우저 렌더링으로 직접 보지는 못함)

## 아직 안 한 것 / 다음에 할 수 있는 것
- 프레즌스·실시간 반영을 나머지 탭(영업비 정산/사업 이윤정산 케이스, 모듈단가, 회사정보 등)까지 확장 — 사용자가 "핵심 탭부터" 하기로 결정했고 확장은 아직 요청 안 됨
- "40번 해설해줘"라는 요청이 세션 중간에 있었는데 첨부 자료/맥락이 없어서 미해결로 넘어감 (사용자가 다시 언급 안 하면 그냥 두면 됨)

## 코드에서 자주 참고할 위치 (전부 `index.html` 안)
- 법인카드: `CORP_CARD_*` 상수, `renderCorpCardMain`, `corpCardRowIssues`
- 차량관리: `renderVehicleMain`, `vehicleRowIssues`
- 실적리스트: `renderImportMain`/`renderUploadMode`/`renderManualEntry`, `buildSalesRecordFromRow`, `buildProfitCaseFromRow`
- 영업비 정산: `renderSalesMain`, `renderRecordRows`
- 사업 이윤정산: `renderProfitMain`(개별), `renderProfitListMain`(가로 목록), `computeProfitCase`
- 프레즌스: `currentUserName` 선언부 바로 아래 "실시간 접속 현황" 섹션 (파일 끝쪽, `fbAuth.onAuthStateChanged` 바로 위)
- 공통 인프라: `saveWithGenericHistory`, `subscribeListToStorage`, `registerColFilterProvider`, `escapeHtml`, `fmtNum`/`fmtWon`

## 개발 관습 (새 세션도 지켜야 할 것)
- 코드 수정 후 `node --check`로 문법 검사 (스크립트 태그 내용만 추출해서)
- 커밋은 로컬 감시 스크립트가 자동으로 하므로 **직접 git commit 할 필요 없음** (로컬 세션 한정 — 클라우드 세션이면 직접 commit/push 필요할 수 있음)
- 큰 기능(여러 탭에 영향, 되돌리기 어려운 설계 결정)은 AskUserQuestion으로 범위 확인 후 진행
- 콤마 포맷 숫자 입력칸: `type="text" inputmode="numeric"`, blur 시에만 재포맷 (커서 튐 방지)
- 표 다시 그릴 때 스크롤 보존 패턴을 새 표에도 반드시 적용 (섹션 8 참고)
