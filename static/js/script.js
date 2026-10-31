// 全局变量
let playersData = [];
const ALL_POSITIONS = ['投手', '捕手', '一垒手', '二垒手', '三垒手', '游击手', '左外野手', '中外野手', '右外野手'];

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    loadPlayers();
    bindAddPlayerForm();
});

// 加载所有球员
async function loadPlayers() {
    try {
        const response = await fetch('/api/players');
        playersData = await response.json();
        displayPlayers(playersData);
    } catch (error) {
        console.error('加载球员数据失败:', error);
        showAlert('加载数据失败，请刷新页面重试', 'danger');
    }
}

// 显示球员列表（简单版本）
function displayPlayers(players) {
    const tableBody = document.getElementById('playersTableBody');
    if (!tableBody) return;
    
    tableBody.innerHTML = '';
    
    if (!players || players.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="11" class="text-center text-muted">
                    暂无球员数据
                </td>
            </tr>
        `;
        return;
    }

    players.forEach((player, index) => {
        // 确保所有字段都有值
        const homeRuns = player.home_runs_batting || player.home_runs || 0;
        const rbi = player.rbi_total || 0;
        const avg = player.batting_average || 0;
        const obp = player.on_base_percentage || 0;
        const iso = player.isolated_power || 0;
        const positionDisplay = renderPositionBadges(player);

        // ⚠️ OPS / 上垒率 / 长打力都**直接读后端算好的值**（Phase R5）。
        // 前端不再自己加一遍 —— 那正是「网页上一个数、CSV 另一个数」的根源。
        const ops = parseFloat(player.ops) || 0;

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${index + 1}</td>
            <td>
                <strong>${player.name}</strong>
                <br><small class="text-muted">背号: ${player.jersey_number || '无'}</small>
            </td>
            <td>${player.jersey_number || '无'}</td>
            <td>
                ${positionDisplay}
            </td>
            <td>
                ${avg > 0 ?
                    `<span class="badge ${getAvgBadgeClass(avg)}">
                        ${avg.toFixed(3)}
                    </span>` :
                    '-'}
            </td>
            <td>
                ${obp > 0 ? obp.toFixed(3) : '-'}
            </td>
            <td>
                ${homeRuns > 0 ?
                    `<span class="badge bg-danger">${homeRuns}</span>` :
                    '-'}
            </td>
            <td>
                ${rbi > 0 ?
                    `<span class="badge bg-success">${rbi}</span>` :
                    '-'}
            </td>
            <td>
                ${ops > 0 ?
                    `<span class="badge ${getOpsBadgeClass(ops)}">${ops.toFixed(3)}</span>` :
                    '-'}
            </td>
            <td>
                ${iso > 0 ? iso.toFixed(3) : '-'}
            </td>
            <td>
                <button class="btn btn-sm btn-danger" onclick="deletePlayer(${player.id}, '${player.name}')">
                    <i class="fas fa-trash"></i>
                </button>
            </td>
        `;

        tableBody.appendChild(row);
    });
}

function getPlayerPositions(player) {
    if (Array.isArray(player.positions) && player.positions.length > 0) {
        return player.positions;
    }
    if (player.positions_string) {
        return player.positions_string.split(',').map(pos => pos.trim()).filter(Boolean);
    }
    if (player.primary_position) {
        return [player.primary_position];
    }
    if (player.position) {
        return [player.position];
    }
    return [];
}

function renderPositionBadges(player) {
    const positions = getPlayerPositions(player);
    if (positions.length === 0) {
        return '<span class="badge bg-secondary">未指定</span>';
    }

    const badges = positions.map(position => (
        `<span class="badge ${getPositionBadgeClass(position)} me-1 mb-1">${position}</span>`
    )).join('');

    if (!player.primary_position || positions.length <= 1) {
        return badges;
    }

    return `
        <div>${badges}</div>
        <small class="text-muted">主位置: ${player.primary_position}</small>
    `;
}

// 新增：根据打击率获取徽章颜色
function getAvgBadgeClass(average) {
    if (average >= 0.300) return 'bg-success';
    if (average >= 0.250) return 'bg-warning';
    return 'bg-secondary';
}

// 新增：根据防御率获取徽章颜色
function getEraBadgeClass(era) {
    if (era <= 3.00) return 'bg-success';
    if (era <= 5.00) return 'bg-warning';
    return 'bg-danger';
}

// 新增：根据OPS获取徽章颜色
function getOpsBadgeClass(ops) {
    if (ops >= 0.900) return 'bg-success';  // 优秀
    if (ops >= 0.800) return 'bg-warning';  // 良好
    if (ops >= 0.700) return 'bg-info';     // 一般
    return 'bg-secondary';                  // 较差
}

// 获取位置对应的徽章类
function getPositionBadgeClass(position) {
    if (!position) return 'bg-secondary';
    
    const positionMap = {
        '投手': 'bg-danger',
        '捕手': 'bg-primary',
        '一垒手': 'bg-success',
        '二垒手': 'bg-info',
        '三垒手': 'bg-warning',
        '游击手': 'bg-secondary',
        '左外野手': 'bg-success',
        '中外野手': 'bg-info',
        '右外野手': 'bg-warning'
    };
    
    // 如果position是多个位置的字符串，取第一个位置
    const firstPosition = position.split(',')[0].trim();
    return positionMap[firstPosition] || 'bg-secondary';
}

function getIsPitcherValue(control) {
    if (!control) return false;
    if (control.type === 'checkbox') {
        return control.checked;
    }

    return ['pitcher', 'true', '1', 'yes', 'y', '投手'].includes(String(control.value || '').toLowerCase());
}

function getSelectedPositions(selectElement) {
    if (!selectElement) return [];
    return Array.from(selectElement.selectedOptions).map(option => option.value).filter(Boolean);
}

function syncPrimaryPositionOptions(primarySelect, positions, currentPrimary) {
    if (!primarySelect) return;

    const availablePositions = [...new Set((positions || []).filter(Boolean))];
    const options = ['<option value="">选择主位置</option>'];
    availablePositions.forEach(pos => {
        const selected = pos === currentPrimary ? 'selected' : '';
        options.push(`<option value="${pos}" ${selected}>${pos}</option>`);
    });
    primarySelect.innerHTML = options.join('');
    primarySelect.disabled = availablePositions.length === 0;

    if (availablePositions.includes(currentPrimary)) {
        primarySelect.value = currentPrimary;
    } else if (availablePositions.length > 0) {
        primarySelect.value = availablePositions[0];
    } else {
        primarySelect.value = '';
    }
}

function syncPlayerTypeFields(typeSelectId, positionsId, primaryId, pitchingCardId = null) {
    const typeSelect = document.getElementById(typeSelectId);
    const positionsSelect = document.getElementById(positionsId);
    const primarySelect = document.getElementById(primaryId);
    if (!typeSelect || !positionsSelect || !primarySelect) return;

    const isPitcher = getIsPitcherValue(typeSelect);
    const pitcherOption = Array.from(positionsSelect.options).find(option => option.value === '投手');

    if (pitcherOption) {
        pitcherOption.disabled = !isPitcher;
        pitcherOption.selected = isPitcher;
    }

    let selectedPositions = getSelectedPositions(positionsSelect).filter(pos => isPitcher || pos !== '投手');
    if (isPitcher && !selectedPositions.includes('投手')) {
        selectedPositions = ['投手', ...selectedPositions];
    }

    Array.from(positionsSelect.options).forEach(option => {
        option.selected = selectedPositions.includes(option.value);
    });

    syncPrimaryPositionOptions(primarySelect, selectedPositions, primarySelect.value);

    const pitchingCard = pitchingCardId ? document.getElementById(pitchingCardId) : null;
    if (pitchingCard) {
        pitchingCard.style.display = isPitcher ? '' : 'none';
    }
}

function bindPlayerTypeFields(typeSelectId, positionsId, primaryId, pitchingCardId = null) {
    const typeSelect = document.getElementById(typeSelectId);
    const positionsSelect = document.getElementById(positionsId);
    const primarySelect = document.getElementById(primaryId);
    if (!typeSelect || !positionsSelect || !primarySelect) return;

    const sync = () => syncPlayerTypeFields(typeSelectId, positionsId, primaryId, pitchingCardId);
    typeSelect.addEventListener(typeSelect.type === 'checkbox' ? 'change' : 'input', sync);
    positionsSelect.addEventListener('change', sync);
    sync();
}

function bindAddPlayerForm() {
    bindPlayerTypeFields('is_pitcher', 'positions', 'primary_position');
}

// 修改 addPlayer 函数
async function addPlayer() {
    console.log("开始添加球员...");
    const isPitcher = document.getElementById('is_pitcher')?.checked || false;

    // 获取选中的多个位置
    const positionSelect = document.getElementById('positions');
    let selectedPositions = positionSelect ? getSelectedPositions(positionSelect) : [];
    let primaryPosition = document.getElementById('primary_position').value;

    if (isPitcher && !selectedPositions.includes('投手')) {
        selectedPositions = ['投手', ...selectedPositions];
    }

    if (!isPitcher) {
        selectedPositions = selectedPositions.filter(pos => pos !== '投手');
    }

    if (primaryPosition && !selectedPositions.includes(primaryPosition)) {
        primaryPosition = selectedPositions[0] || '';
    }

    if (selectedPositions.length === 0) {
        showAlert('请至少选择一个位置', 'warning');
        return;
    }

    if (!primaryPosition) {
        showAlert('请选择主位置', 'warning');
        return;
    }
    
    // 收集表单数据
    const formData = {
        name: document.getElementById('name').value,
        jersey_number: document.getElementById('jersey_number').value,
        is_pitcher: isPitcher,
        player_type: isPitcher ? 'pitcher' : 'fielder',
        positions: selectedPositions,
        primary_position: primaryPosition,
    };
    
    console.log("表单数据:", formData);
    
    // 验证必填字段
    if (!formData.name || !formData.jersey_number) {
        showAlert('请填写姓名和背号', 'warning');
        return;
    }
    
    try {
        console.log("发送请求到后端...");
        // 提交期间禁用按钮，防止重复提交产生重复记录
        const submitBtn = document.querySelector('#addPlayerForm button[type="submit"]');
        if (submitBtn) submitBtn.disabled = true;

        await api.post('/api/players', formData);

        showAlert('球员添加成功！', 'success');
        // 清空表单
        document.getElementById('addPlayerForm').reset();
        // 跳转到球员列表
        setTimeout(() => {
            window.location.href = '/players';
        }, 1500);
    } catch (error) {
        console.error('添加球员失败:', error);
        showAlert(error instanceof ApiError ? error.message : '网络错误，请稍后重试', 'danger');
        const submitBtn = document.querySelector('#addPlayerForm button[type="submit"]');
        if (submitBtn) submitBtn.disabled = false;
    }
}

// 球员编辑：原 editPlayer / savePlayerChanges 两个函数已移除。
// 原因：它们向 PUT /api/players 提交 28 个统计字段，而 Phase R2 起该接口
// 只接受 metadata（name / jersey_number / is_pitcher / positions / primary_position），
// 统计字段一律 400 拒绝 —— 累计数据只能由 game_records 推导。
// 球员编辑现由 templates/players.html 内联实现（只提交 metadata）。

// 辅助函数：安全获取元素值
function getValue(elementId) {
    const element = document.getElementById(elementId);
    return element ? element.value : '';
}


// 删除球员
async function deletePlayer(playerId, playerName) {
    if (!confirm(`确定要删除球员 "${playerName}" 吗？此操作不可恢复。`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/players/${playerId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showAlert(`球员 "${playerName}" 删除成功！`, 'success');
            // 重新加载数据
            loadPlayers();
        } else {
            showAlert('删除失败', 'danger');
        }
    } catch (error) {
        console.error('删除球员失败:', error);
        showAlert('网络错误，请稍后重试', 'danger');
    }
}

// 显示警告信息 —— 统一走 static/js/toast.js 的全局 toast()/showAlert()

// 数据可视化
async function loadVisualization() {
    try {
        const response = await fetch('/api/stats/visualization');
        const data = await response.json();
        
        if (data.image) {
            document.getElementById('visualizationImage').innerHTML = `
                <img src="${data.image}" class="img-fluid" alt="数据可视化图表">
            `;
        }
        
        // 更新统计信息
        document.getElementById('statsInfo').innerHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="stat-card">
                        <h3>${data.total_players || 0}</h3>
                        <p>总球员数</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card bg-success">
                        <h3>${data.batters || 0}</h3>
                        <p>打击球员数</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card bg-warning">
                        <h3>${data.pitchers || 0}</h3>
                        <p>投手数量</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="stat-card bg-info">
                        <h3>${data.total_players ? data.batters / data.total_players * 100 : 0}%</h3>
                        <p>打击球员比例</p>
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        console.error('加载可视化数据失败:', error);
        document.getElementById('visualizationImage').innerHTML = `
            <div class="alert alert-warning">
                无法加载可视化图表，请确保有足够的球员数据。
            </div>
        `;
    }
}

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', function() {
    // 根据当前页面执行不同的初始化
    const currentPath = window.location.pathname;
    
    if (currentPath === '/players' || currentPath === '/') {
        loadPlayers();
    }
    
    if (currentPath === '/stats') {
        loadVisualization();
    }
});
