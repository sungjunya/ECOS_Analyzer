import numpy as np
import pandas as pd
from tensorflow.keras.models import load_model # keras에서 tensorflow.keras로 변경하여 호환성 강화
import joblib 
import os
import requests 
import json
import time 
from datetime import timedelta
from dotenv import load_dotenv
load_dotenv() 
# ── 설정 ──
MODEL_DIR = "models" # 모델 저장 폴더

# API 호출 시 재시도 관련 설정
API_MODEL_NAME = "gemini-2.5-flash-preview-09-2025"

def _generate_interpretation(company, df_actual, df_pred):
    """
    Gemini API를 호출하여 LSTM 예측 결과에 대한 전문적인 해석을 생성합니다.
    """
    
    # 1. API 키를 가져옵니다. (GEMINI_API_KEY 또는 __api_key 환경 변수 확인)
    # app.py에서 설정한 GEMINI_API_KEY를 우선 확인합니다.
    API_KEY = os.getenv('GEMINI_API_KEY', '').strip()
    
    # 만약 GEMINI_API_KEY가 없으면, 특정 환경 변수인 __api_key도 확인합니다.
    if not API_KEY:
        API_KEY = os.getenv('__api_key', '').strip()

    # 2. 키가 유효한지 확인합니다.
    if not API_KEY or API_KEY == 'YOUR_ACTUAL_GEMINI_API_KEY':
        print("경고: Gemini API 키가 올바르게 설정되지 않았습니다. LLM 분석을 건너뜁니다.")
        return (
            "🔴 LLM 해석 실패: API 키가 설정되지 않았거나 유효하지 않습니다. "
            "`app.py` 파일 상단에서 **유효한 키**로 교체하고 저장했는지 확인해 주세요."
        )

    # 예측된 30일 데이터 추이를 분석합니다.
    start_price = df_actual['Close'].iloc[-1]
    final_price = df_pred['Close'].iloc[-1]
    
    # 10일 단위로 변동률 계산 (추이 분석을 위함)
    segments = [10, 20, 30]
    trend_analysis = []
    
    for i, day in enumerate(segments):
        if day <= len(df_pred):
            end_price = df_pred['Close'].iloc[day-1]
            
            if i == 0:
                base_price = start_price
                period_name = "초기 10일 (현재 종가 대비)"
            elif i == 1:
                base_price = df_pred['Close'].iloc[9] 
                period_name = "중기 10일 (10일차 종가 대비)"
            else: # day == 30
                base_price = df_pred['Close'].iloc[19] 
                period_name = "후기 10일 (20일차 종가 대비)"
            
            # 이전 시점 대비 변동률
            change = (end_price - base_price) / base_price * 100
            
            trend_analysis.append({
                "period": period_name,
                "price": f"{end_price:,.0f} KRW",
                "change_pct": f"{change:+.2f}%"
            })

    total_change = (final_price - start_price) / start_price * 100
    
    analysis_data = {
        "company": company,
        "current_price": f"{start_price:,.0f} KRW",
        "final_predicted_price": f"{final_price:,.0f} KRW",
        "total_change_pct": f"{total_change:+.2f}%",
        "trend_segments": trend_analysis,
    }

    system_prompt = (
        "당신은 LSTM 주가 예측 모델의 결과를 분석하는 전문 기술 분석가입니다. "
        "주어진 10일 단위의 가격 변화(momentum) 데이터를 기반으로, "
        "향후 30일간의 주가 '흐름'과 '변동성'에 초점을 맞춘 심층적인 분석 리포트를 작성해야 합니다. "
        "분석에는 왜 이러한 추세가 예측되었는지에 대한 기술적 해석(예: 조정, 돌파 시도, 횡보 패턴)을 포함하고, "
        "예상되는 주가 궤적을 명확히 설명해 주세요. 보고서는 객관적이고 간결한 한 단락의 한국어(하십시오체)여야 합니다."
    )
    
    user_query = (
        f"LSTM 모델이 예측한 '{company}'의 향후 30일 주가 추이 데이터입니다. 이 데이터를 "
        f"분석하여 예측 결과에 대한 전문적인 해석 리포트를 작성해 주세요. "
        f"분석 데이터: {json.dumps(analysis_data, ensure_ascii=False)}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{API_MODEL_NAME}:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
    }
    
    # API 호출 (지수 백오프 적용)
    for attempt in range(5):
        try:
            response = requests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
            response.raise_for_status() 
            result = response.json()
            
            text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '해석을 생성하는 데 실패했습니다.')
            return text
            
        except requests.exceptions.RequestException as e:
            if attempt < 4:
                wait_time = 2 ** attempt
                print(f"API 요청 실패: {e}. {wait_time}초 후 재시도합니다.")
                time.sleep(wait_time)
            else:
                print(f"최종 API 요청 실패: {e}")
                return "네트워크 오류 또는 API 호출 한도 초과로 인해 예측 해석을 불러올 수 없습니다."
        except Exception as e:
            print(f"응답 처리 중 오류 발생: {e}")
            return "예측 결과를 해석하는 중 내부 오류가 발생했습니다."
    return "예측 해석 생성 실패 (최대 재시도 횟수 초과)."


def predict_next_month(df, symbol, time_steps, company): 
    """저장된 모델과 스케일러를 사용하여 다음 30일 주가를 예측하고 LLM 해석을 반환합니다."""
    
    # .을 _로 치환하여 파일 경로 안전하게 만듦
    safe_symbol = symbol.replace(".", "_")
    
    # MODEL_DIR을 models로 변경했으므로, 학습 파일 경로도 확인 필요
    model_path = os.path.join(MODEL_DIR, f"lstm_model_{safe_symbol}_{time_steps}.keras")
    scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")

    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        print(f"Model or scaler file not found. Please train the model first.")
        # 사용자 피드백을 위해 모델 폴더 이름을 정확히 알려줍니다.
        return pd.DataFrame(), None, f"모델 파일이 없어 예측을 수행할 수 없습니다. 모델 폴더가 '{MODEL_DIR}'인지 확인하세요."
    
    try:
        scaler = joblib.load(scaler_path)
        # keras.models.load_model 대신 tensorflow.keras.models.load_model 사용
        model = load_model(model_path) 
        
    except Exception as e:
        print(f"Error loading model or scaler: {e}")
        return pd.DataFrame(), None, f"모델/스케일러 로드 오류: {e}"

    # 'Close' 가격만 사용
    data = df.filter(['Close'])
    
    # ── 30일 예측을 위한 반복 루프 ──
    last_data = data[-time_steps:].values
    last_data_scaled = scaler.transform(last_data)
    
    temp_input = last_data_scaled.flatten().tolist()
    
    lst_output = []
    n_future_days = 30
    
    for i in range(n_future_days):
        if len(temp_input) > time_steps:
            # 여기는 항상 time_steps와 길이가 같거나 작아야 합니다.
            # 예측 루프의 기본 로직을 유지합니다.
            x_input = np.array(temp_input[-time_steps:]).reshape((1, time_steps, 1))
        else:
            x_input = np.array(temp_input).reshape((1, time_steps, 1))
            
        y_pred_scaled = model.predict(x_input, verbose=0)
        
        lst_output.append(y_pred_scaled[0, 0])
        temp_input.append(y_pred_scaled[0, 0])
        temp_input = temp_input[1:] 

    # ── 예측 결과를 원래 스케일로 역변환 및 DataFrame 생성 ──
    scaled_predictions_2d = np.array(lst_output).reshape(-1, 1)
    
    # 역변환을 위한 더 안전한 방식 사용
    # 스케일러가 fit된 feature의 개수와 일치하도록 더미 데이터 생성
    dummy_input = np.zeros((len(scaled_predictions_2d), scaler.n_features_in_))
    dummy_input[:, 0] = scaled_predictions_2d.flatten()
    
    predictions = scaler.inverse_transform(dummy_input)[:, 0]

    last_date = df.index[-1]
    prediction_dates = [last_date + timedelta(days=i) for i in range(1, n_future_days + 1)]
    
    pred_df = pd.DataFrame(predictions, index=prediction_dates, columns=['Close'])
    final_price = pred_df['Close'].iloc[-1]
    
    # ── LLM 해석 생성 ──
    interpretation = _generate_interpretation(company, df, pred_df)
    
    return pred_df, final_price, interpretation