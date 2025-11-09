require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');
const axios = require('axios');

// 환경 변수
const NAVER_CLIENT_ID = process.env.NAVER_API_ID;
const NAVER_CLIENT_SECRET = process.env.NAVER_API_KEY;
const ECOS_API_KEY = process.env.ECOS_API_KEY;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

// 분석 모듈 불러오기
const { getInvestmentSignal } = require('./dataAnalyzer');
const { getRealEstateSignal } = require('./realEstateAnalyzer');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ----------------------- 경제 신호 -----------------------
app.get('/api/signal', async (req, res) => {
  try {
    const period = req.query.period || '1y';
    const data = await getInvestmentSignal(period);
    res.json(data);
  } catch (err) {
    console.error('🚨 경제 API 오류:', err);
    res.status(500).json({ error: '경제 신호 로드 오류' });
  }
});

// ----------------------- 부동산 신호 -----------------------
app.get('/api/realestate', async (req, res) => {
  try {
    const period = req.query.period || '3y';
    const data = await getRealEstateSignal(period);
    res.json(data);
  } catch (err) {
    console.error('🚨 부동산 API 오류:', err);
    res.status(500).json({ error: '부동산 데이터 로드 실패' });
  }
});

// ----------------------- 네이버 뉴스 -----------------------
app.get('/api/news', async (req, res) => {
  const query = req.query.query || '한국 경제';
  const encodedQuery = encodeURI(query);
  const api_url = `https://openapi.naver.com/v1/search/news.json?query=${encodedQuery}&display=5&sort=date`;

  if (!NAVER_CLIENT_ID || !NAVER_CLIENT_SECRET) {
    return res.status(500).json({ success: false, message: '네이버 API 키 미설정' });
  }

  try {
    const response = await axios.get(api_url, {
      headers: {
        'X-Naver-Client-Id': NAVER_CLIENT_ID,
        'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
      },
    });

    const newsItems = response.data.items.map(item => ({
      title: item.title.replace(/<[^>]*>?/gm, ''),
      link: item.link,
      description: item.description.replace(/<[^>]*>?/gm, ''),
      pubDate: item.pubDate,
    }));

    res.json({ success: true, news: newsItems });
  } catch (error) {
    console.error('🚨 네이버 뉴스 API 오류:', error.message);
    res.status(500).json({ success: false, message: '뉴스 호출 실패' });
  }
});

// ----------------------- ECOS 용어사전 -----------------------
app.get('/api/definition', async (req, res) => {
  const word = req.query.word;
  if (!word) return res.status(400).json({ error: 'word 파라미터 필요' });
  if (!ECOS_API_KEY) return res.status(500).json({ error: 'ECOS 키 미설정' });

  const apiUrl = `https://ecos.bok.or.kr/api/StatisticWord/${ECOS_API_KEY}/json/kr/1/10/${encodeURIComponent(word)}`;
  try {
    const response = await axios.get(apiUrl);
    const result = response.data.StatisticWord;
    if (result?.row?.length > 0)
      res.json({ success: true, definition: result.row[0].CONTENT });
    else res.json({ success: true, definition: '정의 없음' });
  } catch (err) {
    console.error('🚨 ECOS 용어사전 API 오류:', err.message);
    res.status(500).json({ error: '용어사전 불러오기 실패' });
  }
});

// ----------------------- 서버 실행 -----------------------
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`✅ 서버 실행 중: http://localhost:${PORT}`));

module.exports = app;
