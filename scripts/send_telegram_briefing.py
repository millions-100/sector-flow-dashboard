#!/usr/bin/env python3
"""Build and send the daily sector-flow briefing to a private Telegram chat."""

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


DASHBOARD_URL = "https://millions-100.github.io/sector-flow-dashboard/"
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


def build_message(snapshot: dict) -> str:
    markets = snapshot.get("markets", {})
    kr = markets.get("kr", {})
    us = markets.get("us", {})
    now = datetime.now(SEOUL).strftime("%Y-%m-%d %H:%M KST")
    kr_market = kr.get("outlook", {}).get("market", {})
    us_market = us.get("outlook", {}).get("market", {})
    us_day = us.get("marketDay", {})
    nasdaq_100 = us_market.get("nasdaq100", {})
    kr_focus = kr.get("outlook", {}).get("focus", {})
    us_focus = us.get("outlook", {}).get("focus", {})

    lines = [
        "📊 오늘의 섹터 핵심 브리핑",
        f"기준 시각: {now}",
        "",
        "핵심 판단",
        f"• 한국: {kr_focus.get('sector', '확인 중')} · {kr_focus.get('status', '-')} · {kr_focus.get('score', '-')}점",
        f"• 미국: {us_focus.get('sector', '확인 중')} · {us_focus.get('status', '-')} · {us_focus.get('score', '-')}점",
        "",
        "시장 배경",
        dated_index_line("KOSPI", kr_market.get("close", "-"), kr_market.get("returnRate", 0), kr.get("marketDay", {}).get("date", "")),
        "",
        dated_index_line("S&P 500", us_market.get("close", "-"), us_market.get("returnRate", us_day.get("kospi", 0)), us_market.get("date", us_day.get("date", ""))),
        "",
        dated_index_line("NASDAQ 100", nasdaq_100.get("close", "-"), nasdaq_100.get("returnRate", 0), nasdaq_100.get("date", us_day.get("date", ""))),
        "",
        "중요 뉴스 요약",
    ]

    news = ranked_news(markets)
    if news:
        for index, article in enumerate(news[:3]):
            score = article["importance"]
            if index:
                lines.append("")
            lines.append(
                f"• [{importance_label(score)} {score}] {article['sector']} — {clean_title(article)}"
            )
    else:
        lines.append("• 최근 공개 뉴스가 없어 시장 흐름만 표시합니다.")

    lines.extend(["", "오늘 집중할 섹터"])
    lines.extend(rotation_lines(kr, ("현재 주도", "확산 중")) or ["• 한국: 신호 확인 중"])
    lines.extend(rotation_lines(us, ("현재 주도", "확산 중")) or ["• 미국: 신호 확인 중"])

    lines.extend(["", "앞으로 관심 가질 섹터"])
    lines.extend(rotation_lines(kr, ("다음 후보",)) or ["• 한국: 다음 후보 확인 중"])
    lines.extend(rotation_lines(us, ("다음 후보",)) or ["• 미국: 다음 후보 확인 중"])

    lines.extend(["", "한국 관심 주식 · 우선순위"])
    extend_spaced(lines, stock_lines(kr) or ["• 최신 가격 확인 중"])
    lines.extend(["", "미국 관심 주식 · 우선순위"])
    extend_spaced(lines, stock_lines(us) or ["• 최신 가격 확인 중"])

    us_sectors = us.get("marketDay", {}).get("sectors", [])
    leader = us_sectors[0].get("name", "확인 중") if us_sectors else "확인 중"
    laggard = us_sectors[-1].get("name", "확인 중") if us_sectors else "확인 중"
    lines.extend(
        [
            "",
            f"한 줄 결론: 현재는 {leader}에 집중하고, {laggard}는 회복 신호 전까지 기다립니다.",
            "",
            f"대시보드: {DASHBOARD_URL}",
            "",
            "오늘의 한마디",
            daily_comment(news[:3], kr, us),
        ]
    )
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
