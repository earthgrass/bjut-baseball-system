/**
 * POWER ARENA — 批量录入整场比赛
 * ============================================================
 * 粘贴 box score → 解析 → 实时预览 → 整场提交。
 *
 * 后端接口 POST /api/game_records/batch（Phase R1 已就绪，全有或全无）。
 * 本文件**不改**后端语义，只负责：
 *   1. 把 box score 文本解析成结构化记录
 *   2. 姓名 → player_id 映射（未知姓名 / 非投手录投球 → 标红）
 *   3. 业务不变量预检（规范 §49：AB >= H、H >= 2B+3B+HR、数值非负）
 *   4. 提交前把每一行摊在预览表里，让人眼确认
 *
 * 局数（IP）口径：按 box score 上印的字面数字入库，与既有 230 条记录一致
 * （中文记法 .1 = 1/3 局）。单位口径统一留给指标引擎阶段，本轮不换算。
 */
(function () {
    'use strict';

    // ── 列定义 ──────────────────────────────────────────────────
    // required 前 7 列固定顺序；optional 是尾部可选列，按位置对应。
    // key 用的是后端 /api/game_records/batch 接受的字段名。

    var BATTING_REQUIRED = [
        { key: 'at_bats', label: 'AB', type: 'int' },
        { key: 'runs', label: 'R', type: 'int' },
        { key: 'hits', label: 'H', type: 'int' },
        { key: 'rbi', label: 'RBI', type: 'int' },
        { key: 'walks', label: 'BB', type: 'int' },
        { key: 'strikeouts', label: 'SO', type: 'int' }
    ];

    var BATTING_OPTIONAL = [
        { key: 'doubles', label: '2B' },
        { key: 'triples', label: '3B' },
        { key: 'home_runs_game', label: 'HR' },
        { key: 'hit_by_pitch', label: 'HBP' },
        { key: 'stolen_bases_game', label: 'SB' },
        { key: 'caught_stealing', label: 'CS' },
        { key: 'sacrifice_flys', label: 'SF' },
        { key: 'sacrifice_hits', label: 'SH' }
    ];

    var PITCHING_REQUIRED = [
        { key: 'innings_pitched', label: 'IP', type: 'float' },
        { key: 'hits_allowed', label: 'H', type: 'int' },
        { key: 'runs_allowed', label: 'R', type: 'int' },
        { key: 'earned_runs', label: 'ER', type: 'int' },
        { key: 'walks_allowed', label: 'BB', type: 'int' },
        { key: 'strikeouts', label: 'SO', type: 'int' }
    ];

    var PITCHING_OPTIONAL = [
        { key: 'home_runs_allowed', label: 'HR' },
        { key: 'pitches', label: 'P' },
        { key: 'strikes', label: 'ST' },
        { key: 'batters_faced', label: 'BF' },
        { key: 'wild_pitches', label: 'WP' }
    ];

    // 表头识别：这些 token 出现在第 2 列时，整行当作表头跳过
    var HEADER_TOKENS = [
        'ab', 'r', 'h', 'rbi', 'bb', 'so', 'ip', 'er', 'hr', '2b', '3b',
        'hbp', 'sb', 'cs', 'sf', 'sh', 'p', 'st', 'bf', 'wp',
        'player', 'name', 'batting', 'pitching',
        '姓名', '名字', '球员', '打数', '安打', '得分', '打点', '保送', '三振',
        '局数', '自责分', '本垒打', '二垒安打', '三垒安打', '打击', '投球'
    ];

    // 合计行：直接跳过，不当成球员（box score 里常见）
    var TOTAL_TOKENS = ['合计', '总计', '小计', 'total', 'sum', 'tpa'];

    var state = {
        playersByName: {},   // name → player | { ambiguous: true, players: [...] }
        playersLoaded: false,
        batting: { rows: [] },
        pitching: { rows: [] }
    };

    // ── 工具 ────────────────────────────────────────────────────

    function isHeaderToken(token) {
        return HEADER_TOKENS.indexOf(String(token).toLowerCase()) !== -1;
    }

    function isTotalToken(token) {
        return TOTAL_TOKENS.indexOf(String(token).toLowerCase()) !== -1;
    }

    function isIntegerToken(token) {
        return /^-?\d+$/.test(token);
    }

    function isNumberToken(token) {
        return /^-?\d+(\.\d+)?$/.test(token);
    }

    function $(id) {
        return document.getElementById(id);
    }

    function escapeHtml(value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // ── 姓名 → 球员 ─────────────────────────────────────────────

    function buildPlayerIndex(players) {
        var index = {};
        players.forEach(function (player) {
            var name = (player.name || '').trim();
            if (!name) return;
            if (!index[name]) {
                index[name] = player;
            } else if (index[name].ambiguous) {
                index[name].players.push(player);
            } else {
                index[name] = { ambiguous: true, players: [index[name], player] };
            }
        });
        return index;
    }

    function resolvePlayer(name) {
        var entry = state.playersByName[name];
        if (!entry) {
            return { error: '找不到球员「' + name + '」' };
        }
        if (entry.ambiguous) {
            return { error: '有 ' + entry.players.length + ' 名球员都叫「' + name + '」，无法确定用哪一个' };
        }
        return { player: entry };
    }

    // ── 解析 ────────────────────────────────────────────────────

    function parseLines(text, required, optional, isPitching) {
        var rows = [];
        var lines = String(text || '').split(/\r?\n/);

        lines.forEach(function (rawLine, index) {
            var line = rawLine.trim();
            var lineNo = index + 1;

            if (!line) return;                       // 空行
            if (line.charAt(0) === '#') return;      // 注释

            var cols = line.split(/\s+/);

            // 合计行
            if (cols.length >= 1 && isTotalToken(cols[0])) return;

            // 表头行：第 2 列不是数字
            if (cols.length < 2 || !isNumberToken(cols[1])) {
                var headish = cols.slice(0, Math.min(cols.length, 4)).some(isHeaderToken);
                if (headish) return;                // 表头，静默跳过
                rows.push({
                    ok: false,
                    lineNo: lineNo,
                    name: cols[0] || '(空)',
                    error: cols.length < 2
                        ? '只有姓名，缺少数据列'
                        : '第 2 列应该是数字，实际是「' + cols[1] + '」'
                });
                return;
            }

            var name = cols[0];
            var values = cols.slice(1);

            if (values.length < required.length) {
                rows.push({
                    ok: false, lineNo: lineNo, name: name,
                    error: '数据列不足：需要 ' + required.length + ' 列，实际 ' + values.length + ' 列'
                });
                return;
            }
            if (values.length > required.length + optional.length) {
                rows.push({
                    ok: false, lineNo: lineNo, name: name,
                    error: '数据列过多：最多 ' + (required.length + optional.length) + ' 列，实际 ' + values.length + ' 列'
                });
                return;
            }

            // 必填列
            var row = { ok: true, lineNo: lineNo, name: name, values: {}, extra: {} };
            for (var i = 0; i < required.length; i++) {
                var spec = required[i];
                var token = values[i];
                var valid = spec.type === 'int' ? isIntegerToken(token) : isNumberToken(token);
                if (!valid) {
                    row.ok = false;
                    row.error = spec.label + ' 应该是' + (spec.type === 'int' ? '整数' : '数字') + '，实际是「' + token + '」';
                    break;
                }
                var num = parseFloat(token);
                if (num < 0) {
                    row.ok = false;
                    row.error = spec.label + ' 不能是负数';
                    break;
                }
                row.values[spec.key] = spec.type === 'int' ? parseInt(token, 10) : num;
            }
            if (!row.ok) {
                rows.push(row);
                return;
            }

            // 可选列
            for (var j = 0; j < optional.length; j++) {
                if (values.length <= required.length + j) break;
                var opt = optional[j];
                var optToken = values[required.length + j];
                if (!isIntegerToken(optToken)) {
                    row.ok = false;
                    row.error = opt.label + ' 应该是整数，实际是「' + optToken + '」';
                    break;
                }
                var optNum = parseInt(optToken, 10);
                if (optNum < 0) {
                    row.ok = false;
                    row.error = opt.label + ' 不能是负数';
                    break;
                }
                row.extra[opt.key] = optNum;
                row.extra.__labels = row.extra.__labels || [];
                row.extra.__labels.push({ key: opt.key, label: opt.label, value: optNum });
            }
            if (!row.ok) {
                rows.push(row);
                return;
            }

            // 姓名映射
            var resolved = resolvePlayer(name);
            if (resolved.error) {
                row.ok = false;
                row.error = resolved.error;
                rows.push(row);
                return;
            }
            var player = resolved.player;
            if (isPitching && !player.is_pitcher) {
                row.ok = false;
                row.error = '「' + name + '」不是投手，不能录投球记录';
                rows.push(row);
                return;
            }

            // 业务不变量（规范 §49）
            if (!isPitching) {
                var ab = row.values.at_bats;
                var h = row.values.hits;
                var extraBases = (row.extra.doubles || 0) + (row.extra.triples || 0) + (row.extra.home_runs_game || 0);
                if (h > ab) {
                    row.ok = false;
                    row.error = '安打 ' + h + ' 超过打数 ' + ab;
                    rows.push(row);
                    return;
                }
                if (h < extraBases) {
                    row.ok = false;
                    row.error = '安打 ' + h + ' 小于二/三/本垒打之和 ' + extraBases;
                    rows.push(row);
                    return;
                }
            }

            row.playerId = player.id;
            row.isPitcher = !!isPitching;
            rows.push(row);
        });

        return rows;
    }

    // ── 渲染预览 ────────────────────────────────────────────────

    function renderPreview(kind) {
        var isPitching = kind === 'pitching';
        var required = isPitching ? PITCHING_REQUIRED : BATTING_REQUIRED;
        var optional = isPitching ? PITCHING_OPTIONAL : BATTING_OPTIONAL;
        var rows = state[kind].rows;
        var tbody = $(isPitching ? 'pitchingPreview' : 'battingPreview');
        var summary = $(isPitching ? 'pitchingSummary' : 'battingSummary');

        tbody.innerHTML = '';

        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-gray-500 py-3">（还没有数据）</td></tr>';
            summary.textContent = '尚未解析';
            summary.className = 'text-sm text-gray-400';
            return;
        }

        var okCount = 0;
        var errorCount = 0;

        rows.forEach(function (row) {
            var tr = document.createElement('tr');
            tr.className = row.ok ? 'row-ok' : 'row-error';

            var cells = '';
            cells += '<td>' + escapeHtml(row.name) + '</td>';

            required.forEach(function (spec) {
                var value = row.values ? row.values[spec.key] : undefined;
                cells += '<td>' + (value === undefined ? '—' : escapeHtml(value)) + '</td>';
            });

            // 额外列
            var extraText = '—';
            if (row.extra && row.extra.__labels && row.extra.__labels.length) {
                extraText = row.extra.__labels.map(function (item) {
                    return escapeHtml(item.label) + '=' + escapeHtml(item.value);
                }).join(' ');
            }
            cells += '<td>' + extraText + '</td>';

            if (row.ok) {
                okCount++;
                cells += '<td class="row-msg-ok">✓ 第 ' + row.lineNo + ' 行</td>';
            } else {
                errorCount++;
                cells += '<td class="row-msg-error">第 ' + row.lineNo + ' 行：' + escapeHtml(row.error) + '</td>';
            }

            tr.innerHTML = cells;
            tbody.appendChild(tr);
        });

        summary.className = 'text-sm ' + (errorCount ? 'text-red-400' : 'text-green-400');
        summary.textContent = errorCount
            ? (okCount + ' 行可用，' + errorCount + ' 行有错')
            : (okCount + ' 行待写入');
    }

    // ── 状态与提交 ──────────────────────────────────────────────

    function reparse() {
        state.batting.rows = parseLines($('battingInput').value, BATTING_REQUIRED, BATTING_OPTIONAL, false);
        state.pitching.rows = parseLines($('pitchingInput').value, PITCHING_REQUIRED, PITCHING_OPTIONAL, true);
        renderPreview('batting');
        renderPreview('pitching');
        updateSubmitState();
    }

    function allRows() {
        return state.batting.rows.concat(state.pitching.rows);
    }

    function updateSubmitState() {
        var rows = allRows();
        var errors = rows.filter(function (row) { return !row.ok; });
        var okRows = rows.filter(function (row) { return row.ok; });
        var date = $('batchGameDate').value;
        var opponent = $('batchOpponent').value.trim();
        var btn = $('batchSubmitBtn');
        var hint = $('batchHint');

        if (!state.playersLoaded) {
            btn.disabled = true;
            hint.textContent = '正在加载球员名单……';
            return;
        }
        if (errors.length) {
            btn.disabled = true;
            hint.textContent = '有 ' + errors.length + ' 行有问题，请先修正标红的行（不会跳过，只会阻止提交）。';
            return;
        }
        if (!okRows.length) {
            btn.disabled = true;
            hint.textContent = '填好日期和对手后，把打击/投球数据粘贴进来即可提交。';
            return;
        }
        if (!date || !opponent) {
            btn.disabled = true;
            hint.textContent = '还差：' + (!date ? '比赛日期' : '') + (!date && !opponent ? ' 和 ' : '') + (!opponent ? '对手球队' : '');
            return;
        }

        btn.disabled = false;
        hint.textContent = '将写入 ' + okRows.length + ' 条比赛记录（' +
            state.batting.rows.filter(function (r) { return r.ok; }).length + ' 条打击 + ' +
            state.pitching.rows.filter(function (r) { return r.ok; }).length + ' 条投球）。';
    }

    function collectRecords() {
        var records = [];
        state.batting.rows.forEach(function (row) {
            if (!row.ok) return;
            var record = { player_id: row.playerId, is_pitching: false };
            Object.keys(row.values).forEach(function (key) { record[key] = row.values[key]; });
            Object.keys(row.extra).forEach(function (key) {
                if (key === '__labels') return;
                record[key] = row.extra[key];
            });
            records.push(record);
        });
        state.pitching.rows.forEach(function (row) {
            if (!row.ok) return;
            var record = { player_id: row.playerId, is_pitching: true };
            Object.keys(row.values).forEach(function (key) { record[key] = row.values[key]; });
            Object.keys(row.extra).forEach(function (key) {
                if (key === '__labels') return;
                record[key] = row.extra[key];
            });
            records.push(record);
        });
        return records;
    }

    async function submitBatch() {
        var date = $('batchGameDate').value;
        var opponent = $('batchOpponent').value.trim();
        var records = collectRecords();

        if (!date) { toast('请填写比赛日期', 'error'); return; }
        if (!opponent) { toast('请填写对手球队', 'error'); return; }
        if (!records.length) { toast('没有可写入的记录', 'error'); return; }

        var btn = $('batchSubmitBtn');
        btn.disabled = true;
        var originalText = btn.textContent;
        btn.textContent = '写入中……';

        try {
            var result = await api.post('/api/game_records/batch', {
                game_date: date,
                opponent: opponent,
                records: records
            });
            toast('已写入 ' + result.created + ' 条比赛记录', 'success');
            setTimeout(function () { window.location.href = '/game_stats'; }, 1200);
        } catch (error) {
            console.error('批量写入失败:', error);
            toast(error instanceof ApiError ? error.message : '网络错误，请稍后重试', 'error');
            btn.textContent = originalText;
            updateSubmitState();
        }
    }

    function resetBatchForm() {
        $('battingInput').value = '';
        $('pitchingInput').value = '';
        $('batchOpponent').value = '';
        reparse();
        toast('已清空', 'info');
    }

    // ── 加载 ────────────────────────────────────────────────────

    async function loadPlayers() {
        try {
            var players = await api.get('/api/players');
            state.playersByName = buildPlayerIndex(players || []);
            state.playersLoaded = true;
        } catch (error) {
            console.error('加载球员名单失败:', error);
            toast('加载球员名单失败，无法校验姓名', 'error');
        }
        updateSubmitState();
    }

    async function loadOpponents() {
        try {
            var opponents = await api.get('/api/matchup/opponents');
            var list = $('opponentsList');
            if (!list) return;
            list.innerHTML = '';
            (opponents || []).forEach(function (opponent) {
                var option = document.createElement('option');
                option.value = opponent;
                list.appendChild(option);
            });
        } catch (error) {
            console.error('加载对手列表失败:', error);
        }
    }

    // ── 启动 ────────────────────────────────────────────────────
    if (typeof document !== 'undefined') {
        document.addEventListener('DOMContentLoaded', function () {
            var today = new Date().toISOString().split('T')[0];
            $('batchGameDate').value = today;

            $('battingInput').addEventListener('input', reparse);
            $('pitchingInput').addEventListener('input', reparse);
            $('batchGameDate').addEventListener('change', updateSubmitState);
            $('batchOpponent').addEventListener('input', updateSubmitState);

            renderPreview('batting');
            renderPreview('pitching');
            updateSubmitState();

            loadPlayers();
            loadOpponents();
        });
    }

    // 暴露给模板里的 onclick
    if (typeof window !== 'undefined') {
        window.submitBatch = submitBatch;
        window.resetBatchForm = resetBatchForm;
    }

    // ── 供 node 单测直接调用纯逻辑（解析 / 姓名映射）────────────
    // 规范 §47 Level 1：parser 必须有单元测试。
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            state: state,
            BATTING_REQUIRED: BATTING_REQUIRED,
            BATTING_OPTIONAL: BATTING_OPTIONAL,
            PITCHING_REQUIRED: PITCHING_REQUIRED,
            PITCHING_OPTIONAL: PITCHING_OPTIONAL,
            parseLines: parseLines,
            buildPlayerIndex: buildPlayerIndex,
            isIntegerToken: isIntegerToken,
            isNumberToken: isNumberToken,
            setPlayers: function (players) {
                state.playersByName = buildPlayerIndex(players || []);
                state.playersLoaded = true;
            }
        };
    }
})();
