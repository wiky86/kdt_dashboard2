// 전역 변수
let newTabData = [];

// DOM 로드 완료 시 실행
document.addEventListener('DOMContentLoaded', function() {
    console.log('페이지 로드 완료');
    
    // 구글 시트에서 데이터 로드
    loadGoogleSheetsData();
    
    console.log('초기 렌더링 완료');
});



// 새 탭 데이터 렌더링
function renderNewTabData() {
    const container = document.getElementById('searchResults');
    if (!container) return;
    
    // NCS직무 옵션 업데이트
    updateNCSJobOptions();
    
    // 초기 로딩 시에는 최신 개강일 기준 10개만 표시
    const latestCourses = getLatestCourses(10);
    renderSearchResults(latestCourses);
}

// NCS직무 옵션 업데이트
function updateNCSJobOptions() {
    const select = document.getElementById('ncsJobSelect');
    if (!select) return;
    
    const ncsJobs = [...new Set(newTabData.map(item => item.ncsJob))];
    
    select.innerHTML = '<option value="">전체 NCS직무</option>' +
        ncsJobs.map(job => `<option value="${job}">${job}</option>`).join('');
}

// 데이터 그룹화 함수
function groupTrainingData(data) {
    const groups = {};
    
    data.forEach(item => {
        const key = `${item.institution}|${item.courseName}|${item.trainingFee}`;
        
        if (!groups[key]) {
            groups[key] = {
                institution: item.institution,
                courseName: item.courseName,
                trainingFee: item.trainingFee,
                ncsJob: item.ncsJob,
                trainingHours: item.trainingHours,
                hourlyFee: item.hourlyFee,
                sessions: []
            };
        }
        
        // 세션 정보 추가
        groups[key].sessions.push({
            session: item.session || '1',
            startDate: item.startDate || '',
            confirmedStudents: item.confirmedStudents || '0',
            recruitmentCapacity: item.recruitmentCapacity || '0',
            satisfaction: item.satisfaction || '0',
            evaluators: item.evaluators || '0',
            recruitmentRate: item.recruitmentRate || '0',
            completionRate: item.completionRate || '0',
            employmentRate: item.employmentRate || '0'
        });
    });
    
    return Object.values(groups);
}

// 검색 결과 렌더링
function renderSearchResults(data) {
    const container = document.getElementById('searchResults');
    if (!container) return;
    
    if (data.length === 0) {
        container.innerHTML = '<div class="loading">검색 결과가 없습니다.</div>';
        // 내보내기 버튼 숨기기
        document.getElementById('exportExcelBtn').style.display = 'none';
        document.getElementById('exportPDFBtn').style.display = 'none';
        return;
    }
    
    // 데이터 그룹화
    const groupedData = groupTrainingData(data);
    
    // 결과 개수 표시
    const resultCount = groupedData.length;
    const totalSessions = groupedData.reduce((sum, group) => sum + group.sessions.length, 0);
    
    container.innerHTML = `
        <div style="margin-bottom: 16px; padding: 12px; background: #f0f9ff; border: 1px solid #0ea5e9; border-radius: 8px;">
            <div style="display: flex; align-items: center; gap: 8px; color: #0369a1; font-weight: 600;">
                <i class="fas fa-info-circle"></i>
                <span>검색 결과: ${resultCount}개 과정 (총 ${totalSessions}회차)</span>
            </div>
        </div>
        ${groupedData.map((group, index) => `
            <div class="task-item" style="cursor: pointer;" onclick="showTrainingDetail('${group.institution}|${group.courseName}|${group.trainingFee}')">
                <div class="task-title">${group.institution}</div>
                <div class="task-meta">
                    <strong>${group.courseName}</strong><br>
                    훈련비: ${group.trainingFee}원 | NCS직무: ${group.ncsJob} | 훈련시간: ${group.trainingHours}시간 | 시간당훈련비: ${group.hourlyFee}원<br>
                    <span style="color: #3b82f6; font-weight: 500;">총 ${group.sessions.length}회차</span>
                </div>
            </div>
        `).join('')}
    `;
    
    // 내보내기 버튼 표시
    document.getElementById('exportExcelBtn').style.display = 'inline-flex';
    document.getElementById('exportPDFBtn').style.display = 'inline-flex';
    
    // 현재 검색 결과 저장 (내보내기용)
    window.currentSearchResults = data;
}

// 검색 실행
function performSearch() {
    const institution = document.getElementById('institutionSearch').value || '';
    const course = document.getElementById('courseSearch').value || '';
    const ncsJob = document.getElementById('ncsJobSelect').value || '';
    const minHours = document.getElementById('minHours').value || '';
    const minHourlyFee = document.getElementById('minHourlyFee').value || '';
    
    // 고급 필터
    const minCompletionRate = document.getElementById('minCompletionRate').value || '';
    const minEmploymentRate = document.getElementById('minEmploymentRate').value || '';
    const minSatisfaction = document.getElementById('minSatisfaction').value || '';
    const startDateFrom = document.getElementById('startDateFrom').value || '';
    const startDateTo = document.getElementById('startDateTo').value || '';
    
    let filteredData = newTabData;
    
    // 기본 필터
    if (institution) {
        filteredData = filteredData.filter(item => 
            item.institution.toLowerCase().includes(institution.toLowerCase())
        );
    }
    
    if (course) {
        filteredData = filteredData.filter(item => 
            item.courseName.toLowerCase().includes(course.toLowerCase())
        );
    }
    
    if (ncsJob) {
        filteredData = filteredData.filter(item => item.ncsJob === ncsJob);
    }
    
    if (minHours) {
        filteredData = filteredData.filter(item => 
            parseInt(item.trainingHours) >= parseInt(minHours)
        );
    }
    
    if (minHourlyFee) {
        filteredData = filteredData.filter(item => 
            parseInt(item.hourlyFee.replace(/,/g, '')) >= parseInt(minHourlyFee)
        );
    }
    
    // 고급 필터
    if (minCompletionRate) {
        filteredData = filteredData.filter(item => 
            parseFloat(item.completionRate) >= parseFloat(minCompletionRate)
        );
    }
    
    if (minEmploymentRate) {
        filteredData = filteredData.filter(item => 
            parseFloat(item.employmentRate) >= parseFloat(minEmploymentRate)
        );
    }
    
    if (minSatisfaction) {
        filteredData = filteredData.filter(item => 
            parseFloat(item.satisfaction) >= parseFloat(minSatisfaction)
        );
    }
    
    if (startDateFrom) {
        filteredData = filteredData.filter(item => 
            new Date(item.startDate) >= new Date(startDateFrom)
        );
    }
    
    if (startDateTo) {
        filteredData = filteredData.filter(item => 
            new Date(item.startDate) <= new Date(startDateTo)
        );
    }
    
    // 그룹화된 데이터로 검색 결과 렌더링
    renderSearchResults(filteredData);
}

// 최신 개강일 기준으로 과정 정렬하여 반환
function getLatestCourses(count = 10) {
    // 개강일이 있는 데이터만 필터링하고 날짜순으로 정렬
    const validCourses = newTabData.filter(item => item.startDate && item.startDate.trim() !== '');
    
    // 개강일 기준으로 내림차순 정렬 (최신순)
    const sortedCourses = validCourses.sort((a, b) => {
        const dateA = new Date(a.startDate);
        const dateB = new Date(b.startDate);
        return dateB - dateA; // 최신 날짜가 먼저 오도록
    });
    
    return sortedCourses.slice(0, count);
}

// 검색 초기화
function clearSearch() {
    // 기본 필터 초기화
    document.getElementById('institutionSearch').value = '';
    document.getElementById('courseSearch').value = '';
    document.getElementById('ncsJobSelect').value = '';
    document.getElementById('minHours').value = '';
    document.getElementById('minHourlyFee').value = '';
    
    // 고급 필터 초기화
    document.getElementById('minCompletionRate').value = '';
    document.getElementById('minEmploymentRate').value = '';
    document.getElementById('minSatisfaction').value = '';
    document.getElementById('startDateFrom').value = '';
    document.getElementById('startDateTo').value = '';
    
    // 초기화 시에도 최신 10개만 표시
    const latestCourses = getLatestCourses(10);
    renderSearchResults(latestCourses);
}

// 훈련 과정 상세 보기
function showTrainingDetail(groupKey) {
    console.log('상세 보기:', groupKey);
    
    // 상세 페이지로 이동
    const detailUrl = `detail.html?group=${encodeURIComponent(groupKey)}`;
    window.location.href = detailUrl;
}

// 새로고침
function refreshData() {
    console.log('훈련 과정 데이터 새로고침 중...');
    
    // 로딩 표시
    document.getElementById('searchResults').innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> 훈련 과정 데이터를 불러오는 중...</div>';
    
    // 구글 시트에서 데이터 로드
    loadGoogleSheetsData();
}

// 구글 시트에서 데이터 로드
async function loadGoogleSheetsData() {
    const sheetId = '1upfeAj22FEoYAgtSckJLQJ-Tg6FWFxU1ea3IdjfhGzM';
    const apiKey = 'AIzaSyD-zp3ID1MdWeMMQoSMTzHsGcvXZVnNe4k';
    
    try {
        console.log('구글 시트에서 데이터 로드 시작');
        
        // 시트4에서 훈련 과정 데이터 로드
        const sheetRange = '시트4!A:Q';
        const url = `https://sheets.googleapis.com/v4/spreadsheets/${sheetId}/values/${sheetRange}?key=${apiKey}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.values && data.values.length > 1) {
            const headers = data.values[0];
            const rows = data.values.slice(1);
            
            // 데이터 파싱
            newTabData = rows.map((row, index) => ({
                id: index + 1,
                institution: row[0] || '',
                courseName: row[1] || '',
                trainingFee: row[2] || '',
                ncsJob: row[3] || '',
                ncsLevel: row[4] || '',
                trainingDate: row[5] || '',
                trainingHours: row[6] || '',
                hourlyFee: row[7] || '',
                session: row[8] || '',
                startDate: row[9] || '',
                recruitmentCapacity: row[10] || '',
                confirmedStudents: row[11] || '',
                satisfaction: row[12] || '',
                evaluators: row[13] || '',
                recruitmentRate: row[14] || '',
                completionRate: row[15] || '',
                employmentRate: row[16] || ''
            }));
            
            console.log('구글 시트 데이터 로드 완료:', newTabData.length, '개 항목');
            
            // UI 업데이트
            renderNewTabData();
            
        } else {
            console.log('시트4에 데이터가 없습니다.');
            document.getElementById('searchResults').innerHTML = '<div class="loading">구글 시트4에 데이터가 없습니다.</div>';
        }
        
    } catch (error) {
        console.error('구글 시트 데이터 로드 오류:', error);
        document.getElementById('searchResults').innerHTML = `<div class="loading">데이터 로드 오류: ${error.message}</div>`;
    }
}

// Excel 내보내기
function exportToExcel() {
    if (!window.currentSearchResults || window.currentSearchResults.length === 0) {
        alert('내보낼 데이터가 없습니다.');
        return;
    }
    
    try {
        // CSV 형식으로 데이터 변환
        const headers = [
            '기관명', '과정명', '훈련비', 'NCS직무', 'NCS수준', '훈련일', '훈련시간', 
            '시간당훈련비', '회차', '개강일', '모집정원', '수강확정', '만족도', 
            '평가인원', '모집률', '수료율', '6개월취업률'
        ];
        
        const csvContent = [
            headers.join(','),
            ...window.currentSearchResults.map(item => [
                `"${item.institution}"`,
                `"${item.courseName}"`,
                `"${item.trainingFee}"`,
                `"${item.ncsJob}"`,
                `"${item.ncsLevel}"`,
                `"${item.trainingDate}"`,
                `"${item.trainingHours}"`,
                `"${item.hourlyFee}"`,
                `"${item.session}"`,
                `"${item.startDate}"`,
                `"${item.recruitmentCapacity}"`,
                `"${item.confirmedStudents}"`,
                `"${item.satisfaction}"`,
                `"${item.evaluators}"`,
                `"${item.recruitmentRate}"`,
                `"${item.completionRate}"`,
                `"${item.employmentRate}"`
            ].join(','))
        ].join('\n');
        
        // BOM 추가 (한글 깨짐 방지)
        const BOM = '\uFEFF';
        const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
        
        // 다운로드
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', `훈련과정_데이터_${new Date().toISOString().split('T')[0]}.csv`);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        alert('Excel 파일이 다운로드되었습니다.');
    } catch (error) {
        console.error('Excel 내보내기 오류:', error);
        alert('Excel 내보내기 중 오류가 발생했습니다.');
    }
}

// PDF 내보내기
function exportToPDF() {
    if (!window.currentSearchResults || window.currentSearchResults.length === 0) {
        alert('내보낼 데이터가 없습니다.');
        return;
    }
    
    try {
        // HTML 테이블 생성
        const headers = [
            '기관명', '과정명', '훈련비', 'NCS직무', 'NCS수준', '훈련일', '훈련시간', 
            '시간당훈련비', '회차', '개강일', '모집정원', '수강확정', '만족도', 
            '평가인원', '모집률', '수료율', '6개월취업률'
        ];
        
        let tableHTML = `
            <html>
            <head>
                <meta charset="UTF-8">
                <title>훈련과정 데이터</title>
                <style>
                    body { font-family: Arial, sans-serif; font-size: 12px; }
                    table { width: 100%; border-collapse: collapse; margin: 20px 0; }
                    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                    th { background-color: #f2f2f2; font-weight: bold; }
                    tr:nth-child(even) { background-color: #f9f9f9; }
                    .header { text-align: center; margin-bottom: 20px; }
                    .date { text-align: right; color: #666; }
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>훈련과정 데이터 보고서</h1>
                    <div class="date">생성일: ${new Date().toLocaleDateString('ko-KR')}</div>
                </div>
                <table>
                    <thead>
                        <tr>
                            ${headers.map(header => `<th>${header}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${window.currentSearchResults.map(item => `
                            <tr>
                                <td>${item.institution}</td>
                                <td>${item.courseName}</td>
                                <td>${item.trainingFee}</td>
                                <td>${item.ncsJob}</td>
                                <td>${item.ncsLevel}</td>
                                <td>${item.trainingDate}</td>
                                <td>${item.trainingHours}</td>
                                <td>${item.hourlyFee}</td>
                                <td>${item.session}</td>
                                <td>${item.startDate}</td>
                                <td>${item.recruitmentCapacity}</td>
                                <td>${item.confirmedStudents}</td>
                                <td>${item.satisfaction}</td>
                                <td>${item.evaluators}</td>
                                <td>${item.recruitmentRate}</td>
                                <td>${item.completionRate}</td>
                                <td>${item.employmentRate}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </body>
            </html>
        `;
        
        // 새 창에서 PDF 생성
        const printWindow = window.open('', '_blank');
        printWindow.document.write(tableHTML);
        printWindow.document.close();
        printWindow.focus();
        
        // 인쇄 대화상자 열기
        setTimeout(() => {
            printWindow.print();
        }, 500);
        
    } catch (error) {
        console.error('PDF 내보내기 오류:', error);
        alert('PDF 내보내기 중 오류가 발생했습니다.');
    }
}

// 고급 필터 토글
function toggleAdvancedFilters() {
    const advancedFilters = document.getElementById('advancedFilters');
    const icon = document.getElementById('advancedFilterIcon');
    
    if (advancedFilters.style.display === 'none') {
        advancedFilters.style.display = 'block';
        icon.style.transform = 'rotate(180deg)';
    } else {
        advancedFilters.style.display = 'none';
        icon.style.transform = 'rotate(0deg)';
    }
}

// 설정 표시
function showSettings() {
    alert('설정 기능은 추후 구현 예정입니다.');
}
