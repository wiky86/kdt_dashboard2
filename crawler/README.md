# KDT 데이터 수집기

고용24 웹페이지를 크롤링해서 K-디지털 트레이닝(KDT) 전체 과정의 회차별 데이터를
Supabase `training_sessions` 테이블에 저장합니다. GitHub Actions가 **매주 월요일 새벽 3시 17분(KST)** 에 자동 실행합니다.

## 어떻게 동작하나

1. **목록 페이지** — KDT 과정 목록은 링크와 페이지 이동이 모두 자바스크립트라서 실제 브라우저(Playwright, 화면 없이 실행)로 열고 끝 페이지까지 넘기며 과정을 모읍니다.
2. **상세 페이지** — 과정마다 회차별 상세 페이지(`selectTracseDetl.do`)를 일반 요청으로 읽습니다. 다음 회차를 우선 읽습니다.
   - 아직 DB에 없는 회차 (처음 보는 과정이면 1회차부터 전부)
   - 값이 아직 바뀌는 회차 (모집·진행 중이거나 종강 후 9개월 이내) — 7일마다 다시 읽음
   - 진행 중인 과정의 "마지막 회차 + 1" (새 회차가 생겼는지)
3. **저장** — 회차당 한 행. 이미 저장된 값은 빈 값으로 덮어쓰지 않습니다. 200페이지마다 중간 저장하므로 도중에 멈춰도 그때까지는 남습니다.

한 번 실행에 상세 페이지는 최대 4,000개, 1.2초 간격으로 엽니다(1분에 20페이지 안팎, 최대 3시간 남짓). 다 못 읽은 건 다음 실행에서 이어서 읽습니다. 없는 회차(폐강 등)는 기록해 두고 30일 동안 다시 열지 않습니다.

| 상세 페이지에서 읽는 값 | 계산하는 값 |
|---|---|
| 개강일·종강일, 회차, 훈련비, 훈련일수·훈련시간, NCS 직무·코드·수준, 모집정원, 수강신청·수강확정 인원, 만족도·평가인원, (있으면) 수료인원·수료율·취업률 | 시간당훈련비, 모집률, 수료율(수료인원이 있을 때) |

## 처음 설정 (한 번만)

### 1. Supabase
1. SQL Editor에서 [`supabase/schema.sql`](../supabase/schema.sql)을 실행합니다.
2. Project Settings > API에서 Project URL, `anon` 키, `service_role` 키를 확인합니다.

### 2. GitHub 시크릿
저장소 **Settings > Secrets and variables > Actions > New repository secret**

| 이름 | 값 |
|---|---|
| `SUPABASE_URL` | Supabase Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase `service_role` 키 (**절대 공개 금지**) |

### 3. 대시보드 연결
루트의 [`config.js`](../config.js)에 Project URL과 **anon** 키를 넣습니다. anon 키는 공개돼도 괜찮아요(테이블이 읽기 전용).

### 4. 첫 실행 (Actions 탭 > KDT 데이터 수집 > Run workflow)
1. **inspect** — DB에 쓰지 않고 목록 2페이지·상세 10개만 시험. 실행 Summary에 항목별로 채워진 비율이 나오고, Artifacts의 `inspect/`에 목록 페이지 HTML·스크린샷과 상세 페이지 원본이 저장됩니다.
2. **migrate** — 구글 시트(시트4)의 기존 데이터를 Supabase로 옮깁니다(한 번만).
3. **backfill** — 과거 회차까지 채우기(상세 페이지 최대 8,000개, 몇 시간 걸림). 한 번에 다 안 차면 한두 번 더 실행하거나, 매주 월요일 자동 실행이 이어서 채웁니다.

## 로컬에서 실행

```bash
pip install -r crawler/requirements.txt
python -m playwright install chromium
export SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=...
python -m crawler.main --dry-run --max-pages 20 --csv out/sessions.csv   # DB에 안 쓰고 확인
python -m crawler.main --headful --max-list-pages 1 --dry-run            # 브라우저 창 띄워서 보기
python -m pytest crawler/tests
```

주요 옵션: `--max-pages N`, `--max-list-pages N`, `--delay 초`, `--rescrape-days N`, `--skip-list`, `--inspect DIR`, `--dry-run`.

## 문제 해결

- **목록에서 찾은 과정이 0** — `inspect`의 `list/list_page1.png`로 페이지가 제대로 열렸는지 보고, `list_page1.html`에서 과정 링크의 `onclick` 형태를 확인해 [`list_crawler.py`](list_crawler.py)의 추출 규칙을 맞춥니다. 목록이 실패해도 DB에 이미 있는 과정은 계속 갱신됩니다.
- **특정 항목 비율이 0%** — `inspect/detail/*.txt`(상세 페이지에서 보이는 글자)를 보고 [`detail_scraper.py`](detail_scraper.py)의 정규식을 고칩니다.
- **고용24 접속이 막힘(타임아웃/403)** — GitHub Actions 서버는 해외에 있어 차단될 수 있습니다. 연속 15번 실패하면 수집기가 스스로 멈춥니다. 그럴 땐 국내 PC를 [self-hosted runner](https://docs.github.com/actions/hosting-your-own-runners)로 등록하고 워크플로의 `runs-on: ubuntu-latest`를 `runs-on: self-hosted`로 바꿉니다.
- **자동 실행이 멈춤** — GitHub은 60일간 커밋이 없는 공개 저장소의 예약 실행을 끕니다. Actions 탭에서 다시 켜면 됩니다.
- **사이트 부담** — 요청 간격(`--delay`, 기본 1.2초)과 실행당 페이지 수(`--max-pages`)로 조절합니다. 새벽에 한 번만 돌도록 되어 있습니다.
