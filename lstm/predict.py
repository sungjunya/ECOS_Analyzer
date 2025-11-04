import numpy as np
import pandas as pd
from tensorflow.keras.models import load_model
import joblib # 💡 pickle 대신 joblib 사용
import os
# from data_loader import get_ticker_by_name # 실제 로직에서는 필요하지만 여기서는 생략

# ── lstm_model.py와 동일한 설정 ──
MODEL_DIR = "models" # 모델 저장 폴더

def predict_next_month(df, symbol, time_steps):
    """저장된 모델과 스케일러를 사용하여 다음 1개월(대략 30일) 주가를 예측합니다."""
    
    # .을 _로 치환하여 파일 경로 안전하게 만듦
    safe_symbol = symbol.replace(".", "_") 
    
    # 💡 [수정] 모델 파일 경로 및 확장자 (.keras) 설정
    model_path = os.path.join(MODEL_DIR, f"lstm_model_{safe_symbol}_{time_steps}.keras")
    
    # 💡 [수정] 스케일러 파일 경로 (.pkl) 설정
    scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")

    # 파일 존재 여부 확인
    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        print(f"Model or scaler file not found. Please train the model first.")
        return None, None
    
    try:
        # 💡 [수정] joblib을 사용하여 MinMaxScaler 객체 로드
        scaler = joblib.load(scaler_path)
            
        # 모델 로드
        model = load_model(model_path)
        
    except Exception as e:
        print(f"Error loading model or scaler: {e}")
        return None, None

    # 'Close' 가격만 사용
    data = df.filter(['Close'])
    
    # 테스트 데이터셋: 마지막 time_steps 일 데이터 사용
    last_data = data[-time_steps:].values
    
    # 로드된 스케일러를 사용하여 데이터 변환 (fit_transform이 아님, transform만 사용)
    last_data_scaled = scaler.transform(last_data)
    
    # LSTM 입력 형태로 변경 (1, time_steps, 1)
    X_test = last_data_scaled.reshape(1, time_steps, 1)
    
    # 예측 수행 (정규화된 값)
    pred_price_scaled = model.predict(X_test, verbose=0)
    
    # 예측 결과를 원래의 스케일로 역변환
    # 역변환을 위해 dummy array를 생성하여 2차원 형태로 만듭니다.
    dummy_array = np.zeros(shape=(len(pred_price_scaled), data.shape[1]))
    dummy_array[:, 0] = pred_price_scaled.flatten()
    
    # 역변환하여 최종 예측 가격 획득
    pred_price = scaler.inverse_transform(dummy_array)[:, 0][0]
    
    # 현재 가격
    current_price = df['Close'].iloc[-1]
    
    # 변동률 계산
    change_pct = ((pred_price - current_price) / current_price) * 100
    
    return pred_price, change_pct
