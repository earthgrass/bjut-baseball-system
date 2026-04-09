let playersData = [];
let opponentsData = [];
let matchupRecordCache = new Map();

document.addEventListener('DOMContentLoaded', async function() {
    await Promise.all([loadPlayers(), loadOpponents()]);
});

async function loadPlayers() {
    try {
        const response = await fetch('/api/players');
        playersData = await response.json();

        const playerSelect = document.getElementById('playerSelect');
        playerSelect.innerHTML = '<option value="">请选择球员...</option>';

        playersData.forEach(player => {
            const option = document.createElement('option');
            option.value = player.id;
            option.textContent = `${player.name} (#${player.jersey_number}) - ${player.primary_position || '未指定位置'}`;
            playerSelect.appendChild(option);
        });
    } catch (error) {
        console.error('加载球员数据失败:', error);
        showAlert('加载球员数据失败', 'error');
    }
}

async function loadOpponents() {
    try {
        const response = await fetch('/api/matchup/opponents');
        opponentsData = await response.json();

        const opponentSelect = document.getElementById('opponentSelect');
        opponentSelect.innerHTML = '<option value="">请选择对手...';

        opponentsData.forEach(opponent => {
            const option = document.createElement('option');
            option.value = opponent;
            option.textContent = opponent;
            opponentSelect.appendChild(option);
        });
    } catch (error) {
        console.error('加载对手数据失败:', error);
        showAlert('加载对手数据失败', 'error');
    }
}

function buildMatchupQuery() {
    const params = new URLSearchParams();
    const playerId = document.getElementById('playerSelect').value;
    const opponent = document.getElementById('opponentSelect').value;

    if (playerId) {
        params.set('player_id', playerId);
    }
    if (opponent) {
        params.set('opponent', opponent);
    }

    return params;
}

async function loadMatchupStats() {
    const params = buildMatchupQuery();

    if (![...params.keys()].length) {
        showAlert('请至少选择球员或对手中的一个筛选条件', 'warning');
        return;
    }

    try {
        const response = await fetch(`/api/matchup/search_records?${params.toString()}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || '加载筛选记录失败');
        }

        hideAllTeamRecords();
        displayQuerySummary(data);
        renderBattingTable(data.batting_records, {
            cardId: 'filteredBattingCard',
            tableBodyId: 'filteredBattingTableBody',
            emptyMessage: '当前筛选条件下没有打击记录'
        });
        renderPitchingTable(data.pitching_records, {
            cardId: 'filteredPitchingCard',
            tableBodyId: 'filteredPitchingTableBody',
            emptyMessage: '当前筛选条件下没有投球记录'
        });

        if ((!data.batting_records || data.batting_records.length === 0) &&
            (!data.pitching_records || data.pitching_records.length === 0)) {
            showAlert('没有找到符合条件的比赛记录', 'warning');
        }
    } catch (error) {
        console.error('加载对局数据失败:', error);
        showAlert(error.message || '加载对局数据失败', 'error');
        resetFilteredResults();
    }
}

function displayQuerySummary(data) {
    const summaryCard = document.getElementById('querySummaryCard');
    const summaryContent = document.getElementById('querySummaryContent');
    const battingSummary = data.batting_summary;
    const pitchingSummary = data.pitching_summary;

    const summaryParts = [
        `
        <div class="mb-6">
            <h4 class="text-white text-lg font-bold mb-2">${data.title}</h4>
            <p class="text-gray-400 text-sm">
                打击记录 <span class="text-arena-red font-bold">${data.batting_records.length}</span> 条，
                投球记录 <span class="text-arena-red font-bold">${data.pitching_records.length}</span> 条
            </p>
        </div>
        `
    ];

    if (battingSummary) {
        summaryParts.push(`
            <div class="mb-6">
                <h5 class="text-arena-red text-sm font-bold uppercase tracking-wider mb-4">打击汇总</h5>
                <div class="grid grid-cols-3 md:grid-cols-6 gap-3">
                    ${renderStatCard('场次', battingSummary.games)}
                    ${renderStatCard('打数', battingSummary.at_bats)}
                    ${renderStatCard('安打', battingSummary.hits)}
                    ${renderStatCard('打点', battingSummary.rbi)}
                    ${renderStatCard('本垒打', battingSummary.home_runs)}
                    ${renderStatCard('打击率', battingSummary.batting_average.toFixed(3), getAvgClass(battingSummary.batting_average))}
                </div>
            </div>
        `);
    }

    if (pitchingSummary) {
        summaryParts.push(`
            <div>
                <h5 class="text-arena-red text-sm font-bold uppercase tracking-wider mb-4">投球汇总</h5>
                <div class="grid grid-cols-3 md:grid-cols-6 gap-3">
                    ${renderStatCard('场次', pitchingSummary.games)}
                    ${renderStatCard('局数', pitchingSummary.innings_pitched.toFixed(1))}
                    ${renderStatCard('三振', pitchingSummary.strikeouts)}
                    ${renderStatCard('ERA', pitchingSummary.era.toFixed(2))}
                    ${renderStatCard('WHIP', pitchingSummary.whip.toFixed(2))}
                    ${renderStatCard('好球率', pitchingSummary.strike_percentage.toFixed(1) + '%')}
                </div>
            </div>
        `);
    }

    if (!battingSummary && !pitchingSummary) {
        summaryParts.push('<div class="text-gray-500 text-sm">当前筛选条件下没有实际录入的打击或投球数据。</div>');
    }

    summaryContent.innerHTML = summaryParts.join('');
    summaryCard.style.display = 'block';
}

function renderStatCard(label, value, valueClass = '') {
    return `
        <div class="bg-arena-surface/50 p-4 text-center" style="clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px)); border: 1px solid rgba(230, 0, 0, 0.1);">
            <div class="text-gray-500 text-xs uppercase tracking-wider mb-1">${label}</div>
            <div class="text-xl font-bold ${valueClass || 'text-white'}">${value}</div>
        </div>
    `;
}

function renderBattingTable(records, options) {
    const { cardId, tableBodyId, emptyMessage } = options;
    const card = document.getElementById(cardId);
    const tableBody = document.getElementById(tableBodyId);

    tableBody.innerHTML = '';

    if (!records || records.length === 0) {
        card.style.display = 'none';
        return;
    }

    records.forEach(record => {
        matchupRecordCache.set(record.id, {
            game_date: record.game_date,
            opponent: record.opponent,
            player_name: record.player_name
        });

        const row = document.createElement('tr');
        row.innerHTML = `
            <td><span class="font-semibold text-white">${record.player_name}</span></td>
            <td>${record.player_jersey}</td>
            <td>${record.game_date}</td>
            <td>${record.opponent}</td>
            <td>${record.at_bats}</td>
            <td>${record.hits}</td>
            <td>${record.runs}</td>
            <td>${record.rbi}</td>
            <td>${record.home_runs}</td>
            <td>${record.strikeouts}</td>
            <td>${record.walks}</td>
            <td>${record.stolen_bases}</td>
            <td><span class="${getAvgClass(record.batting_average)} font-bold">${record.batting_average.toFixed(3)}</span></td>
            <td>
                <button class="btn-primary text-white px-3 py-1 font-heading text-xs font-bold" onclick="deleteGameRecord(${record.id})">
                    删除
                </button>
            </td>
        `;
        tableBody.appendChild(row);
    });

    card.style.display = 'block';
}

function renderPitchingTable(records, options) {
    const { cardId, tableBodyId } = options;
    const card = document.getElementById(cardId);
    const tableBody = document.getElementById(tableBodyId);

    tableBody.innerHTML = '';

    if (!records || records.length === 0) {
        card.style.display = 'none';
        return;
    }

    records.forEach(record => {
        matchupRecordCache.set(record.id, {
            game_date: record.game_date,
            opponent: record.opponent,
            player_name: record.player_name
        });

        const row = document.createElement('tr');
        row.innerHTML = `
            <td><span class="font-semibold text-white">${record.player_name}</span></td>
            <td>${record.player_jersey}</td>
            <td>${record.game_date}</td>
            <td>${record.opponent}</td>
            <td>${record.innings_pitched.toFixed(1)}</td>
            <td>${record.hits_allowed}</td>
            <td>${record.runs_allowed}</td>
            <td>${record.earned_runs}</td>
            <td>${record.walks_allowed}</td>
            <td>${record.strikeouts}</td>
            <td>${record.home_runs_allowed}</td>
            <td>${record.pitches}</td>
            <td>${record.strike_percentage.toFixed(1)}%</td>
            <td>${record.era.toFixed(2)}</td>
            <td>${record.whip.toFixed(2)}</td>
            <td>${record.result_text}</td>
            <td>
                <button class="btn-primary text-white px-3 py-1 font-heading text-xs font-bold" onclick="deleteGameRecord(${record.id})">
                    删除
                </button>
            </td>
        `;
        tableBody.appendChild(row);
    });

    card.style.display = 'block';
}

async function loadAllGameRecords() {
    try {
        const response = await fetch('/api/matchup/all_game_records');
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || '加载所有比赛记录失败');
        }

        renderBattingTable(data.batting_records, {
            cardId: 'allPlayersBattingCard',
            tableBodyId: 'allPlayersBattingTableBody',
            emptyMessage: '当前没有全队打击记录'
        });
        renderPitchingTable(data.pitching_records, {
            cardId: 'allPlayersPitchingCard',
            tableBodyId: 'allPlayersPitchingTableBody',
            emptyMessage: '当前没有全队投球记录'
        });
    } catch (error) {
        console.error('加载所有队员比赛记录失败:', error);
        showAlert(error.message || '加载所有队员比赛记录失败', 'error');
    }
}

function hideAllTeamRecords() {
    document.getElementById('allPlayersBattingCard').style.display = 'none';
    document.getElementById('allPlayersPitchingCard').style.display = 'none';
}

function resetFilteredResults() {
    document.getElementById('querySummaryCard').style.display = 'none';
    document.getElementById('filteredBattingCard').style.display = 'none';
    document.getElementById('filteredPitchingCard').style.display = 'none';
}

async function deleteGameRecord(recordId) {
    const recordMeta = matchupRecordCache.get(recordId) || {};
    const gameDate = recordMeta.game_date || '未知日期';
    const opponent = recordMeta.opponent || '未知对手';
    const playerName = recordMeta.player_name || '';
    const playerText = playerName ? `球员 ${playerName} 的` : '';
    const message = `确定要删除${playerText} ${gameDate} 对阵 ${opponent} 的比赛记录吗？此操作会同步扣减累计数据，且不可恢复。`;

    if (!confirm(message)) {
        return;
    }

    try {
        const response = await fetch(`/api/matchup/game_record/${recordId}`, {
            method: 'DELETE'
        });
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || '删除失败');
        }

        showAlert(`比赛记录删除成功：${result.player_name} 对阵 ${result.opponent} (${result.game_date})`, 'success');

        const hasFilters = document.getElementById('playerSelect').value || document.getElementById('opponentSelect').value;
        if (hasFilters) {
            await loadMatchupStats();
        } else {
            resetFilteredResults();
            await loadAllGameRecords();
        }
    } catch (error) {
        console.error('删除比赛记录失败:', error);
        showAlert(`删除失败: ${error.message}`, 'error');
    }
}

function getAvgClass(average) {
    const avg = parseFloat(average);
    if (avg >= 0.300) return 'text-green-400';
    if (avg >= 0.250) return 'text-yellow-400';
    return 'text-gray-400';
}

function resetFilters() {
    document.getElementById('playerSelect').value = '';
    document.getElementById('opponentSelect').value = '';
    resetFilteredResults();
}

function showAlert(message, type = 'info') {
    const existingAlert = document.querySelector('.alert-toast');
    if (existingAlert) {
        existingAlert.remove();
    }

    const alertDiv = document.createElement('div');

    let bgColor, borderColor;
    switch (type) {
        case 'success':
            bgColor = 'rgba(34, 197, 94, 0.1)';
            borderColor = 'rgba(34, 197, 94, 0.3)';
            break;
        case 'error':
            bgColor = 'rgba(239, 68, 68, 0.1)';
            borderColor = 'rgba(239, 68, 68, 0.3)';
            break;
        case 'warning':
            bgColor = 'rgba(245, 158, 11, 0.1)';
            borderColor = 'rgba(245, 158, 11, 0.3)';
            break;
        default:
            bgColor = 'rgba(230, 0, 0, 0.1)';
            borderColor = 'rgba(230, 0, 0, 0.3)';
    }

    alertDiv.className = 'alert-toast fixed top-5 right-5 z-50';
    alertDiv.style.cssText = `
        background: ${bgColor};
        border: 1px solid ${borderColor};
        clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px));
        min-width: 300px;
        padding: 1rem;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    `;

    alertDiv.innerHTML = `
        <div class="flex items-center gap-3">
            <span class="text-white">${message}</span>
            <button type="button" class="text-gray-400 hover:text-white ml-auto text-xl leading-none" onclick="this.parentElement.parentElement.remove()">&times;</button>
        </div>
    `;

    document.body.appendChild(alertDiv);

    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 4000);
}