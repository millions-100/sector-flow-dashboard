#!/usr/bin/env python3
"""Build and send the daily US-market briefing to a private Telegram chat."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SEOUL = ZoneInfo("Asia/Seoul")
TRUSTED_SOURCES = (
    "연합뉴스",
    "로이터",
    "reuters",
    "ap ",
    "bloomberg",
    "한국은행",
    "정부",
    "거래소",
    "공시",
)
HIGH_IMPACT_WORDS = (
    "금리",
    "물가",
    "규제",
    "관세",
    "실적",
    "수주",
    "계약",
    "수출",
    "전쟁",
    "유가",
    "반도체",
    "파업",
    "인수",
)


def signed(value: float) -> str:
    return f"{float(value):+.2f}%"


def news_score(article: dict, sector_rank: int) -> int:
    text = f"{article.get('source', '')} {article.get('title', '')}".lower()
    score = 55
    if any(source in text for source in TRUSTED_SOURCES):
        score += 12
    if any(word in text for word in HIGH_IMPACT_WORDS):
        score += 15
    score += max(0, 10 - sector_rank * 2)
    try:
        published = datetime.strptime(article.get("date", ""), "%Y-%m-%d").date()
        age = (datetime.now(SEOUL).date() - published).days
        score += 10 if age <= 1 else 5 if age <= 3 else 0
    except ValueError:
        pass
    return min(95, score)


def importance_label(score: int) -> str:
    if score >= 88:
        return "매우 높음"
    if score >= 75:
        return "높음"
    if score >= 62:
        return "보통"
    return "낮음"


def ranked_news(markets: dict) -> list[dict]:
    items = []
    for market_key in ("kr", "us"):
        market = markets.get(market_key, {})
        sector_order = {
            row.get("name"): index
            for index, row in enumerate(market.get("marketDay", {}).get("sectors", []))
        }
        for sector, articles in market.get("news", {}).items():
            rank = sector_order.get(sector, 9)
            for article in articles or []:
                items.append(
                    {
                        **article,
                        "market": "한국" if market_key == "kr" else "미국",
                        "sector": sector,
                        "importance": news_score(article, rank),
                    }
                )
    items.sort(key=lambda item: (item["importance"], item.get("date", "")), reverse=True)
    seen = set()
    unique = []
    for item in items:
        title = item.get("title", "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        unique.append(item)
        if len(unique) == 4:
            break
    return unique


def top_sector_lines(market: dict, limit: int = 3) -> list[str]:
    rows = market.get("marketDay", {}).get("sectors", [])[:limit]
    return [f"{index}. {row['name']} {signed(row.get('returnRate', 0))}" for index, row in enumerate(rows, 1)]


def prioritized_entries(market: dict, limit: int = 3) -> list[tuple[str, dict]]:
    stage_bonus = {"현재 주도": 18, "확산 중": 12, "다음 후보": 6}
    stages = {
        row.get("sector"): row.get("stage")
        for row in market.get("outlook", {}).get("rotation", [])
    }
    ranked = []
    technicals = market.get("technicalEntries", {})
    if not technicals:
        focus = market.get("outlook", {}).get("focus", {}).get("sector", "")
        technicals = {focus: market.get("outlook", {}).get("entries", [])}
    for sector, entries in technicals.items():
        for entry in entries:
            in_range = bool(entry.get("isInFairRange")) or "도달" in entry.get("entryStatus", "")
            priority = float(entry.get("appeal", 0)) + stage_bonus.get(stages.get(sector), 0)
            priority += 24 if in_range else 0
            if float(entry.get("rsi", 50)) >= 70:
                priority -= 10
            ranked.append((priority, sector, entry))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return [(sector, entry) for _, sector, entry in ranked[:limit]]


def stock_lines(market: dict, limit: int = 3) -> list[str]:
    entries = prioritized_entries(market, limit)
    currency = market.get("currency", "")
    lines = []
    for rank, (sector, entry) in enumerate(entries, 1):
        close = entry.get("close", 0)
        price = f"{close:,.0f}원" if currency == "KRW" else f"${close:,.2f}"
        in_range = bool(entry.get("isInFairRange")) or "도달" in entry.get("entryStatus", "")
        price_status = "✅ 적정가격 진입" if in_range else "⏳ 적정가격 대기"
        lines.append(
            f"{rank}. {entry.get('name')} ({entry.get('code', '-')}) · {sector}\n"
            f"   현재 {price}\n"
            f"   적정가격 {entry.get('zone1', '-')} · {price_status}\n"
            f"   관심 {entry.get('appeal', '-')}점 · RSI {entry.get('rsi', '-')}"
        )
    return lines


def clean_title(article: dict, limit: int = 78) -> str:
    title = article.get("title", "").strip()
    source = article.get("source", "").strip()
    if source:
        suffix = f" - {source}"
        if title.endswith(suffix):
            title = title[: -len(suffix)]
    title = title.strip(" \"'“”‘’")
    return title if len(title) <= limit else f"{title[: limit - 1].rstrip()}…"


def rotation_lines(market: dict, stages: tuple[str, ...]) -> list[str]:
    rows = [
        row
        for row in market.get("outlook", {}).get("rotation", [])
        if row.get("stage") in stages
    ]
    return [
        f"• {row.get('sector')} · {row.get('stage')} · 신호 {row.get('signal', '-')}"
        for row in rows[:2]
    ]


def dated_index_line(name: str, close: str, return_rate: float, date: str) -> str:
    short_date = date[5:].replace("-", "/") if len(date) >= 10 else date or "기준일 확인 중"
    return f"• {name} {close} · {signed(return_rate)}\n  {short_date} 종가 · 전 거래일 대비"


def extend_spaced(lines: list[str], items: list[str]) -> None:
    for index, item in enumerate(items):
        if index:
            lines.append("")
        lines.append(item)


def news_impact_reason(article: dict) -> str:
    title = article.get("title", "").lower()
    if any(word in title for word in ("실적", "순익", "영업이익", "매출", "earnings", "profit", "revenue", "guidance")):
        return "실적·이익 전망을 언급한 부분이 섹터의 이익 추정치 개선 가능성을 보여주는 재료입니다."
    if any(word in title for word in ("수주", "계약", "수출", "order", "contract", "export")):
        return "수주·계약을 언급한 부분이 향후 매출 가시성을 높일 수 있는 재료입니다."
    if any(word in title for word in ("금리", "물가", "고용", "연준", "rate", "inflation", "jobs", "fed")):
        return "금리·경기 기대를 바꾸는 부분이 성장주 할인율과 섹터 자금 흐름에 영향을 주는 재료입니다."
    if any(word in title for word in ("관세", "규제", "정책", "정부", "보조금", "tariff", "regulation", "policy")):
        return "정책·규제 변화 부분이 섹터의 비용과 수요 전망을 바꿀 수 있는 재료입니다."
    if any(word in title for word in ("수요", "판매", "출하", "demand", "sales", "shipments")):
        return "수요·판매 흐름을 언급한 부분이 업황 회복 여부를 판단하는 직접적인 근거입니다."
    if any(word in title for word in ("상승", "급등", "질주", "신고가", "winning streak", "rally", "record high")):
        return "주가 모멘텀을 언급한 부분이 해당 섹터로 자금이 유입되고 있음을 보여주는 단기 재료입니다."
    return "업황 기대와 자금 흐름 변화를 언급한 부분이 해당 섹터를 다시 평가하게 만드는 재료입니다."


def daily_comment(news: list[dict], kr: dict, us: dict) -> str:
    news_scores: dict[str, int] = {}
    for article in news:
        sector = article.get("sector", "")
        news_scores[sector] = news_scores.get(sector, 0) + int(article.get("importance", 0))
    news_leader = max(news_scores, key=news_scores.get) if news_scores else "주요 뉴스 섹터"
    leader_articles = [article for article in news if article.get("sector") == news_leader]
    lead_article = max(leader_articles, key=lambda row: row.get("importance", 0)) if leader_articles else {}

    kr_leader = kr.get("outlook", {}).get("focus", {}).get("sector", "한국 주도 섹터")
    us_leader = us.get("outlook", {}).get("focus", {}).get("sector", "미국 주도 섹터")
    next_sectors = []
    for market in (kr, us):
        for row in market.get("outlook", {}).get("rotation", []):
            if row.get("stage") == "다음 후보" and row.get("sector"):
                next_sectors.append(row["sector"])

    if lead_article:
        evidence = (
            f"• 뉴스 근거\n"
            f"  “{clean_title(lead_article, 68)}”\n"
            f"  {news_impact_reason(lead_article)}"
        )
    else:
        evidence = "• 뉴스 근거\n  중요도 높은 신규 뉴스가 부족해 가격 흐름을 우선 확인합니다."

    if news_leader in {kr_leader, us_leader}:
        price_check = f"• 가격 확인\n  {news_leader}가 실제 상대강도 선두와 겹쳐 뉴스가 가격으로 확인되고 있습니다."
        judgment = "• 판단\n  적정가격에 진입한 해당 섹터 종목을 우선 보세요."
    else:
        price_check = f"• 가격 확인\n  상대강도 선두는 한국 {kr_leader}, 미국 {us_leader}로 뉴스 섹터와 다릅니다."
        judgment = "• 판단\n  뉴스만 따른 추격보다 가격 흐름이 확인된 종목을 우선 보세요."
    if next_sectors:
        judgment += f" 다음 순환 후보는 {', '.join(next_sectors[:2])}입니다."
    return f"{evidence}\n\n{price_check}\n\n{judgment}"


def market_news_score(article: dict) -> int:
    text = f"{article.get('source', '')} {article.get('title', '')}".lower()
    score = 42
    trusted = ("reuters", "bloomberg", "associated press", "federal reserve", "cnbc", "wall street journal", "wsj")
    mainstream = ("yahoo finance", "financial times", "marketwatch", "barron's", "nbc news", "fox business", "fortune")
    direct = ("rate", "inflation", "cpi", "jobs", "payroll", "treasury", "earnings", "guidance", "tariff", "nvidia")
    broad = ("s&p 500", "nasdaq", "stock market", "stock markets", "yield", "recession", "sell-off", "correction", "ai")
    irrelevant = ("college", "challenge winners", "scholarship", "community event", "sports", "lottery")
    is_trusted = any(word in text for word in trusted)
    is_mainstream = any(word in text for word in mainstream)
    score += 20 if is_trusted else 10 if is_mainstream else 0
    score += 24 if any(word in text for word in direct) else 14 if any(word in text for word in broad) else 0
    score -= 40 if any(word in text for word in irrelevant) else 0
    if not is_trusted and not is_mainstream:
        score = min(score, 60)
    return max(20, min(95, score))


def market_news_reason(article: dict) -> str:
    title = article.get("title", "").lower()
    if any(word in title for word in ("fed", "rate", "powell", "inflation", "cpi")):
        return "금리 기대와 성장주 할인율을 바꿔 QQQ·QLD에 직접 영향을 줄 수 있습니다."
    if any(word in title for word in ("jobs", "payroll", "employment", "unemployment")):
        return "고용 강도는 연준의 금리 경로와 경기 연착륙 기대를 동시에 바꿀 수 있습니다."
    if any(word in title for word in ("treasury", "yield", "bond")):
        return "국채금리 변화는 밸류에이션이 높은 나스닥 대형주의 부담 또는 완화 요인입니다."
    if any(word in title for word in ("nvidia", "ai", "semiconductor", "chip")):
        return "AI·반도체 비중이 큰 나스닥100의 실적 기대와 자금 흐름에 연결됩니다."
    if any(word in title for word in ("earnings", "revenue", "profit", "guidance")):
        return "실적과 가이던스가 지수 이익 전망을 바꾸는 재료입니다."
    if any(word in title for word in ("tariff", "trade", "china", "war")):
        return "관세·무역 변수는 빅테크 공급망과 위험선호에 영향을 줄 수 있습니다."
    return "미국 주식의 위험선호와 주요 지수 방향에 영향을 줄 수 있는 뉴스입니다."


def market_news_brief(article: dict) -> tuple[str, str]:
    title = article.get("title", "").lower()
    falling = any(word in title for word in ("fall", "fell", "drop", "lower", "slip", "plunge", "sell-off", "correction", "losing"))
    rising = any(word in title for word in ("rise", "rose", "higher", "jump", "surge", "rebound", "rally"))
    if any(word in title for word in ("treasury", "yield", "bond")):
        if falling:
            return "미 국채금리 하락", "국채금리 하락으로 나스닥 성장주의 할인율 부담이 완화되는 흐름입니다."
        if rising:
            return "미 국채금리 상승", "국채금리 상승이 고평가 성장주와 QQQ에 부담을 주는 흐름입니다."
        return "미 국채금리 변화", "국채금리 방향이 QQQ·QLD의 밸류에이션에 영향을 주는 내용입니다."
    if any(word in title for word in ("nvidia", "semiconductor", "chip", "ai")):
        if falling:
            return "AI·반도체 약세", "엔비디아와 반도체 약세가 나스닥100의 변동성을 키우는 내용입니다."
        return "AI·반도체 흐름", "엔비디아와 AI 반도체 흐름이 나스닥100 방향을 좌우한다는 내용입니다."
    if any(word in title for word in ("s&p 500", "nasdaq", "stock market", "stock markets")):
        if falling:
            return "미국 증시 조정 확대", "S&P 500과 나스닥의 하락이 이어지며 위험회피가 강해졌다는 내용입니다."
        if rising:
            return "미국 증시 반등", "S&P 500과 나스닥의 반등으로 위험선호가 회복되는 내용입니다."
        return "미국 증시 방향 점검", "S&P 500과 나스닥의 수급·추세를 다룬 주요 시장 뉴스입니다."
    if any(word in title for word in ("fed", "rate", "powell", "inflation", "cpi")):
        return "연준·물가·금리", "연준의 금리 경로 기대가 바뀌며 QQQ·QLD의 할인율에 영향을 주는 내용입니다."
    if any(word in title for word in ("jobs", "payroll", "employment", "unemployment")):
        return "미국 고용지표", "고용 흐름이 경기와 연준의 금리 판단을 바꿀 수 있다는 내용입니다."
    if any(word in title for word in ("earnings", "revenue", "profit", "guidance")):
        return "빅테크 실적", "실적과 가이던스가 나스닥100의 이익 전망에 영향을 주는 내용입니다."
    if any(word in title for word in ("tariff", "trade", "china", "war")):
        return "무역·관세 변수", "무역정책 변화가 빅테크 공급망과 위험선호에 영향을 주는 내용입니다."
    return "미국시장 주요 변수", market_news_reason(article)


def market_news_watchpoint(article: dict) -> str:
    title = article.get("title", "").lower()
    if any(word in title for word in ("treasury", "yield", "bond")):
        return "확인: 미국 10년물과 QQQ가 다음 거래일에도 같은 방향을 유지하는지 봅니다."
    if any(word in title for word in ("nvidia", "semiconductor", "chip", "ai")):
        return "확인: 엔비디아·반도체 ETF가 나스닥보다 강해지는지 봅니다."
    if any(word in title for word in ("s&p 500", "nasdaq", "stock market", "stock markets")):
        return "확인: VIX 진정과 상승 종목 수 회복이 함께 나타나는지 봅니다."
    if any(word in title for word in ("fed", "rate", "powell", "inflation", "cpi")):
        return "확인: 금리 기대 변화가 미국 10년물과 성장주 가격에 반영되는지 봅니다."
    if any(word in title for word in ("jobs", "payroll", "employment", "unemployment")):
        return "확인: 고용 발표 뒤 국채금리와 나스닥 선물이 어느 방향으로 움직이는지 봅니다."
    if any(word in title for word in ("earnings", "revenue", "profit", "guidance")):
        return "확인: 실적보다 다음 분기 가이던스와 시간외 주가 반응을 우선 봅니다."
    if any(word in title for word in ("tariff", "trade", "china", "war")):
        return "확인: 반도체·빅테크 공급망 종목으로 충격이 확산되는지 봅니다."
    return "확인: VIX·국채금리·시장 상승 종목 수가 같은 방향인지 봅니다."


def combined_news_summary(news: list[dict]) -> list[str]:
    summaries = []
    topics = []
    for article in news[:3]:
        topic, summary = market_news_brief(article)
        topics.append(topic)
        summaries.append(f"• {summary}")
    negative = any("조정" in topic or "약세" in topic or "상승" in topic for topic in topics)
    supportive = any("하락" in topic or "반등" in topic for topic in topics)
    if negative and supportive:
        conclusion = "• 종합: 금리 부담 완화보다 증시·반도체 약세가 강해 아직 위험회피가 우세합니다."
    elif negative:
        conclusion = "• 종합: 지수와 성장주 약세가 함께 나타나 변동성 진정을 먼저 확인해야 합니다."
    elif supportive:
        conclusion = "• 종합: 금리와 지수 흐름은 우호적이며 QQQ의 추세 유지 여부가 핵심입니다."
    else:
        conclusion = "• 종합: VIX와 미국 10년물 방향이 QQQ·QLD의 다음 움직임을 결정할 가능성이 큽니다."
    return [*summaries, conclusion]


def similar_price_lines(return_rate: float, item: dict, *, always: bool = False, label: str = "비슷한 종가") -> list[str]:
    if (not always and float(return_rate or 0) >= 0) or not item:
        return []
    try:
        short_date = datetime.strptime(item.get("date", ""), "%Y-%m-%d").strftime("%y/%m/%d")
    except ValueError:
        short_date = item.get("date", "-")
    return [
        f"  ↳ {label}: {short_date} · {float(item.get('close') or 0):,.2f}",
        f"     경과: {item.get('daysAgo', '-')}일 전",
    ]


def instrument_lines(label: str, item: dict) -> list[str]:
    if not item or item.get("error"):
        return [f"• {label}: 최신 데이터 확인 중"]
    return [
        f"• {label} ${item.get('price', 0):,.2f} · {signed(item.get('returnRate', 0))}",
        f"  RSI {item.get('rsi', '-')} ({item.get('rsiLabel', '-')}) · {item.get('trend', '-')}",
        f"  관심 가격 {item.get('fairRange', '-')} · {item.get('interestStatus', '-')}",
        f"  1주 {signed(item.get('weekReturn', 0))} · 1개월 {signed(item.get('monthReturn', 0))} · 고점 대비 {signed(item.get('drawdown', 0))}",
    ]


def market_judgment(pulse: dict) -> tuple[str, str]:
    qqq = pulse.get("qqq", {})
    qld = pulse.get("qld", {})
    vix = pulse.get("vix", {})
    qqq_rsi = float(qqq.get("rsi") or 50)
    vix_value = float(vix.get("value") or 0)
    if vix_value >= 25 or qqq.get("trend") == "추세 회복 필요":
        market_state = "위험관리 우선"
    elif qqq_rsi >= 70:
        market_state = "상승 추세지만 단기 과열"
    elif qqq.get("trend") == "상승 추세" and vix_value < 20:
        market_state = "상승 추세 유지"
    else:
        market_state = "중립 · 방향 확인"

    if qld.get("isInFairRange") and market_state == "상승 추세 유지":
        qld_action = "QLD는 기술적 관심 구간 안에서 분할 관찰"
    elif float(qld.get("fairPriceDistance") or 0) > 0:
        qld_action = "QLD는 추격보다 표시된 관심 가격까지 조정 대기"
    else:
        qld_action = "QLD는 QQQ 추세 회복을 확인한 뒤 관찰"
    return market_state, qld_action


def build_message(snapshot: dict) -> str:
    us = snapshot.get("markets", {}).get("us", {})
    pulse = us.get("marketPulse", {})
    market = us.get("outlook", {}).get("market", {})
    nasdaq = market.get("nasdaq100", {})
    date = pulse.get("date") or us.get("marketDay", {}).get("date", "기준일 확인 중")
    now_dt = datetime.now(SEOUL)
    now = now_dt.strftime("%Y-%m-%d %H:%M KST")
    try:
        market_date = datetime.strptime(date, "%Y-%m-%d").date()
        stale_note = " · 미국 휴장/최근 거래일 기준" if (now_dt.date() - market_date).days >= 4 else ""
    except ValueError:
        stale_note = ""
    vix = pulse.get("vix", {})
    treasury = pulse.get("treasury10y", {})
    similar_prices = pulse.get("previousSimilarPrice", {})
    sp_return = float(market.get("returnRate") or 0)
    nasdaq_return = float(nasdaq.get("returnRate") or 0)

    lines = [
        "🇺🇸 미국시장 마감 브리핑",
        f"작성 시각: {now}",
        f"시장 기준: {date} 미국 종가{stale_note}",
        "",
        "시장 한눈에 보기",
        f"• S&P 500 {market.get('close', '-')} · {signed(sp_return)}",
    ]
    lines.extend(similar_price_lines(sp_return, similar_prices.get("sp500", {})))
    lines.append(f"• NASDAQ 100 {nasdaq.get('close', '-')} · {signed(nasdaq_return)}")
    lines.extend(similar_price_lines(nasdaq_return, similar_prices.get("nasdaq100", {})))
    lines.extend(
        [
        "",
        "QQQ · QLD 기술 상태",
        ]
    )
    lines.extend(instrument_lines("QQQ", pulse.get("qqq", {})))
    lines.append("")
    lines.extend(instrument_lines("QLD", pulse.get("qld", {})))
    lines.extend(
        [
            "",
            "공포·금리",
            f"• VIX {vix.get('value', '-')} · {signed(vix.get('returnRate', 0))} · {vix.get('state', '확인 중')}",
        ]
    )
    lines.extend(similar_price_lines(vix.get("returnRate", 0), similar_prices.get("vix", {}), always=True, label="비슷한 VIX"))
    lines.extend(
        [
            f"• 미국 10년물 {treasury.get('value', '-')}% · 전일 대비 {float(treasury.get('basisPointChange') or 0):+.1f}bp",
            "",
            "중요 뉴스 종합",
        ]
    )

    ranked_news_items = sorted(
        us.get("marketNews", []),
        key=lambda article: (market_news_score(article), article.get("publishedAt", "")),
        reverse=True,
    )
    news = []
    seen_topics = set()
    for article in ranked_news_items:
        topic, _ = market_news_brief(article)
        if topic in seen_topics:
            continue
        seen_topics.add(topic)
        news.append(article)
        if len(news) == 3:
            break
    if news:
        lines.extend(combined_news_summary(news))
    else:
        lines.append("• 신규 주요 뉴스 확인 중")
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def telegram_request(token: str, method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(payload or {}).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except Exception as exc:
        raise RuntimeError(f"Telegram 요청에 실패했습니다: {type(exc).__name__}") from None
    if not result.get("ok"):
        raise RuntimeError(f"Telegram이 요청을 거부했습니다: {result.get('description', 'unknown error')}")
    return result


def find_private_chat_id(token: str) -> str:
    result = telegram_request(token, "getUpdates")
    chats = []
    for update in result.get("result", []):
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        if chat.get("type") == "private" and chat.get("id") is not None:
            chats.append(str(chat["id"]))
    if not chats:
        raise RuntimeError("개인 대화를 찾지 못했습니다. 봇 채팅에서 /start를 한 번 보내 주세요.")
    return chats[-1]


def split_message(message: str, limit: int = 3800) -> list[str]:
    chunks = []
    current = []
    size = 0
    for paragraph in message.split("\n"):
        extra = len(paragraph) + 1
        if current and size + extra > limit:
            chunks.append("\n".join(current))
            current = []
            size = 0
        current.append(paragraph)
        size += extra
    if current:
        chunks.append("\n".join(current))
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    message = build_message(snapshot)
    if args.preview:
        print(message)
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("GitHub 비밀 설정 TELEGRAM_BOT_TOKEN이 없습니다.")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or find_private_chat_id(token)
    for chunk in split_message(message):
        telegram_request(
            token,
            "sendMessage",
            {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"},
        )
    print("Telegram briefing sent successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
