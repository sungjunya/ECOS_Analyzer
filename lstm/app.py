import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os, shutil
import yfinance as yf

# 🚨 [수정된 부분]: VS Code 환경에서 .env 파일 로드를 위한 코드 추가
# load_dotenv는 os.getenv가 .env 파일의 변수를 읽을 수 있도록 해줍니다.
try:
    from dotenv import load_dotenv
    # 프로젝트의 루트 디렉토리에 있는 .env 파일을 로드
    load_dotenv()
    print("SUCCESS: .env 파일 로드 완료.")
except ImportError:
    print("WARNING: python-dotenv 라이브러리가 설치되지 않았습니다. pip install python-dotenv 로 설치해 주세요.")
    
# 💡 lstm_model.py, predict.py, data_loader.py 파일이 같은 폴더에 있어야 합니다.
try:
    # 모듈 임포트 시도
    from lstm_model import train_lstm_model
    from predict import predict_next_month
    from data_loader import load_stock_data
    HAS_MODEL_FILES = True
except ImportError as e:
    st.warning(f"경고: 필요한 모듈(lstm_model, predict, data_loader) 중 일부를 찾을 수 없습니다. ({e})")
    st.warning("모델 학습 및 예측 기능이 비활성화됩니다. 파일을 확인해 주세요.")
    HAS_MODEL_FILES = False

# ── 설정 ──
st.set_page_config(page_title="LSTM 예측기", layout="wide")
st.markdown("""
<h1 style='text-align: center; color: #1E90FF; font-weight: bold;'>주식 이름으로 LSTM 예측</h1>
<p style='text-align: center; color: #666;'>Volume 포함 다변량 LSTM + 30일 예측 + Gemini AI 리포트</p>
""", unsafe_allow_html=True)

MODEL_DIR = "models"
os.makedirs(MODEL_DIR, exist_ok=True) # 모델 저장 디렉토리 생성

# =========================================================================
# 💡 Plotly 시각화 함수 (30일 예측 차트)
# - 내부적으로 'Close'를 사용하지만, 사용자 표시에는 '종가'를 사용합니다.
# =========================================================================
def visualize_prediction(df_actual, df_prediction, symbol):
    """실제 주가와 30일 예측 추이를 Plotly로 시각화합니다."""
    
    # Plotly 시각화를 위해 'Close' 컬럼명을 '종가'로 변경하여 사용
    df_actual_plot = df_actual.rename(columns={'Close': '종가'})
    df_prediction_plot = df_prediction.rename(columns={'Close': '종가'})
    
    # 1. 실제 주가 데이터
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_actual_plot.index, 
        y=df_actual_plot['종가'], 
        name='실제 주가', 
        line=dict(color='#1f77b4', width=3) # 친구 코드의 색상 및 두께 적용
    ))

    # 2. 예측 추이 데이터 (점선)
    # 예측 시작점(실제 마지막 날)과 예측 첫날을 연결
    last_actual_point = pd.DataFrame(
        {'종가': df_actual_plot['종가'].iloc[-1]}, 
        index=[df_actual_plot.index[-1]]
    )
    combined_df = pd.concat([last_actual_point, df_prediction_plot])
    
    fig.add_trace(go.Scatter(
        x=combined_df.index,
        y=combined_df['종가'],
        name='30일 예측 추이',
        line=dict(dash='dot', color='red', width=3)
    ))

    # 3. 30일 후 최종 예측 가격 (마커)
    final_price = df_prediction_plot['종가'].iloc[-1]
    final_prediction_date = df_prediction_plot.index[-1]
    
    fig.add_trace(go.Scatter(
        x=[final_prediction_date],
        y=[final_price],
        mode='markers+text',
        name='최종 예측 가격',
        text=[f"{final_price:,.0f}원"],
        textposition='top center',
        marker=dict(size=14, color='red', symbol='star') # 친구 코드의 마커 스타일 적용
    ))

    # 레이아웃 설정
    fig.update_layout(
        title=f"<b>{symbol}</b> 주가 예측",
        yaxis_title="가격 (KRW)",
        xaxis_title="날짜",
        height=550, # 친구 코드의 높이 적용
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        template="plotly_white" # 친구 코드의 템플릿 적용
    )
    # 🚨 use_container_width=True -> width='stretch'로 변경
    st.plotly_chart(fig, width='stretch') # 반응형 설정

# =========================================================================
# 💡 인기 검색 종목 데이터 및 함수 (yfinance 기반)
# =========================================================================
def get_top_stocks():
    """인기 종목의 실시간 주가와 등락률을 yfinance로 가져옵니다."""
    TOP_TICKERS = {
        "005930.KS": "삼성전자",
        "373220.KS": "LG에너지솔루션",
        "000660.KS": "SK하이닉스",
        "005490.KS": "POSCO홀딩스",
        "035420.KS": "네이버",
    }
    top_stocks_list = []
    
    for ticker, name in TOP_TICKERS.items():
        try:
            stock_info = yf.Ticker(ticker).history(period="2d")
            
            current_price = stock_info['Close'].iloc[-1] if not stock_info.empty else 0
            if len(stock_info) >= 2:
                previous_close = stock_info['Close'].iloc[-2]
                change_pct = ((current_price - previous_close) / previous_close) * 100
            else:
                change_pct = 0.0

            top_stocks_list.append({
                "name": name,
                "ticker": ticker,
                "price": current_price,
                "change_pct": change_pct,
            })
        except Exception:
            # 데이터 로드 실패 시 0으로 설정
            top_stocks_list.append({"name": name, "ticker": ticker, "price": 0, "change_pct": 0.0})
            
    return top_stocks_list

def select_stock(name, ticker):
    """인기 종목 클릭 시 세션 상태를 업데이트하고 초기화합니다."""
    # 종목명과 티커를 함께 저장하여 검색 기능을 강화
    st.session_state.input_temp = f"{name} [{ticker}]"
    st.session_state.company_name = name 
    
    # 새 검색 시 예측 관련 세션 상태 초기화
    for k in ['df', 'symbol', 'model_trained', 'pred_df', 'final_price', 'interpretation']:
        if k in st.session_state:
             st.session_state[k] = pd.DataFrame() if k in ['df','pred_df'] else False if k=='model_trained' else None


# =========================================================================
# 💡 세션 초기화 및 입력 처리
# =========================================================================

# 세션 상태에 필요한 모든 키 초기화
keys = ['company_name','df','symbol','model_trained','time_steps','input_temp',
        'pred_df','final_price','interpretation','model_symbol','model_time_steps']
for k in keys:
    if k not in st.session_state:
        st.session_state[k] = "" if k in ['company_name','input_temp','interpretation'] else \
                             pd.DataFrame() if k in ['df','pred_df'] else \
                             False if k=='model_trained' else None

def submit():
    """검색창 입력 시 실행되는 함수 (Enter 키 또는 클릭)"""
    txt = st.session_state.input_temp.strip()
    # 입력된 값에서 티커가 포함되어 있을 경우 종목명만 추출
    name = txt.split('[')[0].strip() if '[' in txt else txt
    
    if name and name != st.session_state.company_name:
        st.session_state.company_name = name
        # 상태 초기화
        for k in ['df','symbol','model_trained','pred_df','final_price','interpretation']:
             st.session_state[k] = pd.DataFrame() if k in ['df','pred_df'] else False if k=='model_trained' else None

# -------------------------------------------------------------------------
# [UI] 2개의 컬럼으로 분할: 인기 종목 (1) | 검색 + 결과 (2)
# -------------------------------------------------------------------------
top_stocks = get_top_stocks()
col_top, col_main = st.columns([1, 2])

# 1. 인기 검색 종목 순위표 (col_top)
with col_top:
    st.subheader("인기 종목 🚀 (실시간)")
    st.caption("클릭하시면 종목이 검색됩니다.")
    
    for i, stock in enumerate(top_stocks):
        if stock['price'] > 0:
            price_display = f"{stock['price']:,.0f}원"
            change_pct = stock['change_pct']
            
            # 친구 코드의 스타일 적용
            trend_text = "상승" if change_pct > 0 else "하락" if change_pct < 0 else "보합"
            label = f"**{i+1}. {stock['name']}**\n{price_display} | {trend_text} {abs(change_pct):.2f}%"

            st.button(
                label,
                key=f"stock_{i}",
                on_click=select_stock,
                args=(stock['name'], stock['ticker']),
                width='stretch' # 🚨 use_container_width=True -> width='stretch'로 변경
            )
        else:
            st.caption(f"**{i+1}. {stock['name']}** (데이터 없음)")

# 2. 검색창 및 결과 표시 (col_main)
with col_main:
    st.subheader("종목 검색")
    st.text_input(
        "주식 이름 입력 → **Enter**",
        key="input_temp",
        on_change=submit,
        placeholder="예: 셀트리온, 풍산, 카카오",
        label_visibility="collapsed"
    )

# =========================================================================
# 💡 데이터 로딩 및 결과 표시 로직
# =========================================================================

# 데이터 로딩
if st.session_state.company_name and st.session_state.df.empty and HAS_MODEL_FILES:
    with st.spinner(f"'{st.session_state.company_name}' 데이터 로딩 중..."):
        try:
            # data_loader.py의 load_stock_data 함수 호출
            df, symbol = load_stock_data(st.session_state.company_name)
            
            # 데이터 유효성 검사 (최소 60일 필요)
            if df.empty or len(df) < 60:
                st.error("데이터 부족 또는 종목을 찾을 수 없습니다. 다른 종목을 검색해 주세요.")
                st.session_state.company_name = ""
                st.session_state.input_temp = ""
            else:
                st.session_state.df = df
                st.session_state.symbol = symbol
        except Exception as e:
            st.error(f"데이터 로딩 중 오류 발생: {e}")
            st.session_state.company_name = ""
            st.session_state.input_temp = ""

# UI (주가 추이 및 예측 결과 표시)
if not st.session_state.df.empty:
    df = st.session_state.df
    symbol = st.session_state.symbol
    company = st.session_state.company_name

    col1, col2 = st.columns([1, 2])

    with col1:
        st.success(f"**{company}** ({symbol})")
        
        # Display DataFrame with Korean column names
        disp_df = df.rename(columns={'Open':'시가', 'High':'고가', 'Low':'저가', 'Close':'종가', 'Volume':'거래량'})
        st.markdown("#### 최근 5일 데이터")
        # 🚨 background_gradient 오류 수정 및 use_container_width -> width='stretch' 변경
        st.dataframe(
            disp_df.tail(5)[['시가','고가','저가','종가','거래량']]
            .style.format("{:,.0f}"), # .background_gradient(cmap='Blues', subset=['종가']) 제거
            width='stretch'
        )

        time_steps = st.selectbox(
            "과거 데이터 (Time Steps)", 
            [30, 60, 90], 
            index=1, 
            key="ts_select", 
            help="LSTM 모델이 학습에 사용할 과거 데이터 기간을 선택하세요."
        )
        st.session_state.time_steps = time_steps

        # --- 모델 재학습 (기존 모델 삭제) ---
        if st.button("모델 재학습 (기존 삭제)", type="secondary", width='stretch'): # 🚨 use_container_width -> width='stretch'로 변경
            if os.path.exists(MODEL_DIR):
                shutil.rmtree(MODEL_DIR)
                os.makedirs(MODEL_DIR)
            st.session_state.model_trained = False
            st.success("기존 모델 삭제 → 아래 **예측 시작** 버튼으로 자동 재학습됩니다.")
            st.rerun()

        # --- 학습 및 예측 버튼 (통합) ---
        if HAS_MODEL_FILES and st.button("LSTM 학습 및 30일 예측 시작", type="primary", width='stretch'): # 🚨 use_container_width -> width='stretch'로 변경
            
            safe_symbol = symbol.replace(".", "_")
            model_path = os.path.join(MODEL_DIR, f"model_{safe_symbol}_{time_steps}.keras")
            scaler_path = os.path.join(MODEL_DIR, f"scaler_{safe_symbol}_{time_steps}.pkl")

            # 1) 모델 없으면 자동 학습
            if not (os.path.exists(model_path) and os.path.exists(scaler_path)):
                 with st.spinner(f"'{company}' 최신 데이터로 모델 학습 중…"):
                    try:
                        train_lstm_model(df, symbol, time_steps)
                        if not (os.path.exists(model_path) and os.path.exists(scaler_path)):
                            st.error("모델 저장 실패. 재시도.")
                    except Exception as e:
                        st.error(f"학습 오류: {e}")
                        
            # 2) 예측
            with st.spinner("30일 예측 + Gemini AI 분석… (20~40초 소요)"):
                try:
                    result = predict_next_month(df, symbol, time_steps, company)
                    
                    if result and len(result) == 3:
                        pred_df, final_price, interpretation = result
                        if pred_df is not None and not pred_df.empty:
                            st.session_state.pred_df = pred_df 
                            st.session_state.final_price = final_price 
                            st.session_state.interpretation = interpretation 
                            st.session_state.model_trained = True
                            st.session_state.model_symbol = symbol
                            st.session_state.model_time_steps = time_steps
                            st.success("예측 완료!")
                        else:
                             st.error(f"예측 실패: {interpretation}")
                    else:
                        st.error("예측 결과 오류. 재학습 후 재시도.")
                        
                except Exception as e:
                    st.error(f"예측 실행 오류: {e}")
                    st.session_state.model_trained = False
            st.rerun() # UI 갱신

        elif not HAS_MODEL_FILES:
            st.error("학습/예측 파일이 없어 버튼이 비활성화되었습니다.")

    with col2:
        st.subheader(f"최근 주가 추이 ({symbol})")
        st.line_chart(df['Close'], width='stretch') # 🚨 use_container_width -> width='stretch' 변경

        # 예측 결과 표시
        current_ts = st.session_state.get('ts_select') or 60
        if (st.session_state.model_trained and
            not st.session_state.pred_df.empty and
            st.session_state.model_symbol == symbol and
            st.session_state.model_time_steps == current_ts):

            pred_df = st.session_state.pred_df
            final_price = st.session_state.final_price
            interpretation = st.session_state.interpretation
            
            # 최종 변동률 계산
            current_price = df['Close'].iloc[-1]
            change_pct = ((final_price - current_price) / current_price) * 100

            st.markdown("---")
            st.subheader(f"✅ 30일 예측 결과 및 AI 분석")

            # 메트릭 카드
            col_a, col_b = st.columns(2)
            col_a.metric("현재 가격", f"{current_price:,.0f}원")
            col_b.metric("30일 후 예측 가격", f"{final_price:,.0f}원", f"{change_pct:+.1f}%")

            # 30일 예측 차트 시각화
            visualize_prediction(df, pred_df, symbol)
            
            # LLM 해석 리포트
            st.subheader("💡 Gemini AI 분석 리포트")
            st.info(interpretation)

else:
    st.info("왼쪽 '인기 종목'을 클릭하거나, 검색창에 주식 이름을 입력하세요.")