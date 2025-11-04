# C:\ECOS\ECOS_Analyzer\lstm\data_loader.py
import pandas as pd
import requests
import time
from io import StringIO
from bs4 import BeautifulSoup

def search_stock_code(query):
    """네이버 검색으로 종목코드 추출"""
    query = query.strip()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    url = f"https://search.naver.com/search.naver?where=stock&query={query}"
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'finance.naver.com/item' in href:
                code = href.split('code=')[1].split('&')[0]
                if code.isdigit() and len(code) == 6:
                    full_symbol = f"{code}.KS"
                    print(f"[검색 성공] '{query}' → {full_symbol}")
                    return full_symbol
        print(f"[검색 실패] '{query}' 매칭 없음")
        return None
    except Exception as e:
        print(f"[검색 에러] {e}")
        return None

def load_stock_data(input_text):
    """주식 이름 → 데이터프레임 반환 (최소 60일)"""
    symbol = search_stock_code(input_text)
    if not symbol:
        return pd.DataFrame(), None

    code = symbol.replace('.KS', '')
    headers = {'User-Agent': 'Mozilla/5.0'}
    all_data = []
    page = 1
    max_pages = 15  
    time.sleep(0.1)

    print(f"[로딩] {symbol} 데이터 수집 중... (최대 7페이지)")

    session = requests.Session()
    for page in range(1, max_pages + 1):
        url = f"https://finance.naver.com/item/sise_day.naver?code={code}&page={page}"
        try:
            resp = session.get(url, headers=headers, timeout=5)
            tables = pd.read_html(StringIO(resp.text), flavor='lxml')[0]
            df_page = tables.dropna()
            if df_page.empty or len(df_page) < 7:
                break
            all_data.append(df_page)
            time.sleep(0.02)
        except Exception as e:
            print(f"[에러] 페이지 {page}: {e}")
            break

    if not all_data:
        return pd.DataFrame(), symbol

    df = pd.concat(all_data, ignore_index=True)
    df['날짜'] = pd.to_datetime(df['날짜'], format='%Y.%m.%d', errors='coerce')
    df = df.dropna(subset=['날짜'])
    df['Close'] = pd.to_numeric(df['종가'].astype(str).str.replace(',', ''), errors='coerce')
    df = df.dropna(subset=['Close'])
    df = df.sort_values('날짜').set_index('날짜')[['Close']]

    print(f"[성공] {symbol}: {len(df)}일 데이터")
    return df, symbol