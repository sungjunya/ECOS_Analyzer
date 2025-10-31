// 📄 dataAnalyzer.js (복합 시그널 모델 최종 버전)
const axios = require('axios');

function getTodayYYYYMM() {
  const d = new Date();
  d.setDate(0); 
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`;
}
const today = getTodayYYYYMM();

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

  // 🚨 금리 통계표
  SPREAD_STAT_CODE: '721Y001',
  SPREAD_ITEM_CODE_3Y: '5020000',
  SPREAD_ITEM_CODE_10Y: '5050000',

  // 🚨 M2 통계표
  M2_STAT_CODE: '101Y004',
  M2_ITEM_CODE: 'BBHA01', 

  // 🚨 CPI/PPI 통계표
  CPI_STAT_CODE: '102Y003',
  CPI_ITEM_CODE: 'ABA2', 

  PPI_STAT_CODE: '404Y014',
  PPI_ITEM_CODE: '*AA'
};

/**
 * 📡 ECOS API에서 특정 지표 데이터 가져오기 (범용 함수)
 */
async function fetchIndicatorData(statCode, itemCode = '') {
  const item = itemCode ? `/${itemCode}` : '';
  const url = `${API_CONFIG.BASE_URL}/${API_CONFIG.KEY}/${API_CONFIG.TYPE}/${API_CONFIG.LANG}/${API_CONFIG.P_START}/${API_CONFIG.P_END}/${statCode}/${API_CONFIG.CYCLE}/${API_CONFIG.START_DATE}/${API_CONFIG.END_DATE}${item}`;
  console.log(`[API] 요청 STAT: ${statCode}, ITEM: ${itemCode}`);

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

/**
 * 📊 전년 동월 대비 증감률 (YoY) 계산
 */
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
      if (prevValue !== 0 && prevValue !== undefined) {
        const rate = ((value - prevValue) / prevValue) * 100;
        yoy.push({ time, value: +rate.toFixed(2) });
      }
    }
  });

  return yoy;
}

/**
 * 📉 장단기 금리 스프레드 계산
 */
function calculateSpread(data3Y, data10Y) {
  const map = new Map(data3Y.map(d => [d.time, d.value]));
  return data10Y
    .filter(d => map.has(d.time))
    .map(d => ({ time: d.time, value: +(d.value - map.get(d.time)).toFixed(2) }))
    .sort((a, b) => a.time.localeCompare(b.time));
}

/**
 * ✂️ 특정 기간(년)의 데이터만 슬라이싱
 */
function sliceLastYears(data, years) {
  if (!data.length) return [];
  const cutoffYear = parseInt(today.slice(0, 4)) - years;
  const cutoff = `${cutoffYear}${today.slice(4)}`;
  return data.filter(d => d.time >= cutoff);
}

/**
 * 1단계: 개별 지표를 정량화된 상태(0~1)로 변환
 * @param {string} indicator - 지표명 ('spread', 'm2', 'cpi')
 * @param {number} value - 해당 지표의 최신 값
 */
function getIndicatorStatus(indicator, value) {
    if (isNaN(value) || value === 'N/A') return 0;
    const v = parseFloat(value);
    
    switch (indicator) {
        case 'spread':
            if (v >= 0.5) return 1.0;
            if (v > 0) return 0.5;
            return 0.0;
        case 'm2':
            if (v >= 3) return 1.0;
            if (v > 0) return 0.5;
            return 0.0;
        case 'cpi':
            // CPI는 높을수록 리스크(부정적)이므로, 반대로 점수 부여
            if (v > 3) return 1.0; // 리스크(1.0)
            if (v > 2) return 0.5;
            return 0.0; // 리스크(0.0)
    }
    return 0;
}

/**
 * 2단계: 4가지 레벨로 분류하는 핵심 로직
 * @param {object} latestValues - 최신 지표 값 {spread: number, m2: number, cpi: number}
 */
function getCompositeSignal(latestValues) {
    const { spread, m2, cpi } = latestValues;

    // 🚨 B. 4가지 레벨 조건문 (핵심 분류) 🚨
    let signalLevel, recommendation, signalColor;

    // 1. 🚨 최대 위험 (Red): 경기 침체(스프레드 역전) AND 유동성 수축(M2 둔화)
    if (spread <= 0 && m2 <= 0) {
        signalLevel = '🚨 최대 위험 (Red)';
        recommendation = '경기 침체와 유동성 수축 동시 발생. 즉시 위험 자산 비중을 70% 이상 축소하고 채권/현금으로 전환하십시오.';
        signalColor = 'red';

    // 2. ⚠️ 긴축 경계 (Orange): 성장하지만 물가 위험이 과도함
    } else if (spread > 0 && cpi > 4) {
        signalLevel = '⚠️ 긴축 경계 (Orange)';
        recommendation = `성장하지만 CPI가 ${cpi}%로 과도함. 중앙은행 금리 인상 사이클에 대비하여 포트폴리오를 방어적으로 운용하십시오.`;
        signalColor = 'orange';

    // 3. 🟡 안정 성장 (Yellow): 유동성이 뒷받침되지만 아직 최적은 아님
    } else if (spread >= 0.5 && m2 > 0) {
        signalLevel = '🟡 안정 성장 (Yellow)';
        recommendation = '유동성이 뒷받침되는 경기 확장 국면. 주식 비중을 유지하되, 인플레이션 위험에 대비해 원자재나 실물 자산을 고려하십시오.';
        signalColor = 'yellow';

    // 4. ✅ 최적 확장 (Green): 강한 금리 신호와 안정적 환경
    } else if (spread >= 1.0 && cpi <= 2) {
        signalLevel = '✅ 최적 확장 (Green)';
        recommendation = '이상적인 투자 환경. 공격적인 주식 매수 및 장기 투자 비중 확대를 추천합니다.';
        signalColor = 'green';
    } else {
        // 나머지 모든 경우는 중립 또는 판단 보류
        signalLevel = '⭐ 중립/관망';
        recommendation = '지표 간 혼조세 또는 기준 미달. 시장 관망을 유지하며 다음 신호를 기다리십시오.';
        signalColor = 'orange'; 
    }
    
    // C. 정량적 종합 점수 (참고용)
    const weights = { spread: 0.5, m2: 0.3, cpi: 0.2 };
    const score = (
        (getIndicatorStatus('spread', spread) * weights.spread) +
        (getIndicatorStatus('m2', m2) * weights.m2) +
        ((1 - getIndicatorStatus('cpi', cpi)) * weights.cpi) // CPI는 리스크(1-리스크)로 변환
    );
    
    return {
        signalLevel,
        recommendation,
        signalColor,
        compositeScore: score.toFixed(2)
    };
}


/**
 * 📊 종합 투자 시그널 생성 메인 함수
 */
async function getInvestmentSignal(period = '1y') {
  const yearsMap = { '1y': 1, '3y': 3, '5y': 5 };
  const years = yearsMap[period] || 1;

  try {
    // 1. 모든 지표의 원본 데이터 병렬 호출
    const [d3Y, d10Y, dM2, dCPI, dPPI] = await Promise.all([
      fetchIndicatorData(API_CONFIG.SPREAD_STAT_CODE, API_CONFIG.SPREAD_ITEM_CODE_3Y),
      fetchIndicatorData(API_CONFIG.SPREAD_STAT_CODE, API_CONFIG.SPREAD_ITEM_CODE_10Y),
      fetchIndicatorData(API_CONFIG.M2_STAT_CODE, API_CONFIG.M2_ITEM_CODE), 
      fetchIndicatorData(API_CONFIG.CPI_STAT_CODE, API_CONFIG.CPI_ITEM_CODE),
      fetchIndicatorData(API_CONFIG.PPI_STAT_CODE, API_CONFIG.PPI_ITEM_CODE) 
    ]);

    // 2. 데이터 가공 및 지표 계산
    const spread = calculateSpread(d3Y, d10Y);
    const m2 = calculateYoY(dM2);
    const cpi = calculateYoY(dCPI);
    const ppi = calculateYoY(dPPI);

    // 3. 최신 데이터 추출 및 기간 슬라이싱
    const latest = (arr) => arr[arr.length - 1] || { time: today, value: 'N/A' };
    const sliceAndLatest = (arr) => latest(sliceLastYears(arr, years));
    
    // 4. 복합 시그널 생성에 필요한 최신 값 추출
    const latestSpread = parseFloat(sliceAndLatest(spread).value);
    const latestM2 = parseFloat(sliceAndLatest(m2).value);
    const latestCPI = parseFloat(sliceAndLatest(cpi).value);
    
    // 5. 🚨 복합 시그널 호출 및 역사적 점수 계산 🚨
    const compositeSignal = getCompositeSignal({
        spread: latestSpread,
        m2: latestM2,
        cpi: latestCPI
    });
    
    // 6. 역사적 복합 점수 계산 (차트용)
    const weights = { spread: 0.5, m2: 0.3, cpi: 0.2 };
    const historicalCompositeScore = [];
    const m2Map = new Map(m2.map(d => [d.time, d.value]));
    const cpiMap = new Map(cpi.map(d => [d.time, d.value]));
    
    for (const d of spread) {
        const m = m2Map.get(d.time);
        const c = cpiMap.get(d.time);
        
        if (m !== undefined && c !== undefined) {
            const spreadStatus = getIndicatorStatus('spread', d.value);
            const m2Status = getIndicatorStatus('m2', m);
            const cpiRisk = getIndicatorStatus('cpi', c);
            
            const score = (
                (spreadStatus * weights.spread) +
                (m2Status * weights.m2) +
                ((1 - cpiRisk) * weights.cpi)
            );
            
            historicalCompositeScore.push({ time: d.time, score: parseFloat(score.toFixed(2)) });
        }
    }
    
    // 7. 결과 객체 구성 (UI에 표시될 최종 값)
    const ensureLatest = (chartData) => {
        if (chartData.length === 0 || chartData[chartData.length - 1].time !== today) {
            return [...chartData, { time: today, value: 'N/A' }];
        }
        return chartData;
    };
    
    return {
      date: today,
      period: `${years}년`,
      compositeSignal: compositeSignal, 
      compositeChartData: sliceLastYears(historicalCompositeScore, years), // 새로운 차트 데이터
      indicators: {
        spread: {
          latest: latestSpread,
          chartData: ensureLatest(sliceLastYears(spread, years))
        },
        m2: {
          latest: latestM2,
          chartData: ensureLatest(sliceLastYears(m2, years))
        },
        cpi: {
          latest: latestCPI,
          chartData: ensureLatest(sliceLastYears(cpi, years))
        },
        ppi: {
          latest: parseFloat(sliceAndLatest(ppi).value), 
          chartData: ensureLatest(sliceLastYears(ppi, years))
        }
      }
    };
  } catch (e) {
    console.error("전체 실패:", e.message);
    return { date: today, period: `${years}년`, indicators: {}, compositeSignal: {
        signalLevel: '분석 오류', recommendation: `전체 데이터 로드 실패: ${e.message}`, signalColor: 'red', compositeScore: 'N/A'
    }, compositeChartData: []};
  }
}

module.exports = { getInvestmentSignal };