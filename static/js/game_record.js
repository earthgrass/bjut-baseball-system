// 切换记录类型显示
function toggleRecordType() {
    const battingFields = document.getElementById('battingFields');
    const pitchingFields = document.getElementById('pitchingFields');
    
    const battingRadio = document.getElementById('battingRecord');
    
    if (battingRadio.checked) {
        battingFields.style.display = 'block';
        pitchingFields.style.display = 'none';
    } else {
        battingFields.style.display = 'none';
        pitchingFields.style.display = 'block';
    }
}

// 当球员选择改变时自动调整记录类型
function onPlayerChange() {
    const playerSelect = document.getElementById('player_id');
    const selectedOption = playerSelect.options[playerSelect.selectedIndex];
    const isPitcher = ['true', '1', 'yes'].includes(
        String(selectedOption?.getAttribute('data-is-pitcher') || '').toLowerCase()
    );
    const battingRadio = document.getElementById('battingRecord');
    const pitchingRadio = document.getElementById('pitchingRecord');
 
    if (!selectedOption || !selectedOption.value) {
        battingRadio.checked = true;
        battingRadio.disabled = false;
        pitchingRadio.disabled = false;
        toggleRecordType();
        return;
    }

    if (isPitcher) {
        pitchingRadio.checked = true;
        pitchingRadio.disabled = false;
        battingRadio.disabled = false;
        toggleRecordType();
    } else {
        battingRadio.checked = true;
        battingRadio.disabled = false;
        pitchingRadio.disabled = true;
        toggleRecordType();
    }
}

async function loadOpponentsForGameRecord() {
    try {
        const response = await fetch('/api/matchup/opponents');
        const opponents = await response.json();
        const datalist = document.getElementById('opponentsList');

        if (!datalist) return;

        datalist.innerHTML = '';
        opponents.forEach(opponent => {
            const option = document.createElement('option');
            option.value = opponent;
            datalist.appendChild(option);
        });
    } catch (error) {
        console.error('加载对手列表失败:', error);
    }
}

// 提交比赛记录
async function submitGameRecord() {
    const playerId = document.getElementById('player_id').value;
    const opponent = document.getElementById('opponent').value;
    const gameDate = document.getElementById('game_date').value;
    const isPitching = document.getElementById('pitchingRecord').checked;
    
    // 基本验证
    if (!playerId || !opponent || !gameDate) {
        showAlert('请填写所有必填字段', 'warning');
        return;
    }
    
    const recordData = {
        player_id: parseInt(playerId),
        opponent: opponent,
        game_date: gameDate,
        is_pitching: isPitching
    };
    
    if (isPitching) {
        // 投手数据验证
        const innings = parseFloat(document.getElementById('innings_pitched').value);
        if (innings <= 0) {
            showAlert('请填写有效的投球局数', 'warning');
            return;
        }
        
        recordData.innings_pitched = innings;
        recordData.hits_allowed = parseInt(document.getElementById('hits_allowed').value) || 0;
        recordData.runs_allowed = parseInt(document.getElementById('runs_allowed').value) || 0;
        recordData.earned_runs = parseInt(document.getElementById('earned_runs').value) || 0;
        recordData.walks_allowed = parseInt(document.getElementById('walks_allowed').value) || 0;
        recordData.strikeouts = parseInt(document.getElementById('strikeouts_pitched').value) || 0;
        recordData.home_runs_allowed = parseInt(document.getElementById('home_runs_allowed').value) || 0;
        recordData.win = document.getElementById('win').checked;
        recordData.loss = document.getElementById('loss').checked;
        recordData.save = document.getElementById('save').checked;
        
        // 新增投手数据
        recordData.pitches = parseInt(document.getElementById('pitches').value) || 0;
        recordData.strikes = parseInt(document.getElementById('strikes').value) || 0;
        recordData.hit_by_pitch_allowed = parseInt(document.getElementById('hit_by_pitch_allowed').value) || 0;
        recordData.batters_faced = parseInt(document.getElementById('batters_faced').value) || 0;
    } else {
        // 打击数据验证
        const atBats = parseInt(document.getElementById('at_bats').value);
        if (atBats < 0) {
            showAlert('打数不能为负数', 'warning');
            return;
        }
        
        recordData.at_bats = atBats;
        recordData.runs = parseInt(document.getElementById('runs').value) || 0;
        recordData.hits = parseInt(document.getElementById('hits').value) || 0;
        recordData.rbi = parseInt(document.getElementById('rbi').value) || 0;
        recordData.walks = parseInt(document.getElementById('walks').value) || 0;
        recordData.strikeouts = parseInt(document.getElementById('strikeouts').value) || 0;
        
        // 新增打击详细数据
        recordData.doubles = parseInt(document.getElementById('doubles').value) || 0;
        recordData.triples = parseInt(document.getElementById('triples').value) || 0;
        recordData.home_runs_game = parseInt(document.getElementById('home_runs_game').value) || 0;
        recordData.hit_by_pitch = parseInt(document.getElementById('hit_by_pitch').value) || 0;
        recordData.stolen_bases_game = parseInt(document.getElementById('stolen_bases_game').value) || 0;
        recordData.caught_stealing = parseInt(document.getElementById('caught_stealing').value) || 0;
        recordData.sacrifice_flys = parseInt(document.getElementById('sacrifice_flys').value) || 0;
        recordData.sacrifice_hits = parseInt(document.getElementById('sacrifice_hits').value) || 0;
    }
    
    try {
        const response = await fetch('/api/game_records', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(recordData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('比赛记录添加成功！', 'success');
            // 清空表单
            document.getElementById('gameRecordForm').reset();
            // 3秒后跳转
            setTimeout(() => {
                window.location.href = '/game_stats';
            }, 1500);
        } else {
            showAlert(result.error || '添加失败', 'danger');
        }
    } catch (error) {
        console.error('添加比赛记录失败:', error);
        showAlert('网络错误，请稍后重试', 'danger');
    }
}

// 显示警告信息
function showAlert(message, type = 'info') {
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
    
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 3000);
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 设置默认日期为今天
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('game_date').value = today;
    
    // 初始化显示
    toggleRecordType();
    onPlayerChange();
    loadOpponentsForGameRecord();
});
