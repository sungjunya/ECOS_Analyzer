# predict.py
import numpy as np
import pandas as pd
from tensorflow.keras.models import load_model 
import joblib 
import os
import requests 
import json
import time 
from datetime import datetime, timedelta
import streamlit as st 
import requests.exceptions 
import numpy as np # np.sign 사용

# ── 설정 ──
MODEL_DIR = "models" 
API_MODEL_NAME = "gemini-2.5-flash-preview-09-2025" 

def add_technical_indicators(df):
    """
    LSTM 학습에 사용된 13가지 기술적 지표를 계산합니다.
    """
    df = df.copy()
    
    # [기존 7개 피처 파생]
    df['SMA_5'] = df['Close'].rolling(5).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs_calc = 100 - (100 / (1 + gain / loss.replace(0, np.nan))) # loss=0일 때 NaN
    df['RSI'] = np.where(loss == 0, np.where(gain > 0, 100, 0), rs_calc)
    
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    
    df['Volume_SMA'] = df['Volume'].rolling(20).mean()
    
    # 🚨 신규 6개 피처 추가 시작 🚨
    
    # 1. 볼린저 밴드 (BB)
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['SMA_20'] + (df['BB_Std'] * 2)
    df['BB_Lower'] = df['SMA_20'] - (df['BB_Std'] * 2)
    
    # 2. OBV (On-Balance Volume)
    df['OBV'] = (df['Close'].diff().apply(np.sign) * df['Volume']).fillna(0).cumsum()
    
    # 3. 스토캐스틱 오실레이터 (Stochastic Oscillator)
    high_14 = df['High'].rolling(window=14).max()
    low_14 = df['Low'].rolling(window=14).min()
    df['Stoch_K'] = 100 * ((df['Close'] - low_14) / (high_14 - low_14).replace(0, 1e-6))
    df['Stoch_D'] = df['Stoch_K'].rolling(window=3).mean()
    
    # 4. ROC (Rate of Change)
    df['ROC'] = (df['Close'] - df['Close'].shift(9)) / df['Close'].shift(9) * 100
    
    # 🚨 신규 지표 추가 끝 🚨
    
    return df.drop(columns=['BB_Std']).dropna()

def _generate_mock_interpretation(company, final_predicted_price, change_pct):
    """API 호출 실패 시 사용자에게 보여줄 가상 해석을 생성합니다."""
    trend = "상승 추세" if change_pct > 0 else "하락 추세" if change_pct < 0 else "보합세"
    
    return (
        f"**[🚨 네트워크/API 오류로 인한 가상 분석 리포트]**\n\n"
        f"현재 {company} 종목에 대한 AI 연결에 실패하였습니다. "
        f"**LSTM 모델 단순 예측 결과:** 향후 30일간 {trend}가 예상됩니다. "
        f"30일 후 예측 종가는 약 **{final_predicted_price:,.0f} KRW**이며, 이는 현재가 대비 "
        f"**{change_pct:+.1f}%**의 변동률을 시사합니다."
    )

# 🚨 [수정] LLM 분석을 위해 신규 지표를 인수로 추가했습니다.
def _generate_interpretation(company, current_price, final_predicted_price, change_pct, 
                             rsi, volume_trend, stoch_k, stoch_d, roc, df_pred):
    """
    Gemini API를 호출하여 LSTM 예측 결과에 대한 전문적인 해석을 생성합니다.
    """
    
    API_KEY = os.getenv('GEMINI_API_KEY', os.getenv('__api_key', '')).strip()
    
    if not API_KEY:
        return _generate_mock_interpretation(company, final_predicted_price, change_pct)
        
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{API_MODEL_NAME}:generateContent"
        f"?key={API_KEY}"
    )
    
    # 🚨 [수정] 분석 데이터에 Stoch K/D 및 ROC 추가
    analysis_data = {
        "종목": company,
        "현재가": f"{current_price:,.0f} KRW",
        "30일 후 예측가": f"{final_predicted_price:,.0f} KRW",
        "예상 등락률": f"{change_pct:+.1f}%",
        "RSI (현재)": f"{rsi:.1f}",
        "Stoch K/D (현재)": f"{stoch_k:.1f} / {stoch_d:.1f}",
        "ROC 9일 변동률": f"{roc:+.1f}%",
        "거래량 추세": volume_trend,
        "10일 가격 변동성 (초기, 중기, 후기)": {
            "초기 10일 변동 (%)": ((df_pred['Close'].iloc[9] - current_price) / current_price * 100).round(1),
            "중기 10일 변동 (%)": ((df_pred['Close'].iloc[19] - df_pred['Close'].iloc[9]) / df_pred['Close'].iloc[9] * 100).round(1),
            "후기 10일 변동 (%)": ((df_pred['Close'].iloc[29] - df_pred['Close'].iloc[19]) / df_pred['Close'].iloc[19] * 100).round(1),
        }
    }
    
    system_prompt = (
        "당신은 인공지능 기반의 금융 기술 분석가입니다. "
        "주어진 LSTM 예측 결과와 핵심 기술 지표를 바탕으로, "
        "시장의 변동성, 추세의 강도, 그리고 예상되는 주가 궤적에 초점을 맞춘 "
        "객관적이고 간결한 한국어(하십시오체) 전문가 리포트를 **5줄 이상**으로 작성해야 합니다. "
        "절대로 '투자 조언', '매수', '매도', '추천' 등의 단어를 사용해서는 안 됩니다."
    )
    
    user_query = (
        f"LSTM 모델이 예측한 '{company}'의 향후 30일 주가 추이 및 기술적 지표 분석 데이터입니다. "
        f"이 데이터를 분석하여 전문적인 해석 리포트를 작성해 주세요. "
        f"분석 데이터: {json.dumps(analysis_data, ensure_ascii=False)}"
    )

    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "tools": [{"google_search": {}}], 
    }
    
    # API 호출 (지수 백오프 적용)
    max_retries = 5
    response = None
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload), timeout=30)
            response.raise_for_status() 
            result = response.json()
            
            text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '해석을 생성하는 데 실패했습니다.')
            return text
            
        except requests.exceptions.RequestException as e:
            if response is not None and response.status_code == 403:
                 print(f"CRITICAL 403 ERROR: API Key or Quota issue suspected. URL check: {url}")
            
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"[{attempt + 1}/{max_retries}] API 요청 실패: {e}. {wait_time}초 후 재시도합니다.") 
                time.sleep(wait_time)
            else:
                error_msg = "네트워크 오류 또는 API 호출 한도 초과로 인해 예측 해석을 불러올 수 없습니다."
                print(f"최종 실패: {error_msg}")
                return _generate_mock_interpretation(company, final_predicted_price, change_pct)
        except Exception as e:
            print(f"응답 처리 중 오류 발생: {e}")
            return "예측 결과를 해석하는 중 내부 오류가 발생했습니다."
            
    return _generate_mock_interpretation(company, final_predicted_price, change_pct)


def predict_next_month(df, symbol, time_steps, company): 
    """저장된 다변량 모델을 사용하여 다음 30일 주가를 예측하고 LLM 해석을 반환합니다."""
    
    safe = symbol.replace(".", "_")
    scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe}_{time_steps}.pkl")
    model_path = os.path.join(MODEL_DIR, f"model_{safe}_{time_steps}.keras") 

    if not os.path.exists(scaler_path) or not os.path.exists(model_path):
        return None, None, f"'{company}' 모델이 없습니다. 'LSTM 학습 및 30일 예측 시작' 버튼으로 자동 학습하세요."

    try:
        scaler = joblib.load(scaler_path)
        model = load_model(model_path)
    except Exception as e:
        return None, None, f"모델 로드 실패 ({e}). 재학습 후 재시도하세요."

    # 1. 예측에 필요한 기술적 지표 추가
    df_proc = add_technical_indicators(df.copy())
    # 🚨 [수정] 피처 목록 업데이트 (lstm_model.py와 일치해야 함 - 13개)
    features = ['Close', 'Volume', 'SMA_5', 'SMA_20', 'RSI', 'MACD', 'Volume_SMA', 
                'BB_Upper', 'BB_Lower', 'OBV', 'Stoch_K', 'Stoch_D', 'ROC']
    
    if len(df_proc) < time_steps:
        return None, None, "기술 지표 생성 후 과거 데이터 부족 (time_steps보다 짧음)"

    # 2. 스케일링 및 최근 데이터 준비
    data_scaled = scaler.transform(df_proc[features].values) 
    recent = data_scaled[-time_steps:] 
    
    # 3. 예측 루프 (안정화된 로직 적용)
    predictions = []
    current_input = recent.reshape(1, time_steps, len(features)) 

    for _ in range(30):
        predicted_scaled_price = model.predict(current_input, verbose=0)[0, 0]
        predictions.append(predicted_scaled_price)
        
        # 다음 단계의 입력 시퀀스 준비
        temp_scaled = current_input[0, -1].copy()
        temp_scaled[0] = predicted_scaled_price

        # 나머지 피처(1~12 인덱스)는 마지막 값 유지
        new_scaled_sequence = np.append(current_input[0, 1:], [temp_scaled], axis=0)
        current_input = new_scaled_sequence.reshape(1, time_steps, len(features))

    # 4. 역변환
    dummy = np.zeros((30, len(features)))
    dummy[:, 0] = predictions 
    pred_prices = scaler.inverse_transform(dummy)[:, 0]

    # 5. 결과 DataFrame 생성
    last_date = df.index[-1]
    dates = [last_date + timedelta(days=i+1) for i in range(30)]
    pred_df = pd.DataFrame({'Close': pred_prices}, index=dates)
    
    # 6. LLM 분석을 위한 통계량 계산
    final_price = float(pred_prices[-1])
    current_price = float(df['Close'].iloc[-1])
    change_pct = (final_price - current_price) / current_price * 100 if current_price != 0 else 0
    
    # 🚨 [수정] LLM 분석을 위한 추가 지표 추출
    latest_indicators = df_proc.iloc[-1]
    
    rsi = latest_indicators['RSI']
    stoch_k = latest_indicators['Stoch_K']
    stoch_d = latest_indicators['Stoch_D']
    roc = latest_indicators['ROC']
    
    volume_trend = "증가" if df['Volume'].iloc[-1] > df['Volume'].mean() else "감소"
    
    # 7. LLM 해석 생성
    interpretation = _generate_interpretation(
        company=company,
        current_price=current_price,
        final_predicted_price=final_price,
        change_pct=change_pct,
        rsi=rsi,
        volume_trend=volume_trend,
        stoch_k=stoch_k, 
        stoch_d=stoch_d, 
        roc=roc,         
        df_pred=pred_df 
    )
    
    return pred_df, final_price, interpretation