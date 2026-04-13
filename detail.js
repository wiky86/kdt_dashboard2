// 전역 변수
let trainingData = null;
let allTrainingData = [];

// DOM 로드 완료 시 실행
document.addEventListener('DOMContentLoaded', function() {
    console.log('상세 페이지 로드 완료');
    
    // URL 파라미터에서 그룹 키 가져오기
    const urlParams = new URLSearchParams(window.location.search);
    const groupKey = urlParams.get('group');
    
    if (!groupKey) {
        showError('상세 정보를 찾을 수 없습니다.');
        return;
    }
    
    console.log('그룹 키:', groupKey);
    
    // 모든 훈련 데이터 로드
    loadAllTrainingData(groupKey);
});

// 모든 훈련 데이터 로드
async function loadAllTrainingData(groupKey) {
    try {
        console.log('훈련 데이터 로드 시작');
        
        // 구글 시트에서 데이터 로드
        const sheetId = '1upfeAj22FEoYAgtSckJLQJ-Tg6FWFxU1ea3IdjfhGzM';
        const apiKey = 'AIzaSyD-zp3ID1MdWeMMQoSMTzHsGcvXZVnNe4k';
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
            
            // 그룹 키로 해당 데이터 찾기
            const [institution, courseName, trainingFee] = groupKey.split('|');
            const groupData = allTrainingData.filter(item => 
                item.institution === institution && 
                item.courseName === courseName && 
                item.trainingFee === trainingFee
            );
            
            if (groupData.length === 0) {
                showError('해당 훈련 과정을 찾을 수 없습니다.');
                return;
            }
            
            // 그룹화된 데이터 생성
            trainingData = {
                institution: groupData[0].institution,
                courseName: groupData[0].courseName,
                trainingFee: groupData[0].trainingFee,
                ncsJob: groupData[0].ncsJob,
                ncsLevel: groupData[0].ncsLevel,
                trainingDate: groupData[0].trainingDate,
                trainingHours: groupData[0].trainingHours,
                hourlyFee: groupData[0].hourlyFee,
                sessions: groupData.map(item => ({
                    session: item.session,
                    startDate: item.startDate,
                    recruitmentCapacity: item.recruitmentCapacity,
                    confirmedStudents: item.confirmedStudents,
                    satisfaction: item.satisfaction,
                    evaluators: item.evaluators,
                    recruitmentRate: item.recruitmentRate,
                    completionRate: item.completionRate,
                    employmentRate: item.employmentRate
                }))
            };
            
            console.log('그룹화된 데이터:', trainingData);
            
            // UI 렌더링
            renderDetailPage();
            
        } else {
            console.log('시트4에 데이터가 없습니다.');
            showError('구글 시트4에 데이터가 없습니다.');
        }
        
    } catch (error) {
        console.error('데이터 로드 오류:', error);
        showError(`데이터 로드 오류: ${error.message}`);
    }
}


// 상세 페이지 렌더링
function renderDetailPage() {
    if (!trainingData) return;
    
    // 기본 정보 렌더링
    renderBasicInfo();
    
    // 회차별 정보 렌더링
    renderSessionsList();
    
    // 차트 생성
    createEnrollmentChart();
}

// 기본 정보 렌더링
function renderBasicInfo() {
    const container = document.getElementById('basicInfo');
    
    container.innerHTML = `
        <div class="info-item">
            <div class="info-label">기관명</div>
            <div class="info-value">${trainingData.institution}</div>
        </div>
        <div class="info-item">
            <div class="info-label">과정명</div>
            <div class="info-value">${trainingData.courseName}</div>
        </div>
        <div class="info-item">
            <div class="info-label">훈련비</div>
            <div class="info-value">${trainingData.trainingFee}원</div>
        </div>
        <div class="info-item">
            <div class="info-label">NCS직무</div>
            <div class="info-value">${trainingData.ncsJob}</div>
        </div>
        <div class="info-item">
            <div class="info-label">NCS수준</div>
            <div class="info-value">${trainingData.ncsLevel}</div>
        </div>
        <div class="info-item">
            <div class="info-label">훈련일</div>
            <div class="info-value">${trainingData.trainingDate}일</div>
        </div>
        <div class="info-item">
            <div class="info-label">훈련시간</div>
            <div class="info-value">${trainingData.trainingHours}시간</div>
        </div>
        <div class="info-item">
            <div class="info-label">시간당훈련비</div>
            <div class="info-value">${trainingData.hourlyFee}원</div>
        </div>
    `;
}

// 회차별 정보 렌더링
function renderSessionsList() {
    const container = document.getElementById('sessionsList');
    
    if (trainingData.sessions.length === 0) {
        container.innerHTML = '<div class="loading">회차 정보가 없습니다.</div>';
        return;
    }
    
    container.innerHTML = trainingData.sessions.map(session => `
        <div class="session-item">
            <div class="session-header">
                <div class="session-number">${session.session}회차</div>
                <div class="session-date">개강일: ${session.startDate}</div>
            </div>
            <div class="session-details">
                <!-- 모집 관련 정보 -->
                <div class="session-section-title">📊 모집 현황</div>
                <div class="session-row">
                    <div class="session-label">모집정원</div>
                    <div class="session-value session-value--danger">${session.recruitmentCapacity}명</div>
                </div>
                <div class="session-row">
                    <div class="session-label">수강확정</div>
                    <div class="session-value session-value--success">${session.confirmedStudents}명</div>
                </div>
                <div class="session-row">
                    <div class="session-label">모집률</div>
                    <div class="session-value session-value--primary">${session.recruitmentRate}%</div>
                </div>
                
                <!-- 성과 관련 정보 -->
                <div class="session-section-title">📈 성과 지표</div>
                <div class="session-row">
                    <div class="session-label">수료율</div>
                    <div class="session-value session-value--cyan">${session.completionRate}%</div>
                </div>
                <div class="session-row">
                    <div class="session-label">6개월취업률</div>
                    <div class="session-value session-value--orange">${session.employmentRate}%</div>
                </div>
                <div class="session-row">
                    <div class="session-label">만족도</div>
                    <div class="session-value session-value--purple">${session.satisfaction}</div>
                </div>
                <div class="session-row">
                    <div class="session-label">평가인원</div>
                    <div class="session-value session-value--muted">${session.evaluators}명</div>
                </div>
            </div>
        </div>
    `).join('');
}

// 등록 차트 생성
function createEnrollmentChart() {
    const canvas = document.getElementById('enrollmentChart');
    if (!canvas || !trainingData) return;
    
    const ctx = canvas.getContext('2d');
    
    // 데이터 라벨 플러그인 등록
    Chart.register(ChartDataLabels);
    
    // 세션을 개강일 순으로 정렬
    const sortedSessions = [...trainingData.sessions].sort((a, b) => 
        new Date(a.startDate) - new Date(b.startDate)
    );
    
    // 통계 계산
    const totalConfirmed = sortedSessions.reduce((sum, s) => sum + parseInt(s.confirmedStudents), 0);
    const totalCapacity = sortedSessions.reduce((sum, s) => sum + parseInt(s.recruitmentCapacity), 0);
    const avgSatisfaction = (sortedSessions.reduce((sum, s) => sum + parseFloat(s.satisfaction), 0) / sortedSessions.length).toFixed(1);
    const avgCompletionRate = (sortedSessions.reduce((sum, s) => sum + parseFloat(s.completionRate), 0) / sortedSessions.length).toFixed(1);
    const avgEmploymentRate = (sortedSessions.reduce((sum, s) => sum + parseFloat(s.employmentRate), 0) / sortedSessions.length).toFixed(1);
    
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: sortedSessions.map(s => s.startDate),
            datasets: [{
                label: '수강확정인원',
                data: sortedSessions.map(s => parseInt(s.confirmedStudents)),
                borderColor: 'rgb(34, 197, 94)',
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                tension: 0.4,
                fill: true,
                pointBackgroundColor: 'rgb(34, 197, 94)',
                pointBorderColor: 'rgb(34, 197, 94)',
                pointRadius: 6,
                pointHoverRadius: 8
            }, {
                label: '모집률 (%)',
                data: sortedSessions.map(s => parseFloat(s.recruitmentRate)),
                borderColor: 'rgb(59, 130, 246)',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.4,
                fill: false,
                pointBackgroundColor: 'rgb(59, 130, 246)',
                pointBorderColor: 'rgb(59, 130, 246)',
                pointRadius: 6,
                pointHoverRadius: 8,
                yAxisID: 'y1'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: `${trainingData.institution} - ${trainingData.courseName}`,
                    font: {
                        size: 18,
                        weight: 'bold'
                    },
                    color: '#1f2937'
                },
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
                datalabels: {
                    display: true,
                    color: '#1f2937',
                    font: {
                        size: 11,
                        weight: 'bold'
                    },
                    formatter: function(value, context) {
                        if (context.datasetIndex === 0) {
                            return value + '명';
                        } else {
                            return value + '%';
                        }
                    },
                    anchor: 'end',
                    align: 'top',
                    offset: 8
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
                            const session = sortedSessions[dataIndex];
                            return [
                                `회차: ${session.session}회차`,
                                `모집률: ${session.recruitmentRate}%`,
                                `수료율: ${session.completionRate}%`,
                                `취업률: ${session.employmentRate}%`
                            ];
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    min: 0,
                    max: 150,
                    title: {
                        display: true,
                        text: '인원 수',
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
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    min: 0,
                    max: 100,
                    title: {
                        display: true,
                        text: '모집률 (%)',
                        font: {
                            size: 14,
                            weight: 'bold'
                        },
                        color: '#6b7280'
                    },
                    grid: {
                        drawOnChartArea: false,
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
                        text: '개강일',
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
    
    // 통계 요약 정보 추가
    addStatisticsSummary(totalConfirmed, totalCapacity, avgSatisfaction, avgCompletionRate, avgEmploymentRate);
}

// 통계 요약 정보 추가
function addStatisticsSummary(totalConfirmed, totalCapacity, avgSatisfaction, avgCompletionRate, avgEmploymentRate) {
    const chartContainer = document.querySelector('.chart-container');
    
    const summaryHTML = `
        <div class="stats-summary" style="margin-top: 24px;">
            <div class="summary-card summary-card--success">
                <div class="summary-value">${totalConfirmed}명</div>
                <div class="summary-label">총 수강확정인원</div>
            </div>
            <div class="summary-card summary-card--danger">
                <div class="summary-value">${totalCapacity}명</div>
                <div class="summary-label">총 모집정원</div>
            </div>
            <div class="summary-card summary-card--purple">
                <div class="summary-value">${avgSatisfaction}</div>
                <div class="summary-label">평균 만족도</div>
            </div>
            <div class="summary-card summary-card--cyan">
                <div class="summary-value">${avgCompletionRate}%</div>
                <div class="summary-label">평균 수료율</div>
            </div>
            <div class="summary-card summary-card--orange">
                <div class="summary-value">${avgEmploymentRate}%</div>
                <div class="summary-label">평균 취업률</div>
            </div>
        </div>
    `;
    
    chartContainer.insertAdjacentHTML('beforeend', summaryHTML);
}

// 오류 표시
function showError(message) {
    document.getElementById('detailContent').innerHTML = `
        <div class="card">
            <div class="error">
                <i class="fas fa-exclamation-triangle"></i>
                ${message}
            </div>
        </div>
    `;
}
