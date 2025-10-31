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
  START_DATE: '201501',
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
  if (avg < 0) return `금리차가 음수(${avg.toFixed(2)}%)예요. 장기 금리가 단기보다 낮다는 뜻으로, 경기가 약할 수 있어요. 현재 ${slopeWord}입니다.`;
  if (avg < 0.5) return `금리차가 ${avg.toFixed(2)}%로 작아요. 회복 단계일 가능성이 있습니다. (${slopeWord})`;
  if (avg < 1) return `금리차가 ${avg.toFixed(2)}%로 보통이에요. 안정 성장 중일 수 있습니다. (${slopeWord})`;
  return `금리차가 ${avg.toFixed(2)}%로 높아요. 경기 확장기에 있을 가능성이 큽니다. (${slopeWord})`;
}
function explainM2(avg, slopeWord) {
  if (avg < 0) return `M2 증가율이 ${avg.toFixed(2)}%로 낮아요. 시중에 돈이 잘 돌지 않습니다. (${slopeWord})`;
  if (avg < 2) return `M2가 ${avg.toFixed(2)}% 증가했습니다. 유동성이 약합니다. (${slopeWord})`;
  if (avg < 4) return `M2가 ${avg.toFixed(2)}% 증가했습니다. 안정적이에요. (${slopeWord})`;
  return `M2가 ${avg.toFixed(2)}%로 많이 증가했습니다. 돈이 풍부합니다. (${slopeWord})`;
}
function explainCPI(avg, slopeWord) {
  if (avg < 1) return `CPI ${avg.toFixed(2)}%. 물가 안정 (${slopeWord})`;
  if (avg < 3) return `CPI ${avg.toFixed(2)}%. 적정한 수준 (${slopeWord})`;
  if (avg < 4) return `CPI ${avg.toFixed(2)}%. 다소 높은 물가 (${slopeWord})`;
  return `CPI ${avg.toFixed(2)}%. 높은 인플레이션 (${slopeWord})`;
}
function explainPPI(avg, slopeWord) {
  if (avg < 1) return `PPI ${avg.toFixed(2)}%. 안정 (${slopeWord})`;
  if (avg < 3) return `PPI ${avg.toFixed(2)}%. 적정 수준 (${slopeWord})`;
  return `PPI ${avg.toFixed(2)}%. 생산비 상승 (${slopeWord})`;
}

// ---------- 통합 요약 (쉬운 버전) ----------
function summarizeEconomy(spread, m2, cpi, ppi, trendSpread, trendM2, trendCPI) {
  let msg = '';
  if (spread < 0 && m2 < 1 && cpi > 3) {
    msg = '장기 금리가 단기 금리보다 낮고, 시중에 돈이 잘 돌지 않으며 물가까지 높습니다. 기업과 가계 모두 지출을 줄이는 시기로, 경기 침체 위험이 큽니다.';
  } else if (spread < 0.5 && cpi > 3) {
    msg = '물가가 계속 오르지만 사람들의 소비와 투자는 활발하지 않습니다. 돈이 돌지 않아 체감 경기는 여전히 어렵고, 물가 안정이 필요합니다.';
  } else if (spread > 0.5 && m2 > 2 && cpi < 3 && trendM2 !== '하락세') {
    msg = '금리와 시중 자금 흐름이 모두 안정되어 있습니다. 경기가 서서히 살아나며 기업과 가계의 활동이 점차 활발해지는 시기입니다.';
  } else if (spread > 1 && cpi < 3 && trendSpread === '상승세') {
    msg = '금리 차가 넉넉하고 물가도 안정되어 있습니다. 경제가 확장되고 일자리와 소비가 늘어나는 건강한 성장 국면입니다.';
  } else if (trendCPI === '하락세' && trendSpread === '상승세') {
    msg = '물가 상승세가 진정되고 금리 상황이 개선되고 있습니다. 경기 전망이 점점 좋아지고 있습니다.';
  } else {
    msg = '전반적으로 경제는 안정된 흐름을 보이고 있습니다. 큰 위기나 호황 없이, 비교적 차분한 상태입니다.';
  }
  return `📊 일반 경제 요약: ${msg}`;
}


// 🚀 [새로운 기능] 신호 점수 계산 (0-100점)
function getSignalScore(key, avgValue) {
    switch (key) {
        case 'spread': // 금리 스프레드 (높을수록 호황)
            if (avgValue >= 1.0) return 100;
            if (avgValue >= 0.5) return 75;
            if (avgValue >= 0.0) return 50;
            return 0; // 역전 또는 0 근방은 위험
        case 'm2': // M2 증가율 (적절히 높을수록 좋음: 2%~4%)
            if (avgValue >= 2.0 && avgValue <= 4.0) return 100;
            if (avgValue > 4.0) return 75; // 유동성 과잉 우려
            if (avgValue >= 0.0) return 50;
            return 0; // 유동성 부족
        case 'cpi': // CPI 증가율 (적절히 낮을수록 좋음: 1%~3%)
            if (avgValue >= 1.0 && avgValue <= 3.0) return 100;
            if (avgValue > 4.0 || avgValue < 0.0) return 0; // 고인플레이션 또는 디플레이션
            return 50;
        default:
            return 50; 
    }
}

// 🚀 [새로운 기능] 복합 점수 계산
function calculateCompositeScore(scores) {
    // 종합 점수 = (금리 신호 * 0.5) + (M2 신호 * 0.3) + (CPI 신호 * 0.2)
    const score = (scores.spread * 0.5) + (scores.m2 * 0.3) + (scores.cpi * 0.2);
    return Math.round(score);
}

// 🚀 [새로운 기능] 4단계 레벨 분류 및 추천
function classifyAndRecommend(avgSpread, avgM2, avgCPI, trendM2, compositeScore) {
    let result = { 
        level: "중립", 
        color: "gray", 
        description: "현재 경제는 뚜렷한 신호 없이 중립적인 흐름을 보이고 있습니다.", 
        recommendation: `종합 점수: ${compositeScore}점. 투자 방향성 판단을 보류하고 추가 지표를 확인하십시오.` 
    };

    // 'M2 증가율 둔화'를 '하락세' 추세 또는 M2 평균 2.0% 미만으로 해석
    const isM2Slowdown = trendM2 === '하락세' || avgM2 < 2.0; 
    // 'M2 증가율 견고'를 M2 평균 2.0% 이상으로 해석
    const isM2Robust = avgM2 >= 2.0; 
    // 'M2/CPI 모두 안정적'을 M2 2% 이상, CPI 3% 이하로 해석
    const isM2AndCPIStable = avgM2 >= 2.0 && avgCPI <= 3.0; 

    // 1. 🚨 최대 위험 (Red)
    if (avgSpread <= 0 && isM2Slowdown) {
        result.level = "최대 위험";
        result.color = "red";
        result.description = "경기 침체 및 유동성 수축 동시 발생.";
        result.recommendation = "즉시 위험 자산 비중을 70% 이상 축소하고 채권/현금으로 전환하십시오.";
        return result;
    }

    // 2. ✅ 최적 확장 (Green)
    if (avgSpread >= 1.0 && isM2AndCPIStable) {
        result.level = "최적 확장";
        result.color = "green";
        result.description = "이상적인 투자 환경.";
        result.recommendation = "공격적인 주식 매수 및 장기 투자 비중 확대를 추천합니다.";
        return result;
    }

    // 3. ⚠️ 긴축 경계 (Orange)
    if (avgSpread > 0 && avgCPI > 4.0) {
        result.level = "긴축 경계";
        result.color = "orange";
        result.description = "성장하지만 물가 위험이 과도함.";
        result.recommendation = "중앙은행의 금리 인상 사이클에 대비하여 포트폴리오를 방어적으로 운용하고, 단기 고금리 자산에 투자하십시오.";
        return result;
    }

    // 4. 🟡 안정 성장 (Yellow)
    if (avgSpread >= 0.5 && isM2Robust) {
        result.level = "안정 성장";
        result.color = "yellow";
        result.description = "유동성이 뒷받침되는 경기 확장 국면.";
        result.recommendation = "주식 비중을 유지하되, 인플레이션 위험에 대비해 원자재나 실물 자산을 고려하십시오.";
        return result;
    }

    return result;
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

    // 🚀 복합 점수 및 레벨 계산
    const scores = {
        spread: getSignalScore('spread', avgSpread),
        m2: getSignalScore('m2', avgM2),
        cpi: getSignalScore('cpi', avgCPI)
    };
    const compositeScore = calculateCompositeScore(scores);
    const classifyResult = classifyAndRecommend(avgSpread, avgM2, avgCPI, trendM2, compositeScore);
    
    // 기존 통합 요약은 그대로 유지 (세부 맥락 제공용)
    const summary = summarizeEconomy(avgSpread, avgM2, avgCPI, avgPPI, trendSpread, trendM2, trendCPI);

    return {
      date: today,
      period: `${years}년`,
      // 🚀 새로운 필드
      classification: classifyResult,
      compositeScore: compositeScore,
      // 기존 필드
      summary,
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