# lstm_model.py
import streamlit as st
import numpy as np
import pandas as pd 
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Input 
from tensorflow.keras.callbacks import EarlyStopping
import joblib
import os
import tensorflow as tf 
import numpy as np 

# ── 설정: 모델 저장 폴더 ──
MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

@st.cache_resource
def _get_model_and_scaler(df, symbol, time_steps=60):
    """실제 LSTM 모델을 학습하고 저장하는 내부 함수"""
    
    df = df.copy()
    
    # 1. 기술적 지표 추가 (총 13개 피처)
    
    # [기존 7개 피처 파생]
    df['SMA_5'] = df['Close'].rolling(5).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-6)
    df['RSI'] = 100 - (100 / (1 + rs))
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Volume_SMA'] = df['Volume'].rolling(20).mean()
    
    # 🚨 신규 6개 피처 추가 시작 (BB, OBV, Stochastic, ROC) 🚨
    
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
    
    # 2. NaN 값 제거 (지표 생성으로 인한 초기 NaN)
    df = df.dropna()
    
    # 3. 사용할 피처 정의 (총 13개)
    # PSR은 재무 지표이므로, LSTM 시퀀스에는 기술 지표만 사용하고, LLM 해석에만 사용합니다.
    features = ['Close', 'Volume', 'SMA_5', 'SMA_20', 'RSI', 'MACD', 'Volume_SMA', 
                'BB_Upper', 'BB_Lower', 'OBV', 'Stoch_K', 'Stoch_D', 'ROC']
    data = df[features].values
    
    # 데이터 부족 재검사
    if len(data) < time_steps:
        st.error(f"지표 생성 후 데이터 부족! {len(data)}일 < {time_steps}일")
        return None, None

    # 4. 스케일링
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(data)

    # 5. 시퀀스 데이터 생성
    X, y = [], []
    for i in range(time_steps, len(scaled)):
        X.append(scaled[i-time_steps:i])
        y.append(scaled[i, 0]) 
    X, y = np.array(X), np.array(y)

    # 6. LSTM 모델 정의 (다변량 features 개수 13개 반영)
    model = Sequential([
        Input(shape=(time_steps, len(features))), 
        LSTM(100, return_sequences=True), 
        LSTM(100),
        Dense(50),
        Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse')
    
    # 7. 모델 학습 
    with st.spinner("LSTM 다변량 모델 학습 중..."):
        model.fit(X, y, epochs=30, batch_size=32, verbose=0,
                  callbacks=[EarlyStopping(patience=7, restore_best_weights=True, monitor='loss')]) 

    # 8. 모델 및 스케일러 저장
    safe_symbol = symbol.replace(".", "_")
    scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")
    model_path = os.path.join(MODEL_DIR, f"model_{safe_symbol}_{time_steps}.keras")
    
    joblib.dump(scaler, scaler_path)
    model.save(model_path)
    
    st.success(f"다변량 모델 저장 완료: `{model_path}`")
    
    # BB_Std 컬럼을 제거하고 processed_df로 반환
    return scaler, model, df.drop(columns=['BB_Std'])

def train_lstm_model(df, symbol, time_steps=60):
    """Streamlit 세션 상태를 관리하는 외부 함수"""
    scaler, model, processed_df = _get_model_and_scaler(df, symbol, time_steps)
    
    if model:
        st.session_state.model_trained = True
        st.session_state.model_symbol = symbol
        st.session_state.model_time_steps = time_steps
        st.session_state.processed_df = processed_df