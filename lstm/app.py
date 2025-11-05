import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import os
import yfinance as yf

# 💡 lstm_model.py, predict.py, data_loader.py 파일이 같은 폴더에 있어야 합니다.
try:
    from lstm_model import train_lstm_model
    from predict import predict_next_month
    from data_loader import load_stock_data
    # 💡 오류 수정: HAS_MODEL_FILES 정의
    HAS_MODEL_FILES = True
except ImportError as e:
    st.warning(f"경고: 필요한 모듈(lstm_model, predict, data_loader) 중 일부를 찾을 수 없습니다. ({e})")
    st.warning("모델 학습 및 예측 기능이 비활성화됩니다. 파일을 확인해 주세요.")
    # 💡 오류 수정: HAS_MODEL_FILES 정의
    HAS_MODEL_FILES = False

# ── 설정 ──
st.set_page_config(page_title="LSTM 예측기", layout="wide")
st.title("주식 이름으로 LSTM 예측")

# =========================================================================
# 💡 Plotly 시각화 함수 (30일 예측 차트)
# =========================================================================
def visualize_prediction(df_actual, df_prediction, symbol):
    """실제 주가와 30일 예측 추이를 Plotly로 시각화합니다."""
    
    # 1. 실제 주가 데이터
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_actual.index, 
        y=df_actual['Close'], 
        name='실제 주가', 
        line=dict(color='blue')
    ))

    # 2. 예측 추이 데이터 (점선)
    # 예측 시작점(실제 마지막 날)과 예측 첫날을 연결하기 위해 실제 마지막 데이터 포인트 추가
    last_actual_point = pd.DataFrame(
        {'Close': df_actual['Close'].iloc[-1]}, 
        index=[df_actual.index[-1]]
    )
    
    # 실제 마지막 날 + 예측 데이터 연결 (차트 상에서 선이 이어지도록)
    combined_df = pd.concat([last_actual_point, df_prediction])
    
    fig.add_trace(go.Scatter(
        x=combined_df.index,
        y=combined_df['Close'],
        name='30일 예측 추이',
        line=dict(dash='dot', color='red', width=2)
    ))

    # 3. 30일 후 최종 예측 가격 (마커)
    final_price = df_prediction['Close'].iloc[-1]
    final_prediction_date = df_prediction.index[-1]
    
    fig.add_trace(go.Scatter(
        x=[final_prediction_date],
        y=[final_price],
        mode='markers+text',
        name='최종 예측 가격',
        text=[f"{final_price:,.0f}원"],
        textposition='top center',
        marker=dict(size=10, color='red')
    ))

    # 레이아웃 설정
    fig.update_layout(
        title=f"{symbol} 주가 (실제 vs. 30일 예측)",
        yaxis_title="가격 (KRW)",
        xaxis_title="날짜",
        height=500,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )
    # 💡 Streamlit 경고 해결: use_container_width=True 대신 width='stretch' 사용
    st.plotly_chart(fig, width='stretch')

# =========================================================================
# 💡 인기 검색 종목 데이터 및 함수
# =========================================================================
def get_top_stocks():
    """인기 종목의 실시간 주가와 등락률을 가져옵니다."""
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
            # yfinance는 한국 주식의 경우 'Adj Close'를 사용하며, 'Close' 가격이 변동될 수 있습니다.
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
        except Exception as e:
            top_stocks_list.append({"name": name, "ticker": ticker, "price": 0, "change_pct": 0.0})
            print(f"Warning: Failed to load real-time data for {name} ({ticker}). Error: {e}")
            
    return top_stocks_list

def select_stock(name, ticker):
    """인기 종목 클릭 시 세션 상태를 업데이트합니다."""
    # 💡 종목명과 티커를 함께 저장하여 검색 기능을 강화합니다.
    input_value = f"{name} [{ticker}]"
    st.session_state.input_temp = input_value
    st.session_state.company_name = name 
    
    # 새 검색 시 예측 관련 세션 상태 초기화
    st.session_state.df = pd.DataFrame()
    st.session_state.symbol = None
    st.session_state.model_trained = False
    st.session_state.pred_df = pd.DataFrame() # 30일 예측 df 초기화
    st.session_state.final_price = None
    st.session_state.interpretation = None


# =========================================================================
# 💡 세션 초기화 및 입력 처리
# =========================================================================

# 세션 상태에 필요한 모든 키 초기화
for key in ['company_name', 'df', 'symbol', 'model_trained', 'time_steps', 'input_temp', 
            'model_symbol', 'model_time_steps', 'pred_df', 'final_price', 'interpretation']:
    if key not in st.session_state:
        if key in ['company_name', 'input_temp', 'interpretation']:
            st.session_state[key] = ""
        elif key in ['df', 'pred_df']:
            st.session_state[key] = pd.DataFrame()
        elif key == 'model_trained':
            st.session_state[key] = False
        else:
            st.session_state[key] = None

# 입력창 + Enter 처리 함수 (종목명 저장 기능)
def submit():
    """검색창 입력 시 실행되는 함수 (Enter 키 또는 클릭)"""
    user_input = st.session_state.input_temp.strip()
    
    # 입력된 값에서 티커가 포함되어 있을 경우 종목명만 추출합니다.
    if '[' in user_input and ']' in user_input:
        company_name_only = user_input.split('[')[0].strip()
    else:
        company_name_only = user_input

    if company_name_only and company_name_only != st.session_state.company_name:
        st.session_state.company_name = company_name_only
        st.session_state.df = pd.DataFrame()
        st.session_state.symbol = None
        st.session_state.model_trained = False
        st.session_state.pred_df = pd.DataFrame() 
        st.session_state.final_price = None


# -------------------------------------------------------------------------
# [UI] 2개의 컬럼으로 분할: 인기 종목 (1) | 검색 + 결과 (2)
# -------------------------------------------------------------------------
top_stocks = get_top_stocks()
col_top, col_main = st.columns([1, 2])

# 1. 인기 검색 종목 순위표 (Top Stocks)
with col_top:
    st.subheader("인기 종목 🚀 (실시간)")
    st.caption("클릭하시면 종목이 검색됩니다.")
    
    for i, stock in enumerate(top_stocks):
        if stock['price'] > 0:
            trend_icon = "⬆️" if stock['change_pct'] > 0 else "⬇️" if stock['change_pct'] < 0 else "➖"
            price_display = f"{stock['price']:,.0f}원"
            change_display = f"{trend_icon} {abs(stock['change_pct']):.2f}%"
        else:
            price_display = "데이터 없음"
            change_display = "---"

        label = (
            f"**{i+1}. {stock['name']}**"
            f" ({price_display} | {change_display})"
        )
        st.button(
            label,
            key=f"stock_{i}",
            on_click=select_stock,
            args=(stock['name'], stock['ticker']),
            width='stretch'
        )

# 2. 검색창 및 결과 표시
with col_main:
    st.subheader("종목 검색")
    st.text_input(
        "주식 이름 입력 → **Enter**",
        key="input_temp",
        on_change=submit,
        help="입력 후 Enter",
        label_visibility="collapsed"
    )

# =========================================================================
# 💡 데이터 로딩 및 결과 표시 로직
# =========================================================================

# 데이터 로딩
# 💡 NameError 해결: HAS_MODEL_FILES가 정의됨
if st.session_state.company_name and st.session_state.df.empty and HAS_MODEL_FILES:
    with st.spinner(f"'{st.session_state.company_name}' 데이터 로딩 중..."):
        try:
            # data_loader.py의 load_stock_data 함수는 종목 이름으로 티커를 찾고 데이터를 반환해야 함
            df, symbol = load_stock_data(st.session_state.company_name)
        except Exception as e:
            st.error(f"데이터 로딩 중 오류 발생: {e}")
            # st.stop() # Canvas 환경에서는 st.stop() 대신 오류를 표시하고 계속 진행하는 것이 좋습니다.
            
        # 데이터 유효성 검사 (최소 60일 필요)
        if df.empty or len(df) < 60:
            st.error("데이터 부족 또는 주식 없음. 다른 종목을 검색해 주세요.")
            st.session_state.company_name = ""
            st.session_state.input_temp = ""
            # st.stop() # Canvas 환경에서는 st.stop() 대신 오류를 표시하고 계속 진행하는 것이 좋습니다.
        else:
            st.session_state.df = df
            st.session_state.symbol = symbol

# UI (주가 추이 및 예측 결과 표시)
if not st.session_state.df.empty:
    df = st.session_state.df
    symbol = st.session_state.symbol
    company = st.session_state.company_name

    col1, col2 = st.columns([1, 2])

    with col1:
        st.success(f"**{company}** ({symbol})")
        st.dataframe(df.tail(5).style.format({"Close": "{:,.0f}원"}), width='stretch')

        # Time Steps 선택 (필수 입력)
        time_steps = st.selectbox("과거 데이터 (Time Steps)", [30, 60, 90], index=1, key="ts_select", help="LSTM 모델이 학습에 사용할 과거 데이터 기간을 선택하세요.")
        st.session_state.time_steps = time_steps

        # 학습 및 예측 버튼
        if HAS_MODEL_FILES and st.button("LSTM 학습 및 30일 예측 시작", width='stretch', disabled=(not HAS_MODEL_FILES)):
            with st.spinner("모델 학습 및 예측, AI 분석 리포트 생성 중... (20~40초 소요)"):
                try:
                    # 1. 학습 및 모델/스케일러 저장 (lstm_model.py)
                    train_lstm_model(df, symbol, time_steps)
                    
                    # 2. 학습된 모델과 스케일러를 사용하여 예측 (predict.py)
                    pred_df, final_price, interpretation = predict_next_month(df, symbol, time_steps, company)
                    
                    # 3. 예측 결과 세션 상태에 저장
                    if pred_df is not None and not pred_df.empty:
                        st.session_state.pred_df = pred_df # 30일 예측 df 저장
                        st.session_state.final_price = final_price # 최종 가격
                        st.session_state.interpretation = interpretation # LLM 해석
                        st.session_state.model_trained = True
                        
                        st.session_state.model_symbol = symbol
                        st.session_state.model_time_steps = time_steps
                        
                    else:
                         st.error(f"예측 결과 생성에 실패했습니다. {interpretation}")

                except Exception as e:
                    st.error(f"모델 학습/예측 중 치명적인 오류 발생: {e}")
                    st.session_state.model_trained = False
                
            st.rerun() # UI 갱신

        elif not HAS_MODEL_FILES:
            st.error("학습/예측 파일이 없어 버튼이 비활성화되었습니다.")


    with col2:
        st.subheader(f"최근 주가 추이 ({symbol})")
        st.line_chart(df['Close'])

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