// services/dataAnalyzer.js (최종 수정: ERROR-101 해결)
const axios = require('axios');

// 현재 날짜를 YYYYMM 형식으로 반환하도록 수정합니다.
function getFormattedDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    // 🚨 YYYYMM 형식으로 반환
    return `${year}${month}`; 
}

const TODAY = new Date();

const API_CONFIG = {
    KEY: process.env.ECOS_API_KEY,
    BASE_URL: 'http://ecos.bok.or.kr/api/StatisticSearch',
    
    // M2 통화량 테스트용 코드
    STAT_CODE: '901Y003',       // 1.1.2 통화(평잔)
    ITEM_CODE_3Y: '010000000',  // M2
    ITEM_CODE_10Y: '010000000', // M2 (로직 유지를 위해)

    // 기간을 YYYYMM 형식으로 변경
    START_DATE: '202401', // YYYYMM
    END_DATE: getFormattedDate(TODAY), // YYYYMM
    
    LANG: 'kr',
    TYPE: 'json',
    P_START: 1, 
    P_END: 500, 
};

/**
 * ECOS API로부터 특정 데이터를 가져오는 함수 (에러 처리 및 URL 로깅 강화)
 */
async function fetchInterestRate(itemCode) {
    const { KEY, BASE_URL, STAT_CODE, START_DATE, END_DATE, LANG, TYPE, P_START, P_END } = API_CONFIG;
    
    // 🚨 주기(CYCLE) M 사용
    const url = `${BASE_URL}/${KEY}/${TYPE}/${LANG}/${P_START}/${P_END}/${STAT_CODE}/M/${START_DATE}/${END_DATE}/${itemCode}`;
    
    console.log(`[BOK API REQUEST] Testing URL: ${url}`);
    
    try {
        const response = await axios.get(url);
        const data = response.data;

        if (data.RESULT && data.RESULT.CODE) {
            const errMsg = `[ECOS API] Code: ${data.RESULT.CODE} / Message: ${data.RESULT.MESSAGE}`;
            throw new Error(errMsg);
        } 
        
        const statisticData = data.StatisticSearch;
        
        if (statisticData && statisticData.row) {
            return statisticData.row.map(item => ({
                time: item.TIME,
                value: parseFloat(item.DATA_VALUE)
            }));
        } else {
            throw new Error(`ECOS API 응답 구조 오류 또는 데이터 없음. (요청 URL: ${url})`);
        }
    } catch (error) {
        if (axios.isAxiosError(error)) {
            throw new Error(`네트워크 오류 발생: ${error.message}`);
        }
        throw error; 
    }
}

/**
 * 장단기 금리 스프레드 계산 및 투자 시그널 생성 (M2 테스트 목적)
 */
async function getInvestmentSignal() {
    // M2 데이터 수집
    const dataM2_1 = await fetchInterestRate(API_CONFIG.ITEM_CODE_3Y);
    const dataM2_2 = await fetchInterestRate(API_CONFIG.ITEM_CODE_10Y);

    const latest3Y = dataM2_1[dataM2_1.length - 1];
    const latest10Y = dataM2_2.find(d => d.time === latest3Y.time); 

    if (!latest3Y || !latest10Y) {
        throw new Error("최신 M2 통화량 데이터를 찾을 수 없습니다. API 설정 및 기간을 확인하세요.");
    }
    
    const spread = latest10Y.value - latest3Y.value; 
    const today = latest3Y.time; 

    // 규칙 기반 의사결정 로직 (M2 테스트용 시그널)
    let signalLevel = 'M2 테스트 성공';
    let recommendation = '✅ M2 통화량 데이터를 성공적으로 가져왔습니다. API 키는 유효합니다. 이제 금리 코드로 돌아가야 합니다.';
    let signalColor = 'green'; 
    
    if (spread !== 0) { 
        signalLevel = 'M2 데이터 오류';
        recommendation = 'M2 데이터에 불일치가 감지되었습니다.';
        signalColor = 'red';
    }

    // 시각화 데이터 준비 
    const chartData = dataM2_1.map((d) => {
        return {
            time: d.time,
            spread: d.value.toFixed(2) // M2 값을 스프레드 자리에 임시로 넣음
        };
    }).filter(d => d.spread !== 'N/A');
    
    return {
        date: today,
        latestSpread: latest3Y.value.toFixed(2), 
        signalLevel,
        recommendation,
        signalColor,
        chartData
    };
}

module.exports = { getInvestmentSignal };