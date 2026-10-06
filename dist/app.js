const state = {
  data: [],
  market: localStorage.getItem("sector-flow-market") || "kr",
  selectedDate: null,
  selectedSector: null,
  query: "",
  sort: "desc",
  range: 5
};

const $ = selector => document.querySelector(selector);
const fmt = value => `${value > 0 ? "+" : ""}${Number(value).toFixed(2)}%`;
const fmtDate = date => new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "long", day: "numeric", weekday: "short" }).format(new Date(`${date}T12:00:00`));
const profile = () => marketRepository.profile;
const formatPrice = value => profile().currency === "USD"
  ? `$${Number(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
  : `${Number(value).toLocaleString("ko-KR")}원`;
const formatHeaderAsOf = value => {
  if (!value) return "—";
  const [date, ...rest] = value.split(" ");
  return `${date.slice(5).replace("-", ".")} ${rest.join(" ")} 기준`.replace(/\s+/g, " ");
};
const formatPriceBasis = info => `${info?.priceDate || "—"} ${info?.marketStatus === "OPEN" ? "장중" : "종가"} 기준`;

async function init() {
  renderLiveState();
  state.data = await marketRepository.setMarket(state.market);
  state.market = marketRepository.activeMarket;
  state.selectedDate = state.data[0]?.date;
  bindEvents();
  render();
}

function currentDay() {
  return state.data.find(day => day.date === state.selectedDate) || state.data[0];
}

function periodDays() {
  const index = Math.max(0, state.data.findIndex(day => day.date === state.selectedDate));
  const count = state.range === "all" ? state.data.length : Number(state.range);
  return state.data.slice(index, index + count);
}

function rankedSectors() {
  const days = periodDays();
  const downDays = days.filter(day => day.kospi < 0);
  const comparisonDays = downDays.length ? downDays : days;
  const groups = new Map();

  comparisonDays.forEach(day => day.sectors.forEach(sector => {
    const item = groups.get(sector.name) || { name: sector.name, returns: [], stocks: new Map(), hits: 0 };
    item.returns.push(sector.returnRate);
    if (sector.returnRate > 0) item.hits += 1;
    sector.stocks.forEach(stock => {
      const saved = item.stocks.get(stock.code) || { ...stock, returns: [] };
      saved.returns.push(stock.returnRate);
      item.stocks.set(stock.code, saved);
    });
    groups.set(sector.name, item);
  }));

  const benchmarkReturn = comparisonDays.reduce((sum, day) => sum + day.kospi, 0);
  return [...groups.values()].map(sector => {
    const average = sector.returns.reduce((a, b) => a + b, 0) / sector.returns.length;
    const cumulative = sector.returns.reduce((a, b) => a + b, 0);
    const persistence = sector.hits / Math.max(1, comparisonDays.length) * 100;
    const excess = cumulative - benchmarkReturn;
    const score = Math.min(99, Math.round(Math.max(0, excess) * 6 + persistence * .3 + Math.max(0, average) * 5));
    const stocks = [...sector.stocks.values()].map(stock => ({
      ...stock,
      returnRate: stock.returns.reduce((a, b) => a + b, 0) / stock.returns.length
    }));
    return { ...sector, returnRate: cumulative, average, persistence, excess, score, stocks };
  }).sort((a, b) => b.score - a.score);
}

function filteredSectors() {
  const query = state.query.trim().toLowerCase();
  return rankedSectors().filter(sector => !query || sector.name.toLowerCase().includes(query) || sector.stocks.some(stock => stock.name.toLowerCase().includes(query) || stock.code.toLowerCase().includes(query)));
}

function render() {
  document.body.dataset.market = state.market;
  renderMarketSwitch();
  renderLiveState();
  renderOutlook();
  renderSummary();
  renderSectors();
  renderStocks();
  renderNews();
  renderHeatmap();
}

function renderMarketSwitch() {
  document.querySelectorAll(".market-switch button").forEach(button => {
    const active = button.dataset.market === state.market;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.disabled = LIVE_STATE.status === "loading";
  });
}

function renderLiveState() {
  const status = $("#liveStatus");
  const date = $("#liveDate");
  const button = $("#refreshBtn");
  const feedback = $("#refreshFeedback");
  if (!status) return;
  status.textContent = LIVE_STATE.message;
  date.textContent = formatHeaderAsOf(DAILY_OUTLOOK.asOf);
  const box = status.closest(".market-state");
  box.classList.toggle("is-loading", LIVE_STATE.status === "loading");
  box.classList.toggle("is-fallback", LIVE_STATE.status === "fallback");
  if (button) {
    button.disabled = LIVE_STATE.status === "loading";
    button.textContent = LIVE_STATE.status === "loading" ? "↻" : LIVE_STATE.refreshResult === "failed" ? "!" : LIVE_STATE.refreshResult ? "✓" : "↻";
    button.title = LIVE_STATE.message;
  }
  if (feedback) {
    feedback.textContent = LIVE_STATE.refreshResult ? LIVE_STATE.message : "";
    feedback.className = `refresh-feedback${LIVE_STATE.refreshResult ? ` show ${LIVE_STATE.refreshResult}` : ""}`;
  }
}

function renderOutlook() {
  const view = DAILY_OUTLOOK;
  $("#outlookAsOf").textContent = `${view.asOf} 기준 · 다음 개장 전 관점`;
  $("#outlookConfidence").textContent = `관심도 ${view.focus.score} / 100`;
  $("#focusSector").textContent = view.focus.sector;
  $("#focusStatus").textContent = view.focus.status;
  $("#focusThesis").textContent = view.focus.thesis;
  $("#focusPositives").innerHTML = view.focus.positives.map(item => `<span>${item}</span>`).join("");
  $("#focusChecks").innerHTML = view.focus.checks.map(item => `<li>${item}</li>`).join("");
  $("#entryGrid").innerHTML = view.entries.map(entry => `<article class="entry-card"><div class="entry-title"><div><h3>${entry.name}</h3><span>${entry.code}</span></div><b>${entry.appeal}<small>/100</small></b></div><div class="entry-current"><span>현재 가격<small>${entry.priceLabel || "최근 확인 가격"}</small></span><strong>${formatPrice(entry.close)}</strong></div><div class="entry-tech"><span>RSI14<b>${entry.rsi ?? "—"} ${entry.rsiLabel || ""}</b></span><span>20일 EMA<b>${entry.ma20 || "—"}</b></span><span>50일 EMA<b>${entry.ma50 || "—"}</b></span></div><div class="entry-status">${entry.entryStatus || "기술적 관심 구간을 관찰 중"}</div><div class="entry-zones"><span>1차 적정 구간<strong>${entry.zone1}</strong></span><span>2차 적정 구간<strong>${entry.zone2}</strong></span></div><p>${entry.basis}</p></article>`).join("");
  $("#rotationFlow").innerHTML = view.rotation.map((item, index) => `<div class="rotation-step ${item.stage === "현재 주도" ? "leader-step" : ""}"><div class="rotation-top"><span>${String(index + 1).padStart(2, "0")}</span><b>${item.stage}</b></div><h3>${item.sector}</h3><div class="signal-track"><i style="width:${item.signal}%"></i></div><p>${item.note}</p></div>`).join("");
  $("#outlookSources").innerHTML = `<span>분석 근거</span>${view.sources.map(source => `<a href="${source.url}" target="_blank" rel="noopener">${source.label}</a>`).join("")}`;
}

function renderSummary() {
  const day = currentDay();
  const days = periodDays();
  const periodReturn = days.reduce((sum, item) => sum + item.kospi, 0);
  const ranking = rankedSectors();
  const benchmark = profile().benchmark;
  $("#benchmarkLabel").textContent = benchmark;
  $("#timelineBenchmarkLabel").textContent = benchmark;
  $("#signalCopy").textContent = `${benchmark} 하락에도 상대적으로 강했던 섹터`;
  $("#summaryDate").textContent = state.range === 1 ? fmtDate(day.date) : `${days.at(-1)?.date.slice(5)} ~ ${day.date.slice(5)}`;
  $("#kospiValue").textContent = fmt(periodReturn);
  $("#kospiValue").className = `kospi-value ${periodReturn < 0 ? "negative" : "positive"}`;
  $("#kospiDesc").textContent = state.range === 1
    ? (day.kospi < 0 ? "전일 대비 하락 · 역행 섹터 탐지 대상" : "전일 대비 상승 · 참고 거래일")
    : `선택 기간 단순 누적 · 하락 거래일 ${days.filter(item => item.kospi < 0).length}일`;
  $("#sectorCount").innerHTML = `${ranking.length}<span>개</span>`;
  $("#bestSector").textContent = ranking[0]?.name || "—";
  $("#averageReturn").textContent = ranking.length ? `${ranking[0].score}점` : "—";
  if (!state.selectedSector || !ranking.some(sector => sector.name === state.selectedSector)) state.selectedSector = ranking[0]?.name;
}

function renderSectors() {
  const sectors = filteredSectors();
  const max = Math.max(...rankedSectors().map(sector => sector.score), 1);
  $("#sectorRanking").innerHTML = sectors.map((sector, index) => `<button class="sector-row ${sector.name === state.selectedSector ? "active" : ""}" data-sector="${sector.name}"><span class="rank">${String(index + 1).padStart(2, "0")}</span><span class="sector-main"><span class="sector-name">${sector.name}</span><span class="leader">초과 ${fmt(sector.excess)} · 상승 지속 ${Math.round(sector.persistence)}%</span><span class="bar"><i style="width:${sector.score / max * 100}%"></i></span></span><span class="score"><span class="return">${sector.score}점</span><small>${fmt(sector.returnRate)}</small></span></button>`).join("");
  document.querySelectorAll(".sector-row").forEach(element => element.onclick = () => {
    state.selectedSector = element.dataset.sector;
    renderSectors();
    renderStocks();
    openDrawer(element.dataset.sector);
  });
}

function renderStocks() {
  const sectors = filteredSectors();
  let stocks = [];
  if (state.query) {
    stocks = sectors.flatMap(sector => sector.stocks.map(stock => ({ ...stock, sector: sector.name }))).filter(stock => stock.name.toLowerCase().includes(state.query.toLowerCase()) || stock.code.toLowerCase().includes(state.query.toLowerCase()) || stock.sector.toLowerCase().includes(state.query.toLowerCase()));
  } else {
    const sector = rankedSectors().find(item => item.name === state.selectedSector) || rankedSectors()[0];
    stocks = (sector?.stocks || []).map(stock => ({ ...stock, sector: sector?.name }));
  }
  stocks.sort((a, b) => state.sort === "asc" ? a.returnRate - b.returnRate : state.sort === "name" ? a.name.localeCompare(b.name, "ko") : b.returnRate - a.returnRate);
  $("#stockTitle").textContent = state.query ? "검색 종목" : `${state.selectedSector || ""} 대표 종목`;
  $("#stockTable").innerHTML = stocks.map(stock => {
    const info = MARKET_INTELLIGENCE.stocks[stock.code];
    return `<tr class="stock-row" data-code="${stock.code}" data-name="${stock.name}"><td><span class="stock-name">${stock.name}</span><small class="code">${stock.code}</small></td><td class="price-cell">${info ? formatPrice(info.price) : "—"}<small>${info ? formatPriceBasis(info) : ""}</small></td><td class="${stock.returnRate >= 0 ? "positive" : "negative"}">${fmt(stock.returnRate)}</td></tr>`;
  }).join("");
  document.querySelectorAll(".stock-row").forEach(element => element.onclick = () => openStockProfile(element.dataset.code, element.dataset.name));
  $("#emptyState").hidden = stocks.length > 0;
  $(".table-wrap").hidden = stocks.length === 0;
}

function renderNews() {
  const sectorNames = [...new Set([DAILY_OUTLOOK.focus.sector, ...rankedSectors().slice(0, 4).map(sector => sector.name)])];
  const items = sectorNames.flatMap(name => (MARKET_INTELLIGENCE.news[name] || []).map(item => ({ ...item, sector: name }))).slice(0, 6);
  $("#newsGrid").innerHTML = items.length
    ? items.map(item => `<a class="news-card" href="${item.url}" target="_blank" rel="noopener"><div class="news-meta"><span class="news-sector">${item.sector}</span><span>${item.source}</span><span>${item.date}</span></div><h3>${item.title}</h3><p>${item.summary}</p></a>`).join("")
    : `<div class="empty">선택 기간 상위 섹터의 등록된 뉴스가 없습니다.</div>`;
}

function renderHeatmap() {
  $("#heatmap").innerHTML = periodDays().map(day => {
    const intensity = Math.min(1, Math.abs(day.sectors[0]?.returnRate || 0) / 4);
    return `<button class="heat-cell ${day.kospi >= 0 ? "rise" : ""} ${day.date === state.selectedDate ? "active" : ""}" data-date="${day.date}"><span class="heat-date">${day.date.slice(5).replace("-", ".")}</span><strong class="heat-kospi ${day.kospi < 0 ? "negative" : "positive"}">${fmt(day.kospi)}</strong><span class="heat-sectors">${day.sectors.slice(0, 4).map((sector, index) => `<i style="opacity:${Math.max(.25, intensity - index * .13)}"></i>`).join("")}</span></button>`;
  }).join("");
  document.querySelectorAll(".heat-cell").forEach(element => element.onclick = () => {
    state.selectedDate = element.dataset.date;
    state.selectedSector = null;
    render();
    window.scrollTo({ top: 260, behavior: "smooth" });
  });
}

function openDrawer(name) {
  const sector = rankedSectors().find(item => item.name === name);
  if (!sector) return;
  $("#drawerTitle").textContent = sector.name;
  $("#drawerReturn").textContent = `${sector.score}점 · ${fmt(sector.returnRate)}`;
  $("#drawerDesc").textContent = `선택 기간 ${profile().benchmark} 하락일 기준 시장 대비 ${fmt(sector.excess)} 초과 수익을 기록했고, 비교 거래일 중 ${Math.round(sector.persistence)}%에서 상승 신호가 포착됐습니다.`;
  $("#drawerStocks").innerHTML = sector.stocks.map(stock => `<div class="drawer-stock"><span><b>${stock.name}</b><small>${stock.code}</small></span><strong class="${stock.returnRate >= 0 ? "positive" : "negative"}">${fmt(stock.returnRate)}</strong></div>`).join("");
  $("#drawer").classList.add("open");
  $("#drawerBackdrop").classList.add("open");
  $("#drawer").setAttribute("aria-hidden", "false");
}

function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawerBackdrop").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
}

function openStockProfile(code, name) {
  const info = MARKET_INTELLIGENCE.stocks[code];
  if (!info) return;
  $("#profileName").textContent = name;
  $("#profileCode").textContent = `${info.exchange || profile().benchmark} · ${code}`;
  $("#profilePrice").textContent = formatPrice(info.price);
  $("#profilePriceDate").textContent = formatPriceBasis(info);
  const firstMetric = state.market === "us" ? `52주 범위<b>${info.fiftyTwoWeekRange || "—"}</b>` : `시가총액<b>${info.marketCap || "—"}</b>`;
  $("#profileMetrics").innerHTML = `<span>${firstMetric}</span><span>거래량<b>${info.volume || "—"}</b></span>`;
  $("#profileDesc").textContent = info.description;
  $("#profileTags").innerHTML = (info.business || []).map(tag => `<span>${tag}</span>`).join("");
  $("#stockModal").classList.add("open");
}

async function switchMarket(market) {
  if (market === state.market || LIVE_STATE.status === "loading") return;
  state.market = market;
  localStorage.setItem("sector-flow-market", market);
  LIVE_STATE.status = "loading";
  LIVE_STATE.message = "시장 데이터 전환 중";
  renderMarketSwitch();
  renderLiveState();
  state.data = await marketRepository.setMarket(market);
  state.selectedDate = state.data[0]?.date;
  state.selectedSector = null;
  render();
}

function bindEvents() {
  document.querySelectorAll(".market-switch button").forEach(button => button.onclick = () => switchMarket(button.dataset.market));
  $("#sortSelect").onchange = event => { state.sort = event.target.value; renderStocks(); };
  $("#refreshBtn").onclick = async () => {
    LIVE_STATE.status = "loading";
    LIVE_STATE.refreshResult = null;
    LIVE_STATE.message = "데이터 새로고침 중";
    renderLiveState();
    state.data = await marketRepository.getMarketDays(true);
    state.selectedDate = state.data[0]?.date;
    state.selectedSector = null;
    render();
  };
  $("#drawerClose").onclick = closeDrawer;
  $("#drawerBackdrop").onclick = closeDrawer;
  $("#timelineJump").onclick = () => $("#timeline").scrollIntoView({ behavior: "smooth" });
  $("#aboutBtn").onclick = () => $("#modal").classList.add("open");
  $("#modalClose").onclick = () => $("#modal").classList.remove("open");
  $("#modal").onclick = event => { if (event.target.id === "modal") event.currentTarget.classList.remove("open"); };
  $("#stockModalClose").onclick = () => $("#stockModal").classList.remove("open");
  $("#stockModal").onclick = event => { if (event.target.id === "stockModal") event.currentTarget.classList.remove("open"); };
  document.onkeydown = event => {
    if (event.key === "Escape") {
      closeDrawer();
      $("#modal").classList.remove("open");
      $("#stockModal").classList.remove("open");
    }
  };
}

init();
