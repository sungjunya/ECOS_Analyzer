# lstm_model.py (수정된 최종 코드)
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
from sklearn.metrics import mean_squared_error 
from joblib import dump, load # joblib.load, joblib.dump 대신 명시적으로 임포트

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True)

@st.cache_resource
def _train_and_evaluate_model(df, symbol, time_steps=60): 
    df = df.copy()
    
    # ... (기술적 지표 생성 로직: 변동 없음)
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
    
    df['BB_Std'] = df['Close'].rolling(window=20).std()
    df['BB_Upper'] = df['SMA_20'] + (df['BB_Std'] * 2)
    df['BB_Lower'] = df['SMA_20'] - (df['BB_Std'] * 2)
    
    df['OBV'] = (df['Close'].diff().apply(np.sign) * df['Volume']).fillna(0).cumsum()
    
    high_14 = df['High'].rolling(window=14).max()
    low_14 = df['Low'].rolling(window=14).min()
    df['Stoch_K'] = 100 * ((df['Close'] - low_14) / (high_14 - low_14).replace(0, 1e-6))
    df['Stoch_D'] = df['Stoch_K'].rolling(window=3).mean()
    
    df['ROC'] = (df['Close'] - df['Close'].shift(9)) / df['Close'].shift(9) * 100
    
    df = df.dropna()
    
    features = ['Close', 'Volume', 'SMA_5', 'SMA_20', 'RSI', 'MACD', 'Volume_SMA', 
                'BB_Upper', 'BB_Lower', 'OBV', 'Stoch_K', 'Stoch_D', 'ROC']
    data = df[features].values
    
    if len(data) < time_steps:
        st.error(f"지표 생성 후 데이터 부족! {len(data)}일 < {time_steps}일")
        return None, None, None, None, None, None 

    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(data)
    
    dates_for_sequences = df.index[time_steps:] 

    X, y = [], []
    for i in range(time_steps, len(scaled)):
        X.append(scaled[i-time_steps:i])
        y.append(scaled[i, 0]) 
    X, y = np.array(X), np.array(y)

    train_size = int(len(X) * 0.8)
    X_train, X_test = X[:train_size], X[train_size:]
    y_train, y_test = y[:train_size], y[train_size:]
    
    test_dates = dates_for_sequences[train_size:]
    
    model = Sequential([
        Input(shape=(time_steps, len(features))), # Input Layer
        LSTM(100, return_sequences=True), # The Feature Extractor
        LSTM(100), # The Pattern Analyzer
        Dense(50), 
        Dense(1) # Output Layer
    ])
    model.compile(optimizer='adam', loss='mse') #Adaptive Moment Estimation
    
    with st.spinner("LSTM 다변량 모델 학습"):
        model.fit(X_train, y_train, epochs=30, batch_size=32, verbose=0,
                # EarlyStopping으로 7번 학습 시에도 Loss값 개선되지 않을 시 과적합으로 판단 (방지용)
                callbacks=[EarlyStopping(patience=7, restore_best_weights=True, monitor='loss')]) 

    scaled_test_y_pred = model.predict(X_test)
    
    # ----------------------------------------------------------------------------------
    # 🚨 [핵심 수정 부분] RMSE/MAE 계산을 위해 정규화된 값(y_test, scaled_test_y_pred)을 반환
    # ----------------------------------------------------------------------------------
    
    # 1. 지표 계산용: 정규화된 값 그대로 사용 (app.py의 calculate_metrics 함수에서 사용할 값)
    # y_test는 이미 정규화된 상태입니다. scaled_test_y_pred도 마찬가지입니다.
    test_y_true_scaled = y_test
    test_y_pred_scaled = scaled_test_y_pred.flatten() 

    # 2. 모델 및 스케일러 저장 (변동 없음)
    safe_symbol = symbol.replace(".", "_")
    scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")
    model_path = os.path.join(MODEL_DIR, f"model_{safe_symbol}_{time_steps}.keras")
    
    joblib.dump(scaler, scaler_path)
    model.save(model_path)
    
    st.success(f"다변량 모델 저장 완료: `{model_path}`")
    
    # 3. 반환 값 변경: test_y_true, test_y_pred를 scaled 값으로 변경
    return scaler, model, df.drop(columns=['BB_Std']), test_y_true_scaled, test_y_pred_scaled, test_dates 

def train_lstm_model(df, symbol, time_steps=60):
    # 🚨 _train_and_evaluate_model에서 scaled 값을 반환받음
    scaler, model, processed_df, test_y_true_scaled, test_y_pred_scaled, test_dates = _train_and_evaluate_model(df, symbol, time_steps)
    
    if model:
        st.session_state.model_trained = True
        st.session_state.model_symbol = symbol
        st.session_state.model_time_steps = time_steps
        st.session_state.processed_df = processed_df
        
        st.session_state.test_dates = test_dates
        
        # 🚨 app.py로 scaled 값을 전달하여, app.py에서 scaled 지표가 계산되도록 함
        return test_y_true_scaled, test_y_pred_scaled
    else:
        return np.array([]), np.array([])