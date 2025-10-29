// 전역 변수
let allTrainingData = [];
let currentChart = null;

// DOM 로드 완료 시 실행
document.addEventListener('DOMContentLoaded', function() {
    console.log('통계 페이지 로드 완료');
    
    // 구글 시트에서 데이터 로드
    loadGoogleSheetsData();
    
    // 필터 타입 변경 이벤트 리스너
    document.getElementById('filterType').addEventListener('change', handleFilterTypeChange);
    
    // 집계 기간 변경 이벤트 리스너
    document.getElementById('timeGrouping').addEventListener('change', updateDateRangeOptions);
    
    console.log('통계 페이지 초기화 완료');
});

// YYYY년 M월 포맷터
function formatYearMonth(date) {
    try {
        const y = date.getFullYear();
        const m = date.getMonth() + 1;
        return `${y}년 ${m}월`;
    } catch (e) {
        return '';
    }
}

// 기간 표시 텍스트 생성
function getPeriodDisplayText(startPeriod, endPeriod, timeGrouping) {
    if (!startPeriod || !endPeriod) {
        return '';
    }
    
    let startText, endText;
    
    switch (timeGrouping) {
        case 'monthly':
            const [startYear, startMonth] = startPeriod.split('-');
            const [endYear, endMonth] = endPeriod.split('-');
            startText = `${startYear}년 ${parseInt(startMonth)}월`;
            endText = `${endYear}년 ${parseInt(endMonth)}월`;
            break;
        case 'quarterly':
            const [qStartYear, qStartQuarter] = startPeriod.split('-Q');
            const [qEndYear, qEndQuarter] = endPeriod.split('-Q');
            startText = `${qStartYear}년 ${qStartQuarter}분기`;
            endText = `${qEndYear}년 ${qEndQuarter}분기`;
            break;
        case 'halfyearly':
            const [hStartYear, hStartHalf] = startPeriod.split('-H');
            const [hEndYear, hEndHalf] = endPeriod.split('-H');
            startText = `${hStartYear}년 ${hStartHalf}반기`;
            endText = `${hEndYear}년 ${hEndHalf}반기`;
            break;
        case 'yearly':
            startText = `${startPeriod}년`;
            endText = `${endPeriod}년`;
            break;
    }
    
    return `${startText} ~ ${endText}`;
}

// 필터 타입 변경 처리
function handleFilterTypeChange() {
    const filterType = document.getElementById('filterType').value;
    const searchFilter = document.getElementById('searchFilter');
    const ncsFilter = document.getElementById('ncsFilter');
    
    // 모든 필터 숨기기
    searchFilter.style.display = 'none';
    ncsFilter.style.display = 'none';
    
    // 선택된 필터 타입에 따라 표시
    if (filterType === 'search') {
        searchFilter.style.display = 'block';
    } else if (filterType === 'ncs') {
        ncsFilter.style.display = 'block';
        updateNCSJobOptions();
    }
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
            allTrainingData = rows.map((row, index) => ({
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
            
            console.log('구글 시트 데이터 로드 완료:', allTrainingData.length, '개 항목');
            
            // 날짜 범위 옵션 업데이트
            updateDateRangeOptions();
            
            // 로딩 상태 숨기기
            document.getElementById('loadingState').style.display = 'none';
            
        } else {
            console.log('시트4에 데이터가 없습니다.');
            document.getElementById('loadingState').innerHTML = '<div class="loading">구글 시트4에 데이터가 없습니다.</div>';
        }
        
    } catch (error) {
        console.error('구글 시트 데이터 로드 오류:', error);
        document.getElementById('loadingState').innerHTML = `<div class="loading">데이터 로드 오류: ${error.message}</div>`;
    }
}

// NCS직무 옵션 업데이트
function updateNCSJobOptions() {
    const select = document.getElementById('ncsJobSelect');
    if (!select) return;
    
    const ncsJobs = [...new Set(allTrainingData.map(item => item.ncsJob).filter(job => job.trim() !== ''))];
    
    select.innerHTML = '<option value="">NCS직무를 선택하세요</option>' +
        ncsJobs.map(job => `<option value="${job}">${job}</option>`).join('');
}

// 날짜 범위 옵션 업데이트
function updateDateRangeOptions() {
    if (allTrainingData.length === 0) return;
    
    const timeGrouping = document.getElementById('timeGrouping').value;
    const startSelect = document.getElementById('startPeriod');
    const endSelect = document.getElementById('endPeriod');
    
    if (!startSelect || !endSelect) return;
    
    // 유효한 시작일이 있는 데이터만 필터링
    const validData = allTrainingData.filter(item => 
        item.startDate && item.startDate.trim() !== '' && 
        !isNaN(new Date(item.startDate).getTime())
    );
    
    if (validData.length === 0) {
        startSelect.innerHTML = '<option value="">데이터가 없습니다</option>';
        endSelect.innerHTML = '<option value="">데이터가 없습니다</option>';
        return;
    }
    
    // 날짜별로 그룹화하여 옵션 생성
    const periods = new Set();
    
    validData.forEach(item => {
        const startDate = new Date(item.startDate);
        let periodKey;
        
        switch (timeGrouping) {
            case 'monthly':
                periodKey = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, '0')}`;
                break;
            case 'quarterly':
                const quarter = Math.floor(startDate.getMonth() / 3) + 1;
                periodKey = `${startDate.getFullYear()}-Q${quarter}`;
                break;
            case 'halfyearly':
                const half = startDate.getMonth() < 6 ? 1 : 2;
                periodKey = `${startDate.getFullYear()}-H${half}`;
                break;
            case 'yearly':
                periodKey = `${startDate.getFullYear()}`;
                break;
        }
        periods.add(periodKey);
    });
    
    // 정렬된 기간 배열 생성
    const sortedPeriods = Array.from(periods).sort();
    
    // 옵션 생성
    const options = sortedPeriods.map(period => {
        let displayText;
        switch (timeGrouping) {
            case 'monthly':
                const [year, month] = period.split('-');
                displayText = `${year}년 ${parseInt(month)}월`;
                break;
            case 'quarterly':
                const [qYear, qQuarter] = period.split('-Q');
                displayText = `${qYear}년 ${qQuarter}분기`;
                break;
            case 'halfyearly':
                const [hYear, hHalf] = period.split('-H');
                displayText = `${hYear}년 ${hHalf}반기`;
                break;
            case 'yearly':
                displayText = `${period}년`;
                break;
        }
        return `<option value="${period}">${displayText}</option>`;
    }).join('');
    
    startSelect.innerHTML = '<option value="">시작 시점 선택</option>' + options;
    endSelect.innerHTML = '<option value="">종료 시점 선택</option>' + options;
    
    // 기본값 설정 (전체 범위)
    if (sortedPeriods.length > 0) {
        startSelect.value = sortedPeriods[0];
        endSelect.value = sortedPeriods[sortedPeriods.length - 1];
    }
}

// 통계 생성
function generateStatistics() {
    console.log('통계 생성 시작');
    
    // 설정값 가져오기
    const timeGrouping = document.getElementById('timeGrouping').value;
    const metricType = document.getElementById('metricType').value;
    const filterType = document.getElementById('filterType').value;
    
    // 필터링된 데이터 가져오기
    let filteredData = getFilteredData();
    
    if (filteredData.length === 0) {
        alert('선택한 조건에 맞는 데이터가 없습니다.');
        return;
    }
    
    // 선택된 날짜 범위 텍스트 생성
    const startPeriod = document.getElementById('startPeriod').value;
    const endPeriod = document.getElementById('endPeriod').value;
    const periodText = getPeriodDisplayText(startPeriod, endPeriod, timeGrouping);
    
    // 시간별 그룹화
    const groupedData = groupDataByTime(filteredData, timeGrouping);
    
    // 차트 생성
    createStatisticsChart(groupedData, timeGrouping, metricType, periodText);
    
    // 통계 요약 생성
    createStatisticsSummary(filteredData, groupedData, metricType);
    
    // 차트 컨테이너 표시
    document.getElementById('chartContainer').style.display = 'block';
    document.getElementById('exportStatsBtn').style.display = 'inline-flex';
}

// 필터링된 데이터 가져오기
function getFilteredData() {
    const filterType = document.getElementById('filterType').value;
    let filteredData = [...allTrainingData];
    
    if (filterType === 'search') {
        const keyword = document.getElementById('searchKeyword').value.trim();
        if (keyword) {
            filteredData = filteredData.filter(item => 
                item.courseName.toLowerCase().includes(keyword.toLowerCase()) ||
                item.institution.toLowerCase().includes(keyword.toLowerCase())
            );
        }
    } else if (filterType === 'ncs') {
        const ncsJob = document.getElementById('ncsJobSelect').value;
        if (ncsJob) {
            filteredData = filteredData.filter(item => item.ncsJob === ncsJob);
        }
    }
    
    // 유효한 개강일이 있는 데이터만 필터링
    filteredData = filteredData.filter(item => 
        item.startDate && item.startDate.trim() !== '' && 
        !isNaN(new Date(item.startDate).getTime())
    );
    
    // 날짜 범위 필터링
    filteredData = applyDateRangeFilter(filteredData);
    
    return filteredData;
}

// 날짜 범위 필터 적용
function applyDateRangeFilter(data) {
    const startPeriod = document.getElementById('startPeriod').value;
    const endPeriod = document.getElementById('endPeriod').value;
    const timeGrouping = document.getElementById('timeGrouping').value;
    
    if (!startPeriod || !endPeriod) {
        return data;
    }
    
    return data.filter(item => {
        const startDate = new Date(item.startDate);
        let periodKey;
        
        switch (timeGrouping) {
            case 'monthly':
                periodKey = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, '0')}`;
                break;
            case 'quarterly':
                const quarter = Math.floor(startDate.getMonth() / 3) + 1;
                periodKey = `${startDate.getFullYear()}-Q${quarter}`;
                break;
            case 'halfyearly':
                const half = startDate.getMonth() < 6 ? 1 : 2;
                periodKey = `${startDate.getFullYear()}-H${half}`;
                break;
            case 'yearly':
                periodKey = `${startDate.getFullYear()}`;
                break;
        }
        
        return periodKey >= startPeriod && periodKey <= endPeriod;
    });
}

// 시간별 데이터 그룹화
function groupDataByTime(data, timeGrouping) {
    const groups = {};
    
    data.forEach(item => {
        const startDate = new Date(item.startDate);
        let timeKey;
        
        switch (timeGrouping) {
            case 'monthly':
                timeKey = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, '0')}`;
                break;
            case 'quarterly':
                const quarter = Math.floor(startDate.getMonth() / 3) + 1;
                timeKey = `${startDate.getFullYear()}-Q${quarter}`;
                break;
            case 'halfyearly':
                const half = startDate.getMonth() < 6 ? 1 : 2;
                timeKey = `${startDate.getFullYear()}-H${half}`;
                break;
            case 'yearly':
                timeKey = `${startDate.getFullYear()}`;
                break;
        }
        
        if (!groups[timeKey]) {
            groups[timeKey] = {
                timeKey: timeKey,
                courses: [],
                totalCapacity: 0,
                totalConfirmed: 0,
                totalRecruitmentRate: 0,
                totalCompletionRate: 0,
                totalEmploymentRate: 0,
                totalSatisfaction: 0,
                count: 0
            };
        }
        
        groups[timeKey].courses.push(item);
        groups[timeKey].totalCapacity += parseInt(item.recruitmentCapacity) || 0;
        groups[timeKey].totalConfirmed += parseInt(item.confirmedStudents) || 0;
        groups[timeKey].totalRecruitmentRate += parseFloat(item.recruitmentRate) || 0;
        groups[timeKey].totalCompletionRate += parseFloat(item.completionRate) || 0;
        groups[timeKey].totalEmploymentRate += parseFloat(item.employmentRate) || 0;
        groups[timeKey].totalSatisfaction += parseFloat(item.satisfaction) || 0;
        groups[timeKey].count++;
    });
    
    // 평균 계산
    Object.values(groups).forEach(group => {
        group.avgRecruitmentRate = group.count > 0 ? group.totalRecruitmentRate / group.count : 0;
        group.avgCompletionRate = group.count > 0 ? group.totalCompletionRate / group.count : 0;
        group.avgEmploymentRate = group.count > 0 ? group.totalEmploymentRate / group.count : 0;
        group.avgSatisfaction = group.count > 0 ? group.totalSatisfaction / group.count : 0;
    });
    
    return groups;
}

// 통계 차트 생성
function createStatisticsChart(groupedData, timeGrouping, metricType, periodText) {
    const ctx = document.getElementById('statisticsChart').getContext('2d');
    
    // 기존 차트 제거
    if (currentChart) {
        currentChart.destroy();
    }
    
    // 데이터 준비
    const labels = Object.keys(groupedData).sort();
    const data = labels.map(label => {
        const group = groupedData[label];
        switch (metricType) {
            case 'recruitmentRate':
                return group.avgRecruitmentRate;
            case 'employmentRate':
                return group.avgEmploymentRate;
            case 'completionRate':
                return group.avgCompletionRate;
            case 'satisfaction':
                return group.avgSatisfaction;
            case 'totalCapacity':
                return group.totalCapacity;
            case 'totalConfirmed':
                return group.totalConfirmed;
            default:
                return 0;
        }
    });
    
    // 차트 제목 설정
    const metricNames = {
        'recruitmentRate': '모집률',
        'employmentRate': '취업률',
        'completionRate': '수료율',
        'satisfaction': '만족도',
        'totalCapacity': '총 모집정원',
        'totalConfirmed': '수강확정 인원'
    };
    
    const timeNames = {
        'monthly': '월별',
        'quarterly': '분기별',
        'halfyearly': '반기별',
        'yearly': '연도별'
    };
    
    document.getElementById('chartTitle').textContent = 
        `${timeNames[timeGrouping]} ${metricNames[metricType]} 통계 (${periodText})`;
    
    // 차트 생성
    currentChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: metricNames[metricType],
                data: data,
                borderColor: 'rgb(59, 130, 246)',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.4,
                fill: true,
                pointBackgroundColor: 'rgb(59, 130, 246)',
                pointBorderColor: 'rgb(59, 130, 246)',
                pointRadius: 6,
                pointHoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 20,
                        font: {
                            size: 12,
                            weight: '500'
                        }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: 'white',
                    bodyColor: 'white',
                    borderColor: 'rgba(255, 255, 255, 0.2)',
                    borderWidth: 1,
                    cornerRadius: 8,
                    displayColors: true,
                    callbacks: {
                        afterBody: function(context) {
                            const dataIndex = context[0].dataIndex;
                            const label = labels[dataIndex];
                            const group = groupedData[label];
                            return [
                                `과정 수: ${group.count}개`,
                                `총 모집정원: ${group.totalCapacity}명`,
                                `총 수강확정: ${group.totalConfirmed}명`
                            ];
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: metricNames[metricType],
                        font: {
                            size: 14,
                            weight: 'bold'
                        },
                        color: '#6b7280'
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.1)'
                    },
                    ticks: {
                        color: '#6b7280',
                        font: {
                            size: 12
                        }
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: '기간',
                        font: {
                            size: 14,
                            weight: 'bold'
                        },
                        color: '#6b7280'
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.1)'
                    },
                    ticks: {
                        color: '#6b7280',
                        font: {
                            size: 12
                        }
                    }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });
}

// 통계 요약 생성
function createStatisticsSummary(filteredData, groupedData, metricType) {
    const summaryContainer = document.getElementById('statsSummary');
    
    // 전체 통계 계산
    const totalCourses = filteredData.length;
    const totalCapacity = filteredData.reduce((sum, item) => sum + (parseInt(item.recruitmentCapacity) || 0), 0);
    const totalConfirmed = filteredData.reduce((sum, item) => sum + (parseInt(item.confirmedStudents) || 0), 0);
    const avgRecruitmentRate = filteredData.reduce((sum, item) => sum + (parseFloat(item.recruitmentRate) || 0), 0) / totalCourses;
    const avgCompletionRate = filteredData.reduce((sum, item) => sum + (parseFloat(item.completionRate) || 0), 0) / totalCourses;
    const avgEmploymentRate = filteredData.reduce((sum, item) => sum + (parseFloat(item.employmentRate) || 0), 0) / totalCourses;
    const avgSatisfaction = filteredData.reduce((sum, item) => sum + (parseFloat(item.satisfaction) || 0), 0) / totalCourses;
    
    // 최고/최저값 계산
    const groups = Object.values(groupedData);
    const values = groups.map(group => {
        switch (metricType) {
            case 'recruitmentRate':
                return group.avgRecruitmentRate;
            case 'employmentRate':
                return group.avgEmploymentRate;
            case 'completionRate':
                return group.avgCompletionRate;
            case 'satisfaction':
                return group.avgSatisfaction;
            case 'totalCapacity':
                return group.totalCapacity;
            case 'totalConfirmed':
                return group.totalConfirmed;
            default:
                return 0;
        }
    });
    
    const maxValue = Math.max(...values);
    const minValue = Math.min(...values);
    const avgValue = values.reduce((sum, val) => sum + val, 0) / values.length;
    
    summaryContainer.innerHTML = `
        <div class="summary-card">
            <div class="summary-value">${totalCourses}</div>
            <div class="summary-label">총 과정 수</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">${totalCapacity.toLocaleString()}</div>
            <div class="summary-label">총 모집정원</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">${totalConfirmed.toLocaleString()}</div>
            <div class="summary-label">총 수강확정</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">${avgRecruitmentRate.toFixed(1)}%</div>
            <div class="summary-label">평균 모집률</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">${avgCompletionRate.toFixed(1)}%</div>
            <div class="summary-label">평균 수료율</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">${avgEmploymentRate.toFixed(1)}%</div>
            <div class="summary-label">평균 취업률</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">${avgSatisfaction.toFixed(1)}</div>
            <div class="summary-label">평균 만족도</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">${maxValue.toFixed(1)}</div>
            <div class="summary-label">최고값</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">${minValue.toFixed(1)}</div>
            <div class="summary-label">최저값</div>
        </div>
        <div class="summary-card">
            <div class="summary-value">${avgValue.toFixed(1)}</div>
            <div class="summary-label">기간별 평균</div>
        </div>
    `;
}

// 통계 내보내기
function exportStatistics() {
    if (!currentChart) {
        alert('내보낼 통계가 없습니다.');
        return;
    }
    
    try {
        // 차트를 이미지로 변환하여 다운로드
        const canvas = document.getElementById('statisticsChart');
        const link = document.createElement('a');
        link.download = `훈련과정_통계_${new Date().toISOString().split('T')[0]}.png`;
        link.href = canvas.toDataURL();
        link.click();
        
        alert('통계 차트가 다운로드되었습니다.');
    } catch (error) {
        console.error('통계 내보내기 오류:', error);
        alert('통계 내보내기 중 오류가 발생했습니다.');
    }
}

// 새로고침
function refreshData() {
    console.log('통계 데이터 새로고침 중...');
    
    // 로딩 상태 표시
    document.getElementById('loadingState').style.display = 'block';
    document.getElementById('chartContainer').style.display = 'none';
    document.getElementById('exportStatsBtn').style.display = 'none';
    
    // 구글 시트에서 데이터 로드
    loadGoogleSheetsData();
}
