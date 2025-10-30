const signalBox = document.getElementById('signal-box');
const signalLevel = document.getElementById('signal-level');
const recommendation = document.getElementById('recommendation');
const latestSpread = document.getElementById('latest-spread');
const currentDate = document.getElementById('current-date');

const colorMap = {
  red: 'signal-red',
  orange: 'signal-orange',
  yellow: 'signal-yellow',
  green: 'signal-green'
};

let chartInstance = null;

async function fetchAndRenderSignal() {
  try {
    const response = await fetch('/api/signal');
    const data = await response.json();

    if (!response.ok) throw new Error(data.error || '서버 오류');

    // UI 업데이트
    currentDate.textContent = formatDate(data.date);
    signalLevel.textContent = data.signalLevel;
    recommendation.textContent = data.recommendation;
    latestSpread.textContent = data.latestSpread;

    signalBox.className = 'signal-box';
    signalBox.classList.add(colorMap[data.signalColor]);

    // 차트 렌더링
    renderChart(data.chartData);

  } catch (error) {
    console.error("오류:", error);
    signalLevel.textContent = '데이터 로드 실패';
    recommendation.textContent = `오류: ${error.message}`;
    signalBox.className = 'signal-red';
  }
}

function formatDate(yyyymmdd) {
  return `${yyyymmdd.substring(0,4)}-${yyyymmdd.substring(4,6)}-${yyyymmdd.substring(6,8)}`;
}

function renderChart(chartData) {
  const ctx = document.getElementById('spreadChart').getContext('2d');
  const labels = chartData.map(d => formatDate(d.time).substring(5)); // MM-DD
  const values = chartData.map(d => parseFloat(d.spread));

  if (chartInstance) chartInstance.destroy();

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: '스프레드 (%)',
        data: values,
        borderColor: 'rgba(54, 162, 235, 1)',
        backgroundColor: 'rgba(54, 162, 235, 0.1)',
        borderWidth: 2,
        pointRadius: 3,
        fill: true,
        tension: 0.3
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top' }
      },
      scales: {
        y: {
          beginAtZero: false,
          grid: { color: ctx => ctx.tick.value === 0 ? 'red' : 'rgba(0,0,0,0.1)' },
          ticks: { callback: v => v + '%' }
        }
      }
    }
  });
}

// 페이지 로드 시 실행
fetchAndRenderSignal();