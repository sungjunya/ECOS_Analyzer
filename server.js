// server.js
require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');
const { getInvestmentSignal } = require('./dataAnalyzer');

const app = express();
const PORT = process.env.PORT || 3000;

// 정적 파일 제공 (public 폴더)
app.use(express.static(path.join(__dirname, 'public')));

app.use(cors());
app.use(express.json());

// API 엔드포인트
app.get('/api/signal', async (req, res) => {
  const period = req.query.period || '1y';
  try {
    const data = await getInvestmentSignal(period);
    res.json(data);
  } catch (err) {
    console.error('API 에러:', err);
    res.status(500).json({ error: err.message });
  }
});

// 모든 경로는 index.html로
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`서버 실행 중: http://localhost:${PORT}`);
});