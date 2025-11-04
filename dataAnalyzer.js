// 📊 dataAnalyzer.js — 일반 투자 신호 분석 모듈 (ECOS 데이터 처리 및 Gemini AI 통합)
// 🚨 환경 호환성을 위해 axios 대신 fetch API를 사용하도록 수정했습니다.
// axios 대신 fetch를 사용하고, API Key는 빈 문자열로 설정해야 환경에서 자동 주입됩니다.
const GEMINI_API_KEY = process.env.GEMINI_API_KEY; // 💡 환경 자동 주입을 위해 빈 문자열로 설정
const GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent";


// [2] ✅ Gemini AI를 호출하여 구조화된 JSON 응답을 생성하는 함수 (지수적 백오프 및 폴백 적용)
async function generateAIContent(prompt) {
    if (!GEMINI_API_KEY && GEMINI_API_URL.includes('key=')) { // 키가 URL에 명시적으로 필요하지만 비어있는 경우 (폴백 로직 유지를 위해 남겨둠)
        // 이 환경에서는 키가 ""여도 자동 주입되므로, 이 경고는 API 호출을 막는 용도로는 사용하지 않습니다.
    }

    const systemInstruction = "당신은 한국 거시 경제 동향을 분석하는 전문 분석가입니다. 당신의 임무는 주어진 데이터를 기반으로 현재 경제 상황에 대한 상세 분석과 함께, 이에 따른 가장 적절한 투자 전략(방어적/중립적/공격적)을 한 문장으로 명확하게 요약하여 JSON 형식으로 제공하는 것입니다. 분석 결과는 항상 한국어로 작성해야 합니다.";

    const responseSchema = {
        type: "OBJECT",
        properties: {
            "analysis": { "type": "STRING", "description": "현재 거시 경제 상황에 대한 상세 분석 및 해설을 한 문단으로 작성합니다. 답변 시작은 항상 주어진 레벨과 점수 값을 인용해야 합니다." },
            "recommendation_summary": { "type": "STRING", "description": "현재 상황에 기반한 가장 적합한 투자 전략(방어적/중립적/공격적)을 담은 짧고 간결한 한 문장으로 작성합니다. '방어적', '중립적', '공격적' 중 하나를 포함해야 합니다." }
        },
        propertyOrdering: ["analysis", "recommendation_summary"]
    };

    const payload = {
        contents: [{ parts: [{ text: prompt }] }],
        // 🚨 [수정] Google Search (Grounding) 기능 요청을 제거하여 400 오류 회피
        // tools: [{ "google_search": {} }], 
        systemInstruction: {
            parts: [{ text: systemInstruction }]
        },
        generationConfig: {
            responseMimeType: "application/json",
            responseSchema: responseSchema
        }
    };

    // API URL에 키를 추가합니다.
    const apiUrlWithKey = `${GEMINI_API_URL}?key=${GEMINI_API_KEY}`;

    const MAX_RETRIES = 3;
    let delay = 1000; // 1초 초기 딜레이

    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
        try {
            // 🚨 axios 대신 표준 fetch API 사용
            const response = await fetch(apiUrlWithKey, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                // HTTP 오류 응답 처리 (예: 400 Bad Request)
                const errorText = await response.text();
                throw new Error(`HTTP Error: ${response.status} - ${errorText.substring(0, 50)}`);
            }

            const result = await response.json();
            const text = result.candidates?.[0]?.content?.parts?.[0]?.text;

            if (text) {
                try {
                    const parsed = JSON.parse(text);
                    return {
                        analysis: parsed.analysis || "AI 분석 결과가 누락되었습니다. (상세 분석)",
                        recommendation_summary: parsed.recommendation_summary || "투자 방향성 요약 실패: AI JSON 필드 누락."
                    };
                } catch (e) {
                    console.error("🚨 JSON 파싱 오류:", e);
                    return {
                        analysis: `AI 분석 실패: 응답 형식이 올바르지 않습니다. 원본 텍스트: ${text.substring(0, 100)}...`,
                        recommendation_summary: "AI 응답 파싱 실패. 원인을 확인하세요."
                    };
                }
            } else {
                return { analysis: "AI 분석 실패: 유효한 응답 없음", recommendation_summary: "분석 실패 (텍스트 없음)" };
            }
        } catch (error) {
            if (attempt < MAX_RETRIES) {
                // console.warn 대신 console.log를 사용하여 재시도 로그를 최소화
                await new Promise(resolve => setTimeout(resolve, delay));
                delay *= 2;
            } else {
                console.error("🚨 Gemini API 호출 최종 실패:", error.message);
                return {
                    analysis: `AI 분석 최종 실패: 통신 오류 (${error.message.substring(0, 50)}...)`,
                    recommendation_summary: "AI 통신 최종 오류로 요약 불가." // 🚨 최종 폴백
                };
            }
        }
    }
}


// 날짜 (YYYYMM 형식)
function getTodayYYYYMM() {
    const d = new Date();
    // 현재 월이 1월인 경우 작년 12월 데이터를 마지막으로 사용 (지표 발표 시차 고려)
    const month = d.getMonth() === 0 ? 12 : d.getMonth();
    const year = d.getMonth() === 0 ? d.getFullYear() - 1 : d.getFullYear();

    // 현재 월 - 1 (데이터 시차를 고려하여 전월까지의 데이터 요청)
    return `${year}${String(month).padStart(2, '0')}`;
}
const today = getTodayYYYYMM();

// 한국은행 ECOS API 설정
const API_CONFIG = {
    // 🚨 ECOS_API_KEY는 process.env를 통해 로드해야 합니다.
    KEY: typeof process !== 'undefined' && process.env.ECOS_API_KEY ? process.env.ECOS_API_KEY : 'YOUR_ECOS_API_KEY',
    BASE_URL: 'https://ecos.bok.or.kr/api/StatisticSearch',
    LANG: 'kr',
    TYPE: 'json',
    P_START: 1,
    P_END: 1000,
    CYCLE: 'M',
    START_DATE: '201001',
    END_DATE: today, // 전월 데이터까지 요청하도록 today 값 업데이트
    SPREAD_STAT_CODE: '721Y001', // 시장 금리
    SPREAD_ITEM_CODE_3Y: '5020000', // 국고채(3년)
    SPREAD_ITEM_CODE_10Y: '5050000', // 국고채(10년)
    M2_STAT_CODE: '101Y004', // 광의통화(M2)
    M2_ITEM_CODE: 'BBHA01', // M2 원계열
    CPI_STAT_CODE: '102Y003', // 소비자 물가지수
    CPI_ITEM_CODE: 'ABA2', // 전국 소비자 물가지수
    PPI_STAT_CODE: '404Y014', // 생산자 물가지수
    PPI_ITEM_CODE: '*AA' // 공업제품
};

// ---------- 유틸 ----------
function avg(arr) {
    if (!arr.length) return 0;
    return arr.reduce((a, b) => a + b.value, 0) / arr.length;
}

// 선형 회귀 기울기 계산
function slope(arr) {
    if (arr.length < 2) return 0;
    let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
    for (let i = 0; i < arr.length; i++) {
        // X: 시간축 (0, 1, 2, ...)
        sumX += i;
        // Y: 값
        sumY += arr[i].value;
        sumXY += i * arr[i].value;
        sumXX += i * i;
    }
    const numerator = (arr.length * sumXY - sumX * sumY);
    const denominator = (arr.length * sumXX - sumX * sumX);

    // 분모가 0인 경우 (데이터 포인트가 1개 이하) 방지
    return denominator === 0 ? 0 : numerator / denominator;
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
        // 🚨 axios 대신 표준 fetch API 사용
        const response = await fetch(url, { timeout: 10000 });
        const data = await response.json();

        const rows = data?.StatisticSearch?.row || [];

        return rows.map(r => ({
            time: r.TIME,
            value: parseFloat(r.DATA_VALUE)
        })).filter(d => !isNaN(d.value));

    } catch (e) {
        console.error(`🚨 ECOS API 호출 오류 (${statCode}):`, e.message);
        return [];
    }
}

// ---------- 지표 계산 ----------
// 전년 동월 대비 증가율 (YoY) 계산
function calculateYoY(data) {
    const result = [];
    // 시간을 키로, 값을 값으로 하는 맵 생성
    const map = new Map(data.map(d => [d.time, d.value]));
    data.forEach(d => {
        const currentYear = parseInt(d.time.slice(0, 4));
        const month = d.time.slice(4);
        const prev = `${currentYear - 1}${month}`; // 전년 동월 시간 키

        if (map.has(prev)) {
            const prevValue = map.get(prev);
            if (prevValue !== 0) { // 0으로 나누는 경우 방지
                const rate = ((d.value - prevValue) / prevValue) * 100;
                result.push({ time: d.time, value: +rate.toFixed(2) });
            }
        }
    });
    return result;
}

// 장단기 금리 스프레드 (10년 - 3년) 계산
function calculateSpread(d3Y, d10Y) {
    const map = new Map(d3Y.map(d => [d.time, d.value]));
    return d10Y.filter(d => map.has(d.time))
        .map(d => ({ time: d.time, value: +(d.value - map.get(d.time)).toFixed(2) }));
}

// 최근 N년치 데이터로 필터링
function sliceYears(data, years) {
    // 요청된 기간의 시작 시점 (YYYYMM) 계산
    const currentYear = parseInt(today.slice(0, 4));
    const currentMonth = today.slice(4, 6);
    const cutoffYear = currentYear - years + (currentMonth > '01' ? 0 : 1); // 1월 이전 데이터도 포함하기 위해 조정
    const cutoff = `${cutoffYear}01`; // N년 전 1월부터 시작

    return data.filter(d => d.time >= cutoff);
}


// ---------- 점수 계산 ----------
// 🚀 투자 신호 점수 계산 (0-100점)
function getSignalScore(key, avgValue) {
    switch (key) {
        case 'spread': // 금리 스프레드 (높을수록 호황)
            if (avgValue >= 1.0) return 100;
            if (avgValue >= 0.5) return 75;
            if (avgValue >= 0.0) return 50;
            return 0; // 역전 또는 0 근방은 위험 (침체/경계)
        case 'm2': // M2 증가율 (적절히 높을수록 좋음: 2%~4%)
            if (avgValue >= 2.0 && avgValue <= 4.0) return 100;
            if (avgValue > 4.0 || avgValue < 0) return 50; // 과잉 또는 부족
            if (avgValue < 2.0) return 75; // 약간 부족
            return 75;
        case 'cpi': // CPI 증가율 (적절히 낮을수록 좋음: 1%~3%)
            if (avgValue >= 1.0 && avgValue <= 3.0) return 100;
            if (avgValue > 4.0 || avgValue < 0.0) return 0; // 고인플레이션 또는 디플레이션
            return 50;
        default:
            return 50;
    }
}

// 🚀 복합 점수 계산 (가중치 적용)
function calculateCompositeScore(scores) {
    // 종합 점수 = (금리 신호 * 0.5) + (M2 신호 * 0.3) + (CPI 신호 * 0.2)
    const score = (scores.spread * 0.5) + (scores.m2 * 0.3) + (scores.cpi * 0.2);
    return Math.round(score);
}

// 🚀 4단계 레벨 분류 (로직 강화)
function classifyOnly(avgSpread, avgM2, avgCPI, trendM2) {
    let level = "중립";
    let color = "gray";

    const isM2Slowdown = trendM2 === '하락세';
    const isM2Robust = avgM2 >= 2.0;
    const isM2AndCPIStable = avgM2 >= 2.0 && avgCPI <= 3.0;
    const isHighInflation = avgCPI > 4.0;

    // 1. 🚨 최대 위험 (Red): 금리 역전 또는 고물가/M2 하락세
    if (avgSpread <= 0 || (isHighInflation && isM2Slowdown)) {
        level = "최대 위험";
        color = "red";
    }
    // 2. ⚠️ 긴축 경계 (Orange): 금리차 정상이나 고물가
    else if (avgSpread > 0 && isHighInflation) {
        level = "긴축 경계";
        color = "orange";
    }
    // 3. ✅ 최적 확장 (Green): 넓은 금리차와 안정된 M2/CPI
    else if (avgSpread >= 1.0 && isM2AndCPIStable) {
        level = "최적 확장";
        color = "green";
    }
    // 4. 🟡 안정 성장 (Yellow): 적정 금리차와 M2 안정
    else if (avgSpread >= 0.5 && isM2Robust) {
        level = "안정 성장";
        color = "yellow";
    }

    return { level, color };
}

// 🚀 과거 데이터에 대한 복합 점수 시계열 계산
function calculateCompositeHistory(spreadData, m2Data, cpiData) {
    const history = [];
    const m2Map = new Map(m2Data.map(d => [d.time, d.value]));
    const cpiMap = new Map(cpiData.map(d => [d.time, d.value]));

    // 세 지표 모두 존재하는 시간대의 데이터를 기준으로 순회
    spreadData.forEach(sData => {
        const time = sData.time;
        const spreadValue = sData.value;
        const m2Value = m2Map.get(time);
        const cpiValue = cpiMap.get(time);

        if (m2Value !== undefined && cpiValue !== undefined) {
            const scores = {
                spread: getSignalScore('spread', spreadValue),
                m2: getSignalScore('m2', m2Value),
                cpi: getSignalScore('cpi', cpiValue)
            };
            const compositeScore = calculateCompositeScore(scores);
            history.push({ time, value: compositeScore });
        }
    });

    return history;
}

// ---------- 메인 ----------
async function getInvestmentSignal(period = '1y') {
    const yearsMap = { '1y': 1, '3y': 3, '5y': 5 };
    const years = yearsMap[period] || 1;

    try {
        // ECOS API 키가 설정되지 않은 경우를 대비하여 수정
        if (API_CONFIG.KEY === 'YOUR_ECOS_API_KEY') {
            throw new Error("ECOS_API_KEY가 설정되지 않았습니다. 한국은행 데이터 수집 불가. `YOUR_ECOS_API_KEY`를 실제 키로 변경해야 합니다.");
        }

        // 5개 지표 병렬 수집
        const [d3Y, d10Y, dM2, dCPI, dPPI] = await Promise.all([
            fetchIndicatorData(API_CONFIG.SPREAD_STAT_CODE, API_CONFIG.SPREAD_ITEM_CODE_3Y),
            fetchIndicatorData(API_CONFIG.SPREAD_STAT_CODE, API_CONFIG.SPREAD_ITEM_CODE_10Y),
            fetchIndicatorData(API_CONFIG.M2_STAT_CODE, API_CONFIG.M2_ITEM_CODE),
            fetchIndicatorData(API_CONFIG.CPI_STAT_CODE, API_CONFIG.CPI_ITEM_CODE),
            fetchIndicatorData(API_CONFIG.PPI_STAT_CODE, API_CONFIG.PPI_ITEM_CODE)
        ]);

        // 가공 (스프레드, YoY)
        const spreadRaw = calculateSpread(d3Y, d10Y);
        const m2Raw = calculateYoY(dM2);
        const cpiRaw = calculateYoY(dCPI);
        const ppiRaw = calculateYoY(dPPI);

        // 기간별 데이터 필터링
        const s = sliceYears(spreadRaw, years);
        const m = sliceYears(m2Raw, years);
        const c = sliceYears(cpiRaw, years);
        const p = sliceYears(ppiRaw, years);

        // 현재/평균 계산
        const avgSpread = avg(s);
        const avgM2 = avg(m);
        const avgCPI = avg(c);
        const avgPPI = avg(p);

        const trendSpread = slopeToWord(slope(s));
        const trendM2 = slopeToWord(slope(m));
        const trendCPI = slopeToWord(slope(c));
        const trendPPI = slopeToWord(slope(p));

        // 복합 점수 및 레벨 계산
        const scores = {
            spread: getSignalScore('spread', avgSpread),
            m2: getSignalScore('m2', avgM2),
            cpi: getSignalScore('cpi', avgCPI)
        };
        const compositeScore = calculateCompositeScore(scores);
        const { level, color } = classifyOnly(avgSpread, avgM2, avgCPI, trendM2);

        // 복합 점수 시계열 계산 (차트 표시용)
        const compositeScoreHistory = calculateCompositeHistory(s, m, c);

        // 🚀 [AI 통합] Gemini에 분석을 요청할 프롬프트 생성
        const aiPrompt = `
            현재 ${years}년 기간 동안의 한국 경제 핵심 지표 분석 결과는 다음과 같습니다:
            - 종합 신호 레벨: ${level} (점수: ${compositeScore}점)
            - 장단기 금리 스프레드 (3년-10년): 평균 ${avgSpread.toFixed(2)}% (추세: ${trendSpread})
            - 광의 통화량 (M2) 증가율 (YoY): 평균 ${avgM2.toFixed(2)}% (추세: ${trendM2})
            - 소비자 물가 지수 (CPI) 증가율 (YoY): 평균 ${avgCPI.toFixed(2)}% (추세: ${trendCPI})
            - 생산자 물가 지수 (PPI) 증가율 (YoY): 평균 ${avgPPI.toFixed(2)}% (추세: ${trendPPI})

            이 데이터를 종합적으로 분석하여, 현재 한국 경제 상황에 대한 **심층 해설**과 **가장 적합한 투자 전략(현금 비중, 투자 방향)**을 요청합니다. 
            상세 해설(analysis)의 시작은 반드시 "현재 시장 레벨: ${level} (${compositeScore}점)..." 형식으로 시작해야 합니다.
        `;

        // AI 분석 호출 (JSON 구조화된 객체 반환)
        const aiAnalysis = await generateAIContent(aiPrompt);

        // 💡 짧은 요약 문구 (하단 표시용) - 원본 요청에 따라 하드코딩 유지
        const shortSummary = "물가 상승 압력과 통화량 증가에도 불구하고, 소비와 투자가 위축되어 체감 경기는 아직 어렵습니다. 물가와 경기 안정화가 필요합니다.";

        return {
            date: today,
            period: `${years}년`,
            classification: {
                level,
                color,
                description: aiAnalysis.analysis, // 상세 분석
                recommendation: aiAnalysis.recommendation_summary, // 🚨 한 줄 투자 방향성 요약
            },
            shortSummary: shortSummary,
            compositeScore: compositeScore,
            compositeScoreHistory: compositeScoreHistory,
            indicators: {
                // 설명 함수는 제거하고 핵심 데이터만 전달하도록 간소화 (AI 분석이 메인)
                spread: { latest: avgSpread.toFixed(2), trend: trendSpread, chartData: s },
                m2: { latest: avgM2.toFixed(2), trend: trendM2, chartData: m },
                cpi: { latest: avgCPI.toFixed(2), trend: trendCPI, chartData: c },
                ppi: { latest: avgPPI.toFixed(2), trend: trendPPI, chartData: p }
            }
        };
    } catch (err) {
        console.error("최종 분석 오류:", err.message);
        return { error: err.message };
    }
}

// 외부에 노출
module.exports = { getInvestmentSignal };
