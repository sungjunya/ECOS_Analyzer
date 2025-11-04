// 🌐 server.js — ECOS Analyzer 안정형 서버 (Naver News, ECOS Definition 통합)
require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');
const axios = require('axios'); // ✅ axios 추가: 외부 API 요청에 사용

// [1] ✅ 네이버 API 키 설정 (⭐여기에 실제 발급받은 키를 넣어주세요⭐)
// 보안을 위해 실제 배포 시에는 이 값을 환경 변수로 관리하는 것을 권장합니다.
const NAVER_CLIENT_ID = process.env.NAVER_API_ID;
const NAVER_CLIENT_SECRET = process.env.NAVER_API_KEY;
const ECOS_API_KEY = process.env.ECOS_API_KEY; // ECOS 키는 환경 변수에서 가져온다고 가정
// ⭐ GEMINI API 키가 realEstateAnalyzer에서 사용되므로, 환경 변수로 관리하는 것이 좋습니다. ⭐
// const GEMINI_API_KEY = process.env.GEMINI_API_KEY; 

// ✅ 두 분석 모듈 불러오기
const { getInvestmentSignal } = require('./dataAnalyzer');
const { getRealEstateSignal } = require('./realEstateAnalyzer'); // ✅ realEstateAnalyzer 모듈이 정확하게 임포트되어 있습니다.

const app = express();
app.use(cors());
app.use(express.json());
// 'public' 디렉토리에 있는 정적 파일(예: index.html, CSS, JS)을 제공합니다.
app.use(express.static(path.join(__dirname, 'public')));

// ----------------------------------------------------------------------
// 기존 ECOS 데이터 라우트
// ----------------------------------------------------------------------

// ✅ 경제 신호 API (일반 투자)
// GET /api/signal?period=1y
app.get('/api/signal', async (req, res) => {
    try {
        const period = req.query.period || '1y';
        // dataAnalyzer.js의 함수 호출
        const data = await getInvestmentSignal(period);
        res.json(data);
    } catch (err) {
        console.error('🚨 경제 API 오류:', err);
        res.status(500).json({ error: '경제 신호 데이터를 불러오는 중 오류가 발생했습니다.' });
    }
});

// ✅ 부동산 신호 API
// GET /api/realestate?period=3y
app.get('/api/realestate', async (req, res) => {
    try {
        const period = req.query.period || '3y';
        // realEstateAnalyzer.js의 함수 호출
        const data = await getRealEstateSignal(period); // ✅ getRealEstateSignal 함수를 정확히 사용하고 있습니다.
        res.json(data);
    } catch (err) {
        console.error('🚨 부동산 API 오류:', err);
        res.status(500).json({ error: '부동산 데이터를 불러오는 중 오류가 발생했습니다.' });
    }
});


// ----------------------------------------------------------------------
// ✅ 신규 통합 API 라우트
// ----------------------------------------------------------------------

// [2] ✅ 네이버 뉴스 검색 API 라우트
// 사용법: /api/news?query=부동산
app.get('/api/news', async (req, res) => {
    // 쿼리 파라미터에서 검색 키워드를 가져오거나 기본값 '한국 경제' 사용
    const query = req.query.query || '한국 경제';
    const encodedQuery = encodeURI(query);

    // 네이버 검색 API URL (5개 최신순)
    const api_url = `https://openapi.naver.com/v1/search/news.json?query=${encodedQuery}&display=5&sort=date`;

    // 네이버 API 키가 설정되지 않았다면 오류 반환
    if (!NAVER_CLIENT_ID || !NAVER_CLIENT_SECRET) {
        return res.status(500).json({ success: false, message: '네이버 API 키가 설정되지 않았습니다.' });
    }

    try {
        const response = await axios.get(api_url, {
            headers: {
                'X-Naver-Client-Id': NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': NAVER_CLIENT_SECRET
            }
        });

        // HTML 태그를 제거하고 필요한 정보만 정리
        const newsItems = response.data.items.map(item => ({
            title: item.title.replace(/<[^>]*>?/gm, ''), // 제목 태그 제거
            link: item.link,
            description: item.description.replace(/<[^>]*>?/gm, ''), // 설명 태그 제거
            pubDate: item.pubDate
        }));

        res.json({ success: true, news: newsItems });

    } catch (error) {
        console.error('🚨 네이버 뉴스 API 호출 에러:', error.message);
        res.status(500).json({ success: false, message: '뉴스 데이터를 불러오는 데 실패했습니다.' });
    }
});


// [3] ✅ ECOS 통계 용어사전 API 라우트
// 사용법: /api/definition?word=소비자심리지수
app.get('/api/definition', async (req, res) => {
    const word = req.query.word;

    if (!word) {
        return res.status(400).json({ error: '검색할 용어(word)를 지정해야 합니다.' });
    }

    // ECOS 키 설정 확인
    if (!ECOS_API_KEY) {
        return res.status(500).json({ error: 'ECOS API 키가 환경 변수에 설정되지 않았습니다.' });
    }

    const encodedWord = encodeURIComponent(word);

    // ECOS 통계 용어사전 API URL 구성
    const apiUrl = `https://ecos.bok.or.kr/api/StatisticWord/${ECOS_API_KEY}/json/kr/1/10/${encodedWord}`;

    try {
        const response = await axios.get(apiUrl);
        const result = response.data.StatisticWord;

        if (result && result.row && result.row.length > 0) {
            // 용어설명(CONTENT)만 반환
            res.json({ success: true, definition: result.row[0].CONTENT });
        } else {
            res.json({ success: true, definition: '해당 용어에 대한 정의를 찾을 수 없습니다.' });
        }

    } catch (error) {
        console.error(`🚨 ECOS 용어사전 API 오류 (${word}):`, error.message);
        res.status(500).json({ error: '용어사전 데이터를 불러오는 중 오류가 발생했습니다.' });
    }
});


// ----------------------------------------------------------------------
// 프론트엔드 라우팅 및 서버 시작
// ----------------------------------------------------------------------

// ✅ 프론트엔드 라우팅 (SPA 지원)
app.get('*', (req, res) => {
    // 클라이언트 측 라우팅을 위해 모든 요청에 public/index.html을 반환
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`✅ 서버 실행 중: http://localhost:${PORT}`));


// Export the app for testing or serverless deployment (optional, but good practice)
module.exports = app;
