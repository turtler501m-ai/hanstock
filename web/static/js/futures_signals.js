const state = {
    signals: [],
    selectedId: null,
    chart: null,
};

const endpoints = {
    summary: "/api/futures-signals/summary",
    signals: "/api/futures-signals",
};

function iconize() {
    document.querySelectorAll("[data-icon]").forEach((element) => {
        if (element.querySelector("svg")) {
            return;
        }
        const icon = document.createElement("i");
        icon.setAttribute("data-lucide", element.dataset.icon);
        element.prepend(icon);
    });
    if (window.lucide) {
        window.lucide.createIcons();
    }
}

function valueFrom(object, keys, fallback = null) {
    for (const key of keys) {
        if (object && object[key] !== undefined && object[key] !== null) {
            return object[key];
        }
    }
    return fallback;
}

function normalizeList(payload) {
    if (Array.isArray(payload)) {
        return payload;
    }
    return payload?.signals || payload?.items || payload?.data || payload?.results || [];
}

function formatNumber(value, suffix = "") {
    if (value === null || value === undefined || value === "") {
        return "-";
    }
    const numeric = Number(value);
    if (Number.isNaN(numeric)) {
        return `${value}${suffix}`;
    }
    return `${numeric.toLocaleString("ko-KR")}${suffix}`;
}

function formatRate(value) {
    if (value === null || value === undefined || value === "") {
        return "-";
    }
    const numeric = Number(value);
    if (Number.isNaN(numeric)) {
        return String(value);
    }
    const percent = Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
    return `${percent.toFixed(1)}%`;
}

function formatTime(value) {
    if (!value) {
        return "-";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return new Intl.DateTimeFormat("ko-KR", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    }[char]));
}

function normalizeStatus(value, fallback = "pending") {
    return String(value || fallback).trim().toLowerCase();
}

function confidenceValue(signal, result) {
    return valueFrom(signal, ["confidence", "parse_confidence", "parser_confidence"], valueFrom(signal.parser || {}, ["confidence", "parse_confidence"], valueFrom(signal.parsed || {}, ["confidence"], valueFrom(result, ["parse_confidence", "confidence"], null))));
}

function normalizeSignal(signal, index) {
    const result = signal.result || signal.verification || {};
    const rawDirection = String(valueFrom(signal, ["direction", "side", "action"], "-")).toLowerCase();
    const direction = ["sell", "short"].includes(rawDirection) ? "short" : "long";
    const parseStatus = normalizeStatus(valueFrom(signal, ["parse_status", "parser_status"], valueFrom(signal.parser || {}, ["status"], "parsed")));
    const verificationStatus = normalizeStatus(valueFrom(result, ["verification_status", "status"], valueFrom(signal, ["verification_status", "status"], "pending")));
    const resultStatus = normalizeStatus(valueFrom(result, ["exit_reason", "result"], verificationStatus));
    const targetValue = valueFrom(signal, ["take_profit_1", "tp1", "target", "take_profit"], null);
    const tp = Array.isArray(signal.targets) ? signal.targets.join(" / ") : (targetValue ?? "-");

    return {
        id: valueFrom(signal, ["id", "signal_id"], index),
        provider: valueFrom(signal, ["provider", "channel", "channel_name", "source"], "-"),
        symbol: valueFrom(signal, ["symbol", "ticker", "contract"], "-"),
        exchange: valueFrom(signal, ["exchange", "market"], ""),
        direction,
        entry: valueFrom(signal, ["entry_price", "entry", "entry_low"], "-"),
        stopLoss: valueFrom(signal, ["stop_loss", "stop", "sl"], "-"),
        takeProfit: tp,
        parseStatus,
        verificationStatus,
        status: verificationStatus,
        resultStatus,
        pnlPoints: valueFrom(result, ["pnl_points", "pnl"], valueFrom(signal, ["pnl_points"], null)),
        signalTime: valueFrom(signal, ["signal_time", "received_at", "created_at", "time"], null),
        rawText: valueFrom(signal, ["raw_text", "raw_message", "message"], valueFrom(signal.message || {}, ["raw_text"], "")),
        rawPayload: valueFrom(signal, ["raw_payload_json", "parsed", "payload"], signal),
        confidence: confidenceValue(signal, result),
    };
}

function statusBucket(status) {
    if (["verified", "parsed", "success", "hit_tp", "hit_sl", "closed", "win", "loss", "tp1", "tp2", "tp3", "sl"].includes(status)) {
        return "verified";
    }
    if (["rejected", "invalid", "duplicate", "failed", "parse_failed"].includes(status)) {
        return "rejected";
    }
    return "pending";
}

function badgeClass(status) {
    const bucket = statusBucket(status);
    return `status-badge status-${bucket}`;
}

function resultClass(status) {
    if (["hit_tp", "tp1", "tp2", "tp3", "win", "verified"].includes(status)) {
        return "result-win";
    }
    if (["hit_sl", "sl", "loss", "rejected"].includes(status)) {
        return "result-loss";
    }
    if (["ambiguous", "needs_review"].includes(status)) {
        return "result-ambiguous";
    }
    if (["pending", "open"].includes(status)) {
        return "result-pending";
    }
    return "result-neutral";
}

function resultLabel(status) {
    const labels = {
        hit_tp: "TP",
        hit_sl: "SL",
        parsed: "파싱",
        success: "성공",
        verified: "검증",
        needs_review: "검토",
        rejected: "거부",
        duplicate: "중복",
        ambiguous: "모호",
        pending: "대기",
        open: "진행",
        expired: "만료",
        invalid: "무효",
        closed: "종료",
    };
    return labels[status] || status || "-";
}

function countStatuses(summary = {}, signals = []) {
    const fallback = signals.reduce((counts, signal) => {
        counts[statusBucket(signal.verificationStatus)] += 1;
        return counts;
    }, { verified: 0, pending: 0, rejected: 0 });

    return {
        verified: valueFrom(summary, ["verified_count", "verification_completed", "completed_count", "verified"], fallback.verified),
        pending: valueFrom(summary, ["pending_count", "verification_pending", "needs_review"], fallback.pending),
        rejected: valueFrom(summary, ["rejected_count", "rejected", "invalid_count", "duplicate_count"], fallback.rejected),
    };
}

function averageConfidence(summary = {}, signals = []) {
    const summaryValue = valueFrom(summary, ["avg_parse_confidence", "average_parse_confidence", "parse_confidence", "confidence"], null);
    if (summaryValue !== null) {
        return summaryValue;
    }
    const values = signals
        .map((signal) => signal.confidence)
        .filter((value) => value !== null && value !== undefined && value !== "")
        .map((value) => Number(value))
        .filter((value) => !Number.isNaN(value));
    if (values.length === 0) {
        return null;
    }
    return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function renderSummary(summary = {}, signals = []) {
    const total = valueFrom(summary, ["collected_today", "today_count", "messages_today", "total"]);
    const counts = countStatuses(summary, signals);
    const verified = counts.verified;
    const needsReview = counts.pending;
    const parseRate = valueFrom(summary, ["parse_success_rate", "parse_rate"], total ? Number(verified || 0) / Number(total) : null);

    document.getElementById("summary-collected").textContent = formatNumber(total);
    document.getElementById("summary-parse-rate").textContent = formatRate(parseRate);
    document.getElementById("summary-pending").textContent = formatNumber(needsReview);
    document.getElementById("summary-win-rate").textContent = formatRate(valueFrom(summary, ["win_rate", "recent_win_rate"]));
    document.getElementById("summary-verified").textContent = formatNumber(verified);
    document.getElementById("summary-rejected").textContent = formatNumber(counts.rejected);
    document.getElementById("summary-confidence").textContent = formatRate(averageConfidence(summary, signals));
    document.getElementById("summary-avg-pnl").textContent = formatNumber(valueFrom(summary, ["avg_pnl_points", "average_pnl_points"], null), " pt");
    document.getElementById("count-verified").textContent = formatNumber(verified);
    document.getElementById("count-pending").textContent = formatNumber(needsReview);
    document.getElementById("count-rejected").textContent = formatNumber(counts.rejected);
}

function renderSignals() {
    const body = document.getElementById("signal-table-body");
    const empty = document.getElementById("signal-empty");
    body.innerHTML = "";
    empty.classList.toggle("visible", state.signals.length === 0);

    state.signals.forEach((signal) => {
        const row = document.createElement("tr");
        const directionLabel = signal.direction === "short" ? "SHORT" : "LONG";
        const directionClass = signal.direction === "short" ? "short" : "long";
        const exchange = signal.exchange ? `<span class="subtle">${escapeHtml(signal.exchange)}</span>` : "";
        row.className = signal.id === state.selectedId ? "selected" : "";
        row.innerHTML = `
            <td>${escapeHtml(formatTime(signal.signalTime))}</td>
            <td>${escapeHtml(signal.provider)}</td>
            <td><strong>${escapeHtml(signal.symbol)}</strong> ${exchange}</td>
            <td><span class="direction-pill direction-${directionClass}">${directionLabel}</span></td>
            <td>${escapeHtml(signal.entry)}</td>
            <td>${escapeHtml(signal.stopLoss)}</td>
            <td>${escapeHtml(signal.takeProfit)}</td>
            <td>${escapeHtml(formatRate(signal.confidence))}</td>
            <td><span class="${badgeClass(signal.verificationStatus)}">${escapeHtml(resultLabel(signal.verificationStatus))}</span></td>
            <td><span class="result-pill ${resultClass(signal.resultStatus)}">${escapeHtml(resultLabel(signal.resultStatus))}</span></td>
        `;
        row.addEventListener("click", () => selectSignal(signal.id));
        body.appendChild(row);
    });
}

function selectSignal(id) {
    state.selectedId = id;
    const signal = state.signals.find((item) => item.id === id) || state.signals[0];
    renderSignals();
    renderDetails(signal);
}

function renderDetails(signal) {
    const raw = document.getElementById("raw-message");
    const details = document.getElementById("parsed-detail");
    const badges = document.getElementById("detail-badges");
    if (!signal) {
        raw.textContent = "신호를 선택하면 Telegram 원문이 표시됩니다.";
        details.innerHTML = "";
        badges.innerHTML = "";
        return;
    }

    raw.textContent = signal.rawText || "원문 메시지가 API 응답에 포함되지 않았습니다.";
    badges.innerHTML = `
        <span class="status-badge status-${statusBucket(signal.parseStatus)}">Parse ${escapeHtml(resultLabel(signal.parseStatus))}</span>
        <span class="${badgeClass(signal.verificationStatus)}">Verification ${escapeHtml(resultLabel(signal.verificationStatus))}</span>
        <span class="confidence-badge">Confidence ${escapeHtml(formatRate(signal.confidence))}</span>
    `;
    const fields = [
        ["제공자", signal.provider],
        ["종목", `${signal.symbol}${signal.exchange ? ` / ${signal.exchange}` : ""}`],
        ["방향", signal.direction.toUpperCase()],
        ["진입가", signal.entry],
        ["손절가", signal.stopLoss],
        ["목표가", signal.takeProfit],
        ["파싱 상태", resultLabel(signal.parseStatus)],
        ["검증 상태", resultLabel(signal.verificationStatus)],
        ["신뢰도", formatRate(signal.confidence)],
        ["손익", signal.pnlPoints === null ? "-" : `${signal.pnlPoints} pt`],
    ];
    details.innerHTML = fields.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("");
}

function renderChart(summary = {}) {
    const canvas = document.getElementById("futures-performance-chart");
    const placeholder = document.getElementById("chart-placeholder");
    const series = summary.performance || summary.chart || {};
    const labels = series.labels || [];
    const pnl = series.pnl || series.cumulative_pnl || [];
    const winRate = series.win_rate || series.winRate || [];

    if (!canvas || !window.Chart || labels.length === 0 || pnl.length === 0) {
        placeholder.classList.add("visible");
        if (state.chart) {
            state.chart.destroy();
            state.chart = null;
        }
        return;
    }

    placeholder.classList.remove("visible");
    if (state.chart) {
        state.chart.destroy();
    }
    state.chart = new Chart(canvas, {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "누적 손익(pt)",
                    data: pnl,
                    borderColor: "#22c55e",
                    backgroundColor: "rgba(34, 197, 94, 0.14)",
                    fill: true,
                    tension: 0.35,
                    yAxisID: "y",
                },
                {
                    label: "승률(%)",
                    data: winRate,
                    borderColor: "#22d3ee",
                    backgroundColor: "rgba(34, 211, 238, 0.08)",
                    fill: false,
                    tension: 0.35,
                    yAxisID: "y1",
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: "#c5d1df" } } },
            scales: {
                x: { ticks: { color: "#96a4b6" }, grid: { color: "rgba(255,255,255,0.05)" } },
                y: { ticks: { color: "#96a4b6" }, grid: { color: "rgba(255,255,255,0.05)" } },
                y1: { position: "right", ticks: { color: "#96a4b6" }, grid: { drawOnChartArea: false } },
            },
        },
    });
}

async function fetchJson(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.json();
}

async function refreshDashboard() {
    const refreshButton = document.getElementById("btn-refresh-futures");
    const lastUpdated = document.getElementById("last-updated");
    refreshButton.disabled = true;
    lastUpdated.textContent = "갱신 중";

    try {
        const [summary, signalsPayload] = await Promise.all([
            fetchJson(endpoints.summary),
            fetchJson(endpoints.signals),
        ]);
        state.signals = normalizeList(signalsPayload).map(normalizeSignal);
        renderSummary(summary, state.signals);
        renderChart(summary);
        renderSignals();
        selectSignal(state.signals[0]?.id ?? null);
        lastUpdated.textContent = `${new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit" }).format(new Date())} 갱신`;
    } catch (error) {
        state.signals = [];
        renderSummary({}, []);
        renderChart({});
        renderSignals();
        renderDetails(null);
        lastUpdated.textContent = "API 대기";
        console.warn("Failed to load futures signals dashboard", error);
    } finally {
        refreshButton.disabled = false;
    }
}

document.getElementById("btn-refresh-futures").addEventListener("click", refreshDashboard);
iconize();
refreshDashboard();
