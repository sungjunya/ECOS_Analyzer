// 📊 dataAnalyzer.js
const axios = require('axios');

// 날짜
function getTodayYYYYMM() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`;
}
const today = getTodayYYYYMM();

// 한국은행 ECOS API
const API_CONFIG = {
  KEY: process.env.ECOS_API_KEY,
  BASE_URL: 'https://ecos.bok.or.kr/api/StatisticSearch',
  LANG: 'kr',
  TYPE: 'json',
  P_START: 1,
  P_END: 1000,
  CYCLE: 'M',
  START_DATE: '201001',
  END_DATE: today,
  SPREAD_STAT_CODE: '721Y001',
  SPREAD_ITEM_CODE_3Y: '5020000',
  SPREAD_ITEM_CODE_10Y: '5050000',
  M2_STAT_CODE: '101Y004',
  M2_ITEM_CODE: 'BBHA01',
  CPI_STAT_CODE: '102Y003',
  CPI_ITEM_CODE: 'ABA2',
  PPI_STAT_CODE: '404Y014',
  PPI_ITEM_CODE: '*AA'
};

// ---------- 유틸 ----------
function avg(arr) {
  if (!arr.length) return 0;
  return arr.reduce((a, b) => a + b.value, 0) / arr.length;
}
function slope(arr) {
  if (arr.length < 2) return 0;
  let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
  for (let i = 0; i < arr.length; i++) {
    sumX += i;
    sumY += arr[i].value;
    sumXY += i * arr[i].value;
    sumXX += i * i;
  }
  return (arr.length * sumXY - sumX * sumY) / (arr.length * sumXX - sumX * sumX);
}
function slopeToWord(v) {
  if (v > 0.02) return '상승세';
  if (v < -0.02) return '하락세';
  return '큰 변화 없음';
}

// ---------- 데이터 수집 ----------
async function fetchIndicatorData(statCode, itemCode = '') {
  const item = itemCode ? `/${itemCode}` : '';
  const url = `${API_CONFIG.BASE_URL}/${API_CONFIG.KEY}/${API_CONFIG.TYPE}/${API_CONFIG.LANG}/${API_CONFIG.P_START}/${API_CONFIG.P_END}/${statCode}/${API_CONFIG.CYCLE}/${API_CONFIG.START_DATE}/${API_CONFIG.END_DATE}${item}`;
  try {
    const { data } = await axios.get(url, { timeout: 10000 });
    const rows = data?.StatisticSearch?.row || [];
    return rows.map(r => ({
      time: r.TIME,
      value: parseFloat(r.DATA_VALUE)
    })).filter(d => !isNaN(d.value));
  } catch (e) {
    console.error('API 오류:', e.message);
    return [];
  }
}

// ---------- 지표 계산 ----------
function calculateYoY(data) {
  const result = [];
  const map = new Map(data.map(d => [d.time, d.value]));
  data.forEach(d => {
    const prev = `${parseInt(d.time.slice(0, 4)) - 1}${d.time.slice(4)}`;
    if (map.has(prev)) {
      const rate = ((d.value - map.get(prev)) / map.get(prev)) * 100;
      result.push({ time: d.time, value: +rate.toFixed(2) });
    }
  });
  return result;
}
function calculateSpread(d3Y, d10Y) {
  const map = new Map(d3Y.map(d => [d.time, d.value]));
  return d10Y.filter(d => map.has(d.time))
             .map(d => ({ time: d.time, value: +(d.value - map.get(d.time)).toFixed(2) }));
}
function sliceYears(data, years) {
  const cutoff = `${parseInt(today.slice(0,4)) - years}${today.slice(4,6)}`;
  return data.filter(d => d.time >= cutoff);
}

// ---------- 설명 ----------
function explainSpread(avg, slopeWord) {
  if (avg < 0) return `금리차가 음수(${avg.toFixed(2)}pp)예요. 장기 금리가 단기보다 낮다는 뜻으로, 경기가 약할 수 있어요. 현재 ${slopeWord}입니다.`;
  if (avg < 0.5) return `금리차가 ${avg.toFixed(2)}pp로 작아요. 경기가 회복 단계일 가능성이 있습니다. (${slopeWord})`;
  if (avg < 1) return `금리차가 ${avg.toFixed(2)}pp로 보통이에요. 경제가 안정적으로 성장 중일 수 있습니다. (${slopeWord})`;
  return `금리차가 ${avg.toFixed(2)}pp로 높아요. 경기 확장기에 있을 가능성이 큽니다. (${slopeWord})`;
}
function explainM2(avg, slopeWord) {
  if (avg < 0) return `M2 증가율이 ${avg.toFixed(2)}%로 낮아요. 시중에 돈이 잘 돌지 않아 소비가 위축될 수 있습니다. (${slopeWord})`;
  if (avg < 2) return `M2가 ${avg.toFixed(2)}% 증가했습니다. 돈의 흐름이 다소 약합니다. (${slopeWord})`;
  if (avg < 4) return `M2가 ${avg.toFixed(2)}% 증가했습니다. 유동성이 안정적이에요. (${slopeWord})`;
  return `M2가 ${avg.toFixed(2)}%로 많이 증가했습니다. 시중에 돈이 풍부한 상태입니다. (${slopeWord})`;
}
function explainCPI(avg, slopeWord) {
  if (avg < 1) return `물가 상승률이 ${avg.toFixed(2)}%로 낮아요. 물가가 안정되어 있습니다. (${slopeWord})`;
  if (avg < 3) return `CPI가 ${avg.toFixed(2)}%로 적당합니다. 물가가 안정적이에요. (${slopeWord})`;
  if (avg < 4) return `CPI가 ${avg.toFixed(2)}%로 다소 높습니다. 물가 상승 압력이 있어요. (${slopeWord})`;
  return `CPI가 ${avg.toFixed(2)}%로 높아요. 생활비가 빠르게 오르고 있습니다. (${slopeWord})`;
}
function explainPPI(avg, slopeWord) {
  if (avg < 1) return `생산자물가(PPI)가 ${avg.toFixed(2)}%로 안정적입니다. (${slopeWord})`;
  if (avg < 3) return `PPI가 ${avg.toFixed(2)}%로 적정 수준이에요. (${slopeWord})`;
  return `PPI가 ${avg.toFixed(2)}%로 높습니다. 기업의 생산비가 증가하고 있을 수 있습니다. (${slopeWord})`;
}

// ---------- 분류 ----------
function classify(spread, m2, cpi) {
  if (spread < 0 && m2 < 1) return { level: "경기 둔화", color: "red", description: "금리 역전과 돈의 흐름 둔화가 동시에 나타나고 있어요." };
  if (spread < 0.5 && cpi > 3) return { level: "물가 부담", color: "orange", description: "물가는 오르는데 경기는 약한 모습이에요." };
  if (spread < 1 && m2 > 1 && cpi < 3.5) return { level: "회복기", color: "yellow", description: "경기가 점차 회복 중입니다." };
  if (spread >= 1 && cpi <= 3) return { level: "확장기", color: "green", description: "금리차와 물가 모두 안정되어 경기 확장 국면이에요." };
  return { level: "중립", color: "gray", description: "특징적인 움직임이 없는 안정된 상태예요." };
}

// ---------- 메인 ----------
async function getInvestmentSignal(period = '1y') {
  const yearsMap = { '1y': 1, '3y': 3, '5y': 5 };
  const years = yearsMap[period] || 1;

  try {
    const [d3Y, d10Y, dM2, dCPI, dPPI] = await Promise.all([
      fetchIndicatorData(API_CONFIG.SPREAD_STAT_CODE, API_CONFIG.SPREAD_ITEM_CODE_3Y),
      fetchIndicatorData(API_CONFIG.SPREAD_STAT_CODE, API_CONFIG.SPREAD_ITEM_CODE_10Y),
      fetchIndicatorData(API_CONFIG.M2_STAT_CODE, API_CONFIG.M2_ITEM_CODE),
      fetchIndicatorData(API_CONFIG.CPI_STAT_CODE, API_CONFIG.CPI_ITEM_CODE),
      fetchIndicatorData(API_CONFIG.PPI_STAT_CODE, API_CONFIG.PPI_ITEM_CODE)
    ]);

    const spread = calculateSpread(d3Y, d10Y);
    const m2 = calculateYoY(dM2);
    const cpi = calculateYoY(dCPI);
    const ppi = calculateYoY(dPPI);

    const s = sliceYears(spread, years);
    const m = sliceYears(m2, years);
    const c = sliceYears(cpi, years);
    const p = sliceYears(ppi, years);

    const avgSpread = avg(s);
    const avgM2 = avg(m);
    const avgCPI = avg(c);
    const avgPPI = avg(p);

    const trendSpread = slopeToWord(slope(s));
    const trendM2 = slopeToWord(slope(m));
    const trendCPI = slopeToWord(slope(c));
    const trendPPI = slopeToWord(slope(p));

    const classifyResult = classify(avgSpread, avgM2, avgCPI);

    return {
      date: today,
      period: `${years}년`,
      classification: classifyResult,
      indicators: {
        spread: { latest: avgSpread.toFixed(2), trend: trendSpread, description: explainSpread(avgSpread, trendSpread), color: classifyResult.color, chartData: s },
        m2: { latest: avgM2.toFixed(2), trend: trendM2, description: explainM2(avgM2, trendM2), color: classifyResult.color, chartData: m },
        cpi: { latest: avgCPI.toFixed(2), trend: trendCPI, description: explainCPI(avgCPI, trendCPI), color: classifyResult.color, chartData: c },
        ppi: { latest: avgPPI.toFixed(2), trend: trendPPI, description: explainPPI(avgPPI, trendPPI), color: classifyResult.color, chartData: p }
      }
    };
  } catch (err) {
    console.error("오류:", err.message);
    return { error: err.message };
  }
}

module.exports = { getInvestmentSignal };
