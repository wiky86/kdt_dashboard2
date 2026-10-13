-- KDT 훈련과정 회차별 데이터 (Supabase SQL Editor에서 한 번 실행)
-- 한 행 = 한 과정의 한 회차

create table if not exists public.training_sessions (
    id                  bigint generated always as identity primary key,

    -- 고용24 식별자 (구글 시트에서 옮겨온 옛 데이터는 null)
    tracse_id           text,            -- 훈련과정 ID (예: AIG20233000936060)
    trainst_cstmr_id    text,            -- 훈련기관 ID (예: 500020039555)
    crse_tracse_se      text,            -- 훈련유형 코드 (KDT: C0104)
    session             integer not null, -- 회차

    institution         text not null,   -- 기관명
    course_name         text not null,   -- 과정명
    training_fee        bigint,          -- 훈련비(원)
    ncs_code            text,
    ncs_job             text,            -- NCS 직무명
    ncs_level           integer,         -- NCS 수준
    training_days       integer,         -- 훈련일수
    training_hours      integer,         -- 총 훈련시간
    hourly_fee          integer,         -- 시간당 훈련비 (훈련비 / 훈련시간)
    start_date          date,            -- 개강일
    end_date            date,            -- 종강일

    capacity            integer,         -- 모집정원
    applicants          integer,         -- 수강신청인원
    confirmed           integer,         -- 수강확정(수강)인원
    completed           integer,         -- 수료인원
    satisfaction        numeric(4,2),    -- 만족도 점수
    evaluators          integer,         -- 만족도 평가인원
    recruitment_rate    numeric(6,1),    -- 모집률 % (수강확정/정원)
    completion_rate     numeric(6,1),    -- 수료율 % (수료/수강확정)
    employment_rate_3m  numeric(6,1),    -- 3개월 취업률 %
    employment_rate_6m  numeric(6,1),    -- 6개월 취업률 %

    source              text not null default 'crawler',  -- crawler | sheet_migration
    web_scraped_at      timestamptz,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);

create unique index if not exists training_sessions_course_session_uq
    on public.training_sessions (tracse_id, trainst_cstmr_id, session);
create index if not exists training_sessions_start_date_idx
    on public.training_sessions (start_date desc);
create index if not exists training_sessions_inst_course_idx
    on public.training_sessions (institution, course_name);

-- updated_at 자동 갱신
create or replace function public.touch_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at := now();
    return new;
end $$;

drop trigger if exists training_sessions_touch on public.training_sessions;
create trigger training_sessions_touch
    before update on public.training_sessions
    for each row execute function public.touch_updated_at();

-- 대시보드는 anon 키로 읽기만, 쓰기는 수집기(service_role 키)만
alter table public.training_sessions enable row level security;

drop policy if exists "public read" on public.training_sessions;
create policy "public read" on public.training_sessions
    for select to anon, authenticated using (true);

-- 구글 시트에서 옮겨온 옛 행(tracse_id 없음)과 수집기가 만든 행이 겹치면
-- 옛 행에만 있던 값을 새 행에 채워 넣고 옛 행은 지운다.
create or replace function public.merge_legacy_rows() returns integer
language plpgsql security definer set search_path = public as $$
declare
    n integer;
begin
    update training_sessions t set
        training_fee       = coalesce(t.training_fee, l.training_fee),
        ncs_job            = coalesce(t.ncs_job, l.ncs_job),
        ncs_level          = coalesce(t.ncs_level, l.ncs_level),
        training_days      = coalesce(t.training_days, l.training_days),
        training_hours     = coalesce(t.training_hours, l.training_hours),
        hourly_fee         = coalesce(t.hourly_fee, l.hourly_fee),
        capacity           = coalesce(t.capacity, l.capacity),
        confirmed          = coalesce(t.confirmed, l.confirmed),
        satisfaction       = coalesce(t.satisfaction, l.satisfaction),
        evaluators         = coalesce(t.evaluators, l.evaluators),
        recruitment_rate   = coalesce(t.recruitment_rate, l.recruitment_rate),
        completion_rate    = coalesce(t.completion_rate, l.completion_rate),
        employment_rate_6m = coalesce(t.employment_rate_6m, l.employment_rate_6m)
    from training_sessions l
    where l.tracse_id is null and t.tracse_id is not null
      and l.institution = t.institution
      and l.course_name = t.course_name
      and l.session = t.session
      and l.start_date is not distinct from t.start_date;

    delete from training_sessions l
    using training_sessions t
    where l.tracse_id is null and t.tracse_id is not null
      and l.institution = t.institution
      and l.course_name = t.course_name
      and l.session = t.session
      and l.start_date is not distinct from t.start_date;
    get diagnostics n = row_count;
    return n;
end $$;

revoke all on function public.merge_legacy_rows() from public, anon, authenticated;

-- 상세 페이지가 없던 회차(폐강 등) 기록: 매일 다시 열어보지 않도록
create table if not exists public.crawl_skips (
    tracse_id        text not null,
    trainst_cstmr_id text not null,
    session          integer not null,
    checked_at       timestamptz not null default now(),
    primary key (tracse_id, trainst_cstmr_id, session)
);
alter table public.crawl_skips enable row level security;  -- 정책 없음 = service_role만 접근
