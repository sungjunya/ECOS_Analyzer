# news_scraper.py

import streamlit as st
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import re
import numpy as np 

# ⚠️ 크롤링 주의 사항: Selenium은 requests보다 느리지만, 403 에러 회피에 필수적입니다.
#    비상업적 학습 목적으로만 사용하고, 충분한 time.sleep을 유지해야 합니다.

@st.cache_data(ttl=600, show_spinner=False)
def scrape_investing_news_titles_selenium(query: str, max_articles: int = 10) -> list:
    """
    한국 Investing.com 주식 시장 뉴스 URL에서 크롤링한 후, 
    다중 키워드(query)를 이용해 필터링합니다. (query는 'sk하이닉스 sk hynix sk' 형태)
    """
    
    # 한국 Investing.com의 주식 시장 뉴스 URL 고정
    base_url = "https://kr.investing.com/news/stock-market-news" 
    target_url = base_url

    news_list = []
    
    # 🚨 전달받은 다중 키워드를 분리 (예: ['sk하이닉스', 'sk', 'hynix'])
    search_keywords = query.lower().split() 
    
    # --- Selenium 설정 ---
    options = Options()
    options.add_argument("--headless")              
    options.add_argument("--no-sandbox")            
    options.add_argument("--disable-dev-shm-usage") 
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # 쿼리를 한국어 그대로 사용
        with st.spinner(f"[{query.upper()}] 뉴스 페이지를 브라우저로 로딩 중 (5초 대기)..."):
            driver.get(target_url) 
            # 403 에러 회피를 위해 충분히 기다립니다.
            time.sleep(5) 
            soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # --- 데이터 추출 및 다중 필터링 로직 ---
        # 제목 링크를 포함하는 요소들을 선택
        news_containers = soup.select('article a[title]')
        
        for container in news_containers:
            title = container.get('title', '').strip()
            link = container.get('href')
            
            title_lower = title.lower()
            
            # 🚨 [수정] 다중 필터링 로직 🚨
            is_relevant = False
            for keyword in search_keywords:
                if keyword in title_lower:
                    is_relevant = True
                    break

            if link and title and is_relevant:
                # kr.investing.com 도메인을 사용하여 링크 구성
                full_link = f"https://kr.investing.com{link}" if link.startswith('/') else link
                news_list.append({"title": title, "link": full_link})
            
            if len(news_list) >= max_articles:
                break
                
        driver.quit()
        return news_list

    except Exception as e:
        if driver:
             try: driver.quit()
             except: pass
        st.error(f"뉴스 크롤링 (Selenium) 실패: {e}")
        st.error("Selenium 설정 및 드라이버 오류 또는 웹사이트 구조 변경 문제일 수 있습니다.")
        return []