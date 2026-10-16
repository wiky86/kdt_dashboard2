// 맞춤 조회: 자주 쓰는 조회(프리셋) + 직접 조건 조합 + 회차별/과정별/기관별 보기
// 데이터는 data.js의 loadTrainingRows()로 읽는다 (17칸 문자열 배열).

(function () {
    'use strict';

    // ---------------------------------------------------------------- 필드 정의
    const FIELDS = {
        confirmed:   { label: '수강확정', unit: '명' },
        capacity:    { label: '모집정원', unit: '명' },
        recruitRate: { label: '모집률', unit: '%' },
        completion:  { label: '수료율', unit: '%' },
        employment:  { label: '6개월 취업률', unit: '%' },
        satisfaction:{ label: '만족도', unit: '점' },
        evaluators:  { label: '평가인원', unit: '명' },
        fee:         { label: '훈련비', unit: '원' },
        hours:       { label: '훈련시간', unit: '시간' },
        hourlyFee:   { label: '시간당훈련비', unit: '원' },
        session:     { label: '회차', unit: '회' },
    };

    const OPS = {
        eq:       { label: '=',        test: (v, x) => v !== null && v === x },
        ne:       { label: '≠',        test: (v, x) => v !== null && v !== x },
        gte:      { label: '≥',        test: (v, x) => v !== null && v >= x },
        lte:      { label: '≤',        test: (v, x) => v !== null && v <= x },
        gt:       { label: '>',        test: (v, x) => v !== null && v > x },
        lt:       { label: '<',        test: (v, x) => v !== null && v < x },
        empty:    { label: '값 없음',  test: v => v === null, noValue: true },
        notEmpty: { label: '값 있음',  test: v => v !== null, noValue: true },
    };

    const TODAY = new Date().toISOString().slice(0, 10);
    const THIS_YEAR = TODAY.slice(0, 4);

    // ---------------------------------------------------------------- 프리셋
    const PRESETS = [
        {
            id: 'unopened', icon: 'fa-circle-xmark', tone: 'danger',
            title: '미개설 회차',
            sub: () => `${THIS_YEAR}년 개강일이 지났는데 수강확정 0명`,
            state: () => ({ year: THIS_YEAR, started: 'started', conds: [{ field: 'confirmed', op: 'eq', value: '0' }],
                            view: 'session', sort: { key: 'start', dir: 'asc' } }),
            desc: '개강일이 지났는데 수강확정 인원이 0명인 회차예요. 과정을 열지 못한 것으로 볼 수 있어요.',
        },
        {
            id: 'lowRecruit', icon: 'fa-arrow-trend-down', tone: 'orange',
            title: '모집률 저조',
            sub: () => `${THIS_YEAR}년 개강, 모집률 50% 미만 (0명 제외)`,
            state: () => ({ year: THIS_YEAR, started: 'started',
                            conds: [{ field: 'recruitRate', op: 'lt', value: '50' }, { field: 'confirmed', op: 'gt', value: '0' }],
                            view: 'session', sort: { key: 'recruitRate', dir: 'asc' } }),
            desc: '개강은 했지만 정원의 절반도 채우지 못한 회차예요.',
        },
        {
            id: 'full', icon: 'fa-users', tone: 'success',
            title: '정원 마감',
            sub: () => `${THIS_YEAR}년 개강, 모집률 100% 이상`,
            state: () => ({ year: THIS_YEAR, conds: [{ field: 'recruitRate', op: 'gte', value: '100' }],
                            view: 'session', sort: { key: 'recruitRate', dir: 'desc' } }),
            desc: '수강확정 인원이 모집정원 이상인 회차예요.',
        },
        {
            id: 'newCourses', icon: 'fa-seedling', tone: 'cyan',
            title: '신규 과정',
            sub: () => `${THIS_YEAR}년에 1회차를 개강한 과정`,
            state: () => ({ year: THIS_YEAR, conds: [{ field: 'session', op: 'eq', value: '1' }],
                            view: 'session', sort: { key: 'start', dir: 'asc' } }),
            desc: '해당 연도에 1회차가 개강한, 새로 생긴 과정이에요.',
        },
        {
            id: 'upcoming', icon: 'fa-calendar-plus', tone: 'purple',
            title: '개강 예정',
            sub: () => '오늘 이후 개강하는 회차',
            state: () => ({ started: 'upcoming', view: 'session', sort: { key: 'start', dir: 'asc' } }),
            desc: '아직 개강하지 않은 회차예요. 수강확정 인원은 모집이 진행되면서 바뀌어요.',
        },
        {
            id: 'topEmployment', icon: 'fa-briefcase', tone: 'success',
            title: '취업률 상위',
            sub: () => '6개월 취업률이 있는 회차, 높은 순',
            state: () => ({ conds: [{ field: 'employment', op: 'notEmpty', value: '' }],
                            view: 'session', sort: { key: 'employment', dir: 'desc' } }),
            desc: '6개월 취업률이 집계된 회차를 높은 순으로 보여줘요.',
        },
        {
            id: 'lowSatisfaction', icon: 'fa-face-frown', tone: 'orange',
            title: '만족도 낮음',
            sub: () => '만족도 4.0 미만, 평가인원 5명 이상',
            state: () => ({ conds: [{ field: 'satisfaction', op: 'lt', value: '4' }, { field: 'evaluators', op: 'gte', value: '5' }],
                            view: 'session', sort: { key: 'satisfaction', dir: 'asc' } }),
            desc: '평가인원이 충분한데 만족도가 4.0점 미만인 회차예요.',
        },
        {
            id: 'aiCampus', icon: 'fa-robot', tone: 'cyan',
            title: 'AI캠퍼스 과정',
            sub: () => `${THIS_YEAR}년 개강 K-디지털트레이닝(AI캠퍼스)`,
            state: () => ({ year: THIS_YEAR, kdt: 'AI캠퍼스', view: 'course', sort: { key: 'firstStart', dir: 'asc' } }),
            desc: 'KDT 구분이 AI캠퍼스인 과정이에요. 과정별로 회차 수와 미개설 회차를 볼 수 있어요.',
        },
        {
            id: 'instStatus', icon: 'fa-building', tone: 'primary',
            title: '기관별 개설 현황',
            sub: () => `${THIS_YEAR}년 기관별 회차·미개설·모집률`,
            state: () => ({ year: THIS_YEAR, view: 'institution', sort: { key: 'sessions', dir: 'desc' } }),
            desc: '기관마다 개강한 회차 수, 미개설 회차 수, 평균 모집률을 비교해요.',
        },
    ];

    // ---------------------------------------------------------------- 상태
    const DEFAULT_STATE = () => ({
        preset: '', year: '', from: '', to: '', ncs: '', inst: '', course: '', kdt: '',
        started: 'all', conds: [], view: 'session', sort: { key: 'start', dir: 'desc' },
    });
    let state = DEFAULT_STATE();
    let rows = [];
    let lastResult = { view: 'session', items: [] };
    let shown = 0;
    const PAGE = 300;

    // ---------------------------------------------------------------- 유틸
    const $ = id => document.getElementById(id);
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const num = s => {
        if (s === null || s === undefined) return null;
        const t = String(s).replace(/[,%\s]/g, '');
        if (t === '') return null;
        const n = Number(t);
        return Number.isFinite(n) ? n : null;
    };
    const fmtInt = n => (n === null || n === undefined ? '-' : Math.round(n).toLocaleString('ko-KR'));
    const fmtPct = n => (n === null || n === undefined ? '-' : `${n.toFixed(1)}%`);
    const fmtSat = n => (n === null || n === undefined ? '-' : n.toFixed(1));
    const avg = arr => {
        const v = arr.filter(x => x !== null && x !== undefined);
        return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
    };

    const kdtBadge = k => (k && k !== '일반') ? ` <span class="badge badge--kdt">${esc(k)}</span>` : '';

    function toast(msg) {
        const t = $('toast');
        t.textContent = msg;
        t.classList.add('show');
        clearTimeout(toast._t);
        toast._t = setTimeout(() => t.classList.remove('show'), 2200);
    }

    // ---------------------------------------------------------------- 데이터
    function parseRows(raw) {
        return raw.map(r => {
            const o = {
                inst: r[0], course: r[1], feeRaw: r[2],
                fee: num(r[2]), ncs: r[3], level: num(r[4]), days: num(r[5]), hours: num(r[6]),
                hourlyFee: num(r[7]), session: num(r[8]), start: r[9] || '',
                capacity: num(r[10]), confirmed: num(r[11]), satisfaction: num(r[12]), evaluators: num(r[13]),
                recruitRate: num(r[14]), completion: num(r[15]), employment: num(r[16]),
                kdt: r[17] || '',
            };
            if (o.recruitRate === null && o.capacity && o.confirmed !== null) {
                o.recruitRate = Math.round(o.confirmed / o.capacity * 1000) / 10;
            }
            o.started = !!o.start && o.start <= TODAY;
            o.unopened = o.started && o.confirmed === 0;
            o.groupKey = `${o.inst}|${o.course}|${o.feeRaw}`;
            return o;
        });
    }

    // ---------------------------------------------------------------- 필터
    function applyFilters(data, s) {
        const inst = s.inst.trim().toLowerCase();
        const course = s.course.trim().toLowerCase();
        const conds = s.conds
            .filter(c => FIELDS[c.field] && OPS[c.op] && (OPS[c.op].noValue || num(c.value) !== null))
            .map(c => ({ field: c.field, test: OPS[c.op].test, x: num(c.value) }));
        return data.filter(r => {
            if (s.year && !r.start.startsWith(s.year)) return false;
            if (s.from && (!r.start || r.start < s.from)) return false;
            if (s.to && (!r.start || r.start > s.to)) return false;
            if (s.ncs && r.ncs !== s.ncs) return false;
            if (s.kdt && (s.kdt === '__none' ? r.kdt : r.kdt !== s.kdt)) return false;
            if (inst && !r.inst.toLowerCase().includes(inst)) return false;
            if (course && !r.course.toLowerCase().includes(course)) return false;
            if (s.started === 'started' && !r.started) return false;
            if (s.started === 'upcoming' && (r.started || !r.start)) return false;
            for (const c of conds) if (!c.test(r[c.field], c.x)) return false;
            return true;
        });
    }

    // ---------------------------------------------------------------- 묶기
    function groupBy(data, keyFn, build) {
        const m = new Map();
        for (const r of data) {
            const k = keyFn(r);
            if (!m.has(k)) m.set(k, []);
            m.get(k).push(r);
        }
        return [...m.entries()].map(([k, list]) => build(k, list));
    }

    function summarizeGroup(list) {
        const started = list.filter(r => r.started);
        const opened = started.filter(r => r.confirmed !== null && r.confirmed > 0);
        const starts = list.map(r => r.start).filter(Boolean).sort();
        return {
            sessions: list.length,
            unopened: started.filter(r => r.unopened).length,
            openRate: started.length ? opened.length / started.length * 100 : null,
            capacity: list.reduce((a, r) => a + (r.capacity || 0), 0),
            confirmed: list.reduce((a, r) => a + (r.confirmed || 0), 0),
            recruitRate: avg(list.map(r => r.recruitRate)),
            satisfaction: avg(list.map(r => r.satisfaction)),
            employment: avg(list.map(r => r.employment)),
            firstStart: starts[0] || '',
            lastStart: starts[starts.length - 1] || '',
        };
    }

    // ---------------------------------------------------------------- 보기별 컬럼
    const VIEWS = {
        session: {
            columns: [
                { key: 'start', label: '개강일', fmt: r => esc(r.start || '-') },
                { key: 'inst', label: '기관명', fmt: r => esc(r.inst), cls: 'col-text' },
                { key: 'course', label: '과정명', fmt: r => esc(r.course) + kdtBadge(r.kdt), cls: 'col-text col-wide' },
                { key: 'session', label: '회차', fmt: r => fmtInt(r.session), num: true },
                { key: 'capacity', label: '정원', fmt: r => fmtInt(r.capacity), num: true },
                { key: 'confirmed', label: '수강확정', fmt: r => r.unopened ? `<span class="badge badge--danger">0</span>` : fmtInt(r.confirmed), num: true },
                { key: 'recruitRate', label: '모집률', fmt: r => fmtPct(r.recruitRate), num: true },
                { key: 'satisfaction', label: '만족도', fmt: r => r.satisfaction === null ? '-' : `${fmtSat(r.satisfaction)}<small> (${fmtInt(r.evaluators)})</small>`, num: true },
                { key: 'completion', label: '수료율', fmt: r => fmtPct(r.completion), num: true },
                { key: 'employment', label: '취업률', fmt: r => fmtPct(r.employment), num: true },
                { key: 'hourlyFee', label: '시간당훈련비', fmt: r => fmtInt(r.hourlyFee), num: true },
            ],
            csv: [['개강일', 'start'], ['기관명', 'inst'], ['과정명', 'course'], ['회차', 'session'], ['KDT구분', 'kdt'], ['NCS직무', 'ncs'],
                  ['훈련비', 'fee'], ['훈련시간', 'hours'], ['시간당훈련비', 'hourlyFee'], ['모집정원', 'capacity'],
                  ['수강확정', 'confirmed'], ['모집률', 'recruitRate'], ['만족도', 'satisfaction'], ['평가인원', 'evaluators'],
                  ['수료율', 'completion'], ['6개월취업률', 'employment']],
            build: data => data,
            link: r => r.groupKey,
        },
        course: {
            columns: [
                { key: 'inst', label: '기관명', fmt: r => esc(r.inst), cls: 'col-text' },
                { key: 'course', label: '과정명', fmt: r => esc(r.course) + kdtBadge(r.kdt), cls: 'col-text col-wide' },
                { key: 'sessions', label: '해당 회차', fmt: r => fmtInt(r.sessions), num: true },
                { key: 'unopened', label: '미개설', fmt: r => r.unopened ? `<span class="badge badge--danger">${r.unopened}</span>` : '0', num: true },
                { key: 'firstStart', label: '첫 개강', fmt: r => esc(r.firstStart || '-') },
                { key: 'lastStart', label: '마지막 개강', fmt: r => esc(r.lastStart || '-') },
                { key: 'confirmed', label: '수강확정 합계', fmt: r => fmtInt(r.confirmed), num: true },
                { key: 'recruitRate', label: '평균 모집률', fmt: r => fmtPct(r.recruitRate), num: true },
                { key: 'satisfaction', label: '평균 만족도', fmt: r => fmtSat(r.satisfaction), num: true },
                { key: 'employment', label: '평균 취업률', fmt: r => fmtPct(r.employment), num: true },
            ],
            csv: [['기관명', 'inst'], ['과정명', 'course'], ['KDT구분', 'kdt'], ['훈련비', 'fee'], ['해당회차', 'sessions'], ['미개설', 'unopened'],
                  ['첫개강', 'firstStart'], ['마지막개강', 'lastStart'], ['수강확정합계', 'confirmed'],
                  ['평균모집률', 'recruitRate'], ['평균만족도', 'satisfaction'], ['평균취업률', 'employment']],
            build: data => groupBy(data, r => r.groupKey, (k, list) => ({
                groupKey: k, inst: list[0].inst, course: list[0].course, fee: list[0].fee, kdt: list[0].kdt, ...summarizeGroup(list),
            })),
            link: r => r.groupKey,
        },
        institution: {
            columns: [
                { key: 'inst', label: '기관명', fmt: r => esc(r.inst), cls: 'col-text col-wide' },
                { key: 'courses', label: '과정 수', fmt: r => fmtInt(r.courses), num: true },
                { key: 'sessions', label: '회차 수', fmt: r => fmtInt(r.sessions), num: true },
                { key: 'unopened', label: '미개설 회차', fmt: r => r.unopened ? `<span class="badge badge--danger">${r.unopened}</span>` : '0', num: true },
                { key: 'openRate', label: '개설률', fmt: r => fmtPct(r.openRate), num: true },
                { key: 'confirmed', label: '수강확정 합계', fmt: r => fmtInt(r.confirmed), num: true },
                { key: 'recruitRate', label: '평균 모집률', fmt: r => fmtPct(r.recruitRate), num: true },
                { key: 'satisfaction', label: '평균 만족도', fmt: r => fmtSat(r.satisfaction), num: true },
                { key: 'employment', label: '평균 취업률', fmt: r => fmtPct(r.employment), num: true },
            ],
            csv: [['기관명', 'inst'], ['과정수', 'courses'], ['회차수', 'sessions'], ['미개설회차', 'unopened'], ['개설률', 'openRate'],
                  ['수강확정합계', 'confirmed'], ['평균모집률', 'recruitRate'], ['평균만족도', 'satisfaction'], ['평균취업률', 'employment']],
            build: data => groupBy(data, r => r.inst, (k, list) => ({
                inst: k, courses: new Set(list.map(r => r.groupKey)).size, ...summarizeGroup(list),
            })),
            link: r => null,
            filterLink: r => r.inst,
        },
    };

    function sortItems(items, sort) {
        const dir = sort.dir === 'asc' ? 1 : -1;
        const k = sort.key;
        return [...items].sort((a, b) => {
            const va = a[k], vb = b[k];
            const ea = va === null || va === undefined || va === '';
            const eb = vb === null || vb === undefined || vb === '';
            if (ea && eb) return 0;
            if (ea) return 1;           // 빈 값은 항상 뒤로
            if (eb) return -1;
            if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
            return String(va).localeCompare(String(vb), 'ko') * dir;
        });
    }

    // ---------------------------------------------------------------- 렌더링
    function renderPresets() {
        $('presetGrid').innerHTML = PRESETS.map(p => `
            <button type="button" class="preset preset--${p.tone}" data-preset="${p.id}">
                <span class="preset-icon"><i class="fas ${p.icon}"></i></span>
                <span class="preset-text">
                    <span class="preset-title">${esc(p.title)}</span>
                    <span class="preset-sub">${esc(p.sub())}</span>
                </span>
            </button>`).join('');
        $('presetGrid').addEventListener('click', e => {
            const btn = e.target.closest('[data-preset]');
            if (!btn) return;
            const p = PRESETS.find(x => x.id === btn.dataset.preset);
            state = { ...DEFAULT_STATE(), ...p.state(), preset: p.id };
            writeForm();
            run();
            $('resultCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }

    function fieldOptions(sel) {
        return Object.entries(FIELDS).map(([k, f]) => `<option value="${k}"${k === sel ? ' selected' : ''}>${f.label}</option>`).join('');
    }
    function opOptions(sel) {
        return Object.entries(OPS).map(([k, o]) => `<option value="${k}"${k === sel ? ' selected' : ''}>${o.label}</option>`).join('');
    }

    function renderConditions() {
        const list = $('conditionList');
        if (!state.conds.length) {
            list.innerHTML = '<div class="hint cond-empty">조건이 없어요. "조건 추가"로 예: 수강확정 = 0</div>';
            return;
        }
        list.innerHTML = state.conds.map((c, i) => {
            const noValue = OPS[c.op] && OPS[c.op].noValue;
            const unit = FIELDS[c.field] ? FIELDS[c.field].unit : '';
            return `<div class="cond-row" data-i="${i}">
                <select class="form-select" data-k="field" aria-label="항목">${fieldOptions(c.field)}</select>
                <select class="form-select cond-op" data-k="op" aria-label="비교">${opOptions(c.op)}</select>
                <div class="cond-value">
                    <input type="number" step="any" class="form-input" data-k="value" value="${esc(c.value)}"
                           placeholder="값" aria-label="값" ${noValue ? 'disabled' : ''}>
                    <span class="cond-unit">${esc(unit)}</span>
                </div>
                <button type="button" class="btn btn-icon" data-remove="${i}" aria-label="조건 삭제"><i class="fas fa-xmark"></i></button>
            </div>`;
        }).join('');
    }

    function readForm() {
        state.year = $('yearSelect').value;
        state.from = $('dateFrom').value;
        state.to = $('dateTo').value;
        state.ncs = $('ncsSelect').value;
        state.kdt = $('kdtSelect').value;
        state.inst = $('instInput').value;
        state.course = $('courseInput').value;
    }

    function writeForm() {
        $('yearSelect').value = state.year;
        $('dateFrom').value = state.from;
        $('dateTo').value = state.to;
        $('ncsSelect').value = state.ncs;
        $('kdtSelect').value = state.kdt;
        $('instInput').value = state.inst;
        $('courseInput').value = state.course;
        setSeg('startedSeg', state.started);
        setSeg('viewSeg', state.view);
        renderConditions();
    }

    function setSeg(id, value) {
        for (const b of $(id).querySelectorAll('button')) {
            const on = b.dataset.value === value;
            b.classList.toggle('active', on);
            b.setAttribute('aria-checked', on ? 'true' : 'false');
        }
    }

    function describe(s) {
        const parts = [];
        if (s.year) parts.push(`${s.year}년 개강`);
        if (s.from || s.to) parts.push(`개강일 ${s.from || '처음'} ~ ${s.to || '끝'}`);
        if (s.started === 'started') parts.push('개강일 지남');
        if (s.started === 'upcoming') parts.push('개강 예정');
        if (s.ncs) parts.push(`NCS ${s.ncs}`);
        if (s.kdt) parts.push(`KDT ${s.kdt === '__none' ? '구분 없음' : s.kdt}`);
        if (s.inst.trim()) parts.push(`기관명에 "${s.inst.trim()}"`);
        if (s.course.trim()) parts.push(`과정명에 "${s.course.trim()}"`);
        for (const c of s.conds) {
            if (!FIELDS[c.field] || !OPS[c.op]) continue;
            if (OPS[c.op].noValue) parts.push(`${FIELDS[c.field].label} ${OPS[c.op].label}`);
            else if (c.value !== '') parts.push(`${FIELDS[c.field].label} ${OPS[c.op].label} ${c.value}${FIELDS[c.field].unit}`);
        }
        return parts.length ? parts.join(' · ') : '전체 회차';
    }

    function run({ pushUrl = true } = {}) {
        readForm();
        const matched = applyFilters(rows, state);
        const view = VIEWS[state.view];
        const items = sortItems(view.build(matched), state.sort);
        lastResult = { view: state.view, items };

        const preset = PRESETS.find(p => p.id === state.preset);
        $('resultTitle').innerHTML = `<i class="fas fa-table"></i> ${esc(preset ? preset.title : '조회 결과')}`;
        $('resultDesc').innerHTML = `${preset ? esc(preset.desc) + '<br>' : ''}<span class="cond-summary">조건: ${esc(describe(state))}</span>`;

        renderSummary(matched);
        shown = 0;
        renderTable(true);
        if (pushUrl) writeUrl();
    }

    function renderSummary(matched) {
        const courses = new Set(matched.map(r => r.groupKey)).size;
        const insts = new Set(matched.map(r => r.inst)).size;
        const startedRows = matched.filter(r => r.started);
        const unopened = startedRows.filter(r => r.unopened).length;
        const recruit = avg(matched.map(r => r.recruitRate));
        const cards = [
            { v: fmtInt(matched.length), l: '회차', tone: '' },
            { v: fmtInt(courses), l: '과정', tone: 'purple' },
            { v: fmtInt(insts), l: '기관', tone: 'cyan' },
            { v: fmtInt(unopened), l: `미개설 회차${startedRows.length ? ` (${(unopened / startedRows.length * 100).toFixed(1)}%)` : ''}`, tone: 'danger' },
            { v: fmtPct(recruit), l: '평균 모집률', tone: 'success' },
        ];
        $('summary').innerHTML = cards.map(c => `
            <div class="summary-card${c.tone ? ' summary-card--' + c.tone : ''}">
                <div class="summary-value">${c.v}</div>
                <div class="summary-label">${c.l}</div>
            </div>`).join('');
    }

    function renderTable(reset) {
        const view = VIEWS[lastResult.view];
        const items = lastResult.items;
        const area = $('resultArea');
        if (!items.length) {
            area.innerHTML = '<div class="empty-state"><i class="fas fa-inbox"></i><p>조건에 맞는 결과가 없어요.</p></div>';
            return;
        }
        const next = Math.min(items.length, (reset ? 0 : shown) + PAGE);
        const head = view.columns.map(c => {
            const on = state.sort.key === c.key;
            const arrow = on ? (state.sort.dir === 'asc' ? 'fa-sort-up' : 'fa-sort-down') : 'fa-sort';
            return `<th class="${c.num ? 'col-num' : ''} ${c.cls || ''}" data-sort="${c.key}" aria-sort="${on ? (state.sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}">
                <button type="button">${c.label} <i class="fas ${arrow}"></i></button></th>`;
        }).join('');
        const body = items.slice(0, next).map((r, i) => {
            const link = view.link(r);
            const attrs = link ? ` data-link="${esc(link)}" tabindex="0" class="row-link"`
                : (view.filterLink ? ` data-inst="${esc(view.filterLink(r))}" tabindex="0" class="row-link"` : '');
            return `<tr${attrs}>${view.columns.map(c => `<td class="${c.num ? 'col-num' : ''} ${c.cls || ''}">${c.fmt(r)}</td>`).join('')}</tr>`;
        }).join('');
        shown = next;
        area.innerHTML = `
            <div class="table-wrap"><table class="report-table">
                <thead><tr>${head}</tr></thead><tbody>${body}</tbody>
            </table></div>
            <div class="table-foot">
                <span>${fmtInt(items.length)}건 중 ${fmtInt(shown)}건 표시${view.filterLink ? ' · 행을 누르면 그 기관의 회차를 볼 수 있어요' : ' · 행을 누르면 과정 상세로 이동해요'}</span>
                ${shown < items.length ? '<button class="btn btn-sm" id="moreBtn" type="button">더 보기</button>' : ''}
            </div>`;
    }

    // ---------------------------------------------------------------- CSV
    function exportCsv() {
        const view = VIEWS[lastResult.view];
        if (!lastResult.items.length) { toast('내보낼 결과가 없어요'); return; }
        const cell = v => {
            if (v === null || v === undefined) return '';
            if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(1);
            return `"${String(v).replace(/"/g, '""')}"`;
        };
        const lines = [view.csv.map(c => c[0]).join(',')]
            .concat(lastResult.items.map(r => view.csv.map(c => cell(r[c[1]])).join(',')));
        const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const a = document.createElement('a');
        const preset = PRESETS.find(p => p.id === state.preset);
        a.href = URL.createObjectURL(blob);
        a.download = `${preset ? preset.title : '맞춤조회'}_${TODAY}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }

    // ---------------------------------------------------------------- URL 공유
    function writeUrl() {
        const p = new URLSearchParams();
        const s = state;
        if (s.preset) p.set('preset', s.preset);
        for (const k of ['year', 'from', 'to', 'ncs', 'inst', 'course', 'kdt']) if (s[k]) p.set(k, s[k].trim());
        if (s.started !== 'all') p.set('started', s.started);
        for (const c of s.conds) p.append('c', `${c.field}:${c.op}:${c.value}`);
        if (s.view !== 'session') p.set('view', s.view);
        p.set('sort', `${s.sort.key}:${s.sort.dir}`);
        history.replaceState(null, '', `${location.pathname}?${p.toString()}`);
    }

    function readUrl() {
        const p = new URLSearchParams(location.search);
        if (![...p.keys()].length) return false;
        const s = DEFAULT_STATE();
        s.preset = p.get('preset') || '';
        for (const k of ['year', 'from', 'to', 'ncs', 'inst', 'course', 'kdt']) s[k] = p.get(k) || '';
        s.started = ['all', 'started', 'upcoming'].includes(p.get('started')) ? p.get('started') : 'all';
        s.conds = p.getAll('c').map(x => {
            const [field, op, ...rest] = x.split(':');
            return { field, op, value: rest.join(':') };
        }).filter(c => FIELDS[c.field] && OPS[c.op]);
        s.view = VIEWS[p.get('view')] ? p.get('view') : 'session';
        const [key, dir] = (p.get('sort') || '').split(':');
        if (key) s.sort = { key, dir: dir === 'asc' ? 'asc' : 'desc' };
        state = s;
        return true;
    }

    // ---------------------------------------------------------------- 이벤트
    function bind() {
        $('runBtn').addEventListener('click', () => { state.preset = ''; run(); });
        $('resetBtn').addEventListener('click', () => { state = DEFAULT_STATE(); writeForm(); run(); });
        for (const id of ['instInput', 'courseInput']) {
            $(id).addEventListener('keydown', e => { if (e.key === 'Enter') { state.preset = ''; run(); } });
        }
        for (const id of ['yearSelect', 'ncsSelect', 'kdtSelect', 'dateFrom', 'dateTo']) {
            $(id).addEventListener('change', () => { state.preset = ''; run(); });
        }
        $('startedSeg').addEventListener('click', e => {
            const b = e.target.closest('button[data-value]');
            if (!b) return;
            state.started = b.dataset.value; state.preset = '';
            setSeg('startedSeg', state.started); run();
        });
        $('viewSeg').addEventListener('click', e => {
            const b = e.target.closest('button[data-value]');
            if (!b || b.dataset.value === state.view) return;
            state.view = b.dataset.value;
            const keys = VIEWS[state.view].columns.map(c => c.key);
            if (!keys.includes(state.sort.key)) state.sort = { key: state.view === 'session' ? 'start' : 'sessions', dir: 'desc' };
            setSeg('viewSeg', state.view); run();
        });

        $('addCondBtn').addEventListener('click', () => {
            state.conds.push({ field: 'confirmed', op: 'eq', value: '' });
            renderConditions();
            const inputs = $('conditionList').querySelectorAll('input[data-k="value"]');
            if (inputs.length) inputs[inputs.length - 1].focus();
        });
        $('conditionList').addEventListener('click', e => {
            const rm = e.target.closest('[data-remove]');
            if (!rm) return;
            state.conds.splice(Number(rm.dataset.remove), 1);
            state.preset = '';
            renderConditions(); run();
        });
        $('conditionList').addEventListener('change', e => {
            const row = e.target.closest('.cond-row');
            if (!row) return;
            const c = state.conds[Number(row.dataset.i)];
            c[e.target.dataset.k] = e.target.value;
            state.preset = '';
            if (e.target.dataset.k !== 'value') renderConditions();
            run();
        });
        $('conditionList').addEventListener('keydown', e => {
            if (e.key === 'Enter' && e.target.dataset.k === 'value') {
                const row = e.target.closest('.cond-row');
                state.conds[Number(row.dataset.i)].value = e.target.value;
                state.preset = ''; run();
            }
        });

        $('resultArea').addEventListener('click', e => {
            const th = e.target.closest('th[data-sort]');
            if (th) {
                const key = th.dataset.sort;
                state.sort = state.sort.key === key
                    ? { key, dir: state.sort.dir === 'asc' ? 'desc' : 'asc' }
                    : { key, dir: VIEWS[state.view].columns.find(c => c.key === key).num ? 'desc' : 'asc' };
                lastResult.items = sortItems(lastResult.items, state.sort);
                renderTable(true); writeUrl();
                return;
            }
            if (e.target.closest('#moreBtn')) { renderTable(false); return; }
            openRow(e.target.closest('tr.row-link'));
        });
        $('resultArea').addEventListener('keydown', e => {
            if (e.key === 'Enter') openRow(e.target.closest('tr.row-link'));
        });

        $('exportBtn').addEventListener('click', exportCsv);
        $('copyLinkBtn').addEventListener('click', async () => {
            writeUrl();
            try { await navigator.clipboard.writeText(location.href); toast('조회 링크를 복사했어요'); }
            catch { toast('복사하지 못했어요. 주소창의 링크를 복사해 주세요'); }
        });
    }

    function openRow(tr) {
        if (!tr) return;
        if (tr.dataset.link) {
            window.location.href = `detail.html?group=${encodeURIComponent(tr.dataset.link)}`;
        } else if (tr.dataset.inst) {
            // 기관 행 → 그 기관의 회차별 보기
            state.inst = tr.dataset.inst; state.view = 'session'; state.preset = '';
            state.sort = { key: 'start', dir: 'desc' };
            writeForm(); run();
        }
    }

    function fillOptions() {
        const years = [...new Set(rows.map(r => r.start.slice(0, 4)).filter(Boolean))].sort().reverse();
        $('yearSelect').innerHTML = '<option value="">전체 연도</option>' +
            years.map(y => `<option value="${y}">${y}년</option>`).join('');
        const ncs = [...new Set(rows.map(r => r.ncs).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko'));
        $('ncsSelect').innerHTML = '<option value="">전체 NCS직무</option>' +
            ncs.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join('');
    }

    // ---------------------------------------------------------------- 시작
    async function init() {
        renderPresets();
        bind();
        const fromUrl = readUrl();
        if (!fromUrl) {
            const p = PRESETS[0];
            state = { ...DEFAULT_STATE(), ...p.state(), preset: p.id };
        }
        writeForm();
        try {
            rows = parseRows(await loadTrainingRows());
        } catch (err) {
            console.error(err);
            $('resultArea').innerHTML = `<div class="error">데이터를 불러오지 못했어요: ${esc(err.message)}</div>`;
            return;
        }
        fillOptions();
        // 연도 옵션에 없는 값(예: 데이터에 아직 없는 연도)도 유지
        if (state.year && ![...$('yearSelect').options].some(o => o.value === state.year)) {
            $('yearSelect').insertAdjacentHTML('beforeend', `<option value="${esc(state.year)}">${esc(state.year)}년</option>`);
        }
        writeForm();
        run({ pushUrl: fromUrl });
        if (!rows.length) {
            $('resultArea').innerHTML = '<div class="empty-state"><i class="fas fa-database"></i><p>아직 저장된 데이터가 없어요. 수집이 끝나면 여기에 나타나요.</p></div>';
        }
    }

    // 테스트에서 쓰도록 내보내기
    window.__reports = { parseRows, applyFilters, sortItems, VIEWS, PRESETS, OPS, summarizeGroup };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
