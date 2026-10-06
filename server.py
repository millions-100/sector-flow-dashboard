#!/usr/bin/env python3
"""Sector Flow local server with a small live-data proxy.

The browser always asks /api/market on load. Public market/news endpoints are
requested server-side so the static UI is not blocked by browser CORS rules.
"""

from __future__ import annotations

import concurrent.futures
import html
import json
import re
import ssl
import sys
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
HOST = "127.0.0.1"
PORT = 8080
CACHE_SECONDS = 60

KR_SECTORS = {
    "방산·우주": [
        ("047810", "한국항공우주"),
        ("079550", "LIG넥스원"),
        ("012450", "한화에어로스페이스"),
        ("064350", "현대로템"),
    ],
    "2차전지": [
        ("373220", "LG에너지솔루션"),
        ("006400", "삼성SDI"),
        ("003670", "포스코퓨처엠"),
    ],
    "반도체": [("000660", "SK하이닉스"), ("005930", "삼성전자"), ("042700", "한미반도체")],
    "로봇": [("277810", "레인보우로보틱스"), ("454910", "두산로보틱스"), ("108490", "로보티즈")],
    "조선": [
        ("009540", "HD한국조선해양"),
        ("042660", "한화오션"),
        ("010140", "삼성중공업"),
    ],
    "바이오": [("207940", "삼성바이오로직스"), ("068270", "셀트리온"), ("326030", "SK바이오팜")],
    "전력·에너지": [("034020", "두산에너빌리티"), ("015760", "한국전력"), ("298040", "효성중공업")],
    "금융": [("105560", "KB금융"), ("055550", "신한지주"), ("086790", "하나금융지주")],
    "통신": [("017670", "SK텔레콤"), ("030200", "KT"), ("032640", "LG유플러스")],
    "자동차": [("005380", "현대차"), ("000270", "기아"), ("012330", "현대모비스")],
}

US_SECTORS = {
    "AI·반도체": {"etf": "SMH", "stocks": [("NVDA", "엔비디아"), ("AVGO", "브로드컴"), ("AMD", "AMD")]},
    "소프트웨어·클라우드": {"etf": "IGV", "stocks": [("MSFT", "마이크로소프트"), ("ORCL", "오라클"), ("CRM", "세일즈포스")]},
    "커뮤니케이션": {"etf": "XLC", "stocks": [("META", "메타"), ("GOOGL", "알파벳"), ("NFLX", "넷플릭스")]},
    "임의소비재": {"etf": "XLY", "stocks": [("AMZN", "아마존"), ("TSLA", "테슬라"), ("HD", "홈디포")]},
    "금융": {"etf": "XLF", "stocks": [("JPM", "JP모건"), ("BAC", "뱅크오브아메리카"), ("GS", "골드만삭스")]},
    "산업재·방산": {"etf": "XLI", "stocks": [("GE", "GE 에어로스페이스"), ("CAT", "캐터필러"), ("RTX", "RTX")]},
    "헬스케어": {"etf": "XLV", "stocks": [("LLY", "일라이 릴리"), ("UNH", "유나이티드헬스"), ("JNJ", "존슨앤드존슨")]},
    "에너지": {"etf": "XLE", "stocks": [("XOM", "엑슨모빌"), ("CVX", "셰브론"), ("COP", "코노코필립스")]},
    "유틸리티": {"etf": "XLU", "stocks": [("NEE", "넥스트에라 에너지"), ("SO", "서던 컴퍼니"), ("DUK", "듀크 에너지")]},
    "필수소비재": {"etf": "XLP", "stocks": [("WMT", "월마트"), ("COST", "코스트코"), ("PG", "P&G")]},
    "소재·금": {"etf": "XLB", "stocks": [("LIN", "린데"), ("NEM", "뉴몬트"), ("FCX", "프리포트 맥모란")]},
}

US_STOCK_INFO = {
    "NVDA": ("AI 가속기와 데이터센터 GPU 생태계를 주도하는 반도체 기업입니다.", ["AI GPU", "데이터센터", "CUDA"]),
    "AVGO": ("AI 네트워킹 반도체와 인프라 소프트웨어를 공급합니다.", ["네트워킹", "ASIC", "인프라 소프트웨어"]),
    "AMD": ("CPU와 GPU, 데이터센터 가속기를 설계하는 팹리스 반도체 기업입니다.", ["CPU", "GPU", "데이터센터"]),
    "MSFT": ("Azure 클라우드와 기업용 소프트웨어, 생성형 AI 서비스를 제공합니다.", ["Azure", "Copilot", "기업 소프트웨어"]),
    "ORCL": ("데이터베이스와 클라우드 인프라를 제공하는 기업용 소프트웨어 회사입니다.", ["데이터베이스", "OCI", "클라우드"]),
    "CRM": ("고객관계관리 소프트웨어와 기업용 AI 서비스를 제공합니다.", ["CRM", "데이터 클라우드", "AI 에이전트"]),
    "META": ("광고 플랫폼과 소셜 서비스, AI 추천 기술을 운영합니다.", ["광고", "소셜 플랫폼", "AI"]),
    "GOOGL": ("검색·광고와 클라우드, 유튜브, AI 모델 사업을 운영합니다.", ["검색", "클라우드", "Gemini"]),
    "NFLX": ("글로벌 스트리밍 구독과 광고형 요금제를 운영합니다.", ["스트리밍", "광고", "콘텐츠"]),
    "AMZN": ("전자상거래와 AWS 클라우드, 광고 사업을 운영합니다.", ["전자상거래", "AWS", "광고"]),
    "TSLA": ("전기차와 에너지저장장치, 자율주행 소프트웨어를 개발합니다.", ["전기차", "에너지", "자율주행"]),
    "JPM": ("소비자금융·기업금융·투자은행을 아우르는 미국 대형 은행입니다.", ["은행", "투자은행", "카드"]),
    "LLY": ("비만·당뇨와 신경계 치료제를 개발하는 글로벌 제약사입니다.", ["비만 치료제", "당뇨", "신약"]),
    "XOM": ("석유·가스의 탐사부터 정제·화학까지 영위하는 통합 에너지 기업입니다.", ["원유", "천연가스", "정제"]),
    "GE": ("상업용·군용 항공기 엔진과 항공 서비스를 제공합니다.", ["항공 엔진", "서비스", "방산"]),
}

US_NEWS_QUERIES = {
    "AI·반도체": "AI semiconductor stocks",
    "소프트웨어·클라우드": "software cloud stocks",
    "커뮤니케이션": "communication services stocks",
    "임의소비재": "consumer discretionary stocks",
    "금융": "US financial sector stocks",
    "산업재·방산": "industrial defense stocks",
    "헬스케어": "healthcare stocks",
    "에너지": "energy stocks oil",
    "유틸리티": "utilities stocks",
    "필수소비재": "consumer staples stocks",
    "소재·금": "materials gold stocks",
}

SECTOR_CHECKS = {
    "방산·우주": ["수출 계약·수주잔고가 실제 실적으로 이어지는지", "행사·정책 기대 이후 거래량이 유지되는지", "대표 3종목의 동반 강세가 이어지는지"],
    "2차전지": ["전기차 수요와 배터리 판가 회복 여부", "외국인 수급이 대형주로 이어지는지", "급등 뒤 전일 저점이 지지되는지"],
    "반도체": ["HBM·메모리 가격 상승이 실적 전망에 반영되는지", "삼성전자와 SK하이닉스가 함께 강한지", "원/달러와 외국인 수급 방향"],
    "로봇": ["정책·제품 뉴스가 실제 수주로 연결되는지", "대장주 외 종목으로 거래가 확산되는지", "급등 구간의 거래량 감소 여부"],
    "조선": ["신규 수주와 선가 흐름", "원가·환율 변화가 마진에 미치는 영향", "대형 조선주 동반 상승 여부"],
}

_cache_lock = threading.Lock()
_cache = {"kr": {"at": 0.0, "payload": None}, "us": {"at": 0.0, "payload": None}}

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


def fetch_json(url: str, timeout: int = 8) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Sector Flow; local dashboard)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
        return json.load(response)


def fetch_quote(code: str) -> tuple[str, dict]:
    url = f"https://polling.finance.naver.com/api/realtime/domestic/stock/{code}"
    item = fetch_json(url)["datas"][0]
    close = float(item.get("closePriceRaw") or str(item["closePrice"]).replace(",", ""))
    change = float(item.get("fluctuationsRatioRaw") or item.get("fluctuationsRatio") or 0)
    diff = float(item.get("compareToPreviousClosePriceRaw") or str(item.get("compareToPreviousClosePrice", "0")).replace(",", ""))
    direction = (item.get("compareToPreviousPrice") or {}).get("name")
    if direction == "FALLING":
        diff = -abs(diff)
        change = -abs(change)
    previous = close - diff
    traded_at = item.get("localTradedAt", "")
    history = fetch_naver_history(code)
    return code, {
        "code": code,
        "name": item.get("stockName", code),
        "price": round(close),
        "previousClose": round(previous),
        "returnRate": change,
        "open": float(item.get("openPriceRaw") or close),
        "high": float(item.get("highPriceRaw") or close),
        "low": float(item.get("lowPriceRaw") or close),
        "volume": item.get("accumulatedTradingVolume", "—"),
        "marketCap": item.get("marketValueFull", "—"),
        "tradedAt": traded_at,
        "date": traded_at[:10],
        "marketStatus": item.get("marketStatus", "CLOSE"),
        "history": history,
    }


def fetch_naver_history(code: str, days: int = 180) -> list[dict]:
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    url = f"https://api.stock.naver.com/chart/domestic/item/{code}/day?startDateTime={start}&endDateTime={end}"
    rows = fetch_json(url)
    return [
        {
            "date": str(row.get("localDate", ""))[:8],
            "close": float(row["closePrice"]),
            "open": float(row.get("openPrice") or row["closePrice"]),
            "high": float(row.get("highPrice") or row["closePrice"]),
            "low": float(row.get("lowPrice") or row["closePrice"]),
            "volume": int(row.get("accumulatedTradingVolume") or 0),
        }
        for row in rows
        if row.get("closePrice") is not None
    ]


def fetch_kospi() -> dict:
    url = "https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI"
    item = fetch_json(url)["datas"][0]
    direction = (item.get("compareToPreviousPrice") or {}).get("name")
    change = float(item.get("fluctuationsRatioRaw") or item.get("fluctuationsRatio") or 0)
    if direction == "FALLING":
        change = -abs(change)
    traded_at = item.get("localTradedAt", "")
    return {
        "close": float(item.get("closePriceRaw") or str(item["closePrice"]).replace(",", "")),
        "returnRate": change,
        "date": traded_at[:10],
        "tradedAt": traded_at,
        "marketStatus": item.get("marketStatus", "CLOSE"),
        "volume": item.get("accumulatedTradingVolume", "—"),
        "value": item.get("accumulatedTradingValue", "—"),
    }


def fetch_yahoo_chart(symbol: str, period: str = "6mo") -> tuple[str, dict]:
    """Return recent daily bars and quote metadata from Yahoo's public chart feed."""
    encoded = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range={period}&interval=1d&events=div%2Csplits"
    result = fetch_json(url)["chart"]["result"][0]
    meta = result["meta"]
    quote = result["indicators"]["quote"][0]
    bars = []
    timestamps = result.get("timestamp", [])
    exchange_timezone = ZoneInfo(meta.get("exchangeTimezoneName", "America/New_York"))
    for index, timestamp in enumerate(timestamps):
        close = quote.get("close", [None])[index]
        if close is None:
            is_latest_session = index == len(timestamps) - 1 and meta.get("regularMarketPrice") is not None
            if not is_latest_session:
                continue
            close = float(meta["regularMarketPrice"])
            open_price = float(meta.get("regularMarketOpen") or close)
            high_price = float(meta.get("regularMarketDayHigh") or close)
            low_price = float(meta.get("regularMarketDayLow") or close)
            volume = int(meta.get("regularMarketVolume") or 0)
        else:
            open_price = float(quote.get("open", [close])[index] or close)
            high_price = float(quote.get("high", [close])[index] or close)
            low_price = float(quote.get("low", [close])[index] or close)
            volume = int(quote.get("volume", [0])[index] or 0)
        bars.append(
            {
                "date": datetime.fromtimestamp(timestamp, tz=exchange_timezone).strftime("%Y-%m-%d"),
                "close": float(close),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "volume": volume,
            }
        )
    for index, bar in enumerate(bars):
        previous = bars[index - 1]["close"] if index else None
        bar["returnRate"] = round((bar["close"] / previous - 1) * 100, 4) if previous else 0.0
    latest = bars[-1]
    traded_at = datetime.fromtimestamp(meta.get("regularMarketTime", 0)).astimezone()
    return symbol, {
        "code": symbol,
        "name": meta.get("shortName") or meta.get("longName") or symbol,
        "price": float(meta.get("regularMarketPrice") or latest["close"]),
        "previousClose": float(meta.get("chartPreviousClose") or (bars[-2]["close"] if len(bars) > 1 else latest["close"])),
        "returnRate": float(meta.get("regularMarketChangePercent") or latest["returnRate"]),
        "open": latest["open"],
        "high": float(meta.get("regularMarketDayHigh") or latest["high"]),
        "low": float(meta.get("regularMarketDayLow") or latest["low"]),
        "volume": int(meta.get("regularMarketVolume") or latest["volume"]),
        "tradedAt": traded_at.isoformat(timespec="minutes"),
        "date": latest["date"],
        "marketStatus": "CLOSE",
        "currency": meta.get("currency", "USD"),
        "exchange": meta.get("fullExchangeName") or meta.get("exchangeName", "US"),
        "fiftyTwoWeekLow": meta.get("fiftyTwoWeekLow"),
        "fiftyTwoWeekHigh": meta.get("fiftyTwoWeekHigh"),
        "history": bars,
    }


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def fetch_news(sector: str, limit: int = 2) -> list[dict]:
    query = urllib.parse.quote(f"{sector.replace('·', ' ')} 주식 when:30d")
    url = f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=8, context=SSL_CONTEXT) as response:
        root = ET.fromstring(response.read())
    items = []
    for item in root.findall("./channel/item")[:20]:
        title = clean_text(item.findtext("title", ""))
        source = clean_text(item.findtext("source", "")) or "Google 뉴스"
        published = item.findtext("pubDate", "")
        try:
            published_at = parsedate_to_datetime(published)
            date = published_at.strftime("%Y-%m-%d")
            sort_key = published_at.timestamp()
        except (TypeError, ValueError):
            date = published[:16]
            sort_key = 0
        items.append(
            {
                "date": date,
                "source": source,
                "title": title,
                "summary": f"{title} 관련 최신 보도입니다. 단기 가격 반응보다 실적·수주로 이어지는지 원문에서 확인하세요.",
                "url": item.findtext("link", "#"),
                "_sort": sort_key,
            }
        )
    items.sort(key=lambda row: row["_sort"], reverse=True)
    for item in items:
        item.pop("_sort", None)
    return items[:limit]


def tick_size(price: float) -> int:
    if price >= 500_000:
        return 1_000
    if price >= 100_000:
        return 500
    if price >= 50_000:
        return 100
    if price >= 10_000:
        return 50
    return 10


def rounded(price: float) -> int:
    tick = tick_size(price)
    return int(round(price / tick) * tick)


def won_range(low: float, high: float) -> str:
    return f"{rounded(low):,}~{rounded(high):,}원"


def usd_range(low: float, high: float) -> str:
    return f"${low:,.2f}~${high:,.2f}"


def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    multiplier = 2 / (period + 1)
    result = sum(values[: min(period, len(values))]) / min(period, len(values))
    for value in values[min(period, len(values)) :]:
        result = (value - result) * multiplier + result
    return result


def rsi(values: list[float], period: int = 14) -> float:
    if len(values) < 2:
        return 50.0
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    window = changes[-period:]
    gains = sum(max(change, 0) for change in window) / len(window)
    losses = sum(max(-change, 0) for change in window) / len(window)
    if losses == 0:
        return 100.0 if gains else 50.0
    relative_strength = gains / losses
    return 100 - (100 / (1 + relative_strength))


def atr(history: list[dict], period: int = 14) -> float:
    if not history:
        return 0.0
    true_ranges = []
    for index, bar in enumerate(history):
        previous_close = history[index - 1]["close"] if index else bar["close"]
        true_ranges.append(max(bar["high"] - bar["low"], abs(bar["high"] - previous_close), abs(bar["low"] - previous_close)))
    window = true_ranges[-period:]
    return sum(window) / len(window)


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * ratio))]


def make_entry(quote: dict, sector_return: float, benchmark_return: float, currency: str = "KRW") -> dict:
    close = quote["price"]
    history = quote.get("history") or [
        {"close": quote.get("previousClose", close), "high": quote.get("high", close), "low": quote.get("low", close), "volume": 0},
        {"close": close, "high": quote.get("high", close), "low": quote.get("low", close), "volume": 0},
    ]
    closes = [float(bar["close"]) for bar in history if bar.get("close") is not None]
    last20 = history[-20:]
    last60 = history[-60:]
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    rsi14 = rsi(closes, 14)
    atr14 = max(atr(history, 14), close * 0.006)
    volume_sum = sum(float(bar.get("volume") or 0) for bar in last20)
    vwap20 = (
        sum(((float(bar["high"]) + float(bar["low"]) + float(bar["close"])) / 3) * float(bar.get("volume") or 0) for bar in last20) / volume_sum
        if volume_sum
        else sum(float(bar["close"]) for bar in last20) / len(last20)
    )
    support = percentile([float(bar["low"]) for bar in last60], 0.25)

    short_fair = ema20 * 0.55 + vwap20 * 0.45
    rsi_discount = max(0.0, min(1.0, (rsi14 - 58) / 22)) * atr14 * 0.7
    zone1_mid = min(close, short_fair - rsi_discount)
    long_fair = ema50 * 0.65 + support * 0.35
    zone2_mid = min(zone1_mid - atr14 * 0.75, long_fair)
    zone1_width = max(atr14 * 0.28, zone1_mid * 0.004)
    zone2_width = max(atr14 * 0.35, zone2_mid * 0.005)
    zone1_low = max(0.01, zone1_mid - zone1_width)
    zone1_high = max(zone1_low, min(close, zone1_mid + zone1_width))
    zone2_low = max(0.01, zone2_mid - zone2_width)
    zone2_high = max(zone2_low, min(zone1_low * 0.995, zone2_mid + zone2_width))

    rsi_fit = max(0, 20 - abs(rsi14 - 50) * 0.6)
    sector_bonus = max(-8, min(12, (sector_return - benchmark_return) * 2.4))
    stock_bonus = max(-8, min(12, (float(quote.get("returnRate") or 0) - benchmark_return) * 2))
    trend_bonus = 6 if close >= ema50 else -4
    overheat_penalty = max(0, (rsi14 - 72) * 0.7)
    appeal = round(max(40, min(95, 48 + rsi_fit + sector_bonus + stock_bonus + trend_bonus - overheat_penalty)))
    if currency == "USD":
        zone1 = usd_range(zone1_low, zone1_high)
        zone2 = usd_range(zone2_low, zone2_high)
        ma20_label = f"${ema20:,.2f}"
        ma50_label = f"${ema50:,.2f}"
    else:
        zone1 = won_range(zone1_low, zone1_high)
        zone2 = won_range(zone2_low, zone2_high)
        ma20_label = f"{rounded(ema20):,}원"
        ma50_label = f"{rounded(ema50):,}원"

    if zone1_low <= close <= zone1_high:
        entry_status = "1차 관심 구간 도달"
    elif close > zone1_high:
        distance = (close / zone1_high - 1) * 100
        entry_status = f"1차 구간까지 약 {distance:.1f}% 조정 대기"
    else:
        entry_status = "관심 구간 아래 · 추세 회복 확인"
    rsi_label = "과열" if rsi14 >= 70 else "강세" if rsi14 >= 58 else "중립" if rsi14 >= 42 else "과매도권"
    watch_signals = [
        "시장 대비 상대강도" if float(quote.get("returnRate") or 0) > benchmark_return else "상대강도 회복 확인",
        "20일 추세 위" if close >= ema20 else "20일 EMA 조정권",
        f"RSI {rsi_label}",
    ]
    price_date = quote.get("date", "")
    price_state = "최근 종가" if quote.get("marketStatus") == "CLOSE" else "장중 현재가"
    return {
        "name": quote["name"],
        "code": quote["code"],
        "close": close,
        "priceLabel": f"{price_date} {price_state}".strip(),
        "priceDate": price_date,
        "appeal": appeal,
        "zone1": zone1,
        "zone2": zone2,
        "rsi": round(rsi14, 1),
        "rsiLabel": rsi_label,
        "ma20": ma20_label,
        "ma50": ma50_label,
        "entryStatus": entry_status,
        "watchReason": " · ".join(watch_signals),
        "basis": "RSI14·20일 EMA·20일 VWAP·50일 EMA·ATR14를 종합한 기술적 적정 구간",
    }


def build_technical_entries(sectors: list[dict], quotes: dict[str, dict], benchmark_return: float, currency: str = "KRW") -> dict[str, list[dict]]:
    technical_entries = {}
    for sector in sectors:
        entries = []
        for stock in sector["stocks"]:
            quote = quotes.get(stock["code"], {})
            if "price" not in quote:
                continue
            entry_quote = {**quote, "name": stock["name"]}
            entries.append(make_entry(entry_quote, sector["returnRate"], benchmark_return, currency))
        entries.sort(key=lambda entry: (entry["appeal"], entry["rsi"] < 70), reverse=True)
        if entries:
            technical_entries[sector["name"]] = entries[:5]
    return technical_entries


def build_kr_payload() -> dict:
    kospi = fetch_kospi()
    code_to_name = {code: name for rows in KR_SECTORS.values() for code, name in rows}
    quotes: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(fetch_quote, code): code for code in code_to_name}
        for future in concurrent.futures.as_completed(futures):
            code = futures[future]
            try:
                key, value = future.result()
                quotes[key] = value
            except Exception as exc:  # one unavailable stock must not blank the dashboard
                quotes[code] = {"code": code, "name": code_to_name[code], "error": str(exc)}

    sectors = []
    for name, members in KR_SECTORS.items():
        stocks = []
        for code, fallback_name in members:
            quote = quotes.get(code, {})
            if "returnRate" not in quote:
                continue
            stocks.append({"name": quote.get("name", fallback_name), "code": code, "returnRate": quote["returnRate"]})
        if stocks:
            average = sum(stock["returnRate"] for stock in stocks) / len(stocks)
            sectors.append({"name": name, "returnRate": round(average, 2), "stocks": stocks})
    sectors.sort(key=lambda row: row["returnRate"], reverse=True)

    top = sectors[0]
    top_quotes = [quotes[stock["code"]] for stock in top["stocks"] if stock["code"] in quotes]
    relative = top["returnRate"] - kospi["returnRate"]
    focus_score = round(max(45, min(95, 60 + relative * 5 + sum(q["returnRate"] > 0 for q in top_quotes) * 4)))
    status = "강세 확산" if top["returnRate"] > 2 and len(top_quotes) > 1 else "상대강도 우위"
    if top["returnRate"] > 4:
        status += " · 추격 주의"

    news: dict[str, list[dict]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_news, sector["name"]): sector["name"] for sector in sectors[:4]}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                news[name] = future.result()
            except Exception:
                news[name] = []

    stages = []
    weakest = sectors[-1]
    stage_rows = [
        (weakest, "탄력 둔화"),
        (sectors[0], "현재 주도"),
        (sectors[1], "확산 중"),
        (sectors[2], "다음 후보"),
    ]
    for sector, stage in stage_rows:
        signal = round(max(12, min(96, 48 + (sector["returnRate"] - kospi["returnRate"]) * 10)))
        names = "·".join(stock["name"] for stock in sector["stocks"][:2])
        stages.append(
            {
                "sector": sector["name"],
                "stage": stage,
                "signal": signal,
                "note": f"{names} 기준 평균 {sector['returnRate']:+.2f}% · KOSPI 대비 {sector['returnRate'] - kospi['returnRate']:+.2f}%p",
            }
        )

    as_of = kospi["tradedAt"].replace("T", " ")[:16]
    market_day = {"date": kospi["date"], "kospi": kospi["returnRate"], "sectors": sectors}
    technical_entries = build_technical_entries(sectors, quotes, kospi["returnRate"])
    positives = [f"{q['name']} {q['returnRate']:+.2f}%" for q in sorted(top_quotes, key=lambda q: q["returnRate"], reverse=True)]
    outlook = {
        "asOf": as_of,
        "market": {"name": "KOSPI", "returnRate": kospi["returnRate"], "close": f"{kospi['close']:,.2f}", "breadth": f"거래대금 {kospi['value']}"},
        "focus": {
            "sector": top["name"],
            "score": focus_score,
            "status": status,
            "thesis": f"최근 거래일 KOSPI가 {kospi['returnRate']:+.2f}% 움직인 동안 {top['name']} 대표 종목 평균은 {top['returnRate']:+.2f}%였습니다. 시장 대비 {relative:+.2f}%p의 상대강도와 종목 확산도를 함께 반영한 결과입니다.",
            "positives": positives,
            "checks": SECTOR_CHECKS.get(top["name"], ["대표 종목의 동반 강세가 유지되는지", "거래량이 가격 상승에 동행하는지", "관련 뉴스가 실적으로 연결되는지"]),
        },
        "entries": technical_entries.get(top["name"], [])[:3],
        "rotation": stages,
        "sources": [
            {"label": "KOSPI 최신 시세", "url": "https://finance.naver.com/sise/sise_index.naver?code=KOSPI"},
            {"label": f"{top['name']} 최신 뉴스", "url": f"https://news.google.com/search?q={urllib.parse.quote(top['name'] + ' 주식')}&hl=ko&gl=KR&ceid=KR%3Ako"},
        ],
    }
    return {
        "ok": True,
        "marketKey": "kr",
        "currency": "KRW",
        "benchmarkLabel": "KOSPI",
        "provider": "네이버 금융 · Google 뉴스",
        "requestedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "marketDay": market_day,
        "quotes": quotes,
        "technicalEntries": technical_entries,
        "news": news,
        "outlook": outlook,
    }


def format_volume(value: int | float) -> str:
    value = float(value or 0)
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"


def fetch_us_news(sector: str, etf: str, limit: int = 2) -> list[dict]:
    query = urllib.parse.quote(f"{US_NEWS_QUERIES.get(sector, 'US sector stocks')} {etf} when:14d")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=8, context=SSL_CONTEXT) as response:
        root = ET.fromstring(response.read())
    items = []
    for item in root.findall("./channel/item")[:20]:
        title = clean_text(item.findtext("title", ""))
        source = clean_text(item.findtext("source", "")) or "Google News"
        published = item.findtext("pubDate", "")
        try:
            published_at = parsedate_to_datetime(published)
            date = published_at.strftime("%Y-%m-%d")
            sort_key = published_at.timestamp()
        except (TypeError, ValueError):
            date = published[:16]
            sort_key = 0
        items.append(
            {
                "date": date,
                "source": source,
                "title": title,
                "summary": f"{sector} 섹터의 실적 전망과 자금 흐름에 영향을 줄 수 있는 최신 보도입니다. 제목의 재료가 실제 매출·가이던스로 이어지는지 원문에서 확인하세요.",
                "url": item.findtext("link", "#"),
                "_sort": sort_key,
            }
        )
    items.sort(key=lambda row: row["_sort"], reverse=True)
    for item in items:
        item.pop("_sort", None)
    return items[:limit]


def build_us_payload() -> dict:
    tickers = {"SPY"}
    for config in US_SECTORS.values():
        tickers.add(config["etf"])
        tickers.update(code for code, _ in config["stocks"])

    charts: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fetch_yahoo_chart, ticker): ticker for ticker in tickers}
        for future in concurrent.futures.as_completed(futures):
            ticker = futures[future]
            try:
                key, value = future.result()
                charts[key] = value
            except Exception as exc:
                charts[ticker] = {"code": ticker, "error": str(exc)}

    benchmark = charts.get("SPY", {})
    if not benchmark.get("history"):
        raise RuntimeError("S&P 500 benchmark data is unavailable")

    return_maps = {
        ticker: {bar["date"]: bar for bar in chart.get("history", [])}
        for ticker, chart in charts.items()
        if chart.get("history")
    }
    market_days = []
    for benchmark_bar in benchmark["history"][1:]:
        date = benchmark_bar["date"]
        sectors = []
        for name, config in US_SECTORS.items():
            etf_bar = return_maps.get(config["etf"], {}).get(date)
            if not etf_bar:
                continue
            stocks = []
            for ticker, korean_name in config["stocks"]:
                stock_bar = return_maps.get(ticker, {}).get(date)
                if stock_bar:
                    stocks.append({"name": korean_name, "code": ticker, "returnRate": round(stock_bar["returnRate"], 2)})
            sectors.append({"name": name, "returnRate": round(etf_bar["returnRate"], 2), "stocks": stocks, "etf": config["etf"]})
        sectors.sort(key=lambda row: row["returnRate"], reverse=True)
        market_days.append({"date": date, "kospi": round(benchmark_bar["returnRate"], 2), "sectors": sectors})

    market_days.sort(key=lambda row: row["date"], reverse=True)
    latest_day = market_days[0]
    top = latest_day["sectors"][0]
    top_quotes = []
    for stock in top["stocks"]:
        quote = charts.get(stock["code"], {})
        if "price" in quote:
            quote = {**quote, "name": stock["name"]}
            top_quotes.append(quote)
    relative = top["returnRate"] - latest_day["kospi"]
    focus_score = round(max(45, min(95, 60 + relative * 6 + sum(q["returnRate"] > 0 for q in top_quotes) * 4)))
    status = "강세 확산" if top["returnRate"] > 1 and len(top_quotes) > 1 else "상대강도 우위"
    if top["returnRate"] > 3:
        status += " · 추격 주의"

    news: dict[str, list[dict]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(fetch_us_news, sector["name"], sector.get("etf", "")): sector["name"]
            for sector in latest_day["sectors"][:4]
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                news[name] = future.result()
            except Exception:
                news[name] = []

    weakest = latest_day["sectors"][-1]
    stage_rows = [(weakest, "탄력 둔화"), (latest_day["sectors"][0], "현재 주도"), (latest_day["sectors"][1], "확산 중"), (latest_day["sectors"][2], "다음 후보")]
    stages = []
    for sector, stage in stage_rows:
        signal = round(max(12, min(96, 48 + (sector["returnRate"] - latest_day["kospi"]) * 12)))
        names = "·".join(stock["name"] for stock in sector["stocks"][:2])
        stages.append(
            {
                "sector": sector["name"],
                "stage": stage,
                "signal": signal,
                "note": f"{sector.get('etf', '')} {sector['returnRate']:+.2f}% · {names} 흐름을 함께 확인",
            }
        )

    quotes = {}
    all_names = {code: name for config in US_SECTORS.values() for code, name in config["stocks"]}
    for code, korean_name in all_names.items():
        quote = charts.get(code, {})
        if "price" not in quote:
            continue
        description, business = US_STOCK_INFO.get(
            code,
            (f"{quote.get('name', korean_name)}의 가격·거래량과 섹터 상대강도를 추적하는 미국 상장 기업입니다.", ["미국 주식", "섹터 대표주"]),
        )
        low_52 = quote.get("fiftyTwoWeekLow")
        high_52 = quote.get("fiftyTwoWeekHigh")
        quotes[code] = {
            **quote,
            "name": korean_name,
            "marketCap": "공개 차트 미제공",
            "volume": format_volume(quote.get("volume", 0)),
            "fiftyTwoWeekRange": f"${low_52:,.2f}~${high_52:,.2f}" if low_52 is not None and high_52 is not None else "—",
            "description": description,
            "business": business,
        }

    positives = [f"{q['name']} {q['returnRate']:+.2f}%" for q in sorted(top_quotes, key=lambda q: q["returnRate"], reverse=True)]
    latest_date = latest_day["date"]
    technical_entries = build_technical_entries(latest_day["sectors"], charts, latest_day["kospi"], "USD")
    outlook = {
        "asOf": f"{latest_date} 16:00 ET",
        "market": {"name": "S&P 500", "returnRate": latest_day["kospi"], "close": f"{benchmark['price']:,.2f}", "breadth": "SPY 및 섹터 ETF 기준"},
        "focus": {
            "sector": top["name"],
            "score": focus_score,
            "status": status,
            "thesis": f"최근 미국 거래일 S&P 500이 {latest_day['kospi']:+.2f}% 움직인 동안 {top['name']} ETF({top.get('etf', '')})는 {top['returnRate']:+.2f}%였습니다. 시장 대비 {relative:+.2f}%p의 상대강도와 대표 종목의 동반 여부를 함께 반영했습니다.",
            "positives": positives,
            "checks": ["섹터 ETF 거래량이 가격 상승에 동행하는지", "대표 3종목이 지수보다 강한 흐름을 유지하는지", "뉴스 재료가 다음 실적 가이던스에 반영되는지"],
        },
        "entries": technical_entries.get(top["name"], [])[:3],
        "rotation": stages,
        "sources": [
            {"label": "S&P 500 ETF 시세", "url": "https://finance.yahoo.com/quote/SPY/"},
            {"label": f"{top['name']} 최신 뉴스", "url": f"https://news.google.com/search?q={urllib.parse.quote('US stocks ' + top['name'])}&hl=en-US&gl=US&ceid=US%3Aen"},
        ],
    }
    return {
        "ok": True,
        "marketKey": "us",
        "currency": "USD",
        "benchmarkLabel": "S&P 500",
        "provider": "Yahoo Finance 공개 차트 · Google News",
        "requestedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "marketDay": latest_day,
        "marketDays": market_days,
        "quotes": quotes,
        "technicalEntries": technical_entries,
        "news": news,
        "outlook": outlook,
    }


def latest_payload(market: str = "kr", force: bool = False) -> dict:
    market = market if market in {"kr", "us"} else "kr"
    now = time.time()
    with _cache_lock:
        cached = _cache[market]
        if not force and cached["payload"] and now - cached["at"] < CACHE_SECONDS:
            return cached["payload"]
    payload = build_us_payload() if market == "us" else build_kr_payload()
    with _cache_lock:
        _cache[market]["at"] = now
        _cache[market]["payload"] = payload
    return payload


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def do_GET(self):  # noqa: N802 - stdlib handler API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/market":
            query = urllib.parse.parse_qs(parsed.query)
            force = query.get("refresh", ["0"])[0] == "1"
            market = query.get("market", ["kr"])[0]
            try:
                body = json.dumps(latest_payload(market, force), ensure_ascii=False).encode("utf-8")
                status = 200
            except Exception as exc:
                body = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8")
                status = 502
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--snapshot":
        destination = Path(sys.argv[2]).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        kr_snapshot = build_kr_payload()
        us_snapshot = build_us_payload()
        kr_snapshot["snapshot"] = True
        us_snapshot["snapshot"] = True
        snapshot = {"ok": True, "snapshot": True, "markets": {"kr": kr_snapshot, "us": us_snapshot}}
        destination.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        print(f"Latest KR/US market snapshot: {destination}")
    else:
        print(f"Sector Flow: http://localhost:{PORT}")
        print("페이지를 열 때마다 최신 공개 시세와 뉴스를 확인합니다. 종료: Ctrl+C")
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
