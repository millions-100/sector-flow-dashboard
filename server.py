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

KR_STOCK_INFO = {
    "047810": ("국산 군용기 개발과 생산을 총괄하는 항공우주 체계종합기업으로, 전투기·훈련기·헬기·위성 사업을 합니다.", ["군용기", "헬기", "위성"]),
    "079550": ("유도무기와 감시정찰, 지휘통제·통신, 항공전자 체계를 개발하는 국내 정밀방산 기업입니다.", ["유도무기", "감시정찰", "항공전자"]),
    "012450": ("K9 자주포·천무를 비롯한 지상 방산체계와 항공기 엔진, 우주 발사체 엔진을 만드는 종합 방산기업입니다.", ["K9 자주포", "항공엔진", "우주"]),
    "064350": ("K2 전차와 장갑차 등 방산차량, 철도차량 및 수소·플랜트 설비를 제작하는 중공업 기업입니다.", ["K2 전차", "철도차량", "플랜트"]),
    "373220": ("전기차·에너지저장장치용 배터리 셀과 배터리 관리 솔루션을 글로벌 완성차 업체에 공급합니다.", ["전기차 배터리", "ESS", "배터리 솔루션"]),
    "006400": ("전기차·에너지저장장치용 배터리와 반도체·디스플레이 소재를 생산하는 전자재료 기업입니다.", ["전기차 배터리", "ESS", "전자재료"]),
    "003670": ("전기차 배터리의 핵심 소재인 양극재·음극재와 첨단 화학소재를 생산하는 배터리 소재 기업입니다.", ["양극재", "음극재", "배터리 소재"]),
    "000660": ("DRAM·NAND 플래시와 AI 서버용 HBM을 설계·생산하는 글로벌 메모리 반도체 기업입니다.", ["HBM", "DRAM", "NAND"]),
    "005930": ("메모리·시스템 반도체와 스마트폰, TV·가전, 네트워크 장비를 만드는 글로벌 전자기업입니다.", ["반도체", "스마트폰", "가전"]),
    "042700": ("반도체 패키징 장비를 만드는 기업으로, AI용 HBM 적층에 쓰이는 TC 본더가 핵심 제품입니다.", ["TC 본더", "HBM 장비", "반도체 후공정"]),
    "277810": ("협동로봇과 휴머노이드 로봇 플랫폼을 개발하며, 이족보행 로봇 기술을 상용화하는 로봇 기업입니다.", ["휴머노이드", "협동로봇", "이족보행"]),
    "454910": ("제조·물류·서비스 현장에 쓰이는 협동로봇과 로봇 자동화 솔루션을 개발·판매합니다.", ["협동로봇", "자동화", "서비스 로봇"]),
    "108490": ("로봇 구동장치 DYNAMIXEL과 자율주행 로봇 플랫폼을 개발하는 로봇 부품·솔루션 기업입니다.", ["액추에이터", "DYNAMIXEL", "자율주행 로봇"]),
    "009540": ("HD현대의 조선 중간지주사로 LNG선·컨테이너선·해양플랜트와 친환경 선박 기술을 총괄합니다.", ["LNG선", "친환경 선박", "해양플랜트"]),
    "042660": ("LNG 운반선과 상선, 잠수함·수상함 등 특수선 및 해양플랜트를 건조하는 조선사입니다.", ["LNG선", "특수선", "해양플랜트"]),
    "010140": ("LNG선·컨테이너선과 FLNG 등 고부가가치 선박·해양설비를 설계하고 건조하는 조선사입니다.", ["LNG선", "FLNG", "컨테이너선"]),
    "207940": ("바이오의약품의 공정개발부터 대규모 생산·품질관리까지 제공하는 글로벌 CDMO 기업입니다.", ["바이오 CDMO", "항체의약품", "ADC"]),
    "068270": ("자가면역질환·항암 분야의 바이오시밀러와 신약을 개발·생산해 글로벌 시장에 판매합니다.", ["바이오시밀러", "항체치료제", "신약"]),
    "326030": ("뇌전증 치료제 세노바메이트를 중심으로 중추신경계 신약을 개발하고 글로벌 판매하는 제약기업입니다.", ["뇌전증", "세노바메이트", "중추신경계"]),
    "034020": ("원전 주기기와 발전용 터빈, 해상풍력·수소 설비를 제작하고 발전소 서비스를 제공하는 에너지 기업입니다.", ["원전", "가스터빈", "해상풍력"]),
    "015760": ("국내 발전사에서 전력을 구매해 송배전망을 운영하고 가정·기업에 전기를 판매하는 공기업입니다.", ["전력 판매", "송배전망", "에너지 신사업"]),
    "298040": ("초고압 변압기·차단기와 전력망 솔루션, 전동기·발전기 등 산업용 전기기기를 만드는 중전기 기업입니다.", ["초고압 변압기", "차단기", "전동기·발전기"]),
    "105560": ("KB국민은행을 중심으로 카드·증권·보험·자산운용을 아우르는 종합 금융지주회사입니다.", ["은행", "카드", "증권·보험"]),
    "055550": ("신한은행을 중심으로 카드·증권·보험·자산운용 사업을 운영하는 종합 금융지주회사입니다.", ["은행", "카드", "증권·보험"]),
    "086790": ("하나은행을 중심으로 증권·카드·캐피탈·자산운용 사업을 운영하는 종합 금융지주회사입니다.", ["은행", "증권", "카드·캐피탈"]),
    "017670": ("이동통신을 기반으로 AI 데이터센터·클라우드·AI 에이전트 사업을 확대하는 통신기업입니다.", ["이동통신", "AI", "데이터센터"]),
    "030200": ("유무선 통신과 기업용 네트워크, 클라우드·데이터센터·미디어 서비스를 제공하는 통신기업입니다.", ["통신", "클라우드", "미디어"]),
    "032640": ("이동통신과 초고속인터넷·스마트홈을 기반으로 AI·데이터센터 사업을 확대하는 통신기업입니다.", ["이동통신", "스마트홈", "데이터센터"]),
    "005380": ("승용차·SUV·상용차를 개발·생산하고 전기차·수소차·자율주행 기술에 투자하는 완성차 기업입니다.", ["완성차", "전기차", "수소차"]),
    "000270": ("승용차·SUV·상용차를 글로벌 시장에 판매하며 전기차와 목적기반차량 사업을 확대하는 완성차 기업입니다.", ["완성차", "전기차", "PBV"]),
    "012330": ("자동차의 섀시·콕핏·전동화 모듈과 핵심 부품, 자율주행·커넥티비티 기술을 공급합니다.", ["자동차 모듈", "전동화", "자율주행"]),
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


def market_position(category: str, share: str, score: int, as_of: str, evidence: str, source_label: str, source_url: str, confidence: float = 0.75) -> dict:
    """Curated structural market-position evidence used alongside daily price data.

    Market definitions differ by industry, so `share` is deliberately a display
    label rather than a value used directly in arithmetic. The normalized score
    reflects share/rank and is discounted toward neutral when evidence confidence
    is lower. Sources and dates stay visible in the UI.
    """
    return {
        "category": category,
        "share": share,
        "score": score,
        "asOf": as_of,
        "evidence": evidence,
        "sourceLabel": source_label,
        "sourceUrl": source_url,
        "confidence": confidence,
        "confidenceLabel": "높음" if confidence >= 0.9 else "보통" if confidence >= 0.7 else "낮음",
    }


# 제품별 시장 정의와 기준 시점이 다른 구조적 데이터입니다. 수치가 공시된
# 경우만 퍼센트를 사용하고, 그 외에는 공식 사업자료의 시장 지위를 보수적으로
# 정규화합니다. 가격 스냅샷과 분리되어 있어 분기별 갱신이 쉽습니다.
MARKET_POSITIONS = {
    # Korea — defense / industrials
    "012450": market_position("글로벌 자주포 수출", "50% 이상 · 세계 1위", 98, "2022 공개자료", "K9이 글로벌 자주포 수출시장의 절반 이상을 차지한 것으로 회사가 공시했습니다.", "한화에어로스페이스", "https://www.hanwhaaerospace.com/eng/media/newsroom/view.do?seq=277", 0.95),
    "047810": market_position("국내 군용기 체계종합", "국내 유일 체계종합업체", 94, "2025 사업자료", "국산 군용기 개발·생산을 총괄하는 국내 유일의 항공기 체계종합업체 지위를 반영했습니다.", "한국항공우주 사업소개", "https://www.koreaaero.com/KO/Business/Business01.aspx", 0.85),
    "079550": market_position("국내 정밀유도무기", "선도 사업자", 90, "2025 사업자료", "유도무기·감시정찰·지휘통제 핵심 체계의 국내 선도 지위를 반영했습니다.", "LIG넥스원 사업소개", "https://www.lignex1.com/business/precision-guided-munitions/", 0.78),
    "064350": market_position("국내 전차 체계", "유일 양산 체계업체", 92, "2025 사업자료", "K2 전차를 포함한 국내 주력전차 설계·양산의 독보적 지위를 반영했습니다.", "현대로템 디펜스솔루션", "https://www.hyundai-rotem.co.kr/ko/business/defense/", 0.82),
    # Korea — batteries / semiconductors
    "373220": market_position("글로벌 EV 배터리 사용량", "약 9.5% · 세계 3위", 83, "2025 연간", "SNE Research 기반 글로벌 전기차 배터리 설치량 순위를 반영했습니다.", "SNE Research", "https://sneresearch.com/en/business/report_view/266/page/0", 0.9),
    "006400": market_position("글로벌 EV 배터리 사용량", "약 3% · 글로벌 10위권", 63, "2025 연간", "글로벌 전기차 배터리 설치량 기준 상위 10개사 내 지위를 반영했습니다.", "SNE Research", "https://sneresearch.com/en/business/report_view/266/page/0", 0.85),
    "003670": market_position("글로벌 양극재", "상위권 종합소재사", 70, "2025 사업자료", "양극재·음극재를 동시에 공급하는 글로벌 소수 종합 배터리 소재사의 지위를 반영했습니다.", "포스코퓨처엠 사업소개", "https://www.poscofuturem.com/en/business/batteryMaterial.do", 0.65),
    "000660": market_position("글로벌 HBM 출하량", "62% · 세계 1위", 100, "2025년 2분기", "Counterpoint 기준 HBM 출하량 62%, 매출 57%로 1위였습니다.", "SK하이닉스 뉴스룸", "https://news.skhynix.com/en/2026-market-outlook-focus-on-the-hbm-led-memory-supercycle/", 0.98),
    "005930": market_position("글로벌 메모리 반도체", "DRAM·NAND 최상위권", 94, "2025 업계자료", "DRAM과 NAND 모두 글로벌 최상위 공급자이며 HBM 확대 여부를 별도로 감안했습니다.", "삼성전자 반도체", "https://semiconductor.samsung.com/about-us/", 0.78),
    "042700": market_position("HBM TC 본더", "글로벌 선도 공급사", 91, "2025 사업자료", "HBM 적층 핵심 장비인 TC 본더 시장의 선도 공급 지위를 반영했습니다.", "한미반도체", "https://www.hanmisemi.com/", 0.72),
    # Korea — robots / shipbuilding / biotech
    "277810": market_position("휴머노이드·연구용 로봇", "국내 기술 선도", 78, "2025 사업자료", "KAIST 휴머노이드 기술 기반의 국내 선도 지위를 반영하되 표준화된 점유율 부재로 할인했습니다.", "레인보우로보틱스", "https://rainbow-robotics.com/", 0.62),
    "454910": market_position("협동로봇", "국내 1위권", 84, "2025 사업자료", "다양한 가반하중 제품군과 글로벌 판매망을 갖춘 국내 협동로봇 선도 지위를 반영했습니다.", "두산로보틱스", "https://www.doosanrobotics.com/", 0.68),
    "108490": market_position("스마트 액추에이터", "글로벌 전문 선도사", 79, "2025 사업자료", "DYNAMIXEL 기반 로봇 액추에이터의 글로벌 전문시장 지위를 반영했습니다.", "로보티즈", "https://www.robotis.com/", 0.65),
    "009540": market_position("글로벌 대형 상선 수주", "세계 최상위 조선그룹", 95, "2025 사업자료", "HD현대 조선 3사의 합산 수주·건조 역량과 LNG선 경쟁력을 반영했습니다.", "HD한국조선해양", "https://www.hdksoe.co.kr/", 0.78),
    "042660": market_position("LNG선·특수선", "글로벌 상위 3사", 88, "2025 사업자료", "LNG 운반선과 특수선 중심의 글로벌 대형 조선사 지위를 반영했습니다.", "한화오션", "https://www.hanwhaocean.com/en/business/shipbuilding", 0.72),
    "010140": market_position("LNG선·FLNG", "글로벌 상위 3사", 87, "2025 사업자료", "LNG선·FLNG 등 고부가 선박에서의 글로벌 상위권 지위를 반영했습니다.", "삼성중공업", "https://www.samsungshi.com/eng/business/shipbuilding.aspx", 0.72),
    "207940": market_position("바이오의약품 CDMO 생산능력", "세계 최대 단일기업", 98, "2025 공개자료", "총 생산능력과 대형 항체의약품 공장 규모를 바탕으로 한 글로벌 1위권 CDMO 지위를 반영했습니다.", "삼성바이오로직스", "https://samsungbiologics.com/about/facts-figures", 0.9),
    "068270": market_position("글로벌 바이오시밀러", "주요 제품 선도권", 88, "2025 사업자료", "인플릭시맙 등 주요 바이오시밀러의 미국·유럽 선도 점유 지위를 반영했습니다.", "셀트리온", "https://www.celltrion.com/en-us/business/newdrug", 0.75),
    "326030": market_position("미국 뇌전증 신약", "성장 단계 전문기업", 72, "2025 사업자료", "세노바메이트의 미국 처방 확대를 반영하되 단일 제품 집중도를 감안했습니다.", "SK바이오팜", "https://www.skbp.com/eng/business/product", 0.65),
    # Korea — utilities / finance / telecom / auto
    "034020": market_position("국내 원전 주기기", "핵심 주기기 독점적 공급", 94, "2025 사업자료", "국내 원전 핵심 주기기 제작과 대형 가스터빈 국산화 지위를 반영했습니다.", "두산에너빌리티", "https://www.doosanenerbility.com/en/business/nuclear", 0.82),
    "015760": market_position("국내 송배전·전력판매", "사실상 100% 공기업 체계", 100, "2025 사업구조", "국내 송배전망과 전력판매의 독점적 공공사업 구조를 반영했습니다.", "한국전력", "https://home.kepco.co.kr/kepco/EN/A/htmlView/ENAAHP001.do", 0.98),
    "298040": market_position("초고압 변압기", "글로벌 상위권", 85, "2025 사업자료", "미국·유럽 초고압 변압기 시장의 생산기지와 수주 경쟁력을 반영했습니다.", "효성중공업", "https://www.hyosungheavyindustries.com/en/business/power-transformer", 0.7),
    "105560": market_position("국내 금융그룹", "자산·고객기반 1위권", 94, "2025 경영자료", "총자산·은행 고객기반·비은행 포트폴리오를 종합한 국내 1위권 지위를 반영했습니다.", "KB금융그룹 IR", "https://www.kbfg.com/Eng/ir/presentation.jsp", 0.78),
    "055550": market_position("국내 금융그룹", "자산 2위권", 89, "2025 경영자료", "은행·카드·증권·보험의 균형과 국내 2위권 자산 규모를 반영했습니다.", "신한금융그룹 IR", "https://www.shinhangroup.com/en/invest/irdata", 0.76),
    "086790": market_position("국내 금융그룹", "자산 3위권", 85, "2025 경영자료", "은행·증권 중심의 국내 대형 금융그룹 지위를 반영했습니다.", "하나금융그룹 IR", "https://www.hanafn.com/en/ir/irData.do", 0.74),
    "017670": market_position("국내 이동통신 가입자", "약 39% · 1위", 96, "2025 가입자 기준", "국내 이동통신 가입자 기준 1위 사업자 지위를 반영했습니다.", "과학기술정보통신부 통계", "https://www.msit.go.kr/bbs/list.do?sCode=user&mId=99&mPid=74", 0.9),
    "030200": market_position("국내 이동통신 가입자", "약 23% · 2위", 84, "2025 가입자 기준", "국내 이동통신 가입자와 유선·기업통신 기반의 2위권 지위를 반영했습니다.", "과학기술정보통신부 통계", "https://www.msit.go.kr/bbs/list.do?sCode=user&mId=99&mPid=74", 0.88),
    "032640": market_position("국내 이동통신 가입자", "약 19% · 3위", 76, "2025 가입자 기준", "국내 이동통신 가입자 기준 3위 사업자 지위를 반영했습니다.", "과학기술정보통신부 통계", "https://www.msit.go.kr/bbs/list.do?sCode=user&mId=99&mPid=74", 0.88),
    "005380": market_position("국내 승용차 판매", "현대·기아 합산 약 70%", 94, "2025 연간", "현대차그룹의 국내 판매 지배력과 현대 브랜드의 글로벌 판매 규모를 반영했습니다.", "현대자동차 IR", "https://www.hyundai.com/worldwide/en/company/ir/ir-library/sales-results", 0.82),
    "000270": market_position("국내 승용차 판매", "현대·기아 합산 약 70%", 92, "2025 연간", "현대차그룹의 국내 판매 지배력과 기아의 글로벌 판매 규모를 반영했습니다.", "기아 IR", "https://worldwide.kia.com/int/company/ir/ir-library/sales-results", 0.82),
    "012330": market_position("글로벌 자동차 모듈·부품", "글로벌 상위 10위권", 88, "2025 사업자료", "섀시·콕핏·전동화 모듈의 글로벌 대형 부품사 지위를 반영했습니다.", "현대모비스", "https://www.mobis.com/en/aboutus/aboutus.do", 0.72),
    # United States — technology / consumer / finance
    "NVDA": market_position("PC 외장 GPU 출하", "92% · 세계 1위", 100, "2025년 3분기", "Jon Peddie Research의 외장 GPU 출하 점유율을 대표 지표로 사용했습니다.", "Jon Peddie Research", "https://www.jonpeddie.com/news/q325-pc-gpu-shipments-increased-by-2-5-from-last-quarter-which-might-suggest-a-creep-forward/", 0.95),
    "AVGO": market_position("AI 네트워킹·커스텀 ASIC", "글로벌 선도권", 92, "2025 사업자료", "데이터센터 스위칭 반도체와 하이퍼스케일러용 커스텀 ASIC의 선도 지위를 반영했습니다.", "Broadcom Annual Reports", "https://investors.broadcom.com/financial-information/annual-reports", 0.72),
    "AMD": market_position("PC 외장 GPU 출하", "약 7% · 세계 2위", 70, "2025년 3분기", "외장 GPU 2위와 데이터센터 가속기 도전자 지위를 함께 반영했습니다.", "Jon Peddie Research", "https://www.jonpeddie.com/news/q325-pc-gpu-shipments-increased-by-2-5-from-last-quarter-which-might-suggest-a-creep-forward/", 0.9),
    "MSFT": market_position("글로벌 클라우드 인프라", "약 21% · 세계 2위", 95, "2025년 4분기", "Azure의 글로벌 클라우드 인프라 지출 점유율과 기업 소프트웨어 기반을 반영했습니다.", "Synergy Research 요약", "https://www.srgresearch.com/articles/cloud-market-jumps-to-330-billion-in-2025-genai-is-now-driving-half-of-the-growth", 0.9),
    "ORCL": market_position("글로벌 클라우드 인프라", "약 3% · 상위 5위권", 70, "2025년 3분기", "OCI의 클라우드 인프라 점유율과 데이터베이스 지배력을 함께 반영했습니다.", "Oracle Annual Reports", "https://investor.oracle.com/financial-reporting/annual-reports/default.aspx", 0.7),
    "CRM": market_position("글로벌 CRM 애플리케이션", "약 20% · 세계 1위권", 98, "2024~2025", "CRM 애플리케이션 매출 점유율의 장기 선두 지위를 반영했습니다.", "Salesforce Investor Relations", "https://investor.salesforce.com/", 0.85),
    "META": market_position("글로벌 소셜 플랫폼 광고", "세계 2위권", 92, "2025 사업자료", "Facebook·Instagram의 이용자 규모와 디지털 광고 선도 지위를 반영했습니다.", "Meta Annual Reports", "https://investor.atmeta.com/financials/", 0.72),
    "GOOGL": market_position("글로벌 검색", "약 90% · 세계 1위", 100, "2025 웹 검색", "Google의 글로벌 검색 쿼리 점유율과 광고·YouTube 생태계를 반영했습니다.", "Alphabet Annual Reports", "https://abc.xyz/investor/", 0.9),
    "NFLX": market_position("글로벌 유료 스트리밍", "가입자 규모 세계 1위권", 94, "2025 사업자료", "글로벌 유료 스트리밍 가입자와 시청시간 선도 지위를 반영했습니다.", "Netflix Financial Statements", "https://ir.netflix.net/financials/quarterly-earnings/default.aspx", 0.8),
    "AMZN": market_position("미국 전자상거래", "약 40% · 1위", 100, "2025 추정", "미국 전자상거래 1위와 AWS 클라우드 1위를 함께 반영했습니다.", "Amazon Annual Reports", "https://ir.aboutamazon.com/annual-reports-proxies-and-shareholder-letters/default.aspx", 0.86),
    "TSLA": market_position("미국 순수전기차", "약 45% · 1위", 95, "2025 추정", "미국 BEV 판매 점유율 1위 지위를 반영하되 점유율 하락 추세를 감안했습니다.", "Tesla Annual Reports", "https://ir.tesla.com/#quarterly-disclosure", 0.8),
    "HD": market_position("미국 홈임프루브먼트 소매", "양강 중 1위", 93, "2025 사업자료", "미국 홈임프루브먼트 소매의 최대 사업자 지위를 반영했습니다.", "Home Depot Annual Reports", "https://ir.homedepot.com/financial-reports/annual-reports", 0.78),
    "JPM": market_position("미국 은행 총자산", "1위", 100, "2025년 말", "미국 은행 총자산과 예금·카드·투자은행의 종합 1위 지위를 반영했습니다.", "JPMorgan Annual Reports", "https://www.jpmorganchase.com/ir/annual-report", 0.92),
    "BAC": market_position("미국 은행 총자산", "2위", 94, "2025년 말", "미국 은행 총자산과 소비자 예금의 2위 지위를 반영했습니다.", "Bank of America Annual Reports", "https://investor.bankofamerica.com/annual-reports-and-proxy-statements", 0.9),
    "GS": market_position("글로벌 투자은행", "상위 3위권", 95, "2025 사업자료", "M&A·주식 인수와 기관금융의 글로벌 최상위 지위를 반영했습니다.", "Goldman Sachs Annual Reports", "https://www.goldmansachs.com/investor-relations/financials/current/annual-reports", 0.82),
    # United States — industrial / health / defensive sectors
    "GE": market_position("상업용 항공엔진 설치기반", "글로벌 양강", 98, "2025 사업자료", "CFM 합작을 포함한 대형 상업용 항공엔진 설치기반과 서비스 점유를 반영했습니다.", "GE Aerospace Annual Reports", "https://www.geaerospace.com/investor-relations", 0.82),
    "CAT": market_position("글로벌 건설장비", "세계 1위", 98, "2025 사업자료", "매출 기준 글로벌 건설장비 1위권과 딜러망을 반영했습니다.", "Caterpillar Annual Reports", "https://investors.caterpillar.com/financials/annual-reports/default.aspx", 0.85),
    "RTX": market_position("항공엔진·미사일·항전", "글로벌 최상위권", 95, "2025 사업자료", "Pratt & Whitney·Raytheon·Collins의 각 핵심 시장 선도 지위를 반영했습니다.", "RTX Annual Reports", "https://www.rtx.com/investors/annual-reports", 0.8),
    "LLY": market_position("글로벌 GLP-1", "양강 중 선두권", 98, "2025 사업자료", "tirzepatide 계열의 비만·당뇨 시장 선도권을 반영했습니다.", "Eli Lilly Annual Reports", "https://investor.lilly.com/financial-information/annual-reports", 0.85),
    "UNH": market_position("미국 민간 건강보험", "가입자 1위권", 97, "2025 사업자료", "UnitedHealthcare 가입자 기반과 Optum의 의료서비스 규모를 반영했습니다.", "UnitedHealth Annual Reports", "https://www.unitedhealthgroup.com/investors/annual-reports.html", 0.85),
    "JNJ": market_position("글로벌 제약·의료기기", "글로벌 상위 5위권", 92, "2025 사업자료", "혁신의약품과 의료기기의 다각화된 글로벌 상위권 지위를 반영했습니다.", "Johnson & Johnson Annual Reports", "https://www.investor.jnj.com/financials/annual-reports/default.aspx", 0.78),
    "XOM": market_position("글로벌 상장 통합에너지", "생산·시총 1위권", 96, "2025 사업자료", "상장 통합 메이저 중 생산·정제·화학 규모의 최상위 지위를 반영했습니다.", "ExxonMobil Annual Reports", "https://corporate.exxonmobil.com/investors/annual-reports", 0.8),
    "CVX": market_position("글로벌 상장 통합에너지", "생산·시총 2위권", 91, "2025 사업자료", "상장 통합 메이저 중 업스트림·LNG·정제의 2위권 규모를 반영했습니다.", "Chevron Annual Reports", "https://www.chevron.com/investors/financial-information", 0.78),
    "COP": market_position("미국 독립계 E&P", "생산량 1위권", 89, "2025 사업자료", "독립계 탐사·생산기업 중 글로벌 최대 규모의 생산 기반을 반영했습니다.", "ConocoPhillips Annual Reports", "https://www.conocophillips.com/investor-relations/company-reports/", 0.76),
    "NEE": market_position("미국 재생에너지 발전", "세계 최대급", 97, "2025 사업자료", "풍력·태양광 및 배터리 저장 개발 규모의 글로벌 선도 지위를 반영했습니다.", "NextEra Energy Reports", "https://www.investor.nexteraenergy.com/financial-information/annual-reports-and-proxy-statements", 0.82),
    "SO": market_position("미국 규제 유틸리티", "대형 상위권", 90, "2025 사업자료", "미 남동부 고객 기반과 원전·가스·재생 발전 자산 규모를 반영했습니다.", "Southern Company Reports", "https://investor.southerncompany.com/financials/annual-reports/default.aspx", 0.76),
    "DUK": market_position("미국 규제 유틸리티", "고객수 상위권", 91, "2025 사업자료", "다주(州) 전력·가스 고객 기반과 규제자산 규모를 반영했습니다.", "Duke Energy Reports", "https://investors.duke-energy.com/financials/annual-reports-and-proxy/default.aspx", 0.76),
    "WMT": market_position("미국 식료품 소매", "약 25% · 1위", 100, "2025 추정", "미국 식료품과 종합 소매의 압도적 1위 지위를 반영했습니다.", "Walmart Annual Reports", "https://stock.walmart.com/financials/annual-reports-and-proxies/default.aspx", 0.88),
    "COST": market_position("미국 창고형 할인점", "1위권", 96, "2025 사업자료", "회원제 창고형 할인점의 매출·회원 기반 선도 지위를 반영했습니다.", "Costco Annual Reports", "https://investor.costco.com/financials/annual-reports-and-proxy-statements/default.aspx", 0.82),
    "PG": market_position("글로벌 생활용품", "다수 카테고리 1~2위", 95, "2025 사업자료", "세제·기저귀·그루밍 등 핵심 소비재 카테고리의 글로벌 선도 지위를 반영했습니다.", "P&G Annual Reports", "https://us.pg.com/annualreport2025/", 0.8),
    "LIN": market_position("글로벌 산업용 가스", "약 30% · 세계 1위", 100, "2025 업계자료", "산업용 가스의 글로벌 최대 사업자 지위를 반영했습니다.", "Linde Annual Reports", "https://www.linde.com/investors/financial-reports", 0.85),
    "NEM": market_position("글로벌 금 생산", "상장사 1위권", 96, "2025 사업자료", "금 생산량과 매장량 기준 글로벌 최대 상장 금광기업 지위를 반영했습니다.", "Newmont Reports", "https://www.newmont.com/investors/reports-and-filings/default.aspx", 0.82),
    "FCX": market_position("글로벌 구리 생산", "상장사 상위 5위권", 92, "2025 사업자료", "Grasberg 등 대형 광산을 보유한 글로벌 상위 구리 생산자 지위를 반영했습니다.", "Freeport-McMoRan Reports", "https://investors.fcx.com/investors/financial-information/annual-reports-and-proxy/default.aspx", 0.8),
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

    stock_return = float(quote.get("returnRate") or 0)
    position = MARKET_POSITIONS.get(
        quote["code"],
        market_position("핵심 사업", "점유율 확인 중", 50, "미확인", "비교 가능한 공개 점유율 자료를 확인 중입니다.", "기업 공시 확인 필요", "#", 0.4),
    )

    # 100점 관찰 점수: 기술적 위치 35 + 상대강도 25 + 시장지위 25 + 추세 15.
    # 시장지위의 근거 확신도가 낮을수록 중립값(50) 쪽으로 할인합니다.
    technical_score = max(0, min(100, 100 - abs(rsi14 - 50) * 2.0 - max(0, rsi14 - 70) * 2.5))
    relative_score = max(0, min(100, 50 + (sector_return - benchmark_return) * 7 + (stock_return - benchmark_return) * 5))
    trend_score = 35 + (35 if close >= ema20 else 0) + (30 if close >= ema50 else 0)
    market_score = position["score"] * position["confidence"] + 50 * (1 - position["confidence"])
    score_breakdown = {
        "technical": {"label": "기술적 위치", "score": round(technical_score), "points": round(technical_score * 0.35, 1), "max": 35},
        "relative": {"label": "상대강도", "score": round(relative_score), "points": round(relative_score * 0.25, 1), "max": 25},
        "market": {"label": "시장점유·지위", "score": round(market_score), "points": round(market_score * 0.25, 1), "max": 25},
        "trend": {"label": "추세", "score": round(trend_score), "points": round(trend_score * 0.15, 1), "max": 15},
    }
    appeal = round(sum(item["points"] for item in score_breakdown.values()))
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
        "basis": "기술적 위치 35 · 상대강도 25 · 시장점유·지위 25 · 추세 15를 합산한 관찰 점수",
        "scoreBreakdown": score_breakdown,
        "marketPosition": position,
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

    for code, quote in quotes.items():
        if "price" not in quote:
            continue
        description, business = KR_STOCK_INFO.get(
            code,
            (f"{quote.get('name', code)}의 주요 사업과 제품 정보를 확인 중입니다.", ["사업 정보 확인 중"]),
        )
        quote["description"] = description
        quote["business"] = business

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
