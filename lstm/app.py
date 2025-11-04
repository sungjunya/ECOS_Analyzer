import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
import os

st.set_page_config(page_title="LSTM 예측기", layout="wide")
st.title("주식 이름으로 LSTM 예측")

# =========================================================================
# 💡 인기 검색 종목 데이터 및 함수
# =========================================================================
def get_top_stocks():
    # 인기 종목의 티커와 표시할 이름을 정의합니다. (yfinance에서 사용되는 티커)
    TOP_TICKERS = {
        "005930.KS": "삼성전자",
        "373220.KS": "LG에너지솔루션",
        "000660.KS": "SK하이닉스",
        "005490.KS": "POSCO홀딩스",
        "035420.KS": "네이버",
    }
    
    top_stocks_list = []
    
    # yfinance를 사용하여 실시간 데이터를 가져옵니다.
    for ticker, name in TOP_TICKERS.items():
        try:
            # 2일치 데이터로 현재 주가와 전일 대비 등락률을 계산
            stock_info = yf.Ticker(ticker).history(period="2d")
            
            if len(stock_info) >= 2:
                current_price = stock_info['Close'].iloc[-1]
                previous_close = stock_info['Close'].iloc[-2]
                change_pct = ((current_price - previous_close) / previous_close) * 100
            else:
                # 데이터가 2일 미만일 경우 최신 가격만 사용
                current_price = stock_info['Close'].iloc[-1] if not stock_info.empty else 0
                change_pct = 0.0

            top_stocks_list.append({
                "name": name,
                "ticker": ticker,
                "price": current_price,
                "change_pct": change_pct,
            })
        except Exception as e:
            top_stocks_list.append({
                "name": name,
                "ticker": ticker,
                "price": 0,
                "change_pct": 0.0,
            })
            # yfinance 에러는 너무 자주 발생하므로 콘솔에만 출력
            print(f"Warning: Failed to load real-time data for {name} ({ticker}). Error: {e}")
            
    return top_stocks_list

def select_stock(name, ticker):
    # 입력창에는 '종목명 [티커]' 형식으로 입력되도록 설정
    input_value = f"{name} [{ticker}]"
    st.session_state.input_temp = input_value
    
    # company_name을 업데이트하여 데이터 로딩 로직을 즉시 트리거합니다.
    st.session_state.company_name = name # 순수 종목 이름만 저장
    
    # 나머지 세션 상태 초기화 (검색 시 새 작업을 위해)
    st.session_state.df = pd.DataFrame()
    st.session_state.symbol = None
    st.session_state.model_trained = False
    st.session_state.pred_price = None
    st.session_state.change_pct = None

# =========================================================================

# 세션 초기화
for key in ['company_name', 'df', 'symbol', 'model_trained', 'pred_price', 'change_pct', 'time_steps', 'input_temp', 'model_symbol', 'model_time_steps']:
    if key not in st.session_state:
        if key in ['company_name', 'input_temp']:
            st.session_state[key] = ""
        elif key == 'df':
            st.session_state[key] = pd.DataFrame()
        elif key == 'model_trained':
            st.session_state[key] = False
        else:
            st.session_state[key] = None

# 입력창 + Enter 처리 함수 (종목명 저장 기능)
def submit():
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
        st.session_state.pred_price = None

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
        # 💡 경고 해결: use_container_width=True 대신 width='stretch' 사용
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


# 데이터 로딩 및 결과 표시 
if st.session_state.company_name and st.session_state.df.empty:
    with st.spinner(f"'{st.session_state.company_name}' 데이터 로딩 중..."):
        from data_loader import load_stock_data
        try:
            df, symbol = load_stock_data(st.session_state.company_name)
        except Exception as e:
            st.error(f"데이터 로딩 중 오류 발생: {e}")
            st.stop()
            
    # 데이터 유효성 검사 (최소 60일 필요)
    if df.empty or len(df) < 60:
        st.error("데이터 부족 또는 주식 없음")
        st.session_state.company_name = "" 
        st.stop()
        
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
        st.dataframe(df.tail(5).style.format({"Close": "{:,.0f}원"}), width='stretch') # 💡 경고 해결

        # time_steps 선택
        time_steps = st.selectbox("과거 데이터", [30, 60, 90], index=1, key="ts_select")
        st.session_state.time_steps = time_steps

        # 학습 버튼
        # 💡 로직 변경: 버튼 클릭 시 학습 -> 예측까지 한번에 진행
        if st.button("LSTM 학습 시작", width='stretch'): # 💡 경고 해결
            from lstm_model import train_lstm_model
            from predict import predict_next_month
            
            with st.spinner("모델 학습 및 예측 중... (20~40초 소요)"):
                # 1. 학습 및 모델/스케일러 저장 (lstm_model.py)
                train_lstm_model(df, symbol, time_steps)
            
                # 2. 학습된 모델과 스케일러를 사용하여 예측 (predict.py)
                pred_price, change_pct = predict_next_month(df, symbol, time_steps)
                
                # 3. 예측 결과 세션 상태에 저장
                if pred_price:
                    st.session_state.pred_price = pred_price
                    st.session_state.change_pct = change_pct
                    st.session_state.model_trained = True
                
                # 학습한 time_steps와 symbol을 저장하여 나중에 예측된 결과가 
                # 현재 선택된 time_steps와 일치하는지 확인하는 용도로 사용
                st.session_state.model_symbol = symbol 
                st.session_state.model_time_steps = time_steps 
            
            st.rerun() # UI 갱신

    with col2:
        st.subheader("주가 추이")
        st.line_chart(df['Close'])

        # 예측 결과 표시
        # 모델이 학습되었고, 현재 종목/time_steps와 일치할 때만 표시
        current_ts = st.session_state.get('ts_select') or 60
        if (st.session_state.model_trained and 
            st.session_state.pred_price is not None and 
            st.session_state.model_symbol == symbol and 
            st.session_state.model_time_steps == current_ts):

            pred_price = st.session_state.pred_price
            change_pct = st.session_state.change_pct

            col_a, col_b = st.columns(2)
            col_a.metric("현재 가격", f"{df['Close'].iloc[-1]:,.0f}원")
            col_b.metric("1개월 예측", f"{pred_price:,.0f}원", f"{change_pct:+.1f}%")

            # Plotly 그래프 표시 로직 
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='실제 주가', line=dict(color='blue')))
            
            # 예측 포인트 추가
            future_date = df.index[-1] + pd.DateOffset(months=1)
            fig.add_trace(go.Scatter(x=[df.index[-1], future_date],
                                     y=[df['Close'].iloc[-1], pred_price],
                                     mode='lines+markers', 
                                     name='1개월 예측', 
                                     line=dict(dash='dot', color='red')))
            
            fig.update_layout(title=f"{company} | {current_ts}일 기반 예측", height=500)
            st.plotly_chart(fig, use_container_width=True) # use_container_width는 plotly 함수에 남겨둡니다.

else:
    st.info("왼쪽 **'인기 종목'**을 클릭하거나, 검색창에 이름을 입력하세요.")
