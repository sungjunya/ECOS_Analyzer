// ====================================================================
// 📈 realEstateAnalyzer.js — ECOS 기반 한국 부동산 5단계 위험도 분석기 (최종 안정형)
// - "중립" 제거: 반드시 5단계 중 하나만 반환 (최대 위험 / 긴축 경계 / 침체 탈출 / 확장 초기 / 침체기)
// - 1y/3y/5y별 가중 평균 반영(avgWeighted)
// - Gemini AI 해설 + 투자 전략 JSON 출력
// - server.js와 완벽 호환(module.exports 구조 통일)
// ====================================================================

"use strict";

const axios = require("axios");

// --------------------------------------------------------------------
// [1] 환경 변수 및 상수
// --------------------------------------------------------------------
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || "";
const GEMINI_API_URL =
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent";
const ECOS_API_KEY = process.env.ECOS_API_KEY || "";

function getTodayYYYYMM() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}`;
}
const today = getTodayYYYYMM();

// --------------------------------------------------------------------
// [2] ECOS API 설정
// --------------------------------------------------------------------
const API_CONFIG = {
  KEY: ECOS_API_KEY,
  BASE_URL: "https://ecos.bok.or.kr/api/StatisticSearch",
  LANG: "kr",
  TYPE: "json",
  P_START: 1,
  P_END: 1000,
  CYCLE: "M",
  START_DATE: "201001",
  END_DATE: today,
};

// --------------------------------------------------------------------
// [3] 데이터 유틸 함수
// --------------------------------------------------------------------
function avgWeighted(arr) {
  if (!arr || arr.length === 0) return 0;
  let total = 0, weightSum = 0;
  for (let i = 0; i < arr.length; i++) {
    const w = (i + 1) ** 2; // 최근 데이터에 더 큰 가중치
    total += arr[i].value * w;
    weightSum += w;
  }
  return total / weightSum;
}

function calculateYoY(data) {
  const map = new Map(data.map(d => [d.time, d.value]));
  const result = [];
  data.forEach(d => {
    const prev = `${parseInt(d.time.slice(0, 4)) - 1}${d.time.slice(4)}`;
    if (map.has(prev) && map.get(prev) !== 0) {
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

function f2(n) {
  const v = Number(n);
  if (!isFinite(v)) return "0.00";
  return v.toFixed(2);
}

// --------------------------------------------------------------------
// [4] ECOS fetch 함수
// --------------------------------------------------------------------
async function fetchIndicatorData(statCode, itemCode = "", cycle = "M") {
  if (!API_CONFIG.KEY) {
    console.warn("⚠️ ECOS_API_KEY가 설정되지 않았습니다.");
    return [];
  }

  let itemPath = "";
  if (Array.isArray(itemCode)) itemPath = "/" + itemCode.join("/");
  else if (typeof itemCode === "string" && itemCode.trim() !== "")
    itemPath = `/${itemCode}`;

  const url = `${API_CONFIG.BASE_URL}/${API_CONFIG.KEY}/${API_CONFIG.TYPE}/${API_CONFIG.LANG}/${API_CONFIG.P_START}/${API_CONFIG.P_END}/${statCode}/${cycle}/${API_CONFIG.START_DATE}/${API_CONFIG.END_DATE}${itemPath}`;

  try {
    const { data } = await axios.get(url, { timeout: 15000 });
    if (data?.RESULT?.CODE && data.RESULT.CODE !== "000") {
      console.error(`🚨 ECOS 오류 [${statCode}]: ${data.RESULT.MESSAGE}`);
      return [];
    }
    const rows = data?.StatisticSearch?.row || [];
    return rows
      .map(r => ({ time: r.TIME, value: parseFloat(r.DATA_VALUE) }))
      .filter(d => !isNaN(d.value));
  } catch (err) {
    console.error(`🚨 ECOS 통신 오류 [${statCode}]`, err.message);
    return [];
  }
}

// --------------------------------------------------------------------
// [5] 부동산 위험도 분류 (5단계 고정, 중립 없음)
// --------------------------------------------------------------------
const RISK_DESCRIPTIONS = {
  red: "금리·공급 동시 상승, 급락 및 유동성 경색 위험.",
  orange: "과열 국면의 단기 조정 가능성.",
  yellow: "전세 상승, 매매 하락 둔화, 회복 초기.",
  green: "매매 상승 전환, 거래 회복 구간.",
  blue: "매매·전세 모두 하락세, 거래 위축.",
};

function classifyRealEstateRisk(saleYoY, rentYoY, permitYoY, baseRate, m2YoY) {
    // 🔴 최대 위험: 금리 매우 높고(>3.4), 공급 증가, 유동성↓, 가격 약세
    if (baseRate > 3.4 && permitYoY > 3 && m2YoY < 5 && saleYoY < 0 && rentYoY < 0)
      return { level: "최대 위험", color: "red", description: "금리·공급 동시 상승, 급락 및 유동성 경색 위험." };
  
    // 🟧 긴축 경계: 금리 약 2.8~3.4%, 수요 회복 조짐, M2 높음
    if (baseRate >= 2.8 && baseRate <= 3.4 && (saleYoY > 0.2 || rentYoY > 0.2) && m2YoY >= 6)
      return { level: "긴축 경계", color: "orange", description: "과열 국면의 단기 조정 가능성." };
  
    // 🟨 침체 탈출: 금리 낮고(<3.2), 매매 하락 둔화(-1~+1.2), 전세≥0, M2≥6
    if (baseRate < 3.2 && saleYoY > -1 && saleYoY < 1.2 && rentYoY >= 0 && m2YoY >= 6)
      return { level: "침체 탈출", color: "yellow", description: "전세 상승, 매매 하락 둔화, 회복 초기." };
  
    // 🟩 확장 초기: 금리 낮고(<2.8), 매매·전세 동반 상승, M2↑↑
    if (baseRate < 2.8 && saleYoY >= 0.7 && rentYoY >= 0.4 && m2YoY >= 7)
      return { level: "확장 초기", color: "green", description: "매매 상승 전환, 거래 회복 구간." };
  
    // 🟦 침체기: 나머지 모든 경우
    return { level: "침체기", color: "blue", description: "매매·전세 모두 하락세, 거래 위축." };
  }
  

// --------------------------------------------------------------------
// [6] Gemini AI 프롬프트 생성기
// --------------------------------------------------------------------
function buildAIPrompt({ yearsLabel, riskLevel, riskDesc, rate, saleYoY, rentYoY, permitYoY, m2YoY }) {
    return `
  너는 한국 부동산 시장을 분석하는 거시경제 전문가다.
  아래 데이터를 기반으로, 한국 부동산의 현재 상태를 **8~12문장**으로 자세히 설명하고
  개인 투자자가 참고할 전략을 **2~3문장**으로 요약하라.
  출력은 반드시 **JSON 형식**으로 하고, 코드블록(\`\`\`)을 절대 사용하지 마라.
  
  형식:
  {
    "analysis": "현재 부동산 위험 등급: ${riskLevel}이며, ... (8~12문장)",
    "recommendation_summary": "2~3문장, 개인 투자자 관점의 현실적 조언 ('매수', '관망', '매도' 중 하나 포함)"
  }
  
  📊 데이터 요약 (${yearsLabel}):
  - 위험도: ${riskLevel} (${riskDesc})
  - 기준금리: ${f2(rate)}%
  - 주택매매가격지수(YoY): ${f2(saleYoY)}%
  - 주택전세가격지수(YoY): ${f2(rentYoY)}%
  - 건축허가면적(YoY): ${f2(permitYoY)}%
  - 광의통화량(M2 YoY): ${f2(m2YoY)}%
  
  작성 규칙:
  - 'analysis'는 반드시 "현재 부동산 위험 등급: ${riskLevel}이며, ..."로 시작.
  - 금리·전세·매매·공급(M2) 간 상호작용을 구체적으로 서술.
  - 공급(허가YoY)이 낮으면 향후 공급 부족 → 가격상승 위험을 연결.
  - M2가 높을수록 유동성 유입 가능성을 설명.
  - 전략에는 '매수', '관망', 또는 '매도' 중 하나를 포함하고, 투자자에게 현실적 조언을 제시.
  - 전체 문장은 반드시 **존댓말(합니다체)**로 작성하며, 반말이나 비격식체는 절대 사용하지 않습니다.
  `.trim();
  }
  

// --------------------------------------------------------------------
// [7] Gemini AI 호출
// --------------------------------------------------------------------
function safeParseGemini(text) {
  if (!text || typeof text !== "string") {
    return { analysis: "AI 분석 실패", recommendation_summary: "관망 권고" };
  }
  const fence = text.match(/```[a-zA-Z]*\n?([\s\S]*?)```/);
  const raw = (fence ? fence[1] : text).trim();

  if (raw.startsWith("{") && raw.endsWith("}")) {
    try {
      return JSON.parse(raw);
    } catch (_) {}
  }

  const a = raw.match(/"analysis"\s*:\s*"([\s\S]*?)"\s*(,|\})/);
  const r = raw.match(/"recommendation_summary"\s*:\s*"([\s\S]*?)"\s*(,|\})/);
  return {
    analysis: a?.[1] || "AI 분석 실패",
    recommendation_summary: r?.[1] || "관망 권고",
  };
}

async function generateAIContent(prompt) {
  if (!GEMINI_API_KEY) {
    console.warn("⚠️ GEMINI_API_KEY 미설정 → 기본 분석 제공");
    return {
      analysis: "AI 키가 없어 기본 분석만 표시됩니다.",
      recommendation_summary: "관망 권고",
    };
  }

  const payload = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { temperature: 0.7, responseMimeType: "text/plain" },
  };

  try {
    const res = await axios.post(`${GEMINI_API_URL}?key=${GEMINI_API_KEY}`, payload, {
      headers: { "Content-Type": "application/json" },
      timeout: 20000,
    });

    const text =
      res?.data?.candidates?.[0]?.content?.parts?.[0]?.text ||
      res?.data?.candidates?.[0]?.content?.parts?.[0]?.inline_data?.data ||
      "";
    return safeParseGemini(text);
  } catch (err) {
    console.error("🚨 Gemini 호출 실패:", err.message);
    return {
      analysis: "AI 분석 실패 (응답 오류)",
      recommendation_summary: "관망 권고",
    };
  }
}

// --------------------------------------------------------------------
// [8] 메인 함수
// --------------------------------------------------------------------
async function getRealEstateSignal(period = "5y") {
  const yearsMap = { "1y": 1, "3y": 3, "5y": 5 };
  const years = yearsMap[period] || 5;
  const yearsLabel = `${years}년`;

  try {
    const [baseRate, m2, sale, rent, permit] = await Promise.all([
      fetchIndicatorData("722Y001", "0101000"), // 기준금리
      fetchIndicatorData("101Y004", "BBHA01"),  // M2
      fetchIndicatorData("901Y062", "P63A"),    // 매매
      fetchIndicatorData("901Y063", "P64A"),    // 전세
      fetchIndicatorData("901Y037", ["I43AA", "1"]), // 허가
    ]);

    const sRate = sliceYears(baseRate, years);
    const sM2YoY = sliceYears(calculateYoY(m2), years);
    const sSaleYoY = sliceYears(calculateYoY(sale), years);
    const sRentYoY = sliceYears(calculateYoY(rent), years);
    const sPermitYoY = sliceYears(calculateYoY(permit), years);

    const avgRate = avgWeighted(sRate);
    const avgM2YoY = avgWeighted(sM2YoY);
    const avgSaleYoY = avgWeighted(sSaleYoY);
    const avgRentYoY = avgWeighted(sRentYoY);
    const avgPermitYoY = avgWeighted(sPermitYoY);

    const risk = classifyRealEstateRisk(avgSaleYoY, avgRentYoY, avgPermitYoY, avgRate, avgM2YoY);
    const prompt = buildAIPrompt({
      yearsLabel,
      riskLevel: risk.level,
      riskDesc: risk.description,
      rate: avgRate,
      saleYoY: avgSaleYoY,
      rentYoY: avgRentYoY,
      permitYoY: avgPermitYoY,
      m2YoY: avgM2YoY,
    });
    const ai = await generateAIContent(prompt);

    const shortSummary = `금리 ${f2(avgRate)}%, 매매 ${f2(avgSaleYoY)}%, 전세 ${f2(avgRentYoY)}%, 허가 ${f2(avgPermitYoY)}%, M2 ${f2(avgM2YoY)}% → ${risk.level}`;

    return {
      date: today,
      period: yearsLabel,
      risk: {
        level: risk.level,
        color: risk.color,
        description: risk.description,
        summary: ai.analysis,
        recommendation: ai.recommendation_summary,
      },
      shortSummary,
      indicators: {
        salePriceYoY: { latest: f2(avgSaleYoY), chartData: sSaleYoY },
        rentPriceYoY: { latest: f2(avgRentYoY), chartData: sRentYoY },
        interestRate: { latest: f2(avgRate), chartData: sRate },
        m2YoY: { latest: f2(avgM2YoY), chartData: sM2YoY },
        permitYoY: { latest: f2(avgPermitYoY), chartData: sPermitYoY },
      },
    };
  } catch (err) {
    console.error("🚨 부동산 분석 오류:", err.message);
    return { error: err.message };
  }
}

// --------------------------------------------------------------------
// [9] 모듈 내보내기 (server.js 호환형)
// --------------------------------------------------------------------
module.exports = { getRealEstateSignal };

