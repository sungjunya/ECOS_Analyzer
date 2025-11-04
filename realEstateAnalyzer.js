// 📈 realEstateAnalyzer.js (전체 코드)
const axios = require("axios");

// [1] ✅ Gemini API 호출을 위한 환경 변수와 URL 설정
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || ''; // 환경 변수에서 API 키 로드
const GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent";

// [2] ✅ Gemini AI를 호출하여 구조화된 JSON 응답을 생성하는 함수 (핵심 변경)
// type: 'realestate'에 맞춰 시스템 지침을 설정하고, 결과는 **분석과 추천이 분리된 JSON**으로 반환합니다.
async function generateAIContent(prompt) {
    if (!GEMINI_API_KEY) {
        console.warn("⚠️ GEMINI_API_KEY가 설정되지 않았습니다. AI 분석을 건너뜕니다.");
        // [수정] AI 분석 실패 시 기본 JSON 구조를 반환하여 undefined 오류 방지
        return {
            analysis: "⚠️ AI 분석 키가 설정되지 않아 심층 분석을 사용할 수 없습니다.",
            recommendation_summary: "API 키를 설정하여 분석을 활성화하십시오."
        };
    }

    // 시스템 지침: 부동산 전문 컨설턴트 역할 부여
    const systemInstruction = "당신은 한국 부동산 시장의 동향을 심층 분석하는 전문 투자 컨설턴트입니다. 당신의 임무는 주어진 데이터를 기반으로 시장 상황에 대한 상세 분석과 함께, 이에 따른 가장 적절한 투자 전략(매수/관망/매도)을 한 문장으로 명확하게 요약하여 JSON 형식으로 제공하는 것입니다. 분석 결과는 항상 한국어로 작성해야 합니다.";

    // [변경] JSON 스키마 정의: 분석(긴 문단)과 추천(한 줄)을 분리
    const responseSchema = {
        type: "OBJECT",
        properties: {
            "analysis": { "type": "STRING", "description": "현재 부동산 시장 상황에 대한 상세 분석 및 해설을 한 문단으로 작성합니다. 불필요한 서론/결론, 제목, 불릿 포인트를 사용하지 마십시오. 답변을 할 때 항상 주어진 위험 등급(Level)과 구체적인 지표 값을 인용하여 분석을 시작해야 합니다." },
            "recommendation_summary": { "type": "STRING", "description": "현재 상황에 기반한 가장 적합한 투자 전략(매수/관망/매도)을 담은 짧고 간결한 한 문장으로 작성합니다. '매수', '관망', '매도' 중 하나를 포함해야 합니다." }
        },
        propertyOrdering: ["analysis", "recommendation_summary"]
    };

    const payload = {
        contents: [{ parts: [{ text: prompt }] }],
        systemInstruction: {
            parts: [{ text: systemInstruction }]
        },
        generationConfig: {
            responseMimeType: "application/json",
            responseSchema: responseSchema
        }
    };

    try {
        const response = await axios.post(`${GEMINI_API_URL}?key=${GEMINI_API_KEY}`, payload, {
            headers: { 'Content-Type': 'application/json' },
            timeout: 15000
        });

        const text = response.data.candidates?.[0]?.content?.parts?.[0]?.text;

        if (text) {
            try {
                // JSON 문자열을 객체로 파싱
                const parsed = JSON.parse(text);
                return {
                    analysis: parsed.analysis || "AI 분석 결과가 누락되었습니다.",
                    recommendation_summary: parsed.recommendation_summary || "투자 전략 요약이 누락되었습니다."
                };
            } catch (e) {
                console.error("🚨 JSON 파싱 오류:", e);
                return {
                    analysis: `AI 분석 실패: 응답 형식이 올바르지 않습니다. 원본 텍스트: ${text.substring(0, 100)}...`,
                    recommendation_summary: "분석 실패"
                };
            }
        } else {
            console.error("🚨 Gemini API 응답에서 유효한 텍스트를 찾을 수 없습니다.");
            return { analysis: "AI 분석 실패: 유효한 응답 없음", recommendation_summary: "분석 실패" };
        }

    } catch (error) {
        console.error("🚨 Gemini API 호출 중 오류 발생:", error.message);
        return {
            analysis: `AI 분석 실패: 통신 오류 (${error.message.substring(0, 50)}...)`,
            recommendation_summary: "통신 오류"
        };
    }
}


// 날짜 생성
function getTodayYYYYMM() {
    const d = new Date();
    return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`;
}
const today = getTodayYYYYMM();

// ECOS API 기본 설정 (기존 유지)
const API_CONFIG = {
    KEY: process.env.ECOS_API_KEY,
    BASE_URL: "https://ecos.bok.or.kr/api/StatisticSearch",
    LANG: "kr",
    TYPE: "json",
    P_START: 1,
    P_END: 1000,
    CYCLE: "M",
    START_DATE: "201001",
    END_DATE: today,
};

// ---------- 유틸리티 함수 (기존 유지) ----------
function avg(arr) {
    if (!arr.length) return 0;
    return arr.reduce((a, b) => a + b.value, 0) / arr.length;
}

async function fetchIndicatorData(statCode, itemCode = "", cycle = API_CONFIG.CYCLE) {

    let itemPath = "";
    if (Array.isArray(itemCode)) {
        itemPath = "/" + itemCode.join("/");
    } else if (typeof itemCode === "string" && itemCode.trim() !== "") {
        itemPath = `/${itemCode}`;
    }

    const url = `${API_CONFIG.BASE_URL}/${API_CONFIG.KEY}/${API_CONFIG.TYPE}/${API_CONFIG.LANG}/${API_CONFIG.P_START}/${API_CONFIG.P_END}/${statCode}/${cycle}/${API_CONFIG.START_DATE}/${API_CONFIG.END_DATE}${itemPath}`;

    try {
        const { data } = await axios.get(url, { timeout: 10000 });
        if (data?.RESULT?.CODE && data.RESULT.CODE !== '000') {
            console.error(`API 오류 (${statCode}, Item: ${itemCode}, Cycle: ${cycle}): ${data.RESULT.MESSAGE}`);
            return [];
        }
        const rows = data?.StatisticSearch?.row || [];
        return rows.map(r => ({
            time: r.TIME,
            value: parseFloat(r.DATA_VALUE)
        })).filter(d => !isNaN(d.value));
    } catch (e) {
        console.error(`API 통신 오류 (${statCode}, Item: ${itemCode}, Cycle: ${cycle}):`, e.message);
        return [];
    }
}

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

function sliceYears(data, years) {
    const cutoff = `${parseInt(today.slice(0, 4)) - years}${today.slice(4, 6)}`;
    return data.filter(d => d.time >= cutoff);
}


// ---------- 5단계 부동산 위험 등급 분류 함수 ----------
function classifyRealEstateRisk(saleYoY, rentYoY, permitYoY, interestRate, m2YoY) {
    let result = {
        level: "중립 (Neutral)",
        color: "gray",
    };

    // 핵심 조건 정의 (임계값 설정)
    const isPriceFalling = saleYoY < -0.5 && rentYoY < 0;
    const isPriceSurging = saleYoY > 1.0 && rentYoY > 0.5;
    const isPermitHigh = permitYoY > 5.0;
    const isRateHigh = interestRate >= 3.0;
    const isM2Low = m2YoY < 2.0;
    const isM2High = m2YoY > 5.0;

    // 1. 🛑 최대 위험 (Red)
    if (isPriceFalling && (isRateHigh || isPermitHigh)) {
        result.level = "🛑 최대 위험 (Extreme Risk)";
        result.color = "red";
        return result;
    }

    // 2. ⚠️ 긴축 경계 (Orange)
    if (isPriceSurging && isRateHigh) {
        result.level = "⚠️ 긴축 경계 (Tightening Alert)";
        result.color = "orange";
        return result;
    }

    // 3. 🟡 침체 탈출 (Yellow)
    if (saleYoY >= -0.5 && saleYoY < 1.0 && !isRateHigh && !isM2Low) {
        result.level = "🟡 침체 탈출 (Recovery Signal)";
        result.color = "yellow";
        return result;
    }

    // 4. ✅ 확장 초기 (Light Green)
    if (isPriceSurging && !isRateHigh && !isM2Low && !isM2High && !isPermitHigh) {
        result.level = "✅ 확장 초기 (Early Expansion)";
        result.color = "green";
        return result;
    }

    // 5. 🟦 침체기 (Blue)
    if (isPriceFalling && isM2Low && !isRateHigh) {
        result.level = "🟦 침체기 (Contraction)";
        result.color = "blue";
        return result;
    }

    return result;
}


// ---------- 메인 함수 (period 파라미터 사용) ----------
async function getRealEstateSignal(period = "5y") {
    const yearsMap = { "1y": 1, "3y": 3, "5y": 5 };
    // 🚀 period 인자를 받아 years 변수에 사용
    const years = yearsMap[period] || 5;

    try {
        const [baseRate, m2, sale, rent, permit] = await Promise.all([
            fetchIndicatorData("722Y001", "0101000"),
            fetchIndicatorData("101Y004", "BBHA01"),
            fetchIndicatorData("901Y062", "P63A"), // 주택매매가격지수 (전국)
            fetchIndicatorData("901Y063", "P64A"), // 주택전세가격지수 (전국)
            fetchIndicatorData("901Y037", ["I43AA", "1"]), // 건축허가면적 (전국, 건축 연면적)
        ]);

        // 기간 필터링 및 YoY 변환
        const sRate = sliceYears(baseRate, years);
        const sM2YoY = sliceYears(calculateYoY(m2), years);
        const sSaleYoY = sliceYears(calculateYoY(sale), years);
        const sRentYoY = sliceYears(calculateYoY(rent), years);
        const sPermitYoY = sliceYears(calculateYoY(permit), years);

        // 최근 값 추출 (5단계 분류 및 AI 프롬프트에 사용)
        const latestRate = sRate.length > 0 ? sRate[sRate.length - 1].value : 0;
        const latestM2YoY = sM2YoY.length > 0 ? sM2YoY[sM2YoY.length - 1].value : 0;
        const latestSaleYoY = sSaleYoY.length > 0 ? sSaleYoY[sSaleYoY.length - 1].value : 0;
        const latestRentYoY = sRentYoY.length > 0 ? sRentYoY[sRentYoY.length - 1].value : 0;
        const latestPermitYoY = sPermitYoY.length > 0 ? sPermitYoY[sPermitYoY.length - 1].value : 0;

        // 🚀 5단계 위험 등급 분류 적용
        const riskResult = classifyRealEstateRisk(
            latestSaleYoY,
            latestRentYoY,
            latestPermitYoY,
            latestRate,
            latestM2YoY
        );

        // 🚀 AI 분석 프롬프트 생성
        const aiPrompt = `
            현재 ${years}년 기간 동안의 한국 부동산 핵심 지표 분석 결과는 다음과 같습니다:
            - 부동산 위험 등급: ${riskResult.level}
            - 기준금리: ${latestRate.toFixed(2)}%
            - 주택매매가격지수 증가율 (YoY): ${latestSaleYoY.toFixed(2)}%
            - 주택전세가격지수 증가율 (YoY): ${latestRentYoY.toFixed(2)}%
            - 건축허가면적 증가율 (YoY): ${latestPermitYoY.toFixed(2)}%
            - 광의 통화량 (M2) 증가율 (YoY): ${latestM2YoY.toFixed(2)}%

            이 지표와 등급(${riskResult.level})을 종합적으로 분석하여, 현재 한국 부동산 시장 상황에 대한 **상세 해설**과 **가장 적합한 투자 전략(매수/관망/매도)을 한 문장으로 요약**해 주십시오. 
            JSON의 'analysis' 필드 시작은 반드시 "현재 부동산 위험 등급: ${riskResult.level}..." 형식으로 시작해야 합니다.
        `;

        // 🚀 AI 분석 호출 (JSON 구조화된 객체 반환)
        const aiAnalysis = await generateAIContent(aiPrompt);

        // 💡 짧은 요약 문구 (하단 표시용)
        const shortSummary = `최근 금리(${latestRate.toFixed(2)}%) 변동과 매매가격(${latestSaleYoY.toFixed(2)}%) 추이를 고려하여, 현재 시장 등급은 **${riskResult.level}**입니다. 투자 결정 전 심층 분석을 확인하세요.`;

        // 🚀 결과 요약 메시지 구체화
        let cycleMessage = `금리: ${latestRate.toFixed(2)}% | 매매 YoY: ${latestSaleYoY.toFixed(2)}% | 전세 YoY: ${latestRentYoY.toFixed(2)}% | M2 YoY: ${latestM2YoY.toFixed(2)}%`;

        return {
            date: today,
            period: `${years}년 분석`,
            cycleTitle: "한국 부동산 사이클 체커",
            cycleMessage: cycleMessage,
            // [수정] AI 분석 결과를 summary(상세 분석)와 recommendation(한 줄 요약)으로 분리 할당
            risk: {
                level: riskResult.level,
                color: riskResult.color,
                summary: aiAnalysis.analysis, // 상세 분석 (긴 문단)
                recommendation: aiAnalysis.recommendation_summary, // 한 줄 투자 방향성 (defined 오류 해결)
            },
            // 💡 짧은 요약 필드 유지
            shortSummary: shortSummary,

            // 차트 데이터 (YoY 데이터 전달)
            indicators: {
                salePriceYoY: { latest: latestSaleYoY.toFixed(2), chartData: sSaleYoY },
                rentPriceYoY: { latest: latestRentYoY.toFixed(2), chartData: sRentYoY },
                interestRate: { latest: latestRate.toFixed(2), chartData: sRate },
                m2YoY: { latest: latestM2YoY.toFixed(2), chartData: sM2YoY },
                permitYoY: { latest: latestPermitYoY.toFixed(2), chartData: sPermitYoY }
            }
        };

    } catch (err) {
        console.error("부동산 데이터 분석 오류:", err.message);
        return { error: "부동산 데이터 로드 및 분석 실패: " + err.message };
    }
}

module.exports = { getRealEstateSignal };
