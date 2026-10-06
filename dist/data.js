// 데이터 계층: 실제 API 연동 시 getMarketDays/getDayDetail 함수만 교체하면 됩니다.
const KOREA_SAMPLE_MARKET_DATA = [
  {
    date: "2026-10-02", kospi: 0.46,
    sectors: [
      { name: "방산·우주", returnRate: 4.59, stocks: [{ name: "한국항공우주", code: "047810", returnRate: 5.04 }, { name: "LIG넥스원", code: "079550", returnRate: 5.25 }, { name: "한화에어로스페이스", code: "012450", returnRate: 3.68 }] },
      { name: "2차전지", returnRate: 2.47, stocks: [{ name: "LG에너지솔루션", code: "373220", returnRate: 2.91 }, { name: "삼성SDI", code: "006400", returnRate: 2.12 }, { name: "포스코퓨처엠", code: "003670", returnRate: 2.38 }] },
      { name: "로봇", returnRate: 2.39, stocks: [{ name: "레인보우로보틱스", code: "277810", returnRate: 2.39 }, { name: "두산로보틱스", code: "454910", returnRate: 1.66 }] },
      { name: "반도체", returnRate: 0.22, stocks: [{ name: "SK하이닉스", code: "000660", returnRate: 0.44 }, { name: "삼성전자", code: "005930", returnRate: 0.00 }] }
    ]
  },
  {
    date: "2026-09-25", kospi: -1.82,
    sectors: [
      { name: "방산", returnRate: 3.84, stocks: [{ name: "한화에어로스페이스", code: "012450", returnRate: 5.42 }, { name: "현대로템", code: "064350", returnRate: 3.18 }, { name: "LIG넥스원", code: "079550", returnRate: 2.74 }] },
      { name: "조선", returnRate: 2.61, stocks: [{ name: "HD한국조선해양", code: "009540", returnRate: 3.91 }, { name: "한화오션", code: "042660", returnRate: 2.63 }, { name: "삼성중공업", code: "010140", returnRate: 1.86 }] },
      { name: "바이오", returnRate: 1.73, stocks: [{ name: "삼성바이오로직스", code: "207940", returnRate: 2.41 }, { name: "셀트리온", code: "068270", returnRate: 1.84 }, { name: "SK바이오팜", code: "326030", returnRate: 0.93 }] },
      { name: "통신", returnRate: 0.92, stocks: [{ name: "SK텔레콤", code: "017670", returnRate: 1.24 }, { name: "KT", code: "030200", returnRate: 0.88 }, { name: "LG유플러스", code: "032640", returnRate: 0.63 }] }
    ]
  },
  {
    date: "2026-09-24", kospi: -0.74,
    sectors: [
      { name: "전력·에너지", returnRate: 2.96, stocks: [{ name: "두산에너빌리티", code: "034020", returnRate: 4.12 }, { name: "한국전력", code: "015760", returnRate: 2.55 }, { name: "효성중공업", code: "298040", returnRate: 2.21 }] },
      { name: "금융", returnRate: 1.58, stocks: [{ name: "KB금융", code: "105560", returnRate: 2.08 }, { name: "하나금융지주", code: "086790", returnRate: 1.64 }, { name: "신한지주", code: "055550", returnRate: 1.02 }] },
      { name: "통신", returnRate: 0.81, stocks: [{ name: "KT", code: "030200", returnRate: 1.15 }, { name: "SK텔레콤", code: "017670", returnRate: 0.77 }, { name: "LG유플러스", code: "032640", returnRate: 0.51 }] }
    ]
  },
  {
    date: "2026-09-23", kospi: 0.63,
    sectors: [
      { name: "반도체", returnRate: 2.18, stocks: [{ name: "SK하이닉스", code: "000660", returnRate: 3.04 }, { name: "삼성전자", code: "005930", returnRate: 1.72 }, { name: "한미반도체", code: "042700", returnRate: 1.56 }] },
      { name: "IT서비스", returnRate: 1.21, stocks: [{ name: "NAVER", code: "035420", returnRate: 1.77 }, { name: "카카오", code: "035720", returnRate: 1.08 }, { name: "삼성SDS", code: "018260", returnRate: 0.78 }] }
    ]
  },
  {
    date: "2026-09-22", kospi: -1.16,
    sectors: [
      { name: "음식료", returnRate: 2.47, stocks: [{ name: "삼양식품", code: "003230", returnRate: 4.32 }, { name: "농심", code: "004370", returnRate: 1.88 }, { name: "CJ제일제당", code: "097950", returnRate: 1.21 }] },
      { name: "유틸리티", returnRate: 1.36, stocks: [{ name: "한국가스공사", code: "036460", returnRate: 2.16 }, { name: "한국전력", code: "015760", returnRate: 1.19 }, { name: "지역난방공사", code: "071320", returnRate: 0.74 }] },
      { name: "보험", returnRate: 0.88, stocks: [{ name: "삼성화재", code: "000810", returnRate: 1.32 }, { name: "DB손해보험", code: "005830", returnRate: 0.84 }, { name: "현대해상", code: "001450", returnRate: 0.47 }] }
    ]
  },
  {
    date: "2026-09-19", kospi: -0.38,
    sectors: [
      { name: "조선", returnRate: 1.92, stocks: [{ name: "한화오션", code: "042660", returnRate: 3.14 }, { name: "HD현대중공업", code: "329180", returnRate: 1.62 }, { name: "삼성중공업", code: "010140", returnRate: 1.01 }] },
      { name: "방산", returnRate: 1.41, stocks: [{ name: "LIG넥스원", code: "079550", returnRate: 2.33 }, { name: "한화시스템", code: "272210", returnRate: 1.24 }, { name: "한국항공우주", code: "047810", returnRate: 0.66 }] },
      { name: "통신", returnRate: 0.57, stocks: [{ name: "KT", code: "030200", returnRate: 0.89 }, { name: "SK텔레콤", code: "017670", returnRate: 0.52 }, { name: "LG유플러스", code: "032640", returnRate: 0.31 }] }
    ]
  },
  {
    date: "2026-09-18", kospi: -2.07,
    sectors: [
      { name: "금", returnRate: 3.72, stocks: [{ name: "고려아연", code: "010130", returnRate: 4.61 }, { name: "엘컴텍", code: "037950", returnRate: 3.28 }, { name: "영풍", code: "000670", returnRate: 2.24 }] },
      { name: "방산", returnRate: 2.18, stocks: [{ name: "한화에어로스페이스", code: "012450", returnRate: 3.11 }, { name: "현대로템", code: "064350", returnRate: 2.06 }, { name: "LIG넥스원", code: "079550", returnRate: 1.37 }] },
      { name: "통신", returnRate: 0.76, stocks: [{ name: "SK텔레콤", code: "017670", returnRate: 1.03 }, { name: "KT", code: "030200", returnRate: 0.71 }, { name: "LG유플러스", code: "032640", returnRate: 0.43 }] }
    ]
  },
  {
    date: "2026-09-17", kospi: 0.28,
    sectors: [{ name: "자동차", returnRate: 1.64, stocks: [{ name: "현대차", code: "005380", returnRate: 2.08 }, { name: "기아", code: "000270", returnRate: 1.42 }, { name: "현대모비스", code: "012330", returnRate: 1.12 }] }]
  }
];

const US_SAMPLE_MARKET_DATA = [
  { date: "2026-10-02", kospi: 0.72, sectors: [
    { name: "AI·반도체", returnRate: 1.48, stocks: [{ name: "엔비디아", code: "NVDA", returnRate: 1.34 }, { name: "브로드컴", code: "AVGO", returnRate: 1.71 }, { name: "AMD", code: "AMD", returnRate: 1.26 }] },
    { name: "소프트웨어·클라우드", returnRate: 0.91, stocks: [{ name: "마이크로소프트", code: "MSFT", returnRate: 0.82 }, { name: "오라클", code: "ORCL", returnRate: 1.03 }, { name: "세일즈포스", code: "CRM", returnRate: 0.75 }] }
  ]},
  { date: "2026-10-01", kospi: -0.64, sectors: [
    { name: "에너지", returnRate: 1.43, stocks: [{ name: "엑슨모빌", code: "XOM", returnRate: 1.62 }, { name: "셰브론", code: "CVX", returnRate: 1.21 }, { name: "코노코필립스", code: "COP", returnRate: 1.48 }] },
    { name: "유틸리티", returnRate: 0.78, stocks: [{ name: "넥스트에라 에너지", code: "NEE", returnRate: 0.91 }, { name: "서던 컴퍼니", code: "SO", returnRate: 0.69 }, { name: "듀크 에너지", code: "DUK", returnRate: 0.72 }] }
  ]},
  { date: "2026-09-30", kospi: -1.12, sectors: [
    { name: "필수소비재", returnRate: 1.18, stocks: [{ name: "월마트", code: "WMT", returnRate: 1.44 }, { name: "코스트코", code: "COST", returnRate: 1.07 }, { name: "P&G", code: "PG", returnRate: 0.91 }] },
    { name: "헬스케어", returnRate: 0.83, stocks: [{ name: "일라이 릴리", code: "LLY", returnRate: 1.05 }, { name: "유나이티드헬스", code: "UNH", returnRate: 0.72 }, { name: "존슨앤드존슨", code: "JNJ", returnRate: 0.64 }] }
  ]},
  { date: "2026-09-29", kospi: 0.31, sectors: [{ name: "금융", returnRate: 0.88, stocks: [{ name: "JP모건", code: "JPM", returnRate: 1.02 }, { name: "뱅크오브아메리카", code: "BAC", returnRate: 0.79 }, { name: "골드만삭스", code: "GS", returnRate: 0.83 }] }] },
  { date: "2026-09-28", kospi: -0.47, sectors: [{ name: "소재·금", returnRate: 1.36, stocks: [{ name: "린데", code: "LIN", returnRate: 0.64 }, { name: "뉴몬트", code: "NEM", returnRate: 2.18 }, { name: "프리포트 맥모란", code: "FCX", returnRate: 1.27 }] }] }
];

let SAMPLE_MARKET_DATA = KOREA_SAMPLE_MARKET_DATA;

const LIVE_STATE = {
  status: "loading",
  requestedAt: null,
  lastCheckedAt: null,
  refreshResult: null,
  provider: "네이버 금융 · Google 뉴스",
  message: "최신 데이터 확인 중"
};

function applyLivePayload(payload) {
  if (payload.marketDays?.length) {
    SAMPLE_MARKET_DATA.splice(0, SAMPLE_MARKET_DATA.length, ...payload.marketDays);
  } else {
    const incoming = payload.marketDay;
    const sameDateIndex = SAMPLE_MARKET_DATA.findIndex(day => day.date === incoming.date);
    if (sameDateIndex >= 0) SAMPLE_MARKET_DATA[sameDateIndex] = incoming;
    else SAMPLE_MARKET_DATA.unshift(incoming);
  }
  SAMPLE_MARKET_DATA.sort((a, b) => b.date.localeCompare(a.date));

  Object.entries(payload.quotes || {}).forEach(([code, quote]) => {
    if (!quote || quote.error || !quote.price) return;
    const current = MARKET_INTELLIGENCE.stocks[code] || {
      description: `${quote.name}의 최신 공개 시세와 상대강도를 추적하는 종목입니다.`,
      business: ["시장 주도주", "실시간 추적"]
    };
    MARKET_INTELLIGENCE.stocks[code] = {
      ...current,
      price: quote.price,
      priceDate: quote.date,
      marketStatus: quote.marketStatus || current.marketStatus || "CLOSE",
      tradedAt: quote.tradedAt || current.tradedAt || "",
      marketCap: quote.marketCap || current.marketCap || "—",
      volume: quote.volume || current.volume || "—",
      fiftyTwoWeekRange: quote.fiftyTwoWeekRange || current.fiftyTwoWeekRange || "—",
      exchange: quote.exchange || current.exchange || "",
      description: quote.description || current.description,
      business: quote.business || current.business
    };
  });

  Object.entries(payload.news || {}).forEach(([sector, articles]) => {
    if (articles?.length) MARKET_INTELLIGENCE.news[sector] = articles;
  });
  Object.assign(DAILY_OUTLOOK, payload.outlook || {});
}

async function refreshLiveData(force = false) {
  const previousRequestedAt = LIVE_STATE.requestedAt;
  LIVE_STATE.status = "loading";
  LIVE_STATE.refreshResult = null;
  LIVE_STATE.message = force ? "데이터 새로고침 중" : "최신 데이터 확인 중";
  try {
    let payload = null;
    const sources = [
      `/api/market?market=${ACTIVE_MARKET}&refresh=${force ? 1 : 0}&t=${Date.now()}`,
      `./market-snapshot.json?t=${Date.now()}`
    ];
    for (const source of sources) {
      try {
        const response = await fetch(source, { cache: "no-store" });
        if (!response.ok) continue;
        const candidate = await response.json();
        const selected = candidate.markets?.[ACTIVE_MARKET] || candidate;
        if (selected.ok && selected.marketDay && (!selected.marketKey || selected.marketKey === ACTIVE_MARKET)) { payload = selected; break; }
      } catch (_) {}
    }
    if (!payload) throw new Error("live sources unavailable");
    if (!payload.ok || !payload.marketDay) throw new Error(payload.error || "invalid market payload");
    applyLivePayload(payload);
    LIVE_STATE.status = "live";
    LIVE_STATE.requestedAt = payload.requestedAt;
    LIVE_STATE.lastCheckedAt = new Date().toISOString();
    LIVE_STATE.provider = payload.provider || LIVE_STATE.provider;
    if (force) {
      const changed = Boolean(previousRequestedAt && previousRequestedAt !== payload.requestedAt);
      LIVE_STATE.refreshResult = changed ? "updated" : "current";
      const checkedTime = new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Seoul" }).format(new Date());
      LIVE_STATE.message = changed ? `새 데이터 반영 · ${checkedTime}` : `최신 상태 확인 · ${checkedTime}`;
    } else {
      LIVE_STATE.message = payload.snapshot
        ? "GitHub 자동 갱신 반영"
        : payload.marketDay.date === new Date().toLocaleDateString("sv-SE", { timeZone: ACTIVE_MARKET === "us" ? "America/New_York" : "Asia/Seoul" })
          ? "오늘 데이터 반영"
          : "최근 거래일 반영";
    }
  } catch (error) {
    console.warn("실시간 데이터 갱신 실패, 검증된 기본 데이터를 사용합니다.", error);
    LIVE_STATE.status = "fallback";
    LIVE_STATE.refreshResult = force ? "failed" : null;
    LIVE_STATE.message = force ? "새로고침 실패 · 잠시 후 다시 시도" : "기본 데이터 사용 중";
  }
  return LIVE_STATE;
}

const marketRepository = {
  async getMarketDays(force = false) {
    await refreshLiveData(force);
    return structuredClone(SAMPLE_MARKET_DATA);
  },
  async setMarket(market, force = false) {
    ACTIVE_MARKET = MARKET_PROFILES[market] ? market : "kr";
    const profile = MARKET_PROFILES[ACTIVE_MARKET];
    SAMPLE_MARKET_DATA = profile.data;
    MARKET_INTELLIGENCE = profile.intelligence;
    DAILY_OUTLOOK = profile.outlook;
    LIVE_STATE.provider = profile.provider;
    LIVE_STATE.status = "loading";
    LIVE_STATE.message = "최신 데이터 확인 중";
    await refreshLiveData(force);
    return structuredClone(SAMPLE_MARKET_DATA);
  },
  get activeMarket() { return ACTIVE_MARKET; },
  get profile() { return MARKET_PROFILES[ACTIVE_MARKET]; },
  async getDayDetail(date) { return structuredClone(SAMPLE_MARKET_DATA.find(d => d.date === date)); }
};

// 실제 연동 시 quote/news API 응답으로 교체하는 시장 정보 계층입니다.
let MARKET_INTELLIGENCE = {
  stocks: {
    "047810": { price: 133500, priceDate: "2026-10-02", marketCap: "13.0조원", volume: "25.1만주", description: "군용기·위성·항공기 구조물을 개발·생산하는 국내 대표 항공우주 기업입니다.", business: ["군용기", "위성", "항공우주"] },
    "373220": { price: 371000, priceDate: "2026-10-02", marketCap: "86.8조원", volume: "20.6만주", description: "전기차와 에너지저장장치용 배터리를 생산하는 글로벌 배터리 제조기업입니다.", business: ["전기차 배터리", "ESS", "원통형 배터리"] },
    "006400": { price: 428000, priceDate: "2026-10-02", marketCap: "참고값", volume: "참고 시세", description: "전기차·ESS용 배터리와 전자재료를 생산하는 에너지 솔루션 기업입니다.", business: ["전기차 배터리", "ESS", "전자재료"] },
    "003670": { price: 248000, priceDate: "2026-10-02", marketCap: "참고값", volume: "참고 시세", description: "양극재·음극재 등 이차전지 핵심 소재를 생산합니다.", business: ["양극재", "음극재", "배터리 소재"] },
    "277810": { price: 612000, priceDate: "2026-10-02", marketCap: "참고값", volume: "참고 시세", description: "협동로봇과 휴머노이드 플랫폼을 개발하는 로봇 전문 기업입니다.", business: ["휴머노이드", "협동로봇"] },
    "000660": { price: 1841000, priceDate: "2026-10-02", marketCap: "참고값", volume: "참고 시세", description: "HBM과 DRAM, NAND를 생산하는 글로벌 메모리 반도체 기업입니다.", business: ["HBM", "DRAM", "NAND"] },
    "005930": { price: 276000, priceDate: "2026-10-02", marketCap: "참고값", volume: "1,113만주", description: "메모리·파운드리·모바일·가전 사업을 영위하는 글로벌 전자기업입니다.", business: ["반도체", "모바일", "가전"] },
    "012450": { price: 1072000, priceDate: "2026-10-02", marketCap: "53.3조원", volume: "약 10.2만주", description: "K9 자주포·천무 다연장로켓과 항공엔진을 주력으로 하는 국내 대표 항공우주·방산 기업입니다.", business: ["지상방산", "항공엔진", "우주사업"] },
    "064350": { price: 115900, priceDate: "2026-09-23", marketCap: "12.7조원", volume: "약 22만주", description: "K2 전차 중심의 디펜스솔루션과 철도차량·수소 모빌리티 사업을 영위합니다.", business: ["K2 전차", "철도", "수소 모빌리티"] },
    "079550": { price: 762000, priceDate: "2026-10-02", marketCap: "16.5조원", volume: "약 9.3만주", description: "유도무기, 감시정찰, 항공전자 체계를 개발하는 정밀 유도무기 전문 기업입니다.", business: ["유도무기", "레이더", "항공전자"] },
    "009540": { price: 339500, priceDate: "2026-09-22", marketCap: "24.0조원", volume: "참고 시세", description: "HD현대 조선 계열의 중간지주사로 선박·해양플랜트 기술과 수주 포트폴리오를 관리합니다.", business: ["조선", "해양플랜트", "친환경 선박"] },
    "042660": { price: 88100, priceDate: "2026-09-09", marketCap: "참고값", volume: "참고 시세", description: "LNG선·상선과 특수선, 해양플랜트를 건조하며 미국 함정 MRO 사업을 확대하고 있습니다.", business: ["상선", "특수선", "MRO"] },
    "010140": { price: 21100, priceDate: "2026-09-17", marketCap: "참고값", volume: "참고 시세", description: "LNG선과 초대형 컨테이너선, FLNG 등 고부가 선박 및 해양설비에 집중하는 조선사입니다.", business: ["LNG선", "컨테이너선", "FLNG"] },
    "207940": { price: 1366000, priceDate: "2026-10-02", marketCap: "참고값", volume: "참고 시세", description: "항체의약품 생산부터 공정개발까지 제공하는 글로벌 바이오의약품 CDMO 기업입니다.", business: ["CDMO", "항체의약품", "ADC"] },
    "068270": { price: 214000, priceDate: "2026-09-25", marketCap: "참고값", volume: "샘플", description: "바이오시밀러와 항체의약품을 개발·생산·판매하는 종합 바이오 기업입니다.", business: ["바이오시밀러", "항체치료제"] },
    "326030": { price: 118900, priceDate: "2026-09-25", marketCap: "참고값", volume: "샘플", description: "중추신경계 질환 치료제 발굴부터 글로벌 상업화까지 수행하는 신약개발 기업입니다.", business: ["뇌전증", "신약개발"] },
    "017670": { price: 87100, priceDate: "2026-09-23", marketCap: "18.7조원", volume: "54.7만주", description: "이동통신을 기반으로 AI 데이터센터·AI 에이전트 등 AI 인프라 사업을 확대하고 있습니다.", business: ["이동통신", "AI", "데이터센터"] },
    "030200": { price: 54500, priceDate: "2026-09-25", marketCap: "참고값", volume: "샘플", description: "유무선 통신과 B2B 디지털 전환, 클라우드·미디어 서비스를 제공하는 통신 기업입니다.", business: ["통신", "클라우드", "미디어"] },
    "032640": { price: 14900, priceDate: "2026-09-25", marketCap: "참고값", volume: "샘플", description: "이동통신과 스마트홈을 기반으로 AI·데이터센터 사업을 강화하는 통신 기업입니다.", business: ["통신", "스마트홈", "IDC"] }
  },
  news: {
    "방산": [
      { date: "2026-09-15", source: "한화에어로스페이스 IR", title: "글로벌 투자자 대상 기업설명회 진행", summary: "싱가포르·홍콩에서 글로벌 투자자를 만나 방산 수출과 사업 현황을 설명했습니다. 수주잔고와 해외 생산 확대가 업종의 중기 모멘텀으로 해석됩니다.", url: "https://www.hanwhaaerospace.com/kor/ir/ir-event.do" },
      { date: "2026-10-06", source: "KADEX 2026", title: "국내 주요 방산기업, KADEX 참가 예정", summary: "한화에어로스페이스·현대로템·LIG넥스원 등 주요 기업이 방위산업전에 참가해 신제품과 수출 역량을 공개할 예정입니다.", url: "https://kospik.com/market/schedule/" }
    ],
    "조선": [
      { date: "2026-09-22", source: "뉴스1", title: "HD한국조선해양 누적 수주, 전년 연간 실적 넘어", summary: "RORO선 2척을 3,362억원에 수주하면서 누적 수주액이 187억1천만달러로 늘었습니다. 연간 목표의 80.3%를 달성한 수준입니다.", url: "https://www.news1.kr/amp/industry/general-industry/6298922" },
      { date: "2026-09-17", source: "뉴스핌", title: "수주 기대 회복에 조선주 동반 반등", summary: "실적 고점 기대가 유지되는 가운데 단기 낙폭이 커졌다는 평가와 신규 수주 기대가 맞물리며 주요 조선주가 반등했습니다.", url: "https://www.newspim.com/news/view/20260917000373" }
    ],
    "바이오": [
      { date: "2026-09-28", source: "삼성바이오로직스", title: "BPI서 바이오의약품 제조 공정 혁신 공개", summary: "글로벌 행사에서 제조 공정 혁신과 CDMO 경쟁력을 알렸습니다. ADC와 다중 공장 생산 역량이 핵심 관전 포인트입니다.", url: "https://samsungbiologics.com/front/kr/mediaCenter/newsRoom.do" },
      { date: "2026-09-18", source: "삼성바이오로직스", title: "ADC 상업화 위한 제형·공정 전략 제시", summary: "ADC 전용 역량과 공정 최적화 전략이 소개되며 고부가 CDMO 사업 확대 기대가 부각됐습니다.", url: "https://samsungbiologics.com/front/kr/mediaCenter/newsRoom.do" }
    ],
    "통신": [
      { date: "2026-09-18", source: "SK텔레콤 뉴스룸", title: "추석·아시안게임 통신 품질 종합 대책", summary: "연인원 3,625명을 투입해 통신망을 24시간 모니터링하고 협력사 대금 1,318억원을 조기 지급한다고 밝혔습니다.", url: "https://news.sktelecom.com/231014" }
    ]
  }
};

let DAILY_OUTLOOK = {
  asOf: "2026-10-02 15:30",
  market: { name: "KOSPI", returnRate: 0.46, close: "7,003.74", breadth: "상승 500 · 하락 362" },
  focus: {
    sector: "방산·우주", score: 82, status: "강세 유지 · 추격 주의",
    thesis: "지수가 0.46% 오르는 동안 대표 종목이 3~5%대 상승해 상대강도가 가장 높았습니다. K-DEX 개최가 가까워지며 관심이 집중됐지만, 행사 전 기대가 상당 부분 반영됐을 가능성도 함께 봐야 합니다.",
    positives: ["한국항공우주 +5.04%", "LIG넥스원 +5.25%", "한화에어로스페이스 +3.68%"],
    checks: ["장 초반 급등 추격보다 전일 저점 지지 확인", "행사 이후 거래량 감소·차익실현 여부", "외국인 수급이 지수 상승에 동행하는지 확인"]
  },
  entries: [
    { name: "한국항공우주", code: "047810", close: 133500, appeal: 76, zone1: "127,000~130,000원", zone2: "124,500~126,500원", rsi: 63.2, rsiLabel: "강세", ma20: "128,500원", ma50: "124,500원", entryStatus: "1차 구간까지 조정 대기", basis: "RSI14·20일 EMA·20일 VWAP·50일 EMA·ATR14 종합" },
    { name: "한화에어로스페이스", code: "012450", close: 1072000, appeal: 68, zone1: "1,025,000~1,045,000원", zone2: "1,000,000~1,015,000원", rsi: 61.4, rsiLabel: "강세", ma20: "1,034,000원", ma50: "1,006,000원", entryStatus: "1차 구간까지 조정 대기", basis: "RSI14·20일 EMA·20일 VWAP·50일 EMA·ATR14 종합" },
    { name: "LIG넥스원", code: "079550", close: 762000, appeal: 61, zone1: "715,000~730,000원", zone2: "680,000~700,000원", rsi: 68.1, rsiLabel: "강세", ma20: "724,000원", ma50: "693,000원", entryStatus: "RSI 과열 완화 대기", basis: "RSI14·20일 EMA·20일 VWAP·50일 EMA·ATR14 종합" }
  ],
  rotation: [
    { sector: "반도체", stage: "탄력 둔화", signal: 38, note: "삼성전자 보합·SK하이닉스 +0.44%로 지수 대비 힘이 약해짐" },
    { sector: "방산·우주", stage: "현재 주도", signal: 92, note: "대표주 동반 강세와 전시회 일정이 결합" },
    { sector: "2차전지", stage: "확산 중", signal: 74, note: "LG에너지솔루션 3거래일 연속 상승, 10월 2일 +2.91%" },
    { sector: "조선", stage: "다음 후보", signal: 58, note: "수주·실적은 견조하지만 종목별 주가 흐름은 아직 혼조" }
  ],
  sources: [
    { label: "10월 2일 시장 마감", url: "https://www.seoul.co.kr/news/economy/securities/2026/10/02/20261002500187" },
    { label: "LG에너지솔루션 일별 시세", url: "https://ir.gsifn.io/lgensol/ir_daily.html?koreng=1" },
    { label: "K-DEX 2026", url: "https://k-dex.kr/eng/" },
    { label: "HD한국조선해양 컨센서스", url: "https://comp.wisereport.co.kr/bridgefn/company/c1010001.aspx?cmp_cd=009540" }
  ]
};

const KOREA_INTELLIGENCE = MARKET_INTELLIGENCE;
const KOREA_OUTLOOK = DAILY_OUTLOOK;

const US_INTELLIGENCE = {
  stocks: {
    NVDA: { price: 233.95, priceDate: "2026-10-02", marketCap: "공개 차트 미제공", volume: "135.2M", fiftyTwoWeekRange: "$164.27~$237.88", exchange: "Nasdaq", description: "AI 가속기와 데이터센터 GPU 생태계를 주도하는 반도체 기업입니다.", business: ["AI GPU", "데이터센터", "CUDA"] },
    AVGO: { price: 365.20, priceDate: "2026-10-02", marketCap: "공개 차트 미제공", volume: "—", fiftyTwoWeekRange: "—", exchange: "Nasdaq", description: "AI 네트워킹 반도체와 인프라 소프트웨어를 공급합니다.", business: ["네트워킹", "ASIC", "소프트웨어"] },
    AMD: { price: 213.10, priceDate: "2026-10-02", marketCap: "공개 차트 미제공", volume: "—", fiftyTwoWeekRange: "—", exchange: "Nasdaq", description: "CPU와 GPU, 데이터센터 가속기를 설계합니다.", business: ["CPU", "GPU", "데이터센터"] },
    XOM: { price: 118.40, priceDate: "2026-10-01", marketCap: "공개 차트 미제공", volume: "—", fiftyTwoWeekRange: "—", exchange: "NYSE", description: "원유·가스의 탐사부터 정제·화학까지 영위하는 통합 에너지 기업입니다.", business: ["원유", "천연가스", "정제"] },
    CVX: { price: 164.20, priceDate: "2026-10-01", marketCap: "공개 차트 미제공", volume: "—", fiftyTwoWeekRange: "—", exchange: "NYSE", description: "글로벌 업스트림과 정제 사업을 영위하는 통합 에너지 기업입니다.", business: ["원유", "LNG", "정제"] },
    COP: { price: 104.80, priceDate: "2026-10-01", marketCap: "공개 차트 미제공", volume: "—", fiftyTwoWeekRange: "—", exchange: "NYSE", description: "미국 중심의 원유·천연가스 탐사 및 생산 기업입니다.", business: ["원유", "셰일", "천연가스"] }
  },
  news: {}
};

const US_OUTLOOK = {
  asOf: "2026-10-02 16:00 ET",
  market: { name: "S&P 500", returnRate: 0.72, close: "—", breadth: "SPY 및 섹터 ETF 기준" },
  focus: {
    sector: "AI·반도체", score: 78, status: "상대강도 우위",
    thesis: "S&P 500 대비 반도체 ETF와 대표 종목의 동반 강도를 비교한 기본 화면입니다. 연결된 최신 스냅샷이 도착하면 수치와 순위가 자동으로 교체됩니다.",
    positives: ["엔비디아 +1.34%", "브로드컴 +1.71%", "AMD +1.26%"],
    checks: ["SMH 거래량이 가격 상승에 동행하는지", "대표 3종목이 지수보다 강한지", "실적 가이던스와 AI 투자 흐름이 유지되는지"]
  },
  entries: [
    { name: "엔비디아", code: "NVDA", close: 233.95, appeal: 72, priceLabel: "최근 종가", zone1: "$227.00~$231.00", zone2: "$219.00~$224.00", rsi: 64.8, rsiLabel: "강세", ma20: "$228.40", ma50: "$218.70", entryStatus: "1차 구간까지 조정 대기", basis: "RSI14·20일 EMA·20일 VWAP·50일 EMA·ATR14 종합" },
    { name: "브로드컴", code: "AVGO", close: 365.20, appeal: 68, priceLabel: "최근 종가", zone1: "$354.00~$361.00", zone2: "$342.00~$350.00", rsi: 62.1, rsiLabel: "강세", ma20: "$357.30", ma50: "$344.80", entryStatus: "1차 구간까지 조정 대기", basis: "RSI14·20일 EMA·20일 VWAP·50일 EMA·ATR14 종합" },
    { name: "AMD", code: "AMD", close: 213.10, appeal: 64, priceLabel: "최근 종가", zone1: "$207.00~$211.00", zone2: "$199.00~$204.00", rsi: 59.7, rsiLabel: "강세", ma20: "$208.40", ma50: "$201.20", entryStatus: "1차 구간까지 조정 대기", basis: "RSI14·20일 EMA·20일 VWAP·50일 EMA·ATR14 종합" }
  ],
  rotation: [
    { sector: "유틸리티", stage: "탄력 둔화", signal: 34, note: "금리와 방어주 수요를 함께 확인" },
    { sector: "AI·반도체", stage: "현재 주도", signal: 84, note: "SMH와 대표 3종목의 상대강도" },
    { sector: "소프트웨어·클라우드", stage: "확산 중", signal: 66, note: "IGV와 대형 소프트웨어 동행 여부" },
    { sector: "금융", stage: "다음 후보", signal: 55, note: "장기금리와 순이자마진 기대 확인" }
  ],
  sources: [{ label: "S&P 500 ETF 시세", url: "https://finance.yahoo.com/quote/SPY/" }]
};

const MARKET_PROFILES = {
  kr: { key: "kr", label: "한국", benchmark: "KOSPI", currency: "KRW", data: KOREA_SAMPLE_MARKET_DATA, intelligence: KOREA_INTELLIGENCE, outlook: KOREA_OUTLOOK, provider: "네이버 금융 · Google 뉴스" },
  us: { key: "us", label: "미국", benchmark: "S&P 500", currency: "USD", data: US_SAMPLE_MARKET_DATA, intelligence: US_INTELLIGENCE, outlook: US_OUTLOOK, provider: "Yahoo Finance 공개 차트 · Google News" }
};

let ACTIVE_MARKET = "kr";
