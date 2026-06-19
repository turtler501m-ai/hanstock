(function () {
    const state = {
        status: null,
        latest: null,
        history: [],
        themes: [],
        schedule: null,
        scheduleHistory: [],
        activeTab: 'summary',
    };

    function $(id) {
        return document.getElementById(id);
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    async function fetchJson(url, options) {
        const res = await fetch(url, options || {});
        const text = await res.text();
        let data = {};
        if (text) {
            try {
                data = JSON.parse(text);
            } catch (err) {
                throw new Error(text.slice(0, 300));
            }
        }
        if (!res.ok) {
            const detail = data.detail || data.message || res.statusText;
            throw new Error(detail);
        }
        return data;
    }

    function renderStatusCards() {
        const status = state.status || {};
        const items = [
            ['상태', status.state || '-'],
            ['최신 날짜', status.latest_date || '-'],
            ['시장 분위기', status.market_mood || '-'],
            ['후보 수', status.candidate_count || 0],
            ['내러티브 수', status.narrative_count || 0],
            ['테마 수', status.theme_count || 0],
            ['미매칭', status.unmatched_count || 0],
            ['승인 기준', status.approval_score_min || 75],
        ];
        $('narrative-status-grid').innerHTML = items.map(function (item) {
            return '<div class="narrative-stat"><span>' + escapeHtml(item[0]) + '</span><strong>' + escapeHtml(item[1]) + '</strong></div>';
        }).join('');
    }

    function renderSummary() {
        const status = state.status || {};
        const safety = status.safety || {};
        const badge = $('narrative-state-badge');
        badge.className = 'narrative-badge ' + escapeHtml(status.state || '');
        badge.textContent = status.state || '-';
        const rows = [
            ['전략 ID', status.strategy_id],
            ['오늘 기준일', status.today],
            ['최신 내러티브 날짜', status.latest_date],
            ['시장 분위기 점수', status.mood_score],
            ['후보 저장 파일', status.latest_result_path],
            ['히스토리 파일', status.history_path],
            ['테마 매핑 파일', status.theme_map_path],
            ['DRY_RUN', safety.dry_run],
            ['TRADING_ENV', safety.trading_env],
            ['REQUIRE_APPROVAL', safety.require_approval],
            ['ONLINE_ACCESS_BLOCKED', safety.online_access_blocked],
        ];
        $('narrative-summary-body').innerHTML = rows.map(function (row) {
            return '<tr><th>' + escapeHtml(row[0]) + '</th><td>' + escapeHtml(row[1] == null ? '-' : row[1]) + '</td></tr>';
        }).join('');
        const errors = status.errors || [];
        $('narrative-errors').textContent = errors.length ? errors.join('\n') : '오류 없음';
    }

    function tagList(values) {
        const list = Array.isArray(values) ? values : [];
        if (!list.length) return '<span class="narrative-muted">-</span>';
        return '<div class="narrative-tags">' + list.map(function (value) {
            return '<span class="narrative-tag">' + escapeHtml(value) + '</span>';
        }).join('') + '</div>';
    }

    function renderSignals() {
        const latest = state.latest || {};
        const signals = latest.signals || [];
        $('narrative-signal-count').textContent = signals.length + '개 후보';
        if (!signals.length) {
            $('narrative-signals-body').innerHTML = '<tr><td colspan="7" class="narrative-muted">표시할 시그널이 없습니다.</td></tr>';
            return;
        }
        const fresh = (latest.status || {}).state === 'fresh';
        $('narrative-signals-body').innerHTML = signals.map(function (signal, idx) {
            const score = Number(signal.final_score || signal.score || 0);
            const price = Number(signal.current_price || signal.price || 0);
            const disabled = !fresh || score < 75 || price <= 0 ? ' disabled' : '';
            const title = !fresh
                ? '최신 내러티브 데이터가 아닙니다'
                : (score < 75 ? '승인 기준 점수 미만입니다' : (price <= 0 ? '가격 조회 후 승인요청이 가능합니다' : '승인 대기열에 추가'));
            return '<tr>'
                + '<td>' + (idx + 1) + '</td>'
                + '<td><strong>' + escapeHtml(signal.name || signal.ticker) + '</strong><br><span class="narrative-muted">' + escapeHtml(signal.ticker) + '</span></td>'
                + '<td><span class="narrative-score">' + escapeHtml(score.toFixed(1)) + '</span></td>'
                + '<td>' + tagList(signal.themes) + '</td>'
                + '<td><div class="narrative-reasons">' + escapeHtml((signal.reasons || []).join('\n')) + '</div></td>'
                + '<td><div class="narrative-order-inputs">'
                + '<input class="narrative-price" type="number" min="1" step="1" inputmode="numeric" value="' + (price > 0 ? escapeHtml(price) : '') + '" placeholder="지정가">'
                + '<input class="narrative-qty" type="number" min="1" step="1" inputmode="numeric" value="1" placeholder="수량">'
                + '</div></td>'
                + '<td><button type="button" class="button-ghost compact-button narrative-approval" data-ticker="' + escapeHtml(signal.ticker) + '" data-name="' + escapeHtml(signal.name || signal.ticker) + '" data-score="' + escapeHtml(score) + '"' + disabled + ' title="' + escapeHtml(title) + '">승인요청</button></td>'
                + '</tr>';
        }).join('');
    }

    function renderHistory() {
        const rows = [];
        state.history.forEach(function (entry) {
            (entry.dominant_narratives || []).forEach(function (narrative) {
                rows.push({
                    date: entry.date,
                    theme: narrative.theme,
                    strength: narrative.strength,
                    sentiment: narrative.sentiment,
                    direction: narrative.direction,
                    affected_sectors: narrative.affected_sectors || [],
                    key_facts: narrative.key_facts || [],
                });
            });
        });
        $('narrative-history-count').textContent = rows.length + '개';
        if (!rows.length) {
            $('narrative-history-body').innerHTML = '<tr><td colspan="7" class="narrative-muted">내러티브 이력이 없습니다.</td></tr>';
            return;
        }
        $('narrative-history-body').innerHTML = rows.map(function (row) {
            return '<tr>'
                + '<td>' + escapeHtml(row.date) + '</td>'
                + '<td>' + escapeHtml(row.theme) + '</td>'
                + '<td>' + escapeHtml(row.strength) + '</td>'
                + '<td>' + escapeHtml(row.sentiment) + '</td>'
                + '<td>' + escapeHtml(row.direction) + '</td>'
                + '<td>' + tagList(row.affected_sectors) + '</td>'
                + '<td>' + escapeHtml(row.key_facts.join(', ')) + '</td>'
                + '</tr>';
        }).join('');
    }

    function renderThemes() {
        const themes = state.themes || [];
        if (!themes.length) {
            $('narrative-theme-body').innerHTML = '<tr><td colspan="3" class="narrative-muted">테마 매핑이 없습니다.</td></tr>';
            return;
        }
        $('narrative-theme-body').innerHTML = themes.map(function (theme) {
            const stocks = (theme.stocks || []).map(function (stock) {
                return (stock.name || stock.ticker) + ' ' + stock.ticker;
            });
            return '<tr>'
                + '<td><strong>' + escapeHtml(theme.theme) + '</strong></td>'
                + '<td>' + escapeHtml(theme.stock_count) + '</td>'
                + '<td>' + tagList(stocks) + '</td>'
                + '</tr>';
        }).join('');
    }

    function renderSchedule() {
        const schedule = state.schedule || {};
        const status = state.status || {};
        if ($('narrative-schedule-enabled')) {
            $('narrative-schedule-enabled').checked = !!schedule.enabled;
            $('narrative-schedule-interval').value = schedule.interval_minutes || 30;
            $('narrative-schedule-start').value = schedule.start_hm || '0900';
            $('narrative-schedule-end').value = schedule.end_hm || '1530';
            $('narrative-schedule-weekdays').value = schedule.weekdays || '1-5';
            $('narrative-schedule-mode').value = schedule.mode || 'execute';
        }
        const rows = state.scheduleHistory || [];
        const body = $('narrative-schedule-history-body');
        const summaryBox = $('narrative-schedule-summary');
        if (summaryBox) {
            if (status.state === 'missing') {
                summaryBox.textContent = '내러티브 이력 파일이 없어 스케줄은 실행됐지만 후보가 생성되지 않았습니다. 내러티브 이력 탭에서 오늘 날짜 narrative_history JSON을 저장한 뒤 다시 실행하세요.';
            } else if (!rows.length) {
                summaryBox.textContent = '최근 스케줄 실행 결과가 없습니다.';
            } else {
                const latest = rows[0];
                const summary = latest.summary || {};
                const top = (summary.top_signals || []).map(function (item) {
                    return (item.name || item.ticker || '-') + ' ' + (item.score == null ? '' : item.score);
                }).join(', ');
                summaryBox.textContent = '최근 실행 ' + (latest.recorded_at || '-')
                    + ' | 상태 ' + (summary.state || '-')
                    + ' | 후보 ' + (summary.candidate_count || 0) + '개'
                    + ' | 저장 ' + (summary.saved_count || 0) + '개'
                    + ' | 상위 ' + (top || '-');
            }
        }
        if (!body) return;
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="6" class="narrative-muted">스케줄 실행 이력이 없습니다.</td></tr>';
            return;
        }
        body.innerHTML = rows.map(function (row) {
            const summary = row.summary || {};
            const top = (summary.top_signals || []).map(function (item) {
                return (item.name || item.ticker || '-') + ' ' + (item.score == null ? '' : item.score);
            }).join(', ');
            return '<tr>'
                + '<td>' + escapeHtml(row.recorded_at || '-') + '</td>'
                + '<td>' + escapeHtml(row.mode || '-') + '</td>'
                + '<td>' + escapeHtml(summary.state || (row.ok ? 'ok' : 'error')) + '</td>'
                + '<td>' + escapeHtml(summary.candidate_count || 0) + '</td>'
                + '<td>' + escapeHtml(summary.saved_count || 0) + '</td>'
                + '<td>' + escapeHtml(top || '-') + '</td>'
                + '</tr>';
        }).join('');
    }

    function loadEditorFromState() {
        $('narrative-history-editor').value = JSON.stringify(state.history || [], null, 2);
        $('narrative-editor-status').textContent = '현재 이력을 편집기에 불러왔습니다.';
    }

    async function saveHistoryFromEditor() {
        let parsed;
        try {
            parsed = JSON.parse($('narrative-history-editor').value || '[]');
        } catch (err) {
            $('narrative-editor-status').textContent = 'JSON 파싱 실패: ' + err.message;
            return;
        }
        if (!Array.isArray(parsed)) {
            $('narrative-editor-status').textContent = '최상위 JSON은 배열이어야 합니다.';
            return;
        }
        try {
            const result = await fetchJson('/api/narrative-momentum/history', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({history: parsed}),
            });
            $('narrative-editor-status').textContent = result.count + '개 내러티브 날짜를 저장했습니다.';
            await loadAll();
        } catch (err) {
            $('narrative-editor-status').textContent = err.message || String(err);
        }
    }

    function renderAll() {
        renderStatusCards();
        renderSummary();
        renderSignals();
        renderHistory();
        renderThemes();
        renderSchedule();
    }

    async function loadAll() {
        try {
            const results = await Promise.all([
                fetchJson('/api/narrative-momentum/status'),
                fetchJson('/api/narrative-momentum/latest'),
                fetchJson('/api/narrative-momentum/history'),
                fetchJson('/api/narrative-momentum/theme-map'),
                fetchJson('/api/narrative-momentum/schedule'),
                fetchJson('/api/narrative-momentum/schedule-history'),
            ]);
            state.status = results[0];
            state.latest = results[1];
            state.history = results[2].history || [];
            state.themes = results[3].themes || [];
            state.schedule = (results[4] || {}).schedule || {};
            state.scheduleHistory = (results[5] || {}).history || [];
            renderAll();
        } catch (err) {
            $('narrative-errors').textContent = err.message || String(err);
        }
    }

    async function runScan(saveCandidates) {
        const result = await fetchJson('/api/narrative-momentum/scan', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({save_candidates: !!saveCandidates}),
        });
        state.latest = {
            status: result.status,
            signals: result.signals,
            unmatched: [],
        };
        await loadAll();
    }

    async function saveSchedule() {
        const payload = {
            enabled: $('narrative-schedule-enabled').checked,
            interval_minutes: Number($('narrative-schedule-interval').value || 30),
            start_hm: $('narrative-schedule-start').value || '0900',
            end_hm: $('narrative-schedule-end').value || '1530',
            weekdays: $('narrative-schedule-weekdays').value || '1-5',
            mode: $('narrative-schedule-mode').value || 'execute',
            auto_approve: false,
        };
        const result = await fetchJson('/api/narrative-momentum/schedule', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
        });
        state.schedule = result.schedule || {};
        $('narrative-schedule-status').textContent = '스케줄을 저장했습니다.';
        renderSchedule();
    }

    async function runScheduledNow() {
        const saveCandidates = ($('narrative-schedule-mode')?.value || 'execute') !== 'analysis_only';
        $('narrative-schedule-status').textContent = '실행 중...';
        const result = await fetchJson('/api/narrative-momentum/run-scheduled', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({save_candidates: saveCandidates}),
        });
        $('narrative-schedule-status').textContent = '완료: 후보 ' + (result.total_scanned || 0) + '개, 저장 ' + (result.saved_count || 0) + '개';
        await loadAll();
    }

    async function queueApproval(button) {
        const row = button.closest('tr');
        const ticker = button.dataset.ticker;
        const name = button.dataset.name;
        const score = Number(button.dataset.score || 0);
        const price = Number(row.querySelector('.narrative-price')?.value || 0);
        const qty = Number(row.querySelector('.narrative-qty')?.value || 0);
        if (price <= 0 || qty <= 0) {
            alert('지정가와 수량을 먼저 입력하세요.');
            return;
        }
        const reason = '내러티브 모멘텀 ' + score.toFixed(1) + '점: ' + name + ' ' + ticker;
        button.disabled = true;
        try {
            const result = await fetchJson('/api/narrative-momentum/queue-approval', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ticker, name, score, qty, price, reason}),
            });
            button.textContent = '대기 #' + result.id;
        } catch (err) {
            button.disabled = false;
            alert(err.message || String(err));
        }
    }

    function activateTab(tabName) {
        state.activeTab = tabName;
        document.querySelectorAll('.narrative-tab').forEach(function (btn) {
            const active = btn.dataset.tab === tabName;
            btn.classList.toggle('active', active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        document.querySelectorAll('.narrative-panel').forEach(function (panel) {
            const active = panel.id === 'narrative-tab-' + tabName;
            panel.classList.toggle('active', active);
            panel.hidden = !active;
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.narrative-tab').forEach(function (btn) {
            btn.addEventListener('click', function () {
                activateTab(btn.dataset.tab);
            });
        });
        $('btn-narrative-refresh').addEventListener('click', loadAll);
        $('btn-narrative-scan').addEventListener('click', function () { runScan(false).catch(alert); });
        $('btn-narrative-save-scan').addEventListener('click', function () { runScan(true).catch(alert); });
        $('btn-narrative-save-schedule').addEventListener('click', function () { saveSchedule().catch(alert); });
        $('btn-narrative-run-scheduled').addEventListener('click', function () { runScheduledNow().catch(alert); });
        $('btn-narrative-theme-reload').addEventListener('click', function () {
            fetchJson('/api/narrative-momentum/theme-map/reload', {method: 'POST'}).then(function (data) {
                state.themes = data.themes || [];
                renderThemes();
            }).catch(alert);
        });
        $('btn-narrative-load-editor').addEventListener('click', loadEditorFromState);
        $('btn-narrative-save-history').addEventListener('click', saveHistoryFromEditor);
        document.body.addEventListener('click', function (event) {
            const button = event.target.closest('.narrative-approval');
            if (button) queueApproval(button);
        });
        document.body.addEventListener('input', function (event) {
            if (!event.target.classList.contains('narrative-price') && !event.target.classList.contains('narrative-qty')) return;
            const row = event.target.closest('tr');
            const button = row && row.querySelector('.narrative-approval');
            if (!button) return;
            const latest = state.latest || {};
            const fresh = (latest.status || {}).state === 'fresh';
            const score = Number(button.dataset.score || 0);
            const price = Number(row.querySelector('.narrative-price')?.value || 0);
            const qty = Number(row.querySelector('.narrative-qty')?.value || 0);
            button.disabled = !(fresh && score >= 75 && price > 0 && qty > 0);
        });
        loadAll();
    });
})();
