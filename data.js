// Supabase에서 훈련 과정 회차 데이터를 읽어, 예전 구글 시트(시트4)와 같은
// 17칸 문자열 배열 형식으로 돌려준다. 그래서 각 페이지의 파싱 코드는 그대로 쓴다.
//
// [기관명, 과정명, 훈련비, NCS직무, NCS수준, 훈련일, 훈련시간, 시간당훈련비, 회차, 개강일,
//  모집정원, 수강확정, 만족도, 평가인원, 모집률, 수료율, 6개월취업률]

const TRAINING_COLUMNS = [
    'institution', 'course_name', 'training_fee', 'ncs_job', 'ncs_level',
    'training_days', 'training_hours', 'hourly_fee', 'session', 'start_date',
    'capacity', 'confirmed', 'satisfaction', 'evaluators',
    'recruitment_rate', 'completion_rate', 'employment_rate_6m'
];

function toCell(value) {
    return value === null || value === undefined ? '' : String(value);
}

function toPercentCell(value) {
    if (value === null || value === undefined || value === '') return '';
    return `${Number(value).toFixed(1)}%`;
}

function toRateCell(value) {
    if (value === null || value === undefined || value === '') return '';
    return String(Number(value));
}

async function loadTrainingRows() {
    const cfg = window.APP_CONFIG || {};
    if (!cfg.SUPABASE_URL || cfg.SUPABASE_URL.includes('YOUR-PROJECT')) {
        throw new Error('config.js에 Supabase 주소와 anon 키를 입력해 주세요.');
    }

    const base = `${cfg.SUPABASE_URL.replace(/\/$/, '')}/rest/v1/training_sessions`;
    const query = `select=${TRAINING_COLUMNS.join(',')}&order=start_date.desc.nullslast,id.asc`;
    const pageSize = 1000;
    const rows = [];

    for (let start = 0; ; start += pageSize) {
        const response = await fetch(`${base}?${query}`, {
            headers: {
                apikey: cfg.SUPABASE_ANON_KEY,
                Authorization: `Bearer ${cfg.SUPABASE_ANON_KEY}`,
                'Range-Unit': 'items',
                Range: `${start}-${start + pageSize - 1}`
            }
        });
        if (!response.ok) {
            throw new Error(`Supabase 응답 오류 ${response.status}: ${await response.text()}`);
        }
        const page = await response.json();
        rows.push(...page);
        if (page.length < pageSize) break;
    }

    return rows.map(r => [
        toCell(r.institution),
        toCell(r.course_name),
        toCell(r.training_fee),
        toCell(r.ncs_job),
        toCell(r.ncs_level),
        toCell(r.training_days),
        toCell(r.training_hours),
        toCell(r.hourly_fee),
        toCell(r.session),
        toCell(r.start_date),
        toCell(r.capacity),
        toCell(r.confirmed),
        r.satisfaction === null || r.satisfaction === undefined ? '' : String(Number(r.satisfaction)),
        toCell(r.evaluators),
        toPercentCell(r.recruitment_rate),
        toPercentCell(r.completion_rate),
        toRateCell(r.employment_rate_6m)
    ]);
}
