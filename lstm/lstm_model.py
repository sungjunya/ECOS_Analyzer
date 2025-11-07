import streamlit as st
import numpy as np
import pandas as pd # pandas import 추가
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
# 🚨 Input 레이어를 사용하기 위해 import에 추가
from tensorflow.keras.layers import LSTM, Dense, Input # Input 추가
from tensorflow.keras.callbacks import EarlyStopping
import joblib
import os

# ── 설정: 모델 저장 폴더 ──
MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

# 함수 이름 및 구조 변경: 기존 train_lstm_model을 get_scaler_and_model로 복구하고, 
# 다변량 학습 로직을 적용하며 상태 관리 로직을 train_lstm_model로 분리합니다.

@st.cache_resource
def _get_model_and_scaler(df, symbol, time_steps=60):
    """실제 LSTM 모델을 학습하고 저장하는 내부 함수"""
    if len(df) < time_steps:
        st.error(f"데이터 부족! {len(df)}일 < {time_steps}일")
        return None, None
    
    # 데이터 복사 및 기술적 지표 생성 (친구 코드의 핵심)
    df = df.copy()
    
    # 1. 기술적 지표 추가
    df['SMA_5'] = df['Close'].rolling(5).mean()
    df['SMA_20'] = df['Close'].rolling(20).mean()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    ema12 = df['Close'].ewm(span=12).mean()
    ema26 = df['Close'].ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['Volume_SMA'] = df['Volume'].rolling(20).mean()
    
    # 2. NaN 값 제거 (지표 생성으로 인한 초기 NaN)
    df = df.dropna()

    # 3. 사용할 피처 정의 (다변량)
    features = ['Close', 'Volume', 'SMA_5', 'SMA_20', 'RSI', 'MACD', 'Volume_SMA']
    data = df[features].values
    
    # 데이터 부족 재검사 (지표 생성 후 데이터가 90일 미만으로 줄어들 수 있음)
    if len(data) < time_steps:
        st.error(f"지표 생성 후 데이터 부족! {len(data)}일 < {time_steps}일")
        return None, None

    # 4. 스케일링
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(data)

    # 5. 시퀀스 데이터 생성 (X: 시퀀스, y: 다음 종가)
    X, y = [], []
    # y는 종가(Close)에 해당하는 인덱스 0을 예측합니다.
    for i in range(time_steps, len(scaled)):
        X.append(scaled[i-time_steps:i])
        y.append(scaled[i, 0]) 
    X, y = np.array(X), np.array(y)

    # 6. LSTM 모델 정의 (경고 제거 로직 적용)
    model = Sequential([
        Input(shape=(time_steps, len(features))), # 💡 Input 레이어 추가 및 다변량 features 개수 반영
        LSTM(100, return_sequences=True), # input_shape 제거
        LSTM(100),
        Dense(50),
        Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse')
    
    # 7. 모델 학습 (val_loss 경고 제거 로직 적용)
    with st.spinner("LSTM 다변량 모델 학습 중..."):
        model.fit(X, y, epochs=30, batch_size=32, verbose=0,
                  callbacks=[EarlyStopping(patience=7, restore_best_weights=True, monitor='loss')]) # monitor='loss' 명시

    # 8. 모델 및 스케일러 저장
    safe_symbol = symbol.replace(".", "_")
    scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")
    model_path = os.path.join(MODEL_DIR, f"model_{safe_symbol}_{time_steps}.keras")
    
    joblib.dump(scaler, scaler_path)
    model.save(model_path)
    
    st.success(f"다변량 모델 저장 완료: `{model_path}`")
    
    return scaler, model, df # 마지막에 지표가 추가된 df도 반환

def train_lstm_model(df, symbol, time_steps=60):
    """Streamlit 세션 상태를 관리하는 외부 함수"""
    # 내부 학습 함수 호출
    scaler, model, processed_df = _get_model_and_scaler(df, symbol, time_steps)
    
    if model:
        # 학습 성공 시 세션 상태 업데이트
        st.session_state.model_trained = True
        st.session_state.model_symbol = symbol
        st.session_state.model_time_steps = time_steps
        st.session_state.processed_df = processed_df # LLM 분석에 사용될 지표 포함 데이터 저장