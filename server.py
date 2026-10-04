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
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
HOST = "127.0.0.1"
PORT = 8080
CACHE_SECONDS = 60

SECTORS = {
    "방산·우주": [
        ("047810", "한국항공우주"),
        ("079550", "LIG넥스원"),
        ("012450", "한화에어로스페이스"),
    ],
    "2차전지": [
        ("373220", "LG에너지솔루션"),
        ("006400", "삼성SDI"),
        ("003670", "포스코퓨처엠"),
    ],
    "반도체": [("000660", "SK하이닉스"), ("005930", "삼성전자")],
    "로봇": [("277810", "레인보우로보틱스"), ("454910", "두산로보틱스")],
    "조선": [
        ("009540", "HD한국조선해양"),
        ("042660", "한화오션"),
        ("010140", "삼성중공업"),
    ],
    "바이오": [("207940", "삼성바이오로직스"), ("068270", "셀트리온")],
    "전력·에너지": [("034020", "두산에너빌리티"), ("015760", "한국전력")],
    "금융": [("105560", "KB금융"), ("055550", "신한지주")],
    "통신": [("017670", "SK텔레콤"), ("030200", "KT")],
    "자동차": [("005380", "현대차"), ("000270", "기아")],
}

SECTOR_CHECKS = {
    "방산·우주": ["수출 계약·수주잔고가 실제 실적으로 이어지는지", "행사·정책 기대 이후 거래량이 유지되는지", "대표 3종목의 동반 강세가 이어지는지"],
    "2차전지": ["전기차 수요와 배터리 판가 회복 여부", "외국인 수급이 대형주로 이어지는지", "급등 뒤 전일 저점이 지지되는지"],
    "반도체": ["HBM·메모리 가격 상승이 실적 전망에 반영되는지", "삼성전자와 SK하이닉스가 함께 강한지", "원/달러와 외국인 수급 방향"],
    "로봇": ["정책·제품 뉴스가 실제 수주로 연결되는지", "대장주 외 종목으로 거래가 확산되는지", "급등 구간의 거래량 감소 여부"],
    "조선": ["신규 수주와 선가 흐름", "원가·환율 변화가 마진에 미치는 영향", "대형 조선주 동반 상승 여부"],
}

_cache_lock = threading.Lock()
_cache = {"at": 0.0, "payload": None}

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
    }


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


def make_entry(quote: dict, sector_return: float, kospi_return: float) -> dict:
    close = quote["price"]
    previous = quote["previousClose"]
    session_low = quote["low"]
    zone1_mid = min(close * 0.985, max(previous, session_low))
    zone2_mid = min(session_low * 0.982, previous * 0.975)
    invalid = rounded(min(zone2_mid * 0.965, session_low * 0.95))
    appeal = round(max(48, min(92, 78 + (sector_return - kospi_return) * 2 - max(0, quote["returnRate"]) * 3)))
    return {
        "name": quote["name"],
        "code": quote["code"],
        "close": close,
        "priceLabel": "최근 종가" if quote.get("marketStatus") == "CLOSE" else "장중 현재가",
        "appeal": appeal,
        "zone1": won_range(zone1_mid * 0.99, zone1_mid * 1.005),
        "zone2": won_range(zone2_mid * 0.985, zone2_mid * 1.005),
        "invalid": f"{invalid:,}원 이탈",
        "basis": "전일 종가·당일 저가를 바탕으로 다시 계산한 눌림 관찰 구간",
    }


def build_payload() -> dict:
    kospi = fetch_kospi()
    code_to_name = {code: name for rows in SECTORS.values() for code, name in rows}
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
    for name, members in SECTORS.items():
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
        "entries": [make_entry(q, top["returnRate"], kospi["returnRate"]) for q in sorted(top_quotes, key=lambda q: q["returnRate"], reverse=True)[:3]],
        "rotation": stages,
        "sources": [
            {"label": "KOSPI 최신 시세", "url": "https://finance.naver.com/sise/sise_index.naver?code=KOSPI"},
            {"label": f"{top['name']} 최신 뉴스", "url": f"https://news.google.com/search?q={urllib.parse.quote(top['name'] + ' 주식')}&hl=ko&gl=KR&ceid=KR%3Ako"},
        ],
    }
    return {
        "ok": True,
        "provider": "네이버 금융 · Google 뉴스",
        "requestedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "marketDay": market_day,
        "quotes": quotes,
        "news": news,
        "outlook": outlook,
    }


def latest_payload(force: bool = False) -> dict:
    now = time.time()
    with _cache_lock:
        if not force and _cache["payload"] and now - _cache["at"] < CACHE_SECONDS:
            return _cache["payload"]
    payload = build_payload()
    with _cache_lock:
        _cache["at"] = now
        _cache["payload"] = payload
    return payload


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST), **kwargs)

    def do_GET(self):  # noqa: N802 - stdlib handler API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/market":
            query = urllib.parse.parse_qs(parsed.query)
            force = query.get("refresh", ["0"])[0] == "1"
            try:
                body = json.dumps(latest_payload(force), ensure_ascii=False).encode("utf-8")
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
    print(f"Sector Flow: http://localhost:{PORT}")
    print("페이지를 열 때마다 최신 공개 시세와 뉴스를 확인합니다. 종료: Ctrl+C")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
