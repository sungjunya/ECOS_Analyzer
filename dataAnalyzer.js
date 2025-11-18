// 📊 dataAnalyzer.js — ECOS + Gemini AI 통합 (AI 자동 요약형 최종 완성본)
// ✅ Gemini 2.0 모델 적용 / JSON + 텍스트 응답 완전 호환 / undefined 방지
// ✅ 9개 핵심 지표(금리 스프레드, M2, CPI, PPI, 실업률, CCSI, KOSPI, 무역수지, 환율)
// ✅ 1y/3y/5y 구간별 가중 평균 반영

const GEMINI_API_KEY = process.env.GEMINI_API_KEY || "";
const GEMINI_API_URL =
"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent";

/* -----------------------------
 * 📦 유틸 함수
 * ----------------------------- */
function avgWeighted(arr) {
    if (!arr || arr.length === 0) return 0;
    let total = 0, weightSum = 0;
    for (let i = 0; i < arr.length; i++) {
        const w = i + 1; // 최근 데이터에 더 큰 가중치
        total += arr[i].value * w;
        weightSum += w;
    }
    return total / weightSum;
}

function avg(arr) {
    if (!arr || arr.length === 0) return 0;
    return arr.reduce((a, b) => a + b.value, 0) / arr.length;
}

function getTodayYYYYMM() {
    const d = new Date();
    const year = d.getFullYear();
    const month = d.getMonth() + 1;
    return `${year}${String(month).padStart(2, "0")}`;
}

function slope(arr) {
    if (!arr || arr.length < 2) return 0;
    let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
    for (let i = 0; i < arr.length; i++) {
        sumX += i;
        sumY += arr[i].value;
        sumXY += i * arr[i].value;
        sumXX += i * i;
    }
    const num = arr.length * sumXY - sumX * sumY;
    const den = arr.length * sumXX - sumX * sumX;
    return den === 0 ? 0 : num / den;
}

function sliceYears(data, years) {
    const today = getTodayYYYYMM();
    const currentYear = parseInt(today.slice(0, 4));
    const cutoff = `${currentYear - years + 1}01`;
    return data.filter(d => d.time >= cutoff);
}

/* -----------------------------
 * ⚙️ ECOS API 설정
 * ----------------------------- */
const today = getTodayYYYYMM();
const API_CONFIG = {
    KEY: process.env.ECOS_API_KEY || "YOUR_ECOS_API_KEY",
    BASE_URL: "https://ecos.bok.or.kr/api/StatisticSearch",
    LANG: "kr",
    TYPE: "json",
    P_START: 1,
    P_END: 1000,
    CYCLE: "M",
    START_DATE: "201001",
    END_DATE: today, 

    SPREAD_STAT_CODE: "721Y001",
    SPREAD_ITEM_CODE_3Y: "5020000",
    SPREAD_ITEM_CODE_10Y: "5050000",
    M2_STAT_CODE: "101Y004",
    M2_ITEM_CODE: "BBHA01",
    CPI_STAT_CODE: "102Y003",
    CPI_ITEM_CODE: "ABA2",
    PPI_STAT_CODE: "404Y014",
    PPI_ITEM_CODE: "*AA",
    UNEMPLOYMENT_STAT_CODE: "901Y027",
    UNEMPLOYMENT_ITEM_CODE: "I61BC",
    CCSI_STAT_CODE: "511Y002",
    CCSI_ITEM_CODE: "FME",
    KOSPI_STAT_CODE: "901Y014",
    KOSPI_ITEM_CODE: "1080000",
    TRADE_STAT_CODE: "301Y013",
    TRADE_ITEM_CODE: "000000",
    FX_STAT_CODE: "731Y004",
    FX_ITEM_CODE: "0000001",
};

/* -----------------------------
 * 📡 ECOS fetch
 * ----------------------------- */
async function fetchIndicatorData(statCode, itemCode = "") {
    const url = `${API_CONFIG.BASE_URL}/${API_CONFIG.KEY}/${API_CONFIG.TYPE}/${API_CONFIG.LANG}/${API_CONFIG.P_START}/${API_CONFIG.P_END}/${statCode}/${API_CONFIG.CYCLE}/${API_CONFIG.START_DATE}/${API_CONFIG.END_DATE}/${itemCode}`;
    try {
        const res = await fetch(url);
        const data = await res.json();
        const rows = data?.StatisticSearch?.row || [];
        return rows.map(r => ({
            time: r.TIME,
            value: parseFloat(r.DATA_VALUE)
        })).filter(d => !isNaN(d.value));
    } catch (e) {
        console.error(`🚨 ECOS API 오류(${statCode}):`, e.message);
        return [];
    }
}

function calculateYoY(data) {
    const map = new Map(data.map(d => [d.time, d.value]));
    const res = [];
    data.forEach(d => {
        const prev = `${parseInt(d.time.slice(0, 4)) - 1}${d.time.slice(4)}`;
        if (map.has(prev) && map.get(prev) !== 0) {
            const rate = ((d.value - map.get(prev)) / map.get(prev)) * 100;
            res.push({ time: d.time, value: +rate.toFixed(2) });
        }
    });
    return res;
}

function calculateSpread(d3, d10) {
    const map = new Map(d3.map(d => [d.time, d.value]));
    return d10
        .filter(d => map.has(d.time))
        .map(d => ({ time: d.time, value: +(d.value - map.get(d.time)).toFixed(2) }));
}

/* -----------------------------
 * 📊 점수화 및 가중치
 * ----------------------------- */
function getSignalScore(key, v) {
    switch (key) {
        case "spread": return v >= 1 ? 100 : v >= 0.5 ? 75 : v >= 0 ? 50 : 0;
        case "m2": return v >= 2 && v <= 4 ? 100 : v < 2 ? 75 : 50;
        case "cpi": return v >= 1 && v <= 3 ? 100 : v > 4 || v < 0 ? 0 : 50;
        case "ppi": return v >= 0 && v <= 5 ? 100 : v > 5 ? 75 : 50;
        case "unemployment": return v <= 3 ? 100 : v <= 4 ? 75 : 50;
        case "ccsi": return v >= 100 ? 100 : v >= 90 ? 75 : 50;
        case "kospi_yoy": return v >= 5 ? 100 : v >= 0 ? 75 : 50;
        case "trade_yoy": return v >= 10 ? 100 : v >= 0 ? 75 : 50;
        case "fx_change": return Math.abs(v) <= 5 ? 100 : 50;
        default: return 50;
    }
}

function calculateCompositeScore(scores) {
    const weights = {
        spread: 0.2,
        m2: 0.15,
        cpi: 0.1,
        ppi: 0.1,
        unemployment: 0.15,
        ccsi: 0.1,
        kospi_yoy: 0.1,
        trade_yoy: 0.07,
        fx_change: 0.03
    };
    let total = 0, sum = 0;
    for (const k in scores) {
        if (weights[k]) {
            total += (scores[k] ?? 0) * weights[k];
            sum += weights[k];
        }
    }
    return sum === 0 ? 0 : Math.round(total / sum);
}

/* -----------------------------
 * 🎨 색상 분류
 * ----------------------------- */
function classifyOnly(score) {
    if (score >= 65) return { level: "위험", color: "red" };
    if (score >= 50) return { level: "경계", color: "orange" };
    if (score >= 35) return { level: "주의", color: "yellow" };
    return { level: "양호", color: "green" };
}

/* -----------------------------
 * 🧮 합성 점수 히스토리
 * ----------------------------- */
function calculateCompositeHistory(s, m, c, p, u, cc, k, t, f) {
    const maps = {
        m2: new Map(m.map(d => [d.time, d.value])),
        cpi: new Map(c.map(d => [d.time, d.value])),
        ppi: new Map(p.map(d => [d.time, d.value])),
        u: new Map(u.map(d => [d.time, d.value])),
        cc: new Map(cc.map(d => [d.time, d.value])),
        k: new Map(k.map(d => [d.time, d.value])),
        t: new Map(t.map(d => [d.time, d.value])),
        f: new Map(f.map(d => [d.time, d.value]))
    };
    const history = [];
    s.forEach(sp => {
        const t = sp.time;
        if (
            maps.m2.has(t) && maps.cpi.has(t) && maps.ppi.has(t) &&
            maps.u.has(t) && maps.cc.has(t) && maps.k.has(t) &&
            maps.t.has(t) && maps.f.has(t)
        ) {
            const scores = {
                spread: getSignalScore("spread", sp.value),
                m2: getSignalScore("m2", maps.m2.get(t)),
                cpi: getSignalScore("cpi", maps.cpi.get(t)),
                ppi: getSignalScore("ppi", maps.ppi.get(t)),
                unemployment: getSignalScore("unemployment", maps.u.get(t)),
                ccsi: getSignalScore("ccsi", maps.cc.get(t)),
                kospi_yoy: getSignalScore("kospi_yoy", maps.k.get(t)),
                trade_yoy: getSignalScore("trade_yoy", maps.t.get(t)),
                fx_change: getSignalScore("fx_change", maps.f.get(t)),
            };
            history.push({ time: t, value: calculateCompositeScore(scores) });
        }
    });
    return history;
}

/* -----------------------------
 * 🤖 Gemini AI 분석 (JSON + 텍스트 자동 처리)
 * ----------------------------- */
async function generateAIContent(prompt) {
    if (!GEMINI_API_KEY) {
        console.warn("⚠️ GEMINI_API_KEY가 설정되지 않음");
        return {
            analysis: "AI 키가 없어 기본 분석만 제공합니다.",
            recommendation_summary: "데이터 기반 기본 전략만 표시합니다.",
        };
    }

    // 📌 JSON 강제 지시 + 예시 스키마
    const systemText = `너는 한국 거시경제 애널리스트다.
  반드시 아래 JSON 형식으로만 응답해. 코드블록( \`\`\` ) 사용 금지.
  
  {
    "analysis": "현재 한국 경제의 상태를 2~3문장으로 요약",
    "recommendation_summary": "투자 전략을 1문장으로 요약"
  }`;

    const payload = {
        contents: [{ parts: [{ text: `${systemText}\n\n[입력]\n${prompt}` }] }],
    };

    try {
        const res = await fetch(`${GEMINI_API_URL}?key=${GEMINI_API_KEY}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (!res.ok) {
            console.error("🚨 Gemini 응답 오류:", res.status, await res.text());
            return {
                analysis: "AI 분석 실패 (응답 오류)",
                recommendation_summary: "Gemini 응답을 받지 못했습니다.",
            };
        }

        const data = await res.json();

        // 후보들 중 첫 텍스트 찾기
        const text =
            data?.candidates?.[0]?.content?.parts?.[0]?.text ??
            data?.candidates?.[0]?.content?.parts?.[0]?.inline_data?.data ??
            "";

        if (!text || typeof text !== "string") {
            return {
                analysis: "AI 분석 결과를 불러올 수 없습니다.",
                recommendation_summary: "Gemini 응답이 비어 있습니다.",
            };
        }

        // 1) 코드펜스 제거 (```json ... ```, ``` ... ```)
        const stripCodeFences = (s) => {
            // 첫 번째 코드블록만 추출 → 없으면 원문 유지
            const fence = s.match(/```[a-zA-Z]*\n?([\s\S]*?)```/);
            const raw = fence ? fence[1] : s;
            return raw.trim();
        };

        let raw = stripCodeFences(text);

        // 2) JSON처럼 보이면 파싱 시도
        const looksLikeJson = raw.trim().startsWith("{") && raw.trim().endsWith("}");
        if (looksLikeJson) {
            try {
                const parsed = JSON.parse(raw);
                // 키 보정(fallback)
                return {
                    analysis: String(parsed.analysis ?? parsed.summary ?? "").trim() || "분석 없음",
                    recommendation_summary:
                        String(parsed.recommendation_summary ?? parsed.recommendation ?? parsed.strategy ?? "").trim() ||
                        "요약 없음",
                };
            } catch (e) {
                // 계속 진행 (문단 파싱)
            }
        }

        // 3) JSON 키-값을 텍스트에서 정규식으로 뽑아보는 보조시도
        try {
            const a = raw.match(/"analysis"\s*:\s*"([\s\S]*?)"\s*(,|\})/);
            const r = raw.match(/"recommendation_summary"\s*:\s*"([\s\S]*?)"\s*(,|\})/);
            if (a || r) {
                return {
                    analysis: (a?.[1] || "분석 없음").replace(/\*\*/g, "").trim(),
                    recommendation_summary: (r?.[1] || "요약 없음").replace(/\*\*/g, "").trim(),
                };
            }
        } catch (_) { /* ignore */ }

        // 4) 일반 문단일 때: "투자 전략:" 이후 라인 자동 추출
        let analysisText = raw.replace(/\*\*/g, "").trim();
        let summaryText = "요약 없음";
        const strategyMatch =
            analysisText.match(/투자\s*전략[:：]\s*([^\n]+)/) ||
            analysisText.match(/전략[:：]\s*([^\n]+)/) ||
            analysisText.match(/권장(?:되는)?\s*전략[:：]\s*([^\n]+)/);
        if (strategyMatch) {
            summaryText = strategyMatch[1].trim();
        } else {
            // 전략 단서가 들어간 문장 하나를 요약으로
            const sentence = (analysisText.match(/[^.!?。\n]*?(전략|포트폴리오|비중|분산|방어|중립|공격|헤지)[^.!?。\n]*[.!?。]?/i) || [])[0];
            if (sentence) summaryText = sentence.trim();
        }

        return {
            analysis: analysisText || "분석 없음",
            recommendation_summary: summaryText || "요약 없음",
        };
    } catch (err) {
        console.error("🚨 Gemini 호출 실패:", err.message);
        return {
            analysis: "AI 분석 실패 (예외 발생)",
            recommendation_summary: "Gemini API 호출 오류",
        };
    }
}


/* -----------------------------
 * 🚀 메인 함수
 * ----------------------------- */
async function getInvestmentSignal(period = "1y") {
    const years = { "1y": 1, "3y": 3, "5y": 5 }[period] || 1;

    try {
        const [d3Y, d10Y, dM2, dCPI, dPPI, dUnemp, dCCSI, dKOSPI, dTrade, dFX] =
            await Promise.all([
                fetchIndicatorData(API_CONFIG.SPREAD_STAT_CODE, API_CONFIG.SPREAD_ITEM_CODE_3Y),
                fetchIndicatorData(API_CONFIG.SPREAD_STAT_CODE, API_CONFIG.SPREAD_ITEM_CODE_10Y),
                fetchIndicatorData(API_CONFIG.M2_STAT_CODE, API_CONFIG.M2_ITEM_CODE),
                fetchIndicatorData(API_CONFIG.CPI_STAT_CODE, API_CONFIG.CPI_ITEM_CODE),
                fetchIndicatorData(API_CONFIG.PPI_STAT_CODE, API_CONFIG.PPI_ITEM_CODE),
                fetchIndicatorData(API_CONFIG.UNEMPLOYMENT_STAT_CODE, API_CONFIG.UNEMPLOYMENT_ITEM_CODE),
                fetchIndicatorData(API_CONFIG.CCSI_STAT_CODE, API_CONFIG.CCSI_ITEM_CODE),
                fetchIndicatorData(API_CONFIG.KOSPI_STAT_CODE, API_CONFIG.KOSPI_ITEM_CODE),
                fetchIndicatorData(API_CONFIG.TRADE_STAT_CODE, API_CONFIG.TRADE_ITEM_CODE),
                fetchIndicatorData(API_CONFIG.FX_STAT_CODE, API_CONFIG.FX_ITEM_CODE),
            ]);

        const spreadRaw = calculateSpread(d3Y, d10Y);
        const m2Raw = calculateYoY(dM2);
        const cpiRaw = calculateYoY(dCPI);
        const ppiRaw = calculateYoY(dPPI);
        const kospiRaw = calculateYoY(dKOSPI);
        const tradeRaw = calculateYoY(dTrade);
        const fxRaw = calculateYoY(dFX);

        const s = sliceYears(spreadRaw, years);
        const m = sliceYears(m2Raw, years);
        const c = sliceYears(cpiRaw, years);
        const p = sliceYears(ppiRaw, years);
        const k = sliceYears(kospiRaw, years);
        const t = sliceYears(tradeRaw, years);
        const f = sliceYears(fxRaw, years);
        const u = sliceYears(dUnemp, years);
        const cc = sliceYears(dCCSI, years);

        const avgSpread = avgWeighted(s);
        const avgM2 = avgWeighted(m);
        const avgCPI = avgWeighted(c);
        const avgPPI = avgWeighted(p);
        const avgUnemp = avgWeighted(u);
        const avgCCSI = avgWeighted(cc);
        const avgKOSPI = avgWeighted(k);
        const avgTrade = avgWeighted(t);
        const avgFX = avgWeighted(f);

        const scores = {
            spread: getSignalScore("spread", avgSpread),
            m2: getSignalScore("m2", avgM2),
            cpi: getSignalScore("cpi", avgCPI),
            ppi: getSignalScore("ppi", avgPPI),
            unemployment: getSignalScore("unemployment", avgUnemp),
            ccsi: getSignalScore("ccsi", avgCCSI),
            kospi_yoy: getSignalScore("kospi_yoy", avgKOSPI),
            trade_yoy: getSignalScore("trade_yoy", avgTrade),
            fx_change: getSignalScore("fx_change", avgFX),
        };

        const compositeScore = calculateCompositeScore(scores);
        const { level, color } = classifyOnly(compositeScore);
        const compositeScoreHistory = calculateCompositeHistory(s, m, c, p, u, cc, k, t, f);

        const aiPrompt = `
당신은 한국의 거시경제 및 투자 전문가입니다.
다음 9개 지표를 바탕으로, 한국 경제의 전반적인 상태를 **일반인도 이해하기 쉽게 자세히** 설명하세요.
특히, 각 지표가 의미하는 바와 그것이 경제 전반에 어떤 영향을 주는지 자연스럽게 연결해서 서술하세요.
경제의 긍정적 요인과 부정적 요인을 구분하여 분석하고, 향후 전망에 대해서도 간결하게 언급하세요.

또한, 투자 전략 요약에서는 **개인 투자자가 참고할 만한 현실적인 조언**(예: 주식, 채권, 예금, 분산투자 등)을 2~3문장으로 명확히 제시하세요.

출력은 반드시 아래 JSON 형식으로 반환하세요.
코드블록(\`\`\`)을 사용하지 마세요.

{
  "analysis": "전체 경제 상황에 대한 상세 설명 (5문장 이상)",
  "recommendation_summary": "투자자에게 권장되는 전략 요약 (2~3문장)"
}

📊 데이터 요약:
- 종합 점수: ${compositeScore}점 (${level})
- 금리 스프레드: ${avgSpread.toFixed(2)}%
- M2 YoY: ${avgM2.toFixed(2)}%
- CPI YoY: ${avgCPI.toFixed(2)}%
- PPI YoY: ${avgPPI.toFixed(2)}%
- 실업률: ${avgUnemp.toFixed(2)}%
- CCSI: ${avgCCSI.toFixed(2)}
- KOSPI YoY: ${avgKOSPI.toFixed(2)}%
- 무역수지 YoY: ${avgTrade.toFixed(2)}%
- 환율 YoY: ${avgFX.toFixed(2)}%

이 지표들의 상호작용을 바탕으로 한국 경제의 현재 상태를 구체적으로 설명하고,
특히 '위험' 단계에 해당하는 요인이 무엇인지, '경계' 또는 '회복' 신호가 있다면 어떤 지표에서 나타나는지를 명시하세요.
`;


        const ai = await generateAIContent(aiPrompt);

        return {
            date: today,
            period: `${years}년`,
            classification: {
                level,
                color,
                description: ai?.analysis || "AI 분석을 불러오지 못했습니다.",
                recommendation: ai?.recommendation_summary || "요약 정보 없음.",
            },
            compositeScore,
            compositeScoreHistory,
            indicators: {
                spread: { latest: avgSpread.toFixed(2), chartData: s },
                m2: { latest: avgM2.toFixed(2), chartData: m },
                cpi: { latest: avgCPI.toFixed(2), chartData: c },
                ppi: { latest: avgPPI.toFixed(2), chartData: p },
                unemployment: { latest: avgUnemp.toFixed(2), chartData: u },
                ccsi: { latest: avgCCSI.toFixed(2), chartData: cc },
                kospi_yoy: { latest: avgKOSPI.toFixed(2), chartData: k },
                trade_yoy: { latest: avgTrade.toFixed(2), chartData: t },
                fx_change: { latest: avgFX.toFixed(2), chartData: f },
            },
        };
    } catch (e) {
        console.error("🚨 최종 분석 오류:", e.message);
        return { error: e.message };
    }
}

module.exports = { getInvestmentSignal };
