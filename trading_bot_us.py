import os
import requests
import pandas as pd
import time
from datetime import datetime, timezone, timedelta

# ========================
# 시간대 설정
# ========================
KST = timezone(timedelta(hours=9))

# ========================
# 설정값 (Railway 환경변수에서 읽어옴)
# ========================
APP_KEY = os.environ.get("APP_KEY")
APP_SECRET = os.environ.get("APP_SECRET")
ACCOUNT_NO = os.environ.get("ACCOUNT_NO")
ACCOUNT_PROD = "01"      # 계좌 상품코드 (종합계좌는 01)

BASE_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자 URL

STOCK_CODE = "TSLA"      # 테슬라
MARKET = "NAS"           # 나스닥
QUANTITY = 1             # 거래 수량 (1주)


# ========================
# 1. 토큰 발급
# ========================
def get_token():
    url = f"{BASE_URL}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    res = requests.post(url, json=body)
    token = res.json()["access_token"]
    print("✅ 토큰 발급 완료")
    return token


# ========================
# 2. 현재가 조회 (해외주식)
# ========================
def get_price(token):
    url = f"{BASE_URL}/uapi/overseas-stock/v1/quotations/price"
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "HHDFS00000300",
        "content-type": "application/json"
    }
    params = {
        "AUTH": "",
        "EXCD": MARKET,
        "SYMB": STOCK_CODE
    }
    res = requests.get(url, headers=headers, params=params)
    data = res.json()
    price = float(data["output"]["last"])
    return price


# ========================
# 3. 일봉 데이터 조회 (RSI 계산용)
# ========================
def get_daily_candles(token, days=20):
    url = f"{BASE_URL}/uapi/overseas-stock/v1/quotations/dailyprice"
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "HHDFS76240000",
        "content-type": "application/json"
    }
    today = datetime.now(KST).strftime("%Y%m%d")
    params = {
        "AUTH": "",
        "EXCD": MARKET,
        "SYMB": STOCK_CODE,
        "GUBN": "0",
        "BYMD": today,
        "MODP": "0"
    }
    res = requests.get(url, headers=headers, params=params)
    output = res.json().get("output2", [])
    closes = [float(x["clos"]) for x in output[:days] if x.get("clos")]
    return list(reversed(closes))


# ========================
# 4. RSI 계산
# ========================
def calc_rsi(closes, period=14):
    df = pd.Series(closes)
    delta = df.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]


# ========================
# 5. 매수 주문 (해외주식)
# ========================
def buy_order(token):
    url = f"{BASE_URL}/uapi/overseas-stock/v1/trading/order"
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTT1002U",
        "content-type": "application/json"
    }
    body = {
        "CANO": ACCOUNT_NO,
        "ACNT_PRDT_CD": ACCOUNT_PROD,
        "OVRS_EXCG_CD": MARKET,
        "PDNO": STOCK_CODE,
        "ORD_DVSN": "00",
        "ORD_QTY": str(QUANTITY),
        "OVRS_ORD_UNPR": "0",
        "ORD_SVR_DVSN_CD": "0"
    }
    res = requests.post(url, headers=headers, json=body)
    msg = res.json().get("msg1", "응답 없음")
    print(f"📈 매수 주문: {STOCK_CODE} {QUANTITY}주 → {msg}")


# ========================
# 6. 매도 주문 (해외주식)
# ========================
def sell_order(token):
    url = f"{BASE_URL}/uapi/overseas-stock/v1/trading/order"
    headers = {
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "VTTT1001U",
        "content-type": "application/json"
    }
    body = {
        "CANO": ACCOUNT_NO,
        "ACNT_PRDT_CD": ACCOUNT_PROD,
        "OVRS_EXCG_CD": MARKET,
        "PDNO": STOCK_CODE,
        "ORD_DVSN": "00",
        "ORD_QTY": str(QUANTITY),
        "OVRS_ORD_UNPR": "0",
        "ORD_SVR_DVSN_CD": "0"
    }
    res = requests.post(url, headers=headers, json=body)
    msg = res.json().get("msg1", "응답 없음")
    print(f"📉 매도 주문: {STOCK_CODE} {QUANTITY}주 → {msg}")


# ========================
# 7. 미장 시간 체크 (KST 기준)
# 서머타임 적용 중 (3월~11월): KST 22:30 ~ 익일 05:00
# 서머타임 해제 (11월~3월):    KST 23:30 ~ 익일 06:00
# ========================
def is_us_market_open():
    now = datetime.now(KST)
    hour = now.hour
    minute = now.minute

    if hour == 22 and minute >= 30:
        return True
    if hour == 23:  # 23시 전체 포함
        return True
    if 0 <= hour < 5:
        return True
    if hour == 5 and minute == 0:
        return True
    return False


# ========================
# 8. 전략 실행 (메인 루프)
# ========================
def run_strategy():
    token = get_token()
    token_time = datetime.now(KST)
    position = False

    print(f"\n🤖 미국주식 모의투자 봇 시작 - {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} (KST)")
    print(f"종목: Tesla({STOCK_CODE}) | 전략: RSI(14) | 매수 < 30 / 매도 > 70")
    print(f"거래소: NASDAQ | 수량: {QUANTITY}주")
    print("-" * 55)

    while True:
        now = datetime.now(KST)

        # 토큰 만료 전 재발급 (23시간마다)
        elapsed = (now - token_time).total_seconds()
        if elapsed > 23 * 3600:
            token = get_token()
            token_time = now

        if not is_us_market_open():
            print(f"⏰ 미장 외 시간 ({now.strftime('%H:%M')} KST) - 대기 중...")
            time.sleep(60)
            continue

        try:
            closes = get_daily_candles(token)
            rsi = calc_rsi(closes)
            price = get_price(token)

            status = "보유중" if position else "미보유"
            print(f"[{now.strftime('%H:%M:%S')} KST] 현재가: ${price:.2f} | RSI: {rsi:.1f} | {status}", end="")

            if rsi < 30 and not position:
                print(" → 🟢 매수 신호!")
                buy_order(token)
                position = True

            elif rsi > 70 and position:
                print(" → 🔴 매도 신호!")
                sell_order(token)
                position = False

            else:
                print(" → ⏸ 관망")

        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
            print("토큰 재발급 시도 중...")
            try:
                token = get_token()
                token_time = datetime.now(KST)
            except Exception as e2:
                print(f"토큰 재발급 실패: {e2}")

        time.sleep(300)  # 5분마다 체크


# ========================
# 실행
# ========================
if __name__ == "__main__":
    run_strategy()
