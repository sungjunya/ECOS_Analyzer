const axios = require('axios');

function getTodayYYYYMM() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`;
}
const today = getTodayYYYYMM();

const API_CONFIG = {
  KEY: process.env.ECOS_API_KEY,
  BASE_URL: 'https://ecos.bok.or.kr/api/StatisticSearch',
  LANG: 'kr',
  TYPE: 'json',
  P_START: 1,
  P_END: 1000,  // 수정: 더 많은 데이터 로드
  CYCLE: 'M',
  START_DATE: '201001',  // 수정: 2010년부터 (연속성 확보)
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

async function fetchIndicatorData(statCode, itemCode = '') {
  const item = itemCode ? `/${itemCode}` : '';
  const url = `${API_CONFIG.BASE_URL}/${API_CONFIG.KEY}/${API_CONFIG.TYPE}/${API_CONFIG.LANG}/${API_CONFIG.P_START}/${API_CONFIG.P_END}/${statCode}/${API_CONFIG.CYCLE}/${API_CONFIG.START_DATE}/${API_CONFIG.END_DATE}${item}`;
  console.log(`[API] ${statCode}${item}`);

  try {
    const { data } = await axios.get(url, { timeout: 10000 });
    if (data.RESULT && data.RESULT.CODE !== 'INFO-000') {
      console.error(`[RESULT 에러] ${statCode}: ${data.RESULT.MESSAGE}`);
      return [];
    }

    const rows = data?.StatisticSearch?.row || [];
    if (rows.length === 0) {
      console.warn(`[빈 데이터] ${statCode}`);
      return [];
    }

    const parsed = rows
      .map(r => ({ time: r.TIME, value: parseFloat(r.DATA_VALUE) }))
      .filter(d => !isNaN(d.value))
      .sort((a, b) => a.time.localeCompare(b.time));

    console.log(`[성공] ${statCode} → ${parsed.length}건`);
    return parsed;
  } catch (e) {
    console.error(`[실패] ${statCode}:`, e.message);
    return [];
  }
}

function calculateYoY(data) {
  if (data.length < 13) return [];

  const timeToValue = new Map(data.map(d => [d.time, d.value]));
  const yoy = [];
  const sortedTimes = Array.from(timeToValue.keys()).sort();

  sortedTimes.forEach(time => {
    const year = parseInt(time.slice(0, 4));
    const month = time.slice(4).padStart(2, '0');
    const prevTime = `${year - 1}${month}`;

    if (timeToValue.has(prevTime)) {
      const value = timeToValue.get(time);
      const prevValue = timeToValue.get(prevTime);
      if (prevValue !== 0) {
        const rate = ((value - prevValue) / prevValue) * 100;
        yoy.push({ time, value: +rate.toFixed(2) });
      }
    }
  });

  return yoy;
}

function calculateSpread(data3Y, data10Y) {
  const map = new Map(data3Y.map(d => [d.time, d.value]));
  return data10Y
    .filter(d => map.has(d.time))
    .map(d => ({ time: d.time, value: +(d.value - map.get(d.time)).toFixed(2) }))
    .sort((a, b) => a.time.localeCompare(b.time));
}

function sliceLastYears(data, years) {
  if (!data.length) return [];
  const cutoffYear = parseInt(today.slice(0, 4)) - years;
  const cutoff = `${cutoffYear}${today.slice(4)}`;
  return data.filter(d => d.time >= cutoff);
}

function getSignal(indicator, value) {
  const v = parseFloat(value);
  let level, rec, color;

  switch (indicator) {
    case 'spread':
      if (v > 1.0) { level = '매우 강한 상승장'; rec = '주식 매수 유리'; color = 'green'; }
      else if (v > 0.5) { level = '상승장 신호'; rec = '점진적 매수'; color = 'yellow'; }
      else if (v > 0) { level = '약한 상승'; rec = '관망'; color = 'orange'; }
      else { level = '하락한장 경고'; rec = '방어적 포트폴리오'; color = 'red'; }
      break;
    case 'm2':
      if (v > 5) { level = '강세'; rec = '유동성 증가'; color = 'green'; }
      else if (v > 0) { level = '중립'; rec = '관망'; color = 'yellow'; }
      else { level = '약세'; rec = '유동성 둔화'; color = 'red'; }
      break;
    case 'cpi':
      if (v > 3) { level = '약세'; rec = '긴축 우려'; color = 'red'; }
      else if (v > 2) { level = '중립'; rec = '인플레 주의'; color = 'orange'; }
      else { level = '강세'; rec = '성장 유리'; color = 'green'; }
      break;
    case 'ppi':
      if (v > 3) { level = '약세'; rec = '원가 상승 우려'; color = 'red'; }
      else if (v > 2) { level = '중립'; rec = '원가 주의'; color = 'orange'; }
      else { level = '강세'; rec = '원가 안정'; color = 'green'; }
      break;
  }
  return { level, rec, color };
}

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

    const latest = (arr) => arr[arr.length - 1] || { time: today, value: 'N/A' };

    const ensureLatest = (chartData, name) => {
      if (chartData.length === 0 || chartData[chartData.length - 1].time !== today) {
        return [...chartData, { time: today, value: 'N/A' }];
      }
      return chartData;
    };

    return {
      date: today,
      period: `${years}년`,
      indicators: {
        spread: {
          ...getSignal('spread', latest(sliceLastYears(spread, years)).value),
          latest: latest(sliceLastYears(spread, years)).value,
          chartData: ensureLatest(sliceLastYears(spread, years), 'spread')
        },
        m2: {
          ...getSignal('m2', latest(sliceLastYears(m2, years)).value),
          latest: latest(sliceLastYears(m2, years)).value,
          chartData: ensureLatest(sliceLastYears(m2, years), 'm2')
        },
        cpi: {
          ...getSignal('cpi', latest(sliceLastYears(cpi, years)).value),
          latest: latest(sliceLastYears(cpi, years)).value,
          chartData: ensureLatest(sliceLastYears(cpi, years), 'cpi')
        },
        ppi: {
          ...getSignal('ppi', latest(sliceLastYears(ppi, years)).value),
          latest: latest(sliceLastYears(ppi, years)).value,
          chartData: ensureLatest(sliceLastYears(ppi, years), 'ppi')
        }
      }
    };
  } catch (e) {
    console.error("전체 실패:", e.message);
    return { date: today, period: `${years}년`, indicators: {} };
  }
}

module.exports = { getInvestmentSignal };