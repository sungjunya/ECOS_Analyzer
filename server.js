// server.js
require('dotenv').config(); // .env 파일 로드
const express = require('express');
const path = require('path');
const { getInvestmentSignal } = require('./services/dataAnalyzer');

const app = express();
const PORT = 3000;

// 정적 파일 제공
app.use(express.static(path.join(__dirname, 'public')));

// API 엔드포인트: 분석 결과를 제공
app.get('/api/signal', async (req, res) => {
    try {
        const signalData = await getInvestmentSignal();
        res.json(signalData);
    } catch (error) {
        console.error("API 처리 오류:", error.message);
        // 클라이언트에게 오류 메시지를 500 상태 코드와 함께 전달
        res.status(500).json({ error: error.message || '데이터 분석 중 서버 오류 발생' });
    }
});

app.listen(PORT, () => {
    console.log(`Server running at http://localhost:${PORT}`);
    console.log("ECOS API KEY:", process.env.ECOS_API_KEY ? 'Loaded' : 'Missing');
});