// public/script.js

const signalBox = document.getElementById('signal-box');
const signalLevel = document.getElementById('signal-level');
const recommendation = document.getElementById('recommendation');
const latestSpread = document.getElementById('latest-spread');
const currentDate = document.getElementById('current-date');

const colorMap = {
    'red': 'signal-red',
    'orange': 'signal-orange',
    'yellow': 'signal-yellow',
    'green': 'signal-green'
};

async function fetchAndRenderSignal() {
    try {
        const response = await fetch('/api/signal');
        const data = await response.json();
        
        if (response.status !== 200) {
            // 백엔드에서 500 오류가 발생하고 error 메시지를 반환한 경우
            throw new Error(data.error || '알 수 없는 서버 오류');
        }

        // 1. 시그널 박스 업데이트 (판단된 결과 반영)
        currentDate.textContent = data.date;
        signalLevel.textContent = data.signalLevel;
        recommendation.textContent = data.recommendation;
        latestSpread.textContent = data.latestSpread;

        // 시그널 등급에 따라 배경색 변경
        signalBox.className = ''; 
        signalBox.classList.add(colorMap[data.signalColor]);

        // 2. 차트 렌더링
        renderSpreadChart(data.chartData);

    } catch (error) {
        console.error("프론트엔드 오류:", error);
        signalLevel.textContent = '데이터 로드 실패';
        recommendation.textContent = `오류 발생: ${error.message}. API 키나 통계 코드를 확인하세요.`;
        signalBox.className = 'signal-red';
    }
}

function renderSpreadChart(chartData) {
    const ctx = document.getElementById('spreadChart').getContext('2d');
    
    // 스프레드 데이터 계산 및 라벨 준비
    const labels = chartData.map(d => d.time.substring(4, 8)); // 월/일만 표시
    const spreads = chartData.map(d => parseFloat(d.spread));

    // 기존 차트 인스턴스가 있다면 파괴 (재로드 시 오류 방지)
    if (window.spreadChartInstance) {
        window.spreadChartInstance.destroy();
    }

    window.spreadChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '장단기 금리 스프레드 (10년 - 3년)',
                data: spreads,
                borderColor: 'rgba(54, 162, 235, 1)',
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                borderWidth: 2,
                pointRadius: 3,
                fill: false,
                yAxisID: 'y'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: '스프레드 (%)'
                    },
                    // 0% 선 강조
                    grid: {
                        drawBorder: true,
                        color: (context) => context.tick.value === 0 ? 'red' : 'rgba(0, 0, 0, 0.1)',
                        lineWidth: (context) => context.tick.value === 0 ? 2 : 1,
                    }
                }
            }
        }
    });
}

fetchAndRenderSignal();