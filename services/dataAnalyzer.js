// 📄 dataAnalyzer.js (ECOS 시장금리 월별 버전)
const axios = require('axios');

// 오늘 날짜 기준으로 월 단위 종료일 생성
function getTodayYYYYMM() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}`;
}

const today = getTodayYYYYMM();

const API_CONFIG = {
  KEY: process.env.ECOS_API_KEY,
  BASE_URL: 'https://ecos.bok.or.kr/api/StatisticSearch',

  // 📊 한국은행 ECOS 코드 (시장금리 월별)
  STAT_CODE: '721Y001',        // 시장금리
  ITEM_CODE_3Y: '5020000',     // 3년 국채수익률
  ITEM_CODE_10Y: '5050000',    // 10년 국채수익률

  START_DATE: '202301',        // 2023년 1월부터
  END_DATE: today,             // 현재 월까지
  LANG: 'kr',
  TYPE: 'json',
  P_START: 1,
  P_END: 500,
  CYCLE: 'M'                   // ✅ 월별 데이터
};

/**
 * 📡 ECOS API에서 특정 항목 데이터 가져오기
 */
async function fetchRateData(itemCode) {
  const {
    KEY, BASE_URL, STAT_CODE, START_DATE, END_DATE, LANG, TYPE, P_START, P_END, CYCLE
  } = API_CONFIG;

  const url = `${BASE_URL}/${KEY}/${TYPE}/${LANG}/${P_START}/${P_END}/${STAT_CODE}/${CYCLE}/${START_DATE}/${END_DATE}/${itemCode}`;
  console.log(`[요청] ${itemCode === '5020000' ? '3년' : '10년'} 국채: ${url}`);

  try {
    const response = await axios.get(url, { timeout: 10000 });
    const result = response.data?.StatisticSearch;

    if (!result || !Array.isArray(result.row) || result.row.length === 0) {
      const msg = result?.RESULT?.MESSAGE || result?.result?.MESSAGE || 'API 응답 오류';
      throw new Error(`데이터 없음: ${msg}`);
    }

    return result.row
      .map(item => ({
        time: item.TIME,                   // YYYYMM
        value: parseFloat(item.DATA_VALUE)
      }))
      .filter(d => !isNaN(d.value));

  } catch (error) {
    if (error.response?.data?.RESULT) {
      const err = error.response.data.RESULT;
      throw new Error(`${err.CODE}: ${err.MESSAGE}`);
    }
    throw new Error(`API 요청 실패: ${error.message}`);
  }
}

/**
 * 📈 장단기 금리 스프레드 계산 및 투자 시그널 생성
 */
async function getInvestmentSignal() {
  try {
    const [data3Y, data10Y] = await Promise.all([
      fetchRateData(API_CONFIG.ITEM_CODE_3Y),
      fetchRateData(API_CONFIG.ITEM_CODE_10Y)
    ]);

    // 날짜 기준으로 매칭
    const spreadData = [];
    const map3Y = new Map(data3Y.map(d => [d.time, d.value]));

    for (const d of data10Y) {
      const val3Y = map3Y.get(d.time);
      if (val3Y !== undefined) {
        const spread = d.value - val3Y;
        spreadData.push({
          time: d.time,
          spread: spread.toFixed(2)
        });
      }
    }

    if (spreadData.length === 0) {
      throw new Error("3년/10년 데이터 매칭 실패");
    }

    const latest = spreadData[spreadData.length - 1];
    const spread = parseFloat(latest.spread);

    // 📊 시그널 로직
    let signalLevel, recommendation, signalColor;

    if (spread > 1.0) {
      signalLevel = '매우 강한 상승장';
      recommendation = '주식 매수 유리 (수익률 곡선 정상화)';
      signalColor = 'green';
    } else if (spread > 0.5) {
      signalLevel = '상승장 신호';
      recommendation = '점진적 매수 고려';
      signalColor = 'yellow';
    } else if (spread > 0) {
      signalLevel = '약한 상승';
      recommendation = '관망 또는 단기 채권';
      signalColor = 'orange';
    } else {
      signalLevel = '하락장 경고';
      recommendation = '방어적 포트폴리오 권장';
      signalColor = 'red';
    }

    // 최근 24개월만 표시
    const recentData = spreadData.slice(-24);

    return {
      date: latest.time,
      latestSpread: latest.spread,
      signalLevel,
      recommendation,
      signalColor,
      chartData: recentData
    };

  } catch (error) {
    console.error("분석 실패:", error.message);
    return {
      date: new Date().toISOString().split('T')[0].replace(/-/g, ''),
      latestSpread: 'N/A',
      signalLevel: '연결 실패',
      recommendation: `오류: ${error.message}`,
      signalColor: 'red',
      chartData: []
    };
  }
}

module.exports = { getInvestmentSignal };
