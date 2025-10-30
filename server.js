require('dotenv').config();
const express = require('express');
const path = require('path');
const { getInvestmentSignal } = require('./services/dataAnalyzer');

const app = express();
const PORT = process.env.PORT || 3000;

// 정적 파일 제공
app.use(express.static(path.join(__dirname, 'public')));

// CORS 허용 (로컬 테스트용)
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  next();
});

// API 엔드포인트
app.get('/api/signal', async (req, res) => {
  try {
    const signalData = await getInvestmentSignal();
    res.json(signalData);
  } catch (error) {
    console.error("서버 오류:", error.message);
    res.status(500).json({
      error: error.message,
      code: error.code || 'UNKNOWN'
    });
  }
});

app.listen(PORT, () => {
  console.log(`서버 실행 중: http://localhost:${PORT}`);
  console.log("ECOS API 키:", process.env.ECOS_API_KEY ? 'Loaded' : 'Missing');
});