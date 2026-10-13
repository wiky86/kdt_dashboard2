# KDT 데이터 수집기

고용24에서 K-디지털 트레이닝(KDT, 훈련유형 `C0104`) 전체 과정의 회차별 데이터를 모아
Supabase `training_sessions` 테이블에 저장합니다. GitHub Actions가 **평일 새벽 3시 17분(KST)** 에 자동 실행합니다.

## 어디서 어떤 값을 가져오나

| 값 | 1순위 | 없으면 |
|---|---|---|
| 기관명, 과정명, 회차, 개강일·종강일, 훈련비, 모집정원, 수강신청인원, 만족도, 3·6개월 취업률, NCS코드 | 오픈API 목록 (310L01) | — |
| 훈련시간, 훈련일수, NCS 직무명 | 오픈API 과정/기관정보 (310L02) | 상세 페이지 |
| 수강확정인원, 수료인원 | 오픈API 훈련일정 (310L03) | 상세 페이지 |
| NCS 수준, 만족도 평가인원 | 상세 페이지 크롤링 | — |
| 시간당훈련비, 모집률, 수료율 | 위 값으로 계산 | — |

- 크롤링은 API에 없는 값이 비어 있는 회차만, 한 번 실행에 최대 400페이지까지, 1.5초 간격으로 합니다. 다 못 채운 건 다음 날 이어서 채웁니다.
- 이미 저장된 값은 빈 값으로 덮어쓰지 않습니다.

## 처음 설정 (한 번만)

### 1. 고용24 오픈API 인증키 발급
1. [고용24 Open-API 서비스 소개 및 신청](https://www.work24.go.kr/cm/e/a/0110/selectOpenApiSvcInfo.do?apiSvcId=&upprApiSvcId=&fullApiSvcId=000000000000000000000000000004) 에서 로그인 후 **국민내일배움카드 훈련과정** API를 신청합니다.
2. 승인되면 마이페이지에서 인증키(authKey)를 확인합니다.

### 2. Supabase 준비
1. [supabase.com](https://supabase.com) 에서 프로젝트를 만듭니다. (지역은 Northeast Asia (Seoul) 권장)
2. **SQL Editor**에서 [`supabase/schema.sql`](../supabase/schema.sql) 내용을 붙여넣고 실행합니다.
3. **Project Settings > API**에서 다음 세 값을 복사해 둡니다.
   - Project URL
   - `anon` public 키 → 대시보드용 (공개돼도 됨, 읽기 전용)
   - `service_role` 키 → 수집기용 (**절대 공개 금지**)

### 3. GitHub 시크릿 등록
저장소 **Settings > Secrets and variables > Actions > New repository secret**

| 이름 | 값 |
|---|---|
| `WORK24_API_KEY` | 고용24 인증키 |
| `SUPABASE_URL` | Supabase Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service_role 키 |

### 4. 대시보드 연결
루트의 [`config.js`](../config.js)에 Project URL과 **anon** 키를 넣고 커밋합니다.

### 5. 첫 실행 (Actions 탭 > KDT 데이터 수집 > Run workflow)
순서대로 한 번씩 실행하세요.

1. **inspect** — DB에 쓰지 않고 최근 60일치로 시험 실행. 실행 결과의 Summary에서 항목별 채워진 비율을 보고, Artifacts의 `inspect/` 폴더에 API 원본 응답과 상세 페이지 샘플이 저장됩니다. 비율이 0%인 항목이 있으면 이 파일을 보고 필드 이름을 맞춥니다(아래 '문제 해결').
2. **migrate** — 구글 시트(시트4)의 기존 데이터를 Supabase로 옮깁니다. 한 번만 실행됩니다.
3. **full** — KDT 시작(2020-12)부터 전체 수집. 오래 걸립니다(최대 3시간).

이후로는 평일 새벽에 자동으로 `normal`(최근 약 15개월 ~ 6개월 뒤 개강 회차)이 돕니다.

## 로컬에서 실행

```bash
pip install -r crawler/requirements.txt
export WORK24_API_KEY=... SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
python -m crawler.main --dry-run --csv out/sessions.csv   # DB에 안 쓰고 CSV로 확인
python -m crawler.main                                    # 실제 저장
python -m pytest crawler/tests                            # 테스트
```

주요 옵션: `--full`, `--since/--until YYYY-MM-DD`, `--max-scrape N`, `--skip-scrape`, `--skip-info`, `--skip-schedule`, `--inspect DIR`, `--dry-run`.

## 문제 해결

- **항목 채워진 비율이 0%** — 과정정보·훈련일정 API(310L02/310L03)의 응답 필드 이름은 공식 문서에서 확인되지 않아 후보 이름으로 찾고 있습니다. `inspect` 결과의 `callOpenApiSvcInfo310L02.json`, `...310L03.json`을 열어 실제 필드 이름을 [`work24_api.py`](work24_api.py)의 `FIELD`에 추가하면 됩니다. 상세 페이지 값이 비면 `inspect/detail/*.txt`를 보고 [`detail_scraper.py`](detail_scraper.py)의 정규식을 고칩니다.
- **고용24 접속이 막힘(타임아웃/403)** — GitHub Actions 서버는 해외에 있어 차단될 수 있습니다. 그럴 땐 국내 PC를 [self-hosted runner](https://docs.github.com/actions/hosting-your-own-runners)로 등록하고 워크플로의 `runs-on: ubuntu-latest`를 `runs-on: self-hosted`로 바꿉니다.
- **자동 실행이 멈춤** — GitHub은 60일간 커밋이 없는 공개 저장소의 예약 실행을 자동으로 끕니다. Actions 탭에서 다시 켜면 됩니다.
- **API 호출 한도** — 한 번 실행에 최대 4,000회(full은 20,000회)로 제한돼 있습니다. 한도에 걸리면 그때까지 받은 값은 저장되고 나머지는 다음 실행에서 채웁니다.
