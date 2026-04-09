// 加载打击数据
async function loadBatters() {
    try {
        const response = await fetch('/api/players/batters');
        const batters = await response.json();
        
        const tableBody = document.querySelector('#battersTable tbody');
        tableBody.innerHTML = '';
        
        if (!batters || batters.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="12" class="text-center text-muted">
                        暂无打击球员数据
                    </td>
                </tr>
            `;
            return;
        }
        
        batters.forEach((batter, index) => {
            // 安全获取数据，防止undefined
            const avg = batter['打击率'] || '0.000';
            const obp = batter['上垒率'] || '0.000';
            const atBats = batter['打数'] || 0;
            const hits = batter['安打'] || 0;
            const rbi = batter['打点'] || 0;
            const runs = batter['得分'] || 0;
            const strikeouts = batter['三振'] || 0;
            const walks = batter['保送'] || 0;
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${index + 1}</td>
                <td><strong>${batter.name || '未知球员'}</strong></td>
                <td>${batter.jersey_number || '无'}</td>
                <td>
                    <span class="badge ${getPositionBadgeClass(batter.position)}">
                        ${batter.position || '未指定'}
                    </span>
                </td>
                <td><span class="badge ${getAvgBadgeClass(parseFloat(avg))}">${avg}</span></td>
                <td>${obp}</td>
                <td>${atBats}</td>
                <td>${hits}</td>
                <td><span class="badge bg-success">${rbi}</span></td>
                <td>${runs}</td>
                <td>${strikeouts}</td>
                <td>${walks}</td>
            `;
            tableBody.appendChild(row);
        });
        
        // 初始化DataTable
        if ($.fn.DataTable.isDataTable('#battersTable')) {
            $('#battersTable').DataTable().destroy();
        }
        $('#battersTable').DataTable({
            language: {
                url: 'https://cdn.datatables.net/plug-ins/1.13.4/i18n/zh-HANS.json'
            },
            pageLength: 10,
            order: [[4, 'desc']] // 按打击率降序排列
        });
        
    } catch (error) {
        console.error('加载打击数据失败:', error);
        showAlert('加载打击数据失败', 'danger');
    }
}

// 加载投手数据
async function loadPitchers() {
    try {
        const response = await fetch('/api/players/pitchers');
        const pitchers = await response.json();
        
        const tableBody = document.querySelector('#pitchersTable tbody');
        tableBody.innerHTML = '';
        
        if (!pitchers || pitchers.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="12" class="text-center text-muted">
                        暂无投手数据
                    </td>
                </tr>
            `;
            return;
        }
        
        pitchers.forEach((pitcher, index) => {
            // 安全获取数据，防止undefined
            const era = parseFloat(pitcher['防御率']) || 0.00;
            const whip = parseFloat(pitcher['WHIP']) || 0.00;
            const innings = pitcher['局数'] || 0;
            const hitsAllowed = pitcher['被打安打'] || 0;
            const runsAllowed = pitcher['被得分'] || 0;
            const earnedRuns = pitcher['自责分'] || 0;
            const strikeouts = pitcher['三振'] || 0;
            const walks = pitcher['保送'] || 0;
            const homeRunsAllowed = pitcher['被打本垒打'] || 0;
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${index + 1}</td>
                <td><strong>${pitcher.name || '未知球员'}</strong></td>
                <td>${pitcher.jersey_number || '无'}</td>
                <td>
                    <span class="badge ${getEraBadgeClass(era)}">
                        ${era.toFixed(2)}
                    </span>
                </td>
                <td><span class="badge bg-info">${whip.toFixed(2)}</span></td>
                <td>${innings}</td>
                <td>${hitsAllowed}</td>
                <td>${runsAllowed}</td>
                <td>${earnedRuns}</td>
                <td><span class="badge bg-primary">${strikeouts}</span></td>
                <td>${walks}</td>
                <td>${homeRunsAllowed}</td>
            `;
            tableBody.appendChild(row);
        });
        
        // 初始化DataTable
        if ($.fn.DataTable.isDataTable('#pitchersTable')) {
            $('#pitchersTable').DataTable().destroy();
        }
        $('#pitchersTable').DataTable({
            language: {
                url: 'https://cdn.datatables.net/plug-ins/1.13.4/i18n/zh-HANS.json'
            },
            pageLength: 10,
            order: [[3, 'asc']] // 按防御率升序排列（越低越好）
        });
        
    } catch (error) {
        console.error('加载投手数据失败:', error);
        showAlert('加载投手数据失败', 'danger');
    }
}

// 加载排行榜
async function loadLeaderboards() {
    try {
        // 打击排行榜
        const battingResponse = await fetch('/api/stats/batting_leaderboard');
        const battingLeaders = await battingResponse.json();
        
        const battingTable = document.getElementById('battingLeaderboard');
        battingTable.innerHTML = '';
        
        battingLeaders.forEach((leader, index) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${index + 1}</td>
                <td>${leader.name}</td>
                <td>#${leader.jersey_number}</td>
                <td><strong>${leader.avg?.toFixed(3) || '0.000'}</strong></td>
                <td>${leader.obp?.toFixed(3) || '0.000'}</td>
                <td>${leader.rbi || 0}</td>
            `;
            if (index === 0) row.classList.add('table-success');
            battingTable.appendChild(row);
        });
        
        // 投手排行榜
        const pitchingResponse = await fetch('/api/stats/pitching_leaderboard');
        const pitchingLeaders = await pitchingResponse.json();
        
        const pitchingTable = document.getElementById('pitchingLeaderboard');
        pitchingTable.innerHTML = '';
        
        pitchingLeaders.forEach((leader, index) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${index + 1}</td>
                <td>${leader.name}</td>
                <td>#${leader.jersey_number}</td>
                <td><strong>${leader.era?.toFixed(2) || '0.00'}</strong></td>
                <td>${leader.whip?.toFixed(2) || '0.00'}</td>
                <td>${leader.strikeouts || 0}</td>
            `;
            if (index === 0) row.classList.add('table-info');
            pitchingTable.appendChild(row);
        });
        
    } catch (error) {
        console.error('加载排行榜失败:', error);
        showAlert('加载排行榜失败', 'danger');
    }
}

// 加载打击可视化图表
async function loadBattingVisualization() {
    try {
        const response = await fetch('/api/visualization/batting');
        const data = await response.json();
        
        if (data.image) {
            document.getElementById('battingChart').innerHTML = `
                <div class="card">
                    <div class="card-body">
                        <h6 class="card-title">打击数据统计图表</h6>
                        <img src="${data.image}" class="img-fluid" alt="打击数据可视化">
                        <div class="mt-3">
                            <p><strong>统计摘要:</strong></p>
                            <ul>
                                <li>总打击球员数: ${data.total_batters}</li>
                                <li>平均打击率: ${data.avg_batting_average}</li>
                                <li>总安打数: ${data.total_hits}</li>
                            </ul>
                        </div>
                    </div>
                </div>
            `;
        } else {
            document.getElementById('battingChart').innerHTML = `
                <div class="alert alert-warning">
                    ${data.error || '无法生成图表'}
                </div>
            `;
        }
    } catch (error) {
        console.error('加载打击图表失败:', error);
        document.getElementById('battingChart').innerHTML = `
            <div class="alert alert-danger">
                加载图表失败: ${error.message}
            </div>
        `;
    }
}

// 加载投手可视化图表
async function loadPitchingVisualization() {
    try {
        const response = await fetch('/api/visualization/pitching');
        const data = await response.json();
        
        if (data.image) {
            document.getElementById('pitchingChart').innerHTML = `
                <div class="card">
                    <div class="card-body">
                        <h6 class="card-title">投手数据统计图表</h6>
                        <img src="${data.image}" class="img-fluid" alt="投手数据可视化">
                        <div class="mt-3">
                            <p><strong>统计摘要:</strong></p>
                            <ul>
                                <li>总投手数: ${data.total_pitchers}</li>
                                <li>平均防御率: ${data.avg_era}</li>
                                <li>总三振数: ${data.total_strikeouts}</li>
                            </ul>
                        </div>
                    </div>
                </div>
            `;
        } else {
            document.getElementById('pitchingChart').innerHTML = `
                <div class="alert alert-warning">
                    ${data.error || '无法生成图表'}
                </div>
            `;
        }
    } catch (error) {
        console.error('加载投手图表失败:', error);
        document.getElementById('pitchingChart').innerHTML = `
            <div class="alert alert-danger">
                加载图表失败: ${error.message}
            </div>
        `;
    }
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

// 根据打击率获取徽章颜色
function getAvgBadgeClass(average) {
    const avg = parseFloat(average);
    if (avg >= 0.300) return 'bg-success';
    if (avg >= 0.250) return 'bg-warning';
    return 'bg-secondary';
}

// 根据防御率获取徽章颜色
function getEraBadgeClass(era) {
    const eraValue = parseFloat(era);
    if (eraValue <= 3.00) return 'bg-success';
    if (eraValue <= 5.00) return 'bg-warning';
    return 'bg-danger';
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 默认加载打击数据
    loadBatters();
    loadPitchers();
    loadLeaderboards();
    
    // 监听标签页切换
    const tabEl = document.querySelector('#statsTabs');
    if (tabEl) {
        tabEl.addEventListener('shown.bs.tab', function(event) {
            const target = event.target.getAttribute('data-bs-target');
            
            if (target === '#battersTab') {
                loadBatters();
            } else if (target === '#pitchersTab') {
                loadPitchers();
            } else if (target === '#leaderboardsTab') {
                loadLeaderboards();
            }
        });
    }
});
