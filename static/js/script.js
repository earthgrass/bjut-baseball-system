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
                <td colspan="9" class="text-center text-muted">
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
        const positionDisplay = renderPositionBadges(player);
        
        // 调试OPS值
        console.log(`球员 ${player.name} 的OPS值:`, player.ops, typeof player.ops);
        // 尝试多种方式获取OPS值
        let ops = 0;
        if (player.ops !== undefined && player.ops !== null) {
            ops = parseFloat(player.ops);
            if (isNaN(ops)) ops = 0;
        } else if (player.on_base_percentage !== undefined && player.slugging_percentage !== undefined) {
            // 如果OPS不存在，但上垒率和长打率存在，则计算OPS
            const obp = parseFloat(player.on_base_percentage) || 0;
            const slg = parseFloat(player.slugging_percentage) || 0;
            ops = obp + slg;
        }
        console.log(`最终OPS值:`, ops);
        
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
                <button class="btn btn-sm btn-primary me-1" onclick="editPlayer(${player.id})">
                    <i class="fas fa-edit"></i>
                </button>
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
        const response = await fetch('/api/players', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        console.log("响应状态:", response.status);
        const result = await response.json();
        console.log("响应结果:", result);
        
        if (response.ok) {
            showAlert('球员添加成功！', 'success');
            // 清空表单
            document.getElementById('addPlayerForm').reset();
            // 跳转到球员列表
            setTimeout(() => {
                window.location.href = '/players';
            }, 1500);
        } else {
            showAlert(result.error || '添加失败', 'danger');
        }
    } catch (error) {
        console.error('添加球员失败:', error);
        showAlert('网络错误，请稍后重试', 'danger');
    }
}

// 编辑球员
async function editPlayer(playerId) {
    console.log("编辑球员:", playerId);
    
    const player = playersData.find(p => p.id === playerId);
    if (!player) {
        console.error("找不到球员:", playerId);
        showAlert('找不到该球员', 'danger');
        return;
    }
    
    console.log("球员数据:", player);
    
    // 填充表单
    document.getElementById('editPlayerId').value = player.id;
    const playerPositions = getPlayerPositions(player);
    
    // 生成位置选项HTML
    let positionOptions = '';
    ALL_POSITIONS.forEach(pos => {
        const isSelected = playerPositions.includes(pos);
        positionOptions += `<option value="${pos}" ${isSelected ? 'selected' : ''}>${pos}</option>`;
    });
    
    let primaryPositionOptions = '<option value="">选择主位置</option>';
    ALL_POSITIONS.forEach(pos => {
        const isSelected = player.primary_position === pos;
        primaryPositionOptions += `<option value="${pos}" ${isSelected ? 'selected' : ''}>${pos}</option>`;
    });

    // 确保所有字段都有默认值
    const atBats = player.at_bats_total || 0;
    const hits = player.hits_total || 0;
    const rbi = player.rbi_total || 0;
    const homeRuns = player.home_runs_batting || 0;
    const runs = player.runs_total || 0;
    const walks = player.walks_total || 0;
    const strikeouts = player.strikeouts_batting_total || 0;
    const doubles = player.doubles || 0;
    const triples = player.triples || 0;
    const stolenBases = player.stolen_bases || 0;
    
    const formContent = `
        <div class="row">
            <div class="col-md-6 mb-3">
                <label class="form-label">姓名</label>
                <input type="text" class="form-control" id="editName" value="${player.name || ''}">
            </div>
            <div class="col-md-6 mb-3">
                <label class="form-label">背号</label>
                <input type="text" class="form-control" id="editJerseyNumber" value="${player.jersey_number || ''}">
            </div>
        </div>
        
        <div class="row">
            <div class="col-md-6 mb-3">
                <label class="form-label d-block">投手标记</label>
                <div class="form-check form-switch">
                    <input class="form-check-input" type="checkbox" id="editIsPitcher" ${player.is_pitcher ? 'checked' : ''}>
                    <label class="form-check-label" for="editIsPitcher">是否为投手</label>
                </div>
                <small class="text-muted">勾选后会自动加入“投手”位置，但仍可继续选择其他守备位置。</small>
            </div>
        </div>

        <div class="row">
            <div class="col-md-6 mb-3">
                <label class="form-label">守备位置（可多选）</label>
                <select class="form-select" id="editPositions" multiple size="4">
                    ${positionOptions}
                </select>
                <small class="text-muted">按住Ctrl键（Windows）或Command键（Mac）可多选</small>
            </div>
            <div class="col-md-6 mb-3">
                <label class="form-label">主位置</label>
                <select class="form-select" id="editPrimaryPosition">
                    ${primaryPositionOptions}
                </select>
            </div>
        </div>
        
        <!-- 打击数据 -->
        <div class="card mb-3">
            <div class="card-header bg-primary text-white">
                打击统计数据
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-3 mb-3">
                        <label class="form-label">打数</label>
                        <input type="number" class="form-control" id="editAtBats" 
                               value="${player.at_bats_total || 0}" min="0">
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">安打</label>
                        <input type="number" class="form-control" id="editHits" 
                               value="${player.hits_total || 0}" min="0">
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">打点</label>
                        <input type="number" class="form-control" id="editRbi" 
                               value="${player.rbi_total || 0}" min="0">
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">得分</label>
                        <input type="number" class="form-control" id="editRuns" 
                               value="${player.runs_total || 0}" min="0">
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-md-3 mb-3">
                        <label class="form-label">保送</label>
                        <input type="number" class="form-control" id="editWalks" 
                               value="${player.walks_total || 0}" min="0">
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">三振</label>
                        <input type="number" class="form-control" id="editStrikeoutsBatting" 
                               value="${player.strikeouts_batting_total || 0}" min="0">
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">二垒安打</label>
                        <input type="number" class="form-control" id="editDoubles" 
                               value="${player.doubles || 0}" min="0">
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">三垒安打</label>
                        <input type="number" class="form-control" id="editTriples" 
                               value="${player.triples || 0}" min="0">
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-md-3 mb-3">
                        <label class="form-label">本垒打</label>
                        <input type="number" class="form-control" id="editHomeRuns" 
                               value="${player.home_runs_batting || 0}" min="0">
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">盗垒</label>
                        <input type="number" class="form-control" id="editStolenBases" 
                               value="${player.stolen_bases || 0}" min="0">
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">被中身球</label>
                        <input type="number" class="form-control" id="editHitByPitch" 
                               value="${player.hit_by_pitch || 0}" min="0">
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">被触杀</label>
                        <input type="number" class="form-control" id="editCaughtStealing" 
                               value="${player.caught_stealing || 0}" min="0">
                    </div>
                </div>
                
                <div class="row">
                    <div class="col-md-4 mb-3">
                        <label class="form-label">高飞牺牲打</label>
                        <input type="number" class="form-control" id="editSacrificeFlys" 
                               value="${player.sacrifice_flys || 0}" min="0">
                    </div>
                    <div class="col-md-4 mb-3">
                        <label class="form-label">牺牲触击</label>
                        <input type="number" class="form-control" id="editSacrificeHits" 
                               value="${player.sacrifice_hits || 0}" min="0">
                    </div>
                    <div class="col-md-4 mb-3">
                        <label class="form-label">总垒数</label>
                        <input type="number" class="form-control" id="editTotalBases" 
                               value="${player.total_bases || 0}" min="0" readonly>
                        <small class="text-muted">自动计算</small>
                    </div>
                </div>
                
                <!-- 计算字段 -->
                <div class="row">
                    <div class="col-md-3 mb-3">
                        <label class="form-label">打击率</label>
                        <input type="number" step="0.001" class="form-control" id="editBattingAverage" 
                               value="${player.batting_average || 0}" min="0" max="1" readonly>
                        <small class="text-muted">自动计算</small>
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">上垒率</label>
                        <input type="number" step="0.001" class="form-control" id="editOnBasePercentage" 
                               value="${player.on_base_percentage || 0}" min="0" max="1" readonly>
                        <small class="text-muted">自动计算</small>
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">长打率</label>
                        <input type="number" step="0.001" class="form-control" id="editSluggingPercentage" 
                               value="${player.slugging_percentage || 0}" min="0" max="4" readonly>
                        <small class="text-muted">自动计算</small>
                    </div>
                    <div class="col-md-3 mb-3">
                        <label class="form-label">OPS</label>
                        <input type="number" step="0.001" class="form-control" id="editOps" 
                               value="${player.ops !== undefined && player.ops !== null ? player.ops : 0}" min="0" readonly>
                        <small class="text-muted">自动计算</small>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 投手数据 -->
        <div class="card mb-3" id="editPitchingCard" style="display: ${player.is_pitcher ? 'block' : 'none'};">
                <div class="card-header bg-warning text-white">
                    投手统计数据
                </div>
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-3 mb-3">
                            <label class="form-label">投球局数</label>
                            <input type="number" step="0.1" class="form-control" id="editInningsPitched" 
                                   value="${player.innings_pitched_total || 0}" min="0">
                        </div>
                        <div class="col-md-3 mb-3">
                            <label class="form-label">被安打</label>
                            <input type="number" class="form-control" id="editHitsAllowed" 
                                   value="${player.hits_allowed_total || 0}" min="0">
                        </div>
                        <div class="col-md-3 mb-3">
                            <label class="form-label">被得分</label>
                            <input type="number" class="form-control" id="editRunsAllowed" 
                                   value="${player.runs_allowed_total || 0}" min="0">
                        </div>
                        <div class="col-md-3 mb-3">
                            <label class="form-label">自责分</label>
                            <input type="number" class="form-control" id="editEarnedRuns" 
                                   value="${player.earned_runs_total || 0}" min="0">
                        </div>
                    </div>
                    
                    <div class="row">
                        <div class="col-md-3 mb-3">
                            <label class="form-label">保送</label>
                            <input type="number" class="form-control" id="editWalksAllowed" 
                                   value="${player.walks_allowed_total || 0}" min="0">
                        </div>
                        <div class="col-md-3 mb-3">
                            <label class="form-label">三振</label>
                            <input type="number" class="form-control" id="editStrikeoutsPitched" 
                                   value="${player.strikeouts_total || 0}" min="0">
                        </div>
                        <div class="col-md-3 mb-3">
                            <label class="form-label">被本垒打</label>
                            <input type="number" class="form-control" id="editHomeRunsAllowed" 
                                   value="${player.home_runs_allowed_total || 0}" min="0">
                        </div>
                        <div class="col-md-3 mb-3">
                            <label class="form-label">面对打者数</label>
                            <input type="number" class="form-control" id="editBattersFaced" 
                                   value="${player.batters_faced || 0}" min="0">
                        </div>
                    </div>
                    
                    <div class="row">
                        <div class="col-md-3 mb-3">
                            <label class="form-label">总投球数</label>
                            <input type="number" class="form-control" id="editPitches" 
                                   value="${player.pitches || 0}" min="0">
                        </div>
                        <div class="col-md-3 mb-3">
                            <label class="form-label">好球数</label>
                            <input type="number" class="form-control" id="editStrikes" 
                                   value="${player.strikes || 0}" min="0">
                        </div>
                        <div class="col-md-3 mb-3">
                            <label class="form-label">触身球</label>
                            <input type="number" class="form-control" id="editHitByPitchAllowed" 
                                   value="${player.hit_by_pitch_allowed || 0}" min="0">
                        </div>
                        <div class="col-md-3 mb-3">
                            <label class="form-label">暴投</label>
                            <input type="number" class="form-control" id="editWildPitches" 
                                   value="${player.wild_pitches || 0}" min="0">
                        </div>
                    </div>
                    
                    <!-- 投手计算字段 -->
                    <div class="row">
                        <div class="col-md-4 mb-3">
                            <label class="form-label">防御率</label>
                            <input type="number" step="0.01" class="form-control" id="editEra" 
                                   value="${player.era || 0}" min="0" readonly>
                            <small class="text-muted">自动计算</small>
                        </div>
                        <div class="col-md-4 mb-3">
                            <label class="form-label">WHIP</label>
                            <input type="number" step="0.01" class="form-control" id="editWhip" 
                                   value="${player.whip || 0}" min="0" readonly>
                            <small class="text-muted">自动计算</small>
                        </div>
                        <div class="col-md-4 mb-3">
                            <label class="form-label">好球率</label>
                            <input type="number" step="0.1" class="form-control" id="editStrikePercentage" 
                                   value="${player.strike_percentage || 0}" min="0" max="100" readonly>
                            <small class="text-muted">自动计算</small>
                        </div>
                    </div>
                </div>
            </div>
        
        <!-- 守备数据 -->
        <div class="card mb-3">
            <div class="card-header bg-info text-white">
                守备数据
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-6 mb-3">
                        <label class="form-label">守备失误</label>
                        <input type="number" class="form-control" id="editErrorsFielding" 
                               value="${player.errors_fielding || 0}" min="0">
                    </div>
                    <div class="col-md-6 mb-3">
                        <label class="form-label">捕逸</label>
                        <input type="number" class="form-control" id="editPassedBalls" 
                               value="${player.passed_balls || 0}" min="0">
                    </div>
                </div>
            </div>
        </div>
    `;
    
    console.log("生成的表单内容长度:", formContent.length);
    document.getElementById('editFormContent').innerHTML = formContent;
    bindPlayerTypeFields('editIsPitcher', 'editPositions', 'editPrimaryPosition', 'editPitchingCard');
    
    // 添加实时计算事件监听器
    addCalculationListeners();
    
    // 立即计算一次，确保所有计算字段都有正确值
    setTimeout(() => {
        calculateBattingStats();
        calculatePitchingStats();
    }, 100);
    
    // 显示模态框
    const editModalElement = document.getElementById('editModal');
    if (editModalElement) {
        const editModal = new bootstrap.Modal(editModalElement);
        editModal.show();
        console.log("模态框已显示");
    } else {
        console.error("找不到editModal元素");
    }
}

// 保存编辑
async function savePlayerChanges() {
    console.log("===== 开始保存球员更改 =====");
    
    const playerId = document.getElementById('editPlayerId').value;
    console.log("球员ID:", playerId);
    
    if (!playerId) {
        console.error("没有获取到球员ID");
        showAlert('无法获取球员ID', 'danger');
        return;
    }
    
    try {
        // 安全获取表单元素
        const getElementValue = (id, defaultValue = '') => {
            const element = document.getElementById(id);
            return element ? element.value : defaultValue;
        };
        
        const getElementNumber = (id, defaultValue = 0) => {
            const element = document.getElementById(id);
            if (!element) return defaultValue;
            const value = parseInt(element.value);
            return isNaN(value) ? defaultValue : value;
        };

        const getElementFloat = (id, defaultValue = 0) => {
            const element = document.getElementById(id);
            if (!element) return defaultValue;
            const value = parseFloat(element.value);
            return isNaN(value) ? defaultValue : value;
        };
        
        // 获取选中的多个位置
        const positionSelect = document.getElementById('editPositions');
        let selectedPositions = positionSelect ? getSelectedPositions(positionSelect) : [];
        const isPitcher = document.getElementById('editIsPitcher')?.checked || false;
        let primaryPosition = getElementValue('editPrimaryPosition');

        if (isPitcher && !selectedPositions.includes('投手')) {
            selectedPositions = ['投手', ...selectedPositions];
        }

        if (!isPitcher) {
            selectedPositions = selectedPositions.filter(pos => pos !== '投手');
        }

        if (primaryPosition && !selectedPositions.includes(primaryPosition)) {
            primaryPosition = selectedPositions[0] || '';
        }
        
        // 收集表单数据 - 使用安全的获取方法
        const formData = {
            name: getElementValue('editName'),
            jersey_number: getElementValue('editJerseyNumber'),
            is_pitcher: isPitcher,
            player_type: isPitcher ? 'pitcher' : 'fielder',
            positions: selectedPositions,
            primary_position: primaryPosition,
            
            // 打击数据 - 使用安全的数字获取方法
            at_bats_total: getElementNumber('editAtBats', 0),
            hits_total: getElementNumber('editHits', 0),
            rbi_total: getElementNumber('editRbi', 0),
            home_runs_batting: getElementNumber('editHomeRuns', 0),
            
            // 其他基础数据
            runs_total: getElementNumber('editRuns', 0),
            walks_total: getElementNumber('editWalks', 0),
            strikeouts_batting_total: getElementNumber('editStrikeoutsBatting', 0),
            doubles: getElementNumber('editDoubles', 0),
            triples: getElementNumber('editTriples', 0),
            stolen_bases: getElementNumber('editStolenBases', 0),
            hit_by_pitch: getElementNumber('editHitByPitch', 0),
            caught_stealing: getElementNumber('editCaughtStealing', 0),
            sacrifice_flys: getElementNumber('editSacrificeFlys', 0),
            sacrifice_hits: getElementNumber('editSacrificeHits', 0),
            errors_fielding: getElementNumber('editErrorsFielding', 0),
            passed_balls: getElementNumber('editPassedBalls', 0)
        };

        if (isPitcher) {
            Object.assign(formData, {
                innings_pitched_total: getElementFloat('editInningsPitched', 0),
                hits_allowed_total: getElementNumber('editHitsAllowed', 0),
                runs_allowed_total: getElementNumber('editRunsAllowed', 0),
                earned_runs_total: getElementNumber('editEarnedRuns', 0),
                walks_allowed_total: getElementNumber('editWalksAllowed', 0),
                strikeouts_total: getElementNumber('editStrikeoutsPitched', 0),
                home_runs_allowed_total: getElementNumber('editHomeRunsAllowed', 0),
                batters_faced: getElementNumber('editBattersFaced', 0),
                pitches: getElementNumber('editPitches', 0),
                strikes: getElementNumber('editStrikes', 0),
                hit_by_pitch_allowed: getElementNumber('editHitByPitchAllowed', 0),
                wild_pitches: getElementNumber('editWildPitches', 0)
            });
        }
        
        console.log("===== 前端发送的数据 =====");
        console.log("本垒打 (home_runs_batting):", formData.home_runs_batting);
        console.log("打点 (rbi_total):", formData.rbi_total);
        console.log("安打 (hits_total):", formData.hits_total);
        console.log("打数 (at_bats_total):", formData.at_bats_total);
        console.log("三振 (strikeouts_batting_total):", formData.strikeouts_batting_total);
        console.log("二垒安打 (doubles):", formData.doubles);
        console.log("三垒安打 (triples):", formData.triples);
        console.log("盗垒 (stolen_bases):", formData.stolen_bases);
        console.log("完整数据:", JSON.stringify(formData, null, 2));
        
        // 调试：检查每个输入框的实际值
        console.log("===== 输入框实际值 =====");
        const debugIds = ['editAtBats', 'editHits', 'editRbi', 'editHomeRuns', 'editRuns', 'editWalks', 'editStrikeoutsBatting', 'editDoubles', 'editTriples', 'editStolenBases'];
        debugIds.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                console.log(`${id}: value="${element.value}", parsed=${parseInt(element.value) || 0}`);
            } else {
                console.log(`${id}: 元素未找到`);
            }
        });
        
        // 验证必要数据
        if (!formData.name || !formData.jersey_number) {
            showAlert('姓名和背号不能为空', 'warning');
            return;
        }
        
        if (selectedPositions.length === 0) {
            showAlert('请至少选择一个位置', 'warning');
            return;
        }
        
        if (!formData.primary_position) {
            showAlert('请选择主位置', 'warning');
            return;
        }
        
        const response = await fetch(`/api/players/${playerId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        console.log("响应状态:", response.status);
        const result = await response.json();
        console.log("后端返回数据:", JSON.stringify(result, null, 2));
        
        if (response.ok) {
            showAlert('球员信息更新成功！', 'success');
            
            // 关闭模态框
            const modal = bootstrap.Modal.getInstance(document.getElementById('editModal'));
            if (modal) {
                modal.hide();
            }
            
            // 重新加载数据
            setTimeout(() => {
                loadPlayers();
            }, 300);
        } else {
            showAlert(result.error || '更新失败', 'danger');
        }
    } catch (error) {
        console.error('更新球员失败:', error);
        showAlert('网络错误，请稍后重试', 'danger');
    }
    
    console.log("===== 保存球员更改结束 =====");
}

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

// 显示警告信息
function showAlert(message, type = 'info') {
    // 移除现有的警告
    const existingAlert = document.querySelector('.alert-dismissible');
    if (existingAlert) {
        existingAlert.remove();
    }
    
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = `
        top: 20px;
        right: 20px;
        z-index: 9999;
        min-width: 300px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    `;
    
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // 3秒后自动消失
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 3000);
}

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

// 添加实时计算监听器
function addCalculationListeners() {
    // 监听打击数据变化，实时计算打击率
    const battingInputs = ['editAtBats', 'editHits', 'editDoubles', 'editTriples', 'editHomeRuns'];
    battingInputs.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('input', calculateBattingStats);
        }
    });
    
    // 监听投手数据变化
    const pitchingInputs = ['editInningsPitched', 'editEarnedRuns', 'editWalksAllowed', 'editHitsAllowed', 'editPitches', 'editStrikes'];
    pitchingInputs.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('input', calculatePitchingStats);
        }
    });
}

// 计算打击统计
function calculateBattingStats() {
    try {
        const atBats = parseInt(getValue('editAtBats')) || 0;
        const hits = parseInt(getValue('editHits')) || 0;
        const doubles = parseInt(getValue('editDoubles')) || 0;
        const triples = parseInt(getValue('editTriples')) || 0;
        const homeRuns = parseInt(getValue('editHomeRuns')) || 0;
        const walks = parseInt(getValue('editWalks')) || 0;
        const hitByPitch = parseInt(getValue('editHitByPitch')) || 0;
        const sacrificeFlys = parseInt(getValue('editSacrificeFlys')) || 0;
        
        // 计算打击率
        if (atBats > 0) {
            const avg = hits / atBats;
            const avgElement = document.getElementById('editBattingAverage');
            if (avgElement) avgElement.value = avg.toFixed(3);
        }
        
        // 计算总垒数
        const singles = hits - doubles - triples - homeRuns;
        const totalBases = singles + (doubles * 2) + (triples * 3) + (homeRuns * 4);
        const totalBasesElement = document.getElementById('editTotalBases');
        if (totalBasesElement) totalBasesElement.value = totalBases;
        
        // 计算上垒率
        const plateAppearances = atBats + walks + hitByPitch + sacrificeFlys;
        if (plateAppearances > 0) {
            const obp = (hits + walks + hitByPitch) / plateAppearances;
            const obpElement = document.getElementById('editOnBasePercentage');
            if (obpElement) obpElement.value = obp.toFixed(3);
        }
        
        // 计算长打率
        if (atBats > 0) {
            const slg = totalBases / atBats;
            const slgElement = document.getElementById('editSluggingPercentage');
            if (slgElement) slgElement.value = slg.toFixed(3);
        }
        
        // 计算OPS
        const avg = document.getElementById('editBattingAverage')?.value || 0;
        const obp = document.getElementById('editOnBasePercentage')?.value || 0;
        const slg = document.getElementById('editSluggingPercentage')?.value || 0;
        const ops = parseFloat(obp) + parseFloat(slg);
        const opsElement = document.getElementById('editOps');
        if (opsElement) opsElement.value = ops.toFixed(3);
        
    } catch (error) {
        console.error("计算打击统计数据时出错:", error);
    }
}

// 计算投手统计
function calculatePitchingStats() {
    try {
        const innings = parseFloat(getValue('editInningsPitched')) || 0;
        const earnedRuns = parseInt(getValue('editEarnedRuns')) || 0;
        const walksAllowed = parseInt(getValue('editWalksAllowed')) || 0;
        const hitsAllowed = parseInt(getValue('editHitsAllowed')) || 0;
        const pitches = parseInt(getValue('editPitches')) || 0;
        const strikes = parseInt(getValue('editStrikes')) || 0;
        
        // 计算防御率
        if (innings > 0) {
            const era = (earnedRuns * 9) / innings;
            const eraElement = document.getElementById('editEra');
            if (eraElement) eraElement.value = era.toFixed(2);
        }
        
        // 计算WHIP
        if (innings > 0) {
            const whip = (walksAllowed + hitsAllowed) / innings;
            const whipElement = document.getElementById('editWhip');
            if (whipElement) whipElement.value = whip.toFixed(2);
        }
        
        // 计算好球率
        if (pitches > 0) {
            const strikePercentage = (strikes / pitches) * 100;
            const strikePctElement = document.getElementById('editStrikePercentage');
            if (strikePctElement) strikePctElement.value = strikePercentage.toFixed(1);
        }
        
    } catch (error) {
        console.error("计算投手统计数据时出错:", error);
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
