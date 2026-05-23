const endpoints = {
    health: "/api/health",
    balance: "/api/balance",
    executionPlan: "/api/execution-plan",
    approvals: "/api/approvals?limit=20",
    approve: (id) => `/api/approvals/${id}/approve`,
    reject: (id) => `/api/approvals/${id}/reject`,
    autoApproval: "/api/auto-approval",
    orderMode: "/api/runtime/order-mode",
    kill: "/api/system/kill",
    unkill: "/api/system/unkill",
};

let dashboardState = {
    health: null,
    balance: null,
    plan: null,
    approvals: [],
    chart: null,
};

const actionLabel = { buy: "매수", sell: "매도", hold: "보유", skip: "제외" };

function qs(id) {
    return document.getElementById(id);
}

function setText(id, value) {
    const el = qs(id);
    if (el) el.textContent = value;
}

function formatCurrency(value) {
    const amount = Number(value || 0);
    return amount ? `${amount.toLocaleString("ko-KR")}원` : "-";
}

function formatPercent(value, digits = 1) {
    const number = Number(value || 0);
    return `${number.toFixed(digits)}%`;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

async function fetchJson(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.timeoutMs || 25000);
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                ...(options.headers || {}),
            },
            signal: controller.signal,
        });
        const text = await response.text();
        const data = text ? JSON.parse(text) : {};
        if (!response.ok) {
            throw new Error(data.detail || data.msg || response.statusText);
        }
        return data;
    } finally {
        clearTimeout(timeout);
    }
}

function iconize() {
    document.querySelectorAll("[data-icon]").forEach((element) => {
        if (element.querySelector("svg")) return;
        const icon = document.createElement("i");
        icon.setAttribute("data-lucide", element.dataset.icon);
        element.prepend(icon);
    });
    if (window.lucide) window.lucide.createIcons();
}

function renderHealth() {
    const health = dashboardState.health || {};
    const circuit = health.circuit_breaker || {};
    const killActive = Boolean(health.kill_switch_active);
    const missing = Array.isArray(health.missing) ? health.missing.length : 0;

    const statusItems = document.querySelectorAll(".status-item");
    if (statusItems[0]) {
        statusItems[0].className = `status-item ${missing ? "warn" : "ok"}`;
        statusItems[0].innerHTML = `<span>데이터</span><strong>${missing ? "설정 필요" : "KIS 준비"}</strong><small>${missing ? `${missing}개 환경값 누락` : "계좌 API 연결 가능"}</small>`;
    }
    if (statusItems[1]) {
        statusItems[1].className = "status-item ok";
        statusItems[1].innerHTML = `<span>AI 모델</span><strong>${escapeHtml(health.active_model_version || "v1")}</strong><small>활성 모델</small>`;
    }
    if (statusItems[2]) {
        statusItems[2].className = `status-item ${health.order_submission_enabled ? "ok" : "warn"}`;
        statusItems[2].innerHTML = `<span>주문 권한</span><strong>${health.order_submission_enabled ? "전송 가능" : "승인 필요"}</strong><small>${health.real_orders_enabled ? "실주문 가능" : "실주문 차단"}</small>`;
    }
    if (statusItems[3]) {
        statusItems[3].className = `status-item ${killActive || circuit.open ? "warn" : "ok"}`;
        statusItems[3].innerHTML = `<span>서킷브레이커</span><strong>${killActive ? "Kill Switch" : circuit.open ? "열림" : "닫힘"}</strong><small>${Number(circuit.fail_count || 0)} / ${Number(circuit.threshold || 5)} 오류</small>`;
    }

    updateToggle("toggle-dry-run", Boolean(health.dry_run));
    updateToggle("toggle-live-trading", Boolean(health.enable_live_trading));
    updateToggle("toggle-auto-approval", Boolean(health.auto_approval_enabled));
    updateToggle("toggle-demo-trading", health.trading_env !== "real");

    const modePanel = document.querySelector(".mode-panel");
    if (modePanel) {
        modePanel.querySelector("strong").textContent = health.auto_approval_enabled ? "Auto Approval" : "Approval Mode";
        modePanel.querySelector("small").textContent = health.dry_run ? "DRY_RUN 보호 상태" : "주문 전송 허용 상태";
    }

    const killButton = qs("btn-kill-switch");
    if (killButton) {
        killButton.dataset.active = String(killActive);
        killButton.innerHTML = "";
        killButton.dataset.icon = killActive ? "shield-check" : "octagon-alert";
        iconize();
        killButton.append(killActive ? "Release Kill Switch" : "Kill Switch");
    }
}

function updateToggle(id, enabled) {
    const button = qs(id);
    if (!button) return;
    button.dataset.enabled = String(Boolean(enabled));
    button.classList.toggle("on", Boolean(enabled));
    button.classList.toggle("off", !enabled);
    button.textContent = enabled ? "ON" : "OFF";
}

function renderBalance() {
    const balance = dashboardState.balance || {};
    const holdings = Array.isArray(balance.holdings) ? balance.holdings : [];
    const total = Number(balance.total_eval || 0);
    const stockEval = Number(balance.stock_eval || 0);
    const pnl = Number(balance.pnl || 0);
    const lossUsage = total > 0 && pnl < 0 ? Math.min(100, Math.abs(pnl) / total * 100) : 0;

    setText("total-balance", formatCurrency(total));
    setText("cash-balance", formatCurrency(balance.cash));
    setText("margin-balance", formatCurrency(stockEval));
    setText("position-count", String(holdings.filter((item) => Number(item.qty || 0) > 0).length));
    setText("daily-pnl", `${pnl >= 0 ? "평가손익 +" : "평가손익 "}${formatCurrency(pnl)}`);
    qs("daily-pnl")?.classList.toggle("up", pnl >= 0);
    setText("risk-usage", formatPercent(lossUsage));
    setText("risk-usage-detail", `일일 손실 한도 ${formatPercent(Number(dashboardState.plan?.daily_loss_halt ? 100 : lossUsage))}`);
}

function planRows() {
    const rows = dashboardState.plan?.plan;
    return Array.isArray(rows) ? rows : [];
}

function toDecision(row) {
    const action = String(row.rebalance_action || row.action || "hold").toLowerCase();
    const qty = Number(row.rebalance_qty || row.qty || 0);
    const price = Number(row.price || row.signal_price || row.current_price || 0);
    const score = Number(row.strategy_score || row.score || 0);
    const confidence = Math.max(0.35, Math.min(0.95, score > 1 ? score / 10 : score || 0.55));
    const reasons = [
        row.reason,
        row.ai_strategy_name,
        row.risk_reason,
        row.rebalance_reason,
    ].filter(Boolean);
    return {
        symbol: row.symbol || row.ticker || "-",
        name: row.name || row.symbol || row.ticker || "-",
        action: action in actionLabel ? action : "hold",
        qty,
        price,
        reason: reasons.join(" / ") || row.reason || "",
        source: row.source || "ai_dashboard",
        confidence,
        expectedReturn: Number(row.expected_return || row.rt || 0),
        risk: row.risk_pass === false ? "주의" : "통과",
        model: row.model || row.source || "runtime_plan",
        factors: reasons.length ? reasons : ["실행 계획에서 생성된 후보입니다."],
    };
}

function renderDecisions() {
    const root = qs("decision-table");
    if (!root) return;
    const decisions = planRows().map(toDecision);
    setText("metric-candidates", `${decisions.filter((item) => item.action !== "hold").length}건`);
    if (!decisions.length) {
        root.innerHTML = `<div class="empty-message">실행 계획이 없습니다.</div>`;
        renderExplain(null);
        return;
    }
    root.innerHTML = "";
    decisions.forEach((item, index) => {
        const row = document.createElement("div");
        row.className = `decision-row ${index === 0 ? "selected" : ""}`;
        row.tabIndex = 0;
        const canQueue = ["buy", "sell"].includes(item.action) && item.qty > 0;
        row.innerHTML = `
            <div class="symbol">
                <strong>${escapeHtml(item.name)}</strong>
                <span>${escapeHtml(item.symbol)} · ${escapeHtml(item.model)}</span>
            </div>
            <span class="action-pill ${item.action}">${actionLabel[item.action]}</span>
            <strong>${item.qty ? `${item.qty.toLocaleString("ko-KR")}주` : "-"}</strong>
            <span>${formatCurrency(item.price)}</span>
            <span>신뢰도 ${Math.round(item.confidence * 100)}%</span>
            <span class="subtle">예상 ${item.expectedReturn > 0 ? "+" : ""}${formatPercent(item.expectedReturn)}</span>
            <button type="button" class="mini-button queue-decision" ${canQueue ? "" : "disabled"}
                data-symbol="${escapeHtml(item.symbol)}"
                data-name="${escapeHtml(item.name)}"
                data-action="${escapeHtml(item.action)}"
                data-qty="${item.qty}"
                data-price="${item.price}"
                data-reason="${escapeHtml(item.reason)}"
                data-source="${escapeHtml(item.source)}">
                ${item.action === "buy" ? "매수등록" : item.action === "sell" ? "매도등록" : "등록불가"}
            </button>
        `;
        const selectRow = () => {
            document.querySelectorAll(".decision-row").forEach((node) => node.classList.remove("selected"));
            row.classList.add("selected");
            renderExplain(item);
        };
        row.addEventListener("click", selectRow);
        row.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectRow();
            }
        });
        row.querySelector(".queue-decision")?.addEventListener("click", (event) => {
            event.stopPropagation();
            createApprovalFromDecision(event.currentTarget);
        }, { once: true });
        root.appendChild(row);
    });
    renderExplain(decisions[0]);
}

function renderExplain(item) {
    const root = qs("explain-card");
    if (!root) return;
    if (!item) {
        root.innerHTML = `<div class="empty-message">후보를 선택하면 판단 근거가 표시됩니다.</div>`;
        return;
    }
    const score = Math.round(item.confidence * 100);
    root.innerHTML = `
        <div class="score-ring" style="--score: ${score}%">
            <div>
                <strong>${score}</strong>
                <span>confidence</span>
            </div>
        </div>
        <div>
            <strong>${escapeHtml(item.name)} ${actionLabel[item.action]} 판단</strong>
            <p class="subtle">${escapeHtml(item.model)} · 리스크 ${escapeHtml(item.risk)} · 예상 수익률 ${item.expectedReturn > 0 ? "+" : ""}${formatPercent(item.expectedReturn)}</p>
        </div>
        <ul class="factor-list">
            ${item.factors.map((factor) => `<li>${escapeHtml(factor)}</li>`).join("")}
        </ul>
    `;
}

function renderRiskChecks() {
    const root = qs("risk-checks");
    if (!root) return;
    const balance = dashboardState.balance || {};
    const plan = dashboardState.plan || {};
    const health = dashboardState.health || {};
    const cashRatio = Number(balance.cash_ratio || 0) * 100;
    const stockRatio = Number(balance.stock_ratio || 0) * 100;
    const pending = dashboardState.approvals.filter((item) => item.status === "pending").length;
    const checks = [
        ["현금 버퍼", `현재 ${formatPercent(cashRatio)}`, cashRatio, cashRatio >= 15 ? "pass" : "watch"],
        ["주식 노출", `평가금 ${formatCurrency(balance.stock_eval)}`, stockRatio, stockRatio <= 80 ? "pass" : "watch"],
        ["일일 손실 중지", plan.daily_loss_halt ? "중지 조건 활성" : "정상", plan.daily_loss_halt ? 100 : 0, plan.daily_loss_halt ? "watch" : "pass"],
        ["승인 대기", `${pending}건`, Math.min(100, pending * 20), pending ? "watch" : "pass"],
        ["API 상태", `오류 ${Number(health.circuit_breaker?.fail_count || 0)}건`, Number(health.circuit_breaker?.fail_count || 0) * 20, health.circuit_breaker?.open ? "watch" : "pass"],
    ];
    root.innerHTML = checks.map(([name, detail, value, status]) => `
        <div class="risk-check">
            <div>
                <strong>${escapeHtml(name)}</strong>
                <span>${escapeHtml(detail)}</span>
            </div>
            <div class="bar"><i style="width: ${Math.max(Number(value), 4)}%"></i></div>
            <em class="risk-status ${status}">${status === "pass" ? "통과" : "주의"}</em>
        </div>
    `).join("");
}

function renderApprovals() {
    const root = qs("approval-list");
    if (!root) return;
    const rows = dashboardState.approvals;
    const pending = rows.filter((item) => item.status === "pending").length;
    setText("metric-pending", `승인 대기 ${pending}건`);
    if (!rows.length) {
        root.innerHTML = `<div class="empty-message">승인 대기 주문이 없습니다.</div>`;
        return;
    }
    root.innerHTML = rows.slice(0, 8).map((item) => {
        const action = String(item.action || "").toLowerCase();
        const disabled = item.status !== "pending" ? "disabled" : "";
        return `
            <div class="approval-row">
                <strong>${escapeHtml(item.name || item.symbol)}</strong>
                <span class="action-pill ${action === "buy" ? "buy" : "sell"}">${actionLabel[action] || action}</span>
                <span>${Number(item.qty || 0).toLocaleString("ko-KR")}주</span>
                <span class="subtle">${escapeHtml(item.status || "-")}</span>
                <span class="approval-actions">
                    <button type="button" class="mini-button" data-approval-action="approve" data-id="${item.id}" ${disabled}>승인</button>
                    <button type="button" class="mini-button" data-approval-action="reject" data-id="${item.id}" ${disabled}>거절</button>
                </span>
            </div>
        `;
    }).join("");
    root.querySelectorAll("[data-approval-action]").forEach((button) => {
        button.addEventListener("click", () => updateApproval(button.dataset.id, button.dataset.approvalAction), { once: true });
    });
}

function renderAudits() {
    const root = qs("audit-list");
    if (!root) return;
    const now = new Date().toLocaleTimeString("ko-KR", { hour12: false });
    const plan = dashboardState.plan || {};
    const events = [
        `${now} 계좌 평가금 ${formatCurrency(dashboardState.balance?.total_eval)} 로드`,
        `${now} 실행 계획 ${planRows().length}건 생성`,
        `${now} 후보 스캔 ${Number(plan.scanned || 0).toLocaleString("ko-KR")}건`,
        `${now} 승인 대기 ${dashboardState.approvals.filter((item) => item.status === "pending").length}건`,
    ];
    if (plan.scan_error) events.push(`${now} 스캔 경고: ${plan.scan_error}`);
    root.innerHTML = events.map((event) => `<li>${escapeHtml(event)}</li>`).join("");
}

function renderChart() {
    const ctx = qs("performance-chart");
    if (!ctx || !window.Chart) return;
    if (dashboardState.chart) dashboardState.chart.destroy();
    const holdings = dashboardState.balance?.holdings || [];
    const labels = holdings.length ? holdings.map((item) => item.name || item.symbol) : ["현금"];
    const pnlData = holdings.length ? holdings.map((item) => Number(item.rt || 0)) : [0];
    dashboardState.chart = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: "보유 수익률",
                data: pnlData,
                borderColor: "#22c55e",
                backgroundColor: pnlData.map((value) => value >= 0 ? "rgba(34, 197, 94, 0.35)" : "rgba(239, 68, 68, 0.35)"),
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: "#c5d1df" } } },
            scales: {
                x: { ticks: { color: "#96a4b6" }, grid: { color: "rgba(255,255,255,0.05)" } },
                y: { ticks: { color: "#96a4b6", callback: (value) => `${value}%` }, grid: { color: "rgba(255,255,255,0.05)" } },
            },
        },
    });
    const avg = pnlData.reduce((sum, value) => sum + value, 0) / (pnlData.length || 1);
    setText("paper-return", `${avg >= 0 ? "+" : ""}${formatPercent(avg)}`);
    setText("paper-return-detail", "현재 보유 평균 수익률");
}

function renderAll() {
    renderHealth();
    renderBalance();
    renderDecisions();
    renderRiskChecks();
    renderApprovals();
    renderAudits();
    renderChart();
}

async function refreshDashboard() {
    const results = await Promise.allSettled([
        fetchJson(endpoints.health),
        fetchJson(endpoints.balance),
        fetchJson(endpoints.executionPlan, { timeoutMs: 35000 }),
        fetchJson(endpoints.approvals),
    ]);
    if (results[0].status === "fulfilled") dashboardState.health = results[0].value;
    if (results[1].status === "fulfilled") dashboardState.balance = results[1].value;
    if (results[2].status === "fulfilled") dashboardState.plan = results[2].value;
    if (results[3].status === "fulfilled") dashboardState.approvals = results[3].value.approvals || [];

    const errors = results.filter((item) => item.status === "rejected").map((item) => item.reason.message);
    renderAll();
    if (errors.length) {
        const root = qs("audit-list");
        if (root) root.insertAdjacentHTML("afterbegin", `<li>일부 API 로드 실패: ${escapeHtml(errors[0])}</li>`);
    }
}

async function updateApproval(id, action) {
    const url = action === "approve" ? endpoints.approve(id) : endpoints.reject(id);
    await fetchJson(url, { method: "POST", body: "{}" });
    await refreshDashboard();
}

async function createApprovalFromDecision(button) {
    const action = button.dataset.action;
    const payload = {
        symbol: button.dataset.symbol,
        name: button.dataset.name,
        action,
        qty: Number(button.dataset.qty || 0),
        price: Number(button.dataset.price || 0),
        reason: button.dataset.reason || "",
        source: button.dataset.source || "ai_dashboard",
    };
    if (!["buy", "sell"].includes(payload.action) || payload.qty <= 0) {
        return;
    }
    button.disabled = true;
    button.textContent = "등록중";
    try {
        const result = await fetchJson("/api/approvals", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        button.textContent = result.auto_approved ? "자동승인" : "등록완료";
        await refreshDashboard();
    } catch (error) {
        button.disabled = false;
        button.textContent = action === "buy" ? "매수등록" : "매도등록";
        const root = qs("audit-list");
        if (root) root.insertAdjacentHTML("afterbegin", `<li>승인 등록 실패: ${escapeHtml(error.message)}</li>`);
    }
}

async function createManualBuy(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const message = qs("manual-buy-message");
    const submit = form.querySelector("button[type='submit']");
    const formData = new FormData(form);
    const symbol = String(formData.get("symbol") || "").trim();
    const name = String(formData.get("name") || "").trim() || symbol;
    const qty = Number(formData.get("qty") || 0);
    const price = Number(formData.get("price") || 0);

    if (!/^\d{6}$/.test(symbol)) {
        if (message) {
            message.className = "form-message error";
            message.textContent = "종목코드는 6자리 숫자로 입력하세요.";
        }
        return;
    }
    if (qty <= 0) {
        if (message) {
            message.className = "form-message error";
            message.textContent = "수량은 1 이상이어야 합니다.";
        }
        return;
    }

    if (submit) submit.disabled = true;
    if (message) {
        message.className = "form-message";
        message.textContent = "매수 승인 대기 등록 중...";
    }
    try {
        const result = await fetchJson("/api/approvals", {
            method: "POST",
            body: JSON.stringify({
                symbol,
                name,
                action: "buy",
                qty,
                price,
                reason: "manual buy from AI dashboard",
                source: "ai_dashboard_manual_buy",
            }),
        });
        if (message) {
            message.className = "form-message ok";
            message.textContent = result.auto_approved ? "자동승인 처리되었습니다." : "매수 주문을 승인 대기에 등록했습니다.";
        }
        await refreshDashboard();
    } catch (error) {
        if (message) {
            message.className = "form-message error";
            message.textContent = `등록 실패: ${error.message}`;
        }
    } finally {
        if (submit) submit.disabled = false;
    }
}

async function toggleMode(button) {
    const key = button.dataset.modeKey;
    if (!key) return;
    const enabled = !(button.dataset.enabled === "true");
    button.disabled = true;
    try {
        await fetchJson(endpoints.orderMode, {
            method: "POST",
            body: JSON.stringify({ key, enabled }),
        });
        await refreshDashboard();
    } finally {
        button.disabled = false;
    }
}

async function toggleAutoApproval() {
    const button = qs("toggle-auto-approval");
    const enabled = !(button?.dataset.enabled === "true");
    if (button) button.disabled = true;
    try {
        await fetchJson(endpoints.autoApproval, {
            method: "POST",
            body: JSON.stringify({ enabled }),
        });
        await refreshDashboard();
    } finally {
        if (button) button.disabled = false;
    }
}

async function toggleKillSwitch() {
    const button = qs("btn-kill-switch");
    const active = button?.dataset.active === "true";
    if (button) button.disabled = true;
    try {
        await fetchJson(active ? endpoints.unkill : endpoints.kill, { method: "POST", body: "{}" });
        await refreshDashboard();
    } finally {
        if (button) button.disabled = false;
    }
}

function bindControls() {
    qs("btn-refresh")?.addEventListener("click", refreshDashboard);
    qs("btn-kill-switch")?.addEventListener("click", toggleKillSwitch);
    document.querySelectorAll("[data-mode-key]").forEach((button) => {
        button.addEventListener("click", () => toggleMode(button));
    });
    qs("toggle-auto-approval")?.addEventListener("click", toggleAutoApproval);
    qs("manual-buy-form")?.addEventListener("submit", createManualBuy);
}

iconize();
bindControls();
refreshDashboard();
setInterval(refreshDashboard, 30000);
