# lstm_model.py
import streamlit as st
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
from tensorflow.keras.callbacks import EarlyStopping
import joblib
import os

# ── 수정: 저장 폴더를 lstm/models 로 고정 ──
MODEL_DIR = "models"                     # ← 수정: lstm/models/
os.makedirs(MODEL_DIR, exist_ok=True)    # ← 수정: 자동 생성

@st.cache_resource
def get_scaler_and_model(df, symbol, time_steps=60):
    if len(df) < time_steps:
        st.error(f"데이터 부족! {len(df)}일 < {time_steps}일")
        return None, None

    close_prices = df['Close'].values.reshape(-1, 1)
    scaler = MinMaxScaler()
    scaled_data = scaler.fit_transform(close_prices)

    X, y = [], []
    for i in range(len(scaled_data) - time_steps):
        X.append(scaled_data[i:i + time_steps])
        y.append(scaled_data[i + time_steps, 0])
    X, y = np.array(X), np.array(y)

    model = Sequential([
        LSTM(50, return_sequences=True, input_shape=(time_steps, 1)),
        LSTM(50),
        Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse')
    model.fit(X, y, epochs=20, batch_size=64, verbose=0,
              callbacks=[EarlyStopping(patience=5, restore_best_weights=True)])

    safe_symbol = symbol.replace(".", "_")
    
    # ── 수정: models/ 폴더에 저장 ──
    scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")  # ← 수정
    model_path = os.path.join(MODEL_DIR, f"lstm_model_{safe_symbol}_{time_steps}.keras")  # ← 수정
    
    joblib.dump(scaler, scaler_path)
    model.save(model_path)

    st.success(f"모델 저장 완료: `{MODEL_DIR}/`")
    return scaler, model

def train_lstm_model(df, symbol, time_steps=60):
    scaler, model = get_scaler_and_model(df, symbol, time_steps)
    if model:
        st.session_state.model_trained = True
        st.session_state.model_symbol = symbol
        st.session_state.model_time_steps = time_steps