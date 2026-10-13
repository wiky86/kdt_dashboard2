// Supabase 접속 정보 (Supabase 대시보드 > Project Settings > API)
// anon 키는 브라우저에 공개되어도 되는 키입니다. 테이블은 읽기 전용(RLS)으로 막혀 있어요.
// service_role 키는 절대 여기에 넣지 마세요.
window.APP_CONFIG = {
    SUPABASE_URL: 'https://YOUR-PROJECT-REF.supabase.co',
    SUPABASE_ANON_KEY: 'YOUR-SUPABASE-ANON-KEY'
};
