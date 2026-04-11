import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MPL_CACHE_DIR = os.path.join(PROJECT_ROOT, 'instance', 'matplotlib-cache')
os.makedirs(MPL_CACHE_DIR, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', MPL_CACHE_DIR)

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from functools import wraps
try:
    from flask_migrate import Migrate
except ModuleNotFoundError:
    Migrate = None
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
import sys
import io
from io import BytesIO
import base64
import plotly.express as px
import plotly.io as pio
from datetime import datetime, timezone
import json

from database import (
    db,
    init_db,
    Player,
    GameRecord,
    Position,
    FielderProfile,
    PitcherProfile,
    User,
)

# 设置 matplotlib 使用项目内缓存和本机可用的中文字体
MATPLOTLIB_CJK_FONTS = [
    'PingFang HK',
    'Hiragino Sans GB',
    'Songti SC',
    'Arial Unicode MS',
    'Heiti TC',
    'SimHei',
    'Microsoft YaHei',
    'DejaVu Sans',
]
matplotlib.rcParams['font.sans-serif'] = MATPLOTLIB_CJK_FONTS
matplotlib.rcParams['axes.unicode_minus'] = False

app = Flask(__name__)
os.makedirs(app.instance_path, exist_ok=True)
DATABASE_FILE = os.path.join(app.instance_path, 'baseball_players.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DATABASE_FILE}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['JSON_AS_ASCII'] = False

# 初始化数据库
init_db(app)
migrate = Migrate(app, db) if Migrate else None

# 初始化 Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_page'
login_manager.login_message = '请先登录管理员账号'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def admin_required(f):
    """管理员权限装饰器"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('需要管理员权限', 'error')
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function


# 登录/登出路由
@app.route('/login', methods=['GET'])
def login_page():
    """登录页面"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('login.html')


@app.route('/login', methods=['POST'])
def login_submit():
    """处理登录请求"""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    if not username or not password:
        flash('请输入用户名和密码', 'error')
        return redirect(url_for('login_page'))

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        login_user(user)
        flash('登录成功', 'success')
        return redirect(url_for('index'))
    else:
        flash('用户名或密码错误', 'error')
        return redirect(url_for('login_page'))


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    """登出"""
    logout_user()
    flash('已登出', 'success')
    return redirect(url_for('index'))

def _fielder_query():
    return Player.query.filter(Player._is_pitcher.is_(False))


def _pitcher_query():
    return Player.query.filter(Player._is_pitcher.is_(True))


def _batting_query():
    return Player.query.join(FielderProfile)


def _pitching_query():
    return Player.query.join(PitcherProfile).filter(Player._is_pitcher.is_(True))


def _normalize_player_payload(data, existing_player=None):
    raw_is_pitcher = data.get('is_pitcher')
    player_type = (data.get('player_type') or '').strip().lower()

    if raw_is_pitcher is None:
        if player_type:
            raw_is_pitcher = player_type in {'pitcher', '投手', 'true', '1'}
        elif existing_player:
            raw_is_pitcher = existing_player.is_pitcher
        else:
            raw_is_pitcher = False

    if isinstance(raw_is_pitcher, str):
        is_pitcher = raw_is_pitcher.strip().lower() in {'true', '1', 'yes', 'y', '是', 'pitcher', '投手'}
    else:
        is_pitcher = bool(raw_is_pitcher)

    name = (data.get('name') if data.get('name') is not None else getattr(existing_player, 'name', '')).strip()
    jersey_number = str(
        data.get('jersey_number') if data.get('jersey_number') is not None else getattr(existing_player, 'jersey_number', '')
    ).strip()

    if 'positions' in data:
        raw_positions = data.get('positions') or []
        positions = []
        for pos in raw_positions:
            value = (pos or '').strip()
            if value and value not in positions:
                positions.append(value)
    elif existing_player:
        positions = [pos.name for pos in existing_player.positions]
    else:
        positions = []

    primary_position = (
        data.get('primary_position')
        if data.get('primary_position') is not None
        else getattr(existing_player, 'primary_position', '')
    )
    primary_position = (primary_position or '').strip()

    if primary_position and primary_position not in positions:
        positions.append(primary_position)

    if is_pitcher:
        if '投手' not in positions:
            positions.insert(0, '投手')
    else:
        positions = [pos for pos in positions if pos != '投手']
        if primary_position == '投手':
            primary_position = ''

    if not positions and is_pitcher:
        positions = ['投手']

    if primary_position and primary_position not in positions:
        primary_position = positions[0] if positions else ''
    elif not primary_position and positions:
        primary_position = positions[0]

    return {
        'name': name,
        'jersey_number': jersey_number,
        'player_type': 'pitcher' if is_pitcher else 'fielder',
        'is_pitcher': is_pitcher,
        'positions': positions,
        'primary_position': primary_position,
    }


def _apply_player_profile(player, payload):
    player.name = payload['name']
    player.jersey_number = payload['jersey_number']
    player.is_pitcher = payload.get('is_pitcher', payload['player_type'] == 'pitcher')
    player.apply_player_type('pitcher' if player.is_pitcher else 'fielder')
    player.primary_position = payload['primary_position']
    player.set_positions_by_names(payload['positions'])
    player.normalize_positions()

@app.route('/')
def index():
    """首页"""
    players = Player.query.all()
    return render_template('index.html', players=players)

@app.route('/api/players', methods=['GET'])
def get_players():
    """获取所有球员数据"""
    players = Player.query.all()
    result = [p.to_dict() for p in players]
    return jsonify(result)

@app.route('/api/players', methods=['POST'])
@admin_required
def add_player():
    """添加新球员"""
    data = request.json or {}

    # 验证必填字段
    if not data.get('name') or not data.get('jersey_number'):
        return jsonify({'error': '姓名和背号为必填项'}), 400

    try:
        normalized = _normalize_player_payload(data)
        if not normalized['positions']:
            return jsonify({'error': '请至少选择一个位置'}), 400

        player = Player(join_date=datetime.now(timezone.utc).date())
        db.session.add(player)
        _apply_player_profile(player, normalized)
        player.update_calculated_fields()
        db.session.commit()

        return jsonify({
            'message': '球员添加成功',
            'player': player.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/players/<int:player_id>', methods=['GET'])
def get_player(player_id):
    """获取单个球员数据"""
    player = Player.query.get_or_404(player_id)
    return jsonify(player.to_dict())


@app.route('/api/players/<int:player_id>', methods=['PUT'])
@admin_required
def update_player(player_id):
    """更新球员信息"""
    player = Player.query.get_or_404(player_id)
    data = request.json or {}

    try:
        normalized = _normalize_player_payload(data, existing_player=player)
        if not normalized['positions']:
            return jsonify({'error': '请至少选择一个位置'}), 400

        _apply_player_profile(player, normalized)

        # 更新打击数据
        batting_fields = [
            'at_bats_total',     # 打数
            'hits_total',        # 安打
            'rbi_total',         # 打点
            'home_runs_batting', # 本垒打
            'runs_total',        # 得分
            'walks_total',       # 保送
            'strikeouts_batting_total',  # 三振
            'doubles',           # 二垒安打
            'triples',           # 三垒安打
            'stolen_bases',
            'hit_by_pitch',
            'caught_stealing',
            'sacrifice_flys',
            'sacrifice_hits',
            'errors_fielding',
            'passed_balls'
        ]
        
        # 更新字段
        for field in batting_fields:
            if field in data:
                value = data[field]
                try:
                    if value is None or value == '':
                        int_value = 0
                    else:
                        int_value = int(value)
                    setattr(player, field, int_value)
                except (ValueError, TypeError):
                    pass

        pitcher_fields = [
            'innings_pitched_total', 'hits_allowed_total', 'runs_allowed_total',
            'earned_runs_total', 'walks_allowed_total', 'strikeouts_total',
            'home_runs_allowed_total', 'pitches', 'strikes', 'hit_by_pitch_allowed',
            'batters_faced', 'wild_pitches'
        ]

        for field in pitcher_fields:
            if field in data:
                value = data[field]
                try:
                    if value is None or value == '':
                        parsed_value = 0.0 if field == 'innings_pitched_total' else 0
                    elif field == 'innings_pitched_total':
                        parsed_value = float(value)
                    else:
                        parsed_value = int(value)
                    setattr(player, field, parsed_value)
                except (ValueError, TypeError):
                    pass
        
        # 更新计算字段
        player.update_calculated_fields()

        db.session.commit()

        player_dict = player.to_dict()

        return jsonify({
            'message': '球员信息更新成功',
            'player': player_dict
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    
def update_player_stats(player, data):
    """更新球员统计字段"""
    # 打击数据
    stat_fields = [
        'at_bats_total', 'runs_total', 'hits_total', 'rbi_total',
        'walks_total', 'strikeouts_batting_total', 'doubles', 'triples',
        'home_runs_batting', 'stolen_bases', 'hit_by_pitch', 'caught_stealing',
        'sacrifice_flys', 'sacrifice_hits', 'total_bases', 'errors_fielding',
        'passed_balls', 'wild_pitches'
    ]
    
    for field in stat_fields:
        if field in data:
            if field in ['total_bases']:
                setattr(player, field, int(data[field]))
            else:
                setattr(player, field, int(data[field]))
    
    # 投手数据
    pitcher_fields = [
        'innings_pitched_total', 'hits_allowed_total', 'runs_allowed_total',
        'earned_runs_total', 'walks_allowed_total', 'strikeouts_total',
        'home_runs_allowed_total', 'pitches', 'strikes', 'hit_by_pitch_allowed',
        'batters_faced'
    ]
    
    for field in pitcher_fields:
        if field in data:
            if field in ['innings_pitched_total']:
                setattr(player, field, float(data[field]))
            else:
                setattr(player, field, int(data[field]))

@app.route('/api/players/<int:player_id>', methods=['DELETE'])
@admin_required
def delete_player(player_id):
    """删除球员"""
    player = Player.query.get_or_404(player_id)
    
    # 检查是否是最后一个球员
    total_players = Player.query.count()
    if total_players <= 1:
        return jsonify({'error': '不能删除最后一名球员'}), 400
    
    try:
        # 先删除相关的比赛记录
        GameRecord.query.filter_by(player_id=player_id).delete()
        
        # 再删除球员
        db.session.delete(player)
        db.session.commit()
        
        return jsonify({
            'message': '球员删除成功',
            'remaining_players': total_players - 1
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/players')
def players_page():
    """球员列表页面"""
    return render_template('players.html')

@app.route('/add_player')
@admin_required
def add_player_page():
    """添加球员页面"""
    return render_template('add_player.html')

@app.route('/stats')
def stats_page():
    """数据统计页面"""
    return render_template('stats.html')

@app.route('/api/stats/batting')
def batting_stats():
    """打击数据统计"""
    players = _batting_query().filter(FielderProfile.batting_average > 0).all()
    
    if not players:
        return jsonify({'error': '没有数据'}), 404
    
    data = [{
        'name': p.name,
        'position': p.primary_position or '未指定',
        'batting_average': p.batting_average,
        'home_runs': p.home_runs_batting,
        'rbi': p.rbi_total,
        'stolen_bases': p.stolen_bases
    } for p in players]
    
    return jsonify(data)

@app.route('/api/stats/pitching')
def pitching_stats():
    """投球数据统计"""
    players = _pitching_query().filter(PitcherProfile.era > 0).all()
    
    if not players:
        return jsonify({'error': '没有数据'}), 404
    
    data = [{
        'name': p.name,
        'position': p.primary_position or '未指定',
        'era': p.era,
        'whip': p.whip,
        'strikeouts': p.strikeouts_total,
        'innings': p.innings_pitched_total
    } for p in players]
    
    return jsonify(data)

@app.route('/api/stats/visualization')
def create_visualization():
    """创建可视化图表"""
    players = Player.query.all()
    
    if not players:
        return jsonify({'error': '没有数据'}), 404
    
    # 创建数据框
    df = pd.DataFrame([p.to_dict() for p in players])
    
    # 1. 打击率分布图
    plt.figure(figsize=(10, 6))
    plt.subplot(2, 2, 1)
    batting_players = df[df['batting_average'] > 0]
    if len(batting_players) > 0:
        plt.bar(batting_players['name'], batting_players['batting_average'])
        plt.title('球员打击率')
        plt.xlabel('球员')
        plt.ylabel('打击率')
        plt.xticks(rotation=45)
    
    # 2. 本垒打分布
    plt.subplot(2, 2, 2)
    hr_players = df[df['home_runs'] > 0]
    if len(hr_players) > 0:
        plt.bar(hr_players['name'], hr_players['home_runs'], color='orange')
        plt.title('球员本垒打数')
        plt.xlabel('球员')
        plt.ylabel('本垒打')
        plt.xticks(rotation=45)
    
    # 3. 安打数 vs 打点 散点图
    plt.subplot(2, 2, 3)
    if len(df) > 0:
        plt.scatter(df['hits_total'], df['rbi_total'])
        plt.title('安打 vs 打点')
        plt.xlabel('安打')
        plt.ylabel('打点')
    
    # 4. 防御率分布（投手）
    plt.subplot(2, 2, 4)
    pitcher_players = df[df['era'] > 0]
    if len(pitcher_players) > 0:
        plt.bar(pitcher_players['name'], pitcher_players['era'], color='green')
        plt.title('投手防御率 (越低越好)')
        plt.xlabel('球员')
        plt.ylabel('防御率')
        plt.xticks(rotation=45)
    
    plt.tight_layout()
    
    # 保存图表到内存
    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close()
    
    # 将图片转换为base64
    img_str = base64.b64encode(img_buffer.getvalue()).decode()
    
    return jsonify({
        'image': f'data:image/png;base64,{img_str}',
        'total_players': len(players),
        'batters': len(batting_players),
        'pitchers': len(pitcher_players)
    })

@app.route('/api/export/csv')
def export_csv():
    """导出数据为CSV"""
    players = Player.query.all()
    
    if not players:
        return jsonify({'error': '没有数据'}), 404
    
    df = pd.DataFrame([p.to_dict() for p in players])
    
    # 移除不需要的列
    df = df.drop([
        'id', 'fielder_profile', 'pitcher_profile',
        'has_fielder_profile', 'has_pitcher_profile'
    ], axis=1, errors='ignore')
    
    csv_buffer = BytesIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    csv_buffer.seek(0)
    
    return send_file(
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name='baseball_players_export.csv'
    )

@app.route('/api/players/batters', methods=['GET'])
def get_batters():
    """获取所有打击球员数据"""
    batters = _batting_query().all()
    result = []
    for batter in batters:
        stats = batter.get_batting_stats()
        # 获取位置显示
        position_display = batter.primary_position
        if not position_display and batter.positions:
            position_display = batter.positions[0].name if batter.positions else '未指定'
        
        result.append({
            'id': batter.id,
            'name': batter.name,
            'jersey_number': batter.jersey_number,
            'position': position_display,
            **stats
        })
    return jsonify(result)

@app.route('/api/players/pitchers', methods=['GET'])
def get_pitchers():
    """获取所有投手数据"""
    pitchers = _pitcher_query().all()
    result = []
    for pitcher in pitchers:
        stats = pitcher.get_pitching_stats()
        # 获取位置显示
        position_display = pitcher.primary_position
        if not position_display and pitcher.positions:
            position_display = pitcher.positions[0].name if pitcher.positions else '未指定'
        
        result.append({
            'id': pitcher.id,
            'name': pitcher.name,
            'jersey_number': pitcher.jersey_number,
            'position': position_display,
            **stats
        })
    return jsonify(result)

@app.route('/api/game_records', methods=['POST'])
@admin_required
def add_game_record():
    """添加比赛记录"""
    data = request.json
    player_id = data.get('player_id')
    is_pitching = data.get('is_pitching', False)
    
    player = Player.query.get(player_id)
    if not player:
        return jsonify({'error': '球员不存在'}), 404

    if is_pitching and not player.is_pitcher:
        return jsonify({'error': '当前球员是场员，不能录入投球记录'}), 400
    
    try:
        # 创建比赛记录
        game_record = GameRecord(
            player_id=player_id,
            opponent=data.get('opponent'),
            is_pitching_record=is_pitching,
            game_date=datetime.strptime(data.get('game_date'), '%Y-%m-%d').date()
        )
        
        if is_pitching:
            # 投手数据
            game_record.innings_pitched = float(data.get('innings_pitched', 0))
            game_record.hits_allowed = int(data.get('hits_allowed', 0))
            game_record.runs_allowed = int(data.get('runs_allowed', 0))
            game_record.earned_runs = int(data.get('earned_runs', 0))
            game_record.walks_allowed = int(data.get('walks_allowed', 0))
            game_record.strikeouts_pitched = int(data.get('strikeouts', 0))
            game_record.home_runs_allowed = int(data.get('home_runs_allowed', 0))
            game_record.win = data.get('win', False)
            game_record.loss = data.get('loss', False)
            game_record.save = data.get('save', False)

            # 新增投手数据
            game_record.pitches = int(data.get('pitches', 0))
            game_record.strikes = int(data.get('strikes', 0))
            game_record.hit_by_pitch_allowed = int(data.get('hit_by_pitch_allowed', 0))
            game_record.batters_faced = int(data.get('batters_faced', 0))
            
            # 更新球员累计数据
            player.pitches += game_record.pitches
            player.strikes += game_record.strikes
            player.hit_by_pitch_allowed += game_record.hit_by_pitch_allowed
            player.batters_faced += game_record.batters_faced
            
            # 更新球员累计数据
            player.innings_pitched_total += game_record.innings_pitched
            player.hits_allowed_total += game_record.hits_allowed
            player.runs_allowed_total += game_record.runs_allowed
            player.earned_runs_total += game_record.earned_runs
            player.walks_allowed_total += game_record.walks_allowed
            player.strikeouts_total += game_record.strikeouts_pitched
            player.home_runs_allowed_total += game_record.home_runs_allowed
        else:
            # 打击数据
            game_record.at_bats = int(data.get('at_bats', 0))
            game_record.runs = int(data.get('runs', 0))
            game_record.hits = int(data.get('hits', 0))
            game_record.rbi = int(data.get('rbi', 0))
            game_record.walks = int(data.get('walks', 0))
            game_record.strikeouts = int(data.get('strikeouts', 0))

            # 新增打击数据
            game_record.doubles = int(data.get('doubles', 0))
            game_record.triples = int(data.get('triples', 0))
            game_record.home_runs_batting = int(data.get('home_runs_game', 0))
            game_record.hit_by_pitch = int(data.get('hit_by_pitch', 0))
            game_record.stolen_bases = int(data.get('stolen_bases_game', 0))
            game_record.caught_stealing = int(data.get('caught_stealing', 0))
            game_record.sacrifice_flys = int(data.get('sacrifice_flys', 0))
            game_record.sacrifice_hits = int(data.get('sacrifice_hits', 0))
            
            # 计算总垒数
            game_record.total_bases = (
                game_record.hits - game_record.doubles - game_record.triples - 
                game_record.home_runs_batting +  # 一垒安打数
                game_record.doubles * 2 +
                game_record.triples * 3 +
                game_record.home_runs_batting * 4
            )
            
            # 更新球员累计数据
            player.doubles += game_record.doubles
            player.triples += game_record.triples
            player.home_runs_batting += game_record.home_runs_batting
            player.hit_by_pitch += game_record.hit_by_pitch
            player.stolen_bases += game_record.stolen_bases
            player.caught_stealing += game_record.caught_stealing
            player.sacrifice_flys += game_record.sacrifice_flys
            player.sacrifice_hits += game_record.sacrifice_hits
            player.total_bases += game_record.total_bases
            
            # 更新球员累计数据
            player.at_bats_total += game_record.at_bats
            player.runs_total += game_record.runs
            player.hits_total += game_record.hits
            player.rbi_total += game_record.rbi
            player.walks_total += game_record.walks
            player.strikeouts_batting_total += game_record.strikeouts
        
        # 更新计算字段
        player.update_calculated_fields()
        
        db.session.add(game_record)
        db.session.commit()
        
        return jsonify({
            'message': '比赛记录添加成功',
            'record_id': game_record.id,
            'updated_stats': player.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/api/stats/batting_leaderboard')
def batting_leaderboard():
    """打击排行榜"""
    batters = _batting_query().filter(FielderProfile.at_bats_total > 0).all()
    
    leaders = []
    for batter in batters:
        # 获取位置字符串 - 使用 primary_position 或 positions 中的第一个
        position_display = batter.primary_position
        if not position_display and batter.positions:
            position_display = batter.positions[0].name if batter.positions else '未指定'
        
        leaders.append({
            'name': batter.name,
            'jersey_number': batter.jersey_number,
            'position': position_display,  # 使用新的位置显示方式
            'avg': batter.batting_average,
            'obp': batter.on_base_percentage,
            'hits': batter.hits_total,
            'hr': batter.home_runs_batting,  # 使用 home_runs_batting 而不是 rbi_total
            'rbi': batter.rbi_total
        })
    
    # 按打击率排序
    leaders.sort(key=lambda x: x['avg'], reverse=True)
    
    return jsonify(leaders[:10])  # 返回前10名

@app.route('/api/stats/pitching_leaderboard')
def pitching_leaderboard():
    """投手排行榜"""
    pitchers = _pitcher_query().join(PitcherProfile).filter(PitcherProfile.innings_pitched_total > 0).all()
    
    leaders = []
    for pitcher in pitchers:
        # 获取位置字符串
        position_display = pitcher.primary_position
        if not position_display and pitcher.positions:
            position_display = pitcher.positions[0].name if pitcher.positions else '未指定'
        
        leaders.append({
            'name': pitcher.name,
            'jersey_number': pitcher.jersey_number,
            'position': position_display,
            'era': pitcher.era,
            'whip': pitcher.whip,
            'strikeouts': pitcher.strikeouts_total,
            'wins': 'N/A',  # 需要从比赛记录中计算
            'losses': 'N/A',
            'innings': pitcher.innings_pitched_total
        })
    
    # 按防御率排序（越低越好）
    leaders.sort(key=lambda x: x['era'])
    
    return jsonify(leaders[:10])

@app.route('/api/visualization/batting')
def batting_visualization():
    """打击数据可视化"""
    batters = _batting_query().filter(FielderProfile.at_bats_total > 0).all()
    
    if len(batters) < 3:
        return jsonify({'error': '打击数据不足'}), 404
    
    # 设置中文字体
    plt.rcParams['font.sans-serif'] = MATPLOTLIB_CJK_FONTS
    plt.rcParams['axes.unicode_minus'] = False
    
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    # 1. 打击率分布
    names = [b.name for b in batters]
    averages = [b.batting_average for b in batters]
    
    axes[0, 0].barh(names, averages, color='steelblue')
    axes[0, 0].set_xlabel('打击率', fontsize=10)
    axes[0, 0].set_title('球员打击率排行', fontsize=12, fontweight='bold')
    axes[0, 0].set_xlim(0, 0.5)
    
    # 2. 安打数分布
    hits = [b.hits_total for b in batters]
    axes[0, 1].bar(names, hits, color='darkorange')
    axes[0, 1].set_ylabel('安打数', fontsize=10)
    axes[0, 1].set_title('总安打数', fontsize=12, fontweight='bold')
    axes[0, 1].tick_params(axis='x', rotation=45)
    
    # 3. 打点分布
    rbis = [b.rbi_total for b in batters]
    axes[1, 0].bar(names, rbis, color='forestgreen')
    axes[1, 0].set_ylabel('打点', fontsize=10)
    axes[1, 0].set_title('总打点数', fontsize=12, fontweight='bold')
    axes[1, 0].tick_params(axis='x', rotation=45)
    
    # 4. 上垒率分布
    obps = [b.on_base_percentage for b in batters]
    axes[1, 1].barh(names, obps, color='purple')
    axes[1, 1].set_xlabel('上垒率', fontsize=10)
    axes[1, 1].set_title('上垒率排行', fontsize=12, fontweight='bold')
    axes[1, 1].set_xlim(0, 0.5)
    
    # ... 其他图表部分保持不变
    
    plt.tight_layout()
    
    # 保存图表到内存
    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close()
    
    img_str = base64.b64encode(img_buffer.getvalue()).decode()
    
    return jsonify({
        'image': f'data:image/png;base64,{img_str}',
        'total_batters': len(batters),
        'avg_batting_average': round(sum(averages) / len(averages), 3) if averages else 0,
        'total_hits': sum([b.hits_total for b in batters])
    })

@app.route('/api/visualization/pitching')
def pitching_visualization():
    """投手数据可视化"""
    pitchers = _pitcher_query().join(PitcherProfile).filter(PitcherProfile.innings_pitched_total > 10).all()
    
    if len(pitchers) < 2:
        return jsonify({'error': '投手数据不足'}), 404
    
    # 设置中文字体
    plt.rcParams['font.sans-serif'] = MATPLOTLIB_CJK_FONTS
    plt.rcParams['axes.unicode_minus'] = False
    
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    names = [p.name for p in pitchers]
    
    # 1. 防御率分布
    eras = [p.era for p in pitchers]
    axes[0, 0].bar(names, eras, color='crimson')
    axes[0, 0].set_ylabel('防御率 (越低越好)', fontsize=10)
    axes[0, 0].set_title('投手防御率', fontsize=12, fontweight='bold')
    axes[0, 0].tick_params(axis='x', rotation=45)
    
    # 2. 三振数
    strikeouts = [p.strikeouts_total for p in pitchers]
    axes[0, 1].bar(names, strikeouts, color='darkblue')
    axes[0, 1].set_ylabel('三振数')
    axes[0, 1].set_title('总三振数')
    axes[0, 1].tick_params(axis='x', rotation=45)
    
    # 3. WHIP分布
    whips = [p.whip for p in pitchers]
    axes[1, 0].bar(names, whips, color='darkgreen')
    axes[1, 0].set_ylabel('WHIP (越低越好)')
    axes[1, 0].set_title('每局被上垒率')
    axes[1, 0].tick_params(axis='x', rotation=45)
    
    # 4. 投球局数
    innings = [p.innings_pitched_total for p in pitchers]
    axes[1, 1].bar(names, innings, color='goldenrod')
    axes[1, 1].set_ylabel('投球局数')
    axes[1, 1].set_title('总投球局数')
    axes[1, 1].tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    
    # 保存图表
    img_buffer = BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close()
    
    img_str = base64.b64encode(img_buffer.getvalue()).decode()
    
    return jsonify({
        'image': f'data:image/png;base64,{img_str}',
        'total_pitchers': len(pitchers),
        'avg_era': round(sum(eras) / len(eras), 2),
        'total_strikeouts': sum(strikeouts)
    })

@app.route('/game_stats')
def game_stats_page():
    """比赛数据页面"""
    return render_template('game_stats.html')

@app.route('/add_game_record')
@admin_required
def add_game_record_page():
    """添加比赛记录页面"""
    players = Player.query.all()
    return render_template('add_game_record.html', players=players)

@app.route('/api/debug/players')
def debug_players():
    """调试：查看数据库中的所有球员"""
    players = Player.query.all()
    result = []
    for player in players:
        result.append({
            'id': player.id,
            'name': player.name,
            'jersey_number': player.jersey_number,
            'position': player.primary_position,
            'is_pitcher': player.is_pitcher
        })
    return jsonify({
        'total': len(result),
        'players': result
    })

@app.route('/debug')
def debug_page():
    """调试页面"""
    return render_template('debug.html')

@app.route('/pdf_viewer')
def pdf_viewer_page():
    """PDF查看器页面"""
    return render_template('pdf_viewer.html')

@app.route('/api/pdf/files')
def get_pdf_files():
    """获取所有PDF文件列表"""
    import os
    pdf_files = []
    
    # 遍历data文件夹下的所有年份文件夹
    data_dir = 'data'
    if os.path.exists(data_dir):
        for year in sorted(os.listdir(data_dir), reverse=True):  # 从最新年份开始
            year_path = os.path.join(data_dir, year)
            if os.path.isdir(year_path):
                for file in sorted(os.listdir(year_path)):
                    if file.lower().endswith('.pdf'):
                        file_path = os.path.join(year_path, file)
                        # 获取文件大小
                        file_size = os.path.getsize(file_path)
                        # 格式化文件大小
                        if file_size < 1024:
                            size_str = f"{file_size} B"
                        elif file_size < 1024 * 1024:
                            size_str = f"{file_size / 1024:.1f} KB"
                        else:
                            size_str = f"{file_size / (1024 * 1024):.1f} MB"
                        
                        # 关键修复：构建正确的相对路径
                        # 使用正斜杠，并且确保路径是 data/year/filename.pdf 格式
                        relative_path = f"{year}/{file}"
                        
                        pdf_files.append({
                            'year': year,
                            'filename': file,
                            'path': relative_path,  # 使用相对路径，而不是完整路径
                            'full_path': file_path.replace('\\', '/'),  # 保留完整路径用于调试
                            'size': size_str,
                            'display_name': file.replace('.pdf', '').replace('_', ' ')
                        })
    
    return jsonify(pdf_files)

@app.route('/api/pdf/view/<path:filepath>')
def view_pdf(filepath):
    """查看PDF文件"""
    import os
    import urllib.parse
    
    # 解码URL编码的文件路径
    decoded_filepath = urllib.parse.unquote(filepath)
    
    # 构建完整的文件路径
    full_path = os.path.join('data', decoded_filepath)
    
    # 安全检查：确保路径在data目录下
    full_path = os.path.normpath(full_path)
    if not full_path.startswith('data'):
        return jsonify({'error': '无效的文件路径'}), 400
    
    if not os.path.exists(full_path):
        return jsonify({'error': f'文件不存在: {full_path}'}), 404
    
    try:
        # 读取PDF文件内容
        with open(full_path, 'rb') as f:
            pdf_content = f.read()
        
        # 将PDF内容转换为base64
        import base64
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        return jsonify({
            'filename': os.path.basename(full_path),
            'content': pdf_base64,
            'mime_type': 'application/pdf'
        })
        
    except Exception as e:
        return jsonify({'error': f'读取文件失败: {str(e)}'}), 500

@app.route('/api/test/update_player', methods=['POST'])
def test_update_player():
    """测试更新球员数据"""
    data = request.json

    player = Player.query.first()
    if player:
        if 'home_runs_batting' in data:
            player.home_runs_batting = data['home_runs_batting']
        if 'rbi_total' in data:
            player.rbi_total = data['rbi_total']

        player.update_calculated_fields()
        db.session.commit()

        return jsonify({
            'message': '测试更新成功',
            'player': player.to_dict()
        })
    
    return jsonify({'error': '没有找到球员'}), 404

# 新增：对局信息相关路由
@app.route('/matchup_stats')
def matchup_stats_page():
    """对局信息页面"""
    return render_template('matchup_stats.html')


def _record_has_batting_data(record):
    if record.is_pitching_record:
        return False

    batting_values = [
        record.at_bats, record.runs, record.hits, record.rbi, record.walks,
        record.strikeouts, record.doubles, record.triples, record.home_runs_batting,
        record.stolen_bases, record.hit_by_pitch, record.caught_stealing,
        record.sacrifice_flys, record.sacrifice_hits
    ]
    return any((value or 0) != 0 for value in batting_values)


def _record_has_pitching_data(record):
    if not record.is_pitching_record:
        return False

    pitching_values = [
        record.innings_pitched, record.hits_allowed, record.runs_allowed,
        record.earned_runs, record.walks_allowed, record.strikeouts_pitched,
        record.home_runs_allowed, record.pitches, record.strikes,
        record.hit_by_pitch_allowed, record.batters_faced, record.wild_pitches
    ]
    return (
        any((value or 0) != 0 for value in pitching_values)
        or bool(record.win or record.loss or record.save)
    )


def _build_matchup_player_map(records):
    player_ids = sorted({record.player_id for record in records if record.player_id})
    if not player_ids:
        return {}

    players = Player.query.filter(Player.id.in_(player_ids)).all()
    return {player.id: player for player in players}


def _serialize_batting_matchup_record(record, player=None):
    at_bats = record.at_bats or 0
    hits = record.hits or 0
    batting_average = round(hits / at_bats, 3) if at_bats > 0 else 0.0

    return {
        'id': record.id,
        'player_id': record.player_id,
        'player_name': player.name if player else '未知球员',
        'player_jersey': player.jersey_number if player else '未知',
        'game_date': record.game_date.strftime('%Y-%m-%d'),
        'opponent': record.opponent or '未填写',
        'at_bats': at_bats,
        'runs': record.runs or 0,
        'hits': hits,
        'rbi': record.rbi or 0,
        'walks': record.walks or 0,
        'strikeouts': record.strikeouts or 0,
        'doubles': record.doubles or 0,
        'triples': record.triples or 0,
        'home_runs': record.home_runs_batting or 0,
        'stolen_bases': record.stolen_bases or 0,
        'batting_average': batting_average,
    }


def _serialize_pitching_matchup_record(record, player=None):
    innings_pitched = record.innings_pitched or 0.0
    hits_allowed = record.hits_allowed or 0
    walks_allowed = record.walks_allowed or 0
    earned_runs = record.earned_runs or 0
    pitches = record.pitches or 0
    strikes = record.strikes or 0

    era = round((earned_runs * 9) / innings_pitched, 2) if innings_pitched > 0 else 0.0
    whip = round((hits_allowed + walks_allowed) / innings_pitched, 2) if innings_pitched > 0 else 0.0
    strike_percentage = round((strikes / pitches) * 100, 1) if pitches > 0 else 0.0

    result_tags = []
    if record.win:
        result_tags.append('胜投')
    if record.loss:
        result_tags.append('败投')
    if record.save:
        result_tags.append('救援')

    return {
        'id': record.id,
        'player_id': record.player_id,
        'player_name': player.name if player else '未知球员',
        'player_jersey': player.jersey_number if player else '未知',
        'game_date': record.game_date.strftime('%Y-%m-%d'),
        'opponent': record.opponent or '未填写',
        'innings_pitched': innings_pitched,
        'hits_allowed': hits_allowed,
        'runs_allowed': record.runs_allowed or 0,
        'earned_runs': earned_runs,
        'walks_allowed': walks_allowed,
        'strikeouts': record.strikeouts_pitched or 0,
        'home_runs_allowed': record.home_runs_allowed or 0,
        'pitches': pitches,
        'strikes': strikes,
        'batters_faced': record.batters_faced or 0,
        'strike_percentage': strike_percentage,
        'era': era,
        'whip': whip,
        'result_text': ' / '.join(result_tags) if result_tags else '-',
    }


def _summarize_batting_records(records):
    if not records:
        return None

    summary = {
        'games': len(records),
        'at_bats': 0,
        'runs': 0,
        'hits': 0,
        'rbi': 0,
        'walks': 0,
        'strikeouts': 0,
        'doubles': 0,
        'triples': 0,
        'home_runs': 0,
        'stolen_bases': 0,
        'batting_average': 0.0,
    }

    for record in records:
        summary['at_bats'] += record['at_bats']
        summary['runs'] += record['runs']
        summary['hits'] += record['hits']
        summary['rbi'] += record['rbi']
        summary['walks'] += record['walks']
        summary['strikeouts'] += record['strikeouts']
        summary['doubles'] += record['doubles']
        summary['triples'] += record['triples']
        summary['home_runs'] += record['home_runs']
        summary['stolen_bases'] += record['stolen_bases']

    if summary['at_bats'] > 0:
        summary['batting_average'] = round(summary['hits'] / summary['at_bats'], 3)

    return summary


def _summarize_pitching_records(records):
    if not records:
        return None

    summary = {
        'games': len(records),
        'innings_pitched': 0.0,
        'hits_allowed': 0,
        'runs_allowed': 0,
        'earned_runs': 0,
        'walks_allowed': 0,
        'strikeouts': 0,
        'home_runs_allowed': 0,
        'pitches': 0,
        'strikes': 0,
        'batters_faced': 0,
        'wins': 0,
        'losses': 0,
        'saves': 0,
        'era': 0.0,
        'whip': 0.0,
        'strike_percentage': 0.0,
    }

    for record in records:
        summary['innings_pitched'] += record['innings_pitched']
        summary['hits_allowed'] += record['hits_allowed']
        summary['runs_allowed'] += record['runs_allowed']
        summary['earned_runs'] += record['earned_runs']
        summary['walks_allowed'] += record['walks_allowed']
        summary['strikeouts'] += record['strikeouts']
        summary['home_runs_allowed'] += record['home_runs_allowed']
        summary['pitches'] += record['pitches']
        summary['strikes'] += record['strikes']
        summary['batters_faced'] += record['batters_faced']
        summary['wins'] += 1 if '胜投' in record['result_text'] else 0
        summary['losses'] += 1 if '败投' in record['result_text'] else 0
        summary['saves'] += 1 if '救援' in record['result_text'] else 0

    if summary['innings_pitched'] > 0:
        summary['era'] = round((summary['earned_runs'] * 9) / summary['innings_pitched'], 2)
        summary['whip'] = round(
            (summary['hits_allowed'] + summary['walks_allowed']) / summary['innings_pitched'],
            2
        )

    if summary['pitches'] > 0:
        summary['strike_percentage'] = round((summary['strikes'] / summary['pitches']) * 100, 1)

    return summary


def _build_matchup_title(player=None, opponent=''):
    if player and opponent:
        return f'{player.name} 对阵 {opponent}'
    if player:
        return f'{player.name} 的全部比赛记录'
    if opponent:
        return f'全队对阵 {opponent} 的比赛记录'
    return '全部比赛记录'


def _build_matchup_payload(records, player=None, opponent=''):
    player_map = _build_matchup_player_map(records)
    batting_records = [
        _serialize_batting_matchup_record(record, player_map.get(record.player_id))
        for record in records
        if _record_has_batting_data(record)
    ]
    pitching_records = [
        _serialize_pitching_matchup_record(record, player_map.get(record.player_id))
        for record in records
        if _record_has_pitching_data(record)
    ]

    return {
        'title': _build_matchup_title(player=player, opponent=opponent),
        'filters': {
            'player_id': player.id if player else None,
            'player_name': player.name if player else '',
            'opponent': opponent,
        },
        'batting_records': batting_records,
        'pitching_records': pitching_records,
        'batting_summary': _summarize_batting_records(batting_records),
        'pitching_summary': _summarize_pitching_records(pitching_records),
    }

@app.route('/api/matchup/opponents')
def get_opponents():
    """获取所有对手列表"""
    opponents = (
        db.session.query(GameRecord.opponent)
        .distinct()
        .filter(GameRecord.opponent.isnot(None))
        .order_by(GameRecord.opponent.asc())
        .all()
    )
    opponent_list = [opponent[0] for opponent in opponents if opponent[0]]
    return jsonify(opponent_list)


@app.route('/api/matchup/search_records')
def search_matchup_records():
    """按球员、对手或两者组合筛选比赛记录。"""
    player_id = request.args.get('player_id', type=int)
    opponent = (request.args.get('opponent') or '').strip()

    if not player_id and not opponent:
        return jsonify({'error': '请至少选择一个筛选条件'}), 400

    query = GameRecord.query
    player = None

    if player_id:
        player = Player.query.get(player_id)
        if not player:
            return jsonify({'error': '球员不存在'}), 404
        query = query.filter(GameRecord.player_id == player_id)

    if opponent:
        query = query.filter(GameRecord.opponent == opponent)

    records = query.order_by(GameRecord.game_date.desc(), GameRecord.id.desc()).all()
    return jsonify(_build_matchup_payload(records, player=player, opponent=opponent))

@app.route('/api/matchup/player_vs_opponent')
def get_player_vs_opponent_stats():
    """获取球员对阵特定对手的历史数据"""
    player_id = request.args.get('player_id', type=int)
    opponent = request.args.get('opponent')
    
    if not player_id or not opponent:
        return jsonify({'error': '缺少参数'}), 400
    
    # 获取该球员对阵该对手的所有比赛记录
    records = GameRecord.query.filter_by(
        player_id=player_id,
        opponent=opponent
    ).order_by(GameRecord.game_date.desc()).all()
    
    if not records:
        return jsonify({'error': '没有找到相关比赛记录'}), 404
    
    # 计算累计数据
    total_stats = {
        'games': len(records),
        'at_bats': 0,
        'runs': 0,
        'hits': 0,
        'rbi': 0,
        'walks': 0,
        'strikeouts': 0,
        'doubles': 0,
        'triples': 0,
        'home_runs': 0,
        'stolen_bases': 0,
        'batting_average': 0.0
    }
    
    for record in records:
        total_stats['at_bats'] += record.at_bats or 0
        total_stats['runs'] += record.runs or 0
        total_stats['hits'] += record.hits or 0
        total_stats['rbi'] += record.rbi or 0
        total_stats['walks'] += record.walks or 0
        total_stats['strikeouts'] += record.strikeouts or 0
        total_stats['doubles'] += record.doubles or 0
        total_stats['triples'] += record.triples or 0
        total_stats['home_runs'] += record.home_runs_batting or 0
        total_stats['stolen_bases'] += record.stolen_bases or 0
    
    # 计算打击率
    if total_stats['at_bats'] > 0:
        total_stats['batting_average'] = round(total_stats['hits'] / total_stats['at_bats'], 3)
    
    # 格式化比赛记录
    formatted_records = []
    for record in records:
        formatted_records.append({
            'game_date': record.game_date.strftime('%Y-%m-%d'),
            'opponent': record.opponent,
            'at_bats': record.at_bats or 0,
            'runs': record.runs or 0,
            'hits': record.hits or 0,
            'rbi': record.rbi or 0,
            'walks': record.walks or 0,
            'strikeouts': record.strikeouts or 0,
            'doubles': record.doubles or 0,
            'triples': record.triples or 0,
            'home_runs': record.home_runs_batting or 0,
            'stolen_bases': record.stolen_bases or 0,
            'is_pitching': record.is_pitching_record
        })
    
    return jsonify({
        'total_stats': total_stats,
        'game_records': formatted_records
    })

@app.route('/api/matchup/player_game_records')
def get_player_game_records():
    """获取球员的所有比赛记录"""
    player_id = request.args.get('player_id', type=int)
    
    if not player_id:
        return jsonify({'error': '缺少参数'}), 400
    
    records = GameRecord.query.filter_by(player_id=player_id).order_by(GameRecord.game_date.desc()).all()
    
    formatted_records = []
    for record in records:
        formatted_records.append({
            'id': record.id,
            'game_date': record.game_date.strftime('%Y-%m-%d'),
            'opponent': record.opponent,
            'at_bats': record.at_bats or 0,
            'runs': record.runs or 0,
            'hits': record.hits or 0,
            'rbi': record.rbi or 0,
            'walks': record.walks or 0,
            'strikeouts': record.strikeouts or 0,
            'doubles': record.doubles or 0,
            'triples': record.triples or 0,
            'home_runs': record.home_runs_batting or 0,
            'stolen_bases': record.stolen_bases or 0,
            'is_pitching': record.is_pitching_record
        })
    
    return jsonify(formatted_records)

@app.route('/api/matchup/all_game_records')
def get_all_game_records():
    """获取所有队员的比赛记录"""
    records = GameRecord.query.order_by(GameRecord.game_date.desc(), GameRecord.id.desc()).all()
    return jsonify(_build_matchup_payload(records))

@app.route('/api/matchup/game_record/<int:record_id>', methods=['DELETE'])
@admin_required
def delete_game_record(record_id):
    """删除比赛记录"""
    record = GameRecord.query.get_or_404(record_id)
    
    try:
        # 获取球员信息
        player = Player.query.get(record.player_id)
        
        # 从球员累计数据中减去这场比赛的数据，确保不会出现负数
        def safe_subtract(current_value, subtract_value, field_name):
            """安全减法，确保结果不小于0"""
            result = current_value - subtract_value
            return max(result, 0)
        
        if record.is_pitching_record:
            # 投手数据
            player.innings_pitched_total = safe_subtract(player.innings_pitched_total, record.innings_pitched or 0, 'innings_pitched_total')
            player.hits_allowed_total = safe_subtract(player.hits_allowed_total, record.hits_allowed or 0, 'hits_allowed_total')
            player.runs_allowed_total = safe_subtract(player.runs_allowed_total, record.runs_allowed or 0, 'runs_allowed_total')
            player.earned_runs_total = safe_subtract(player.earned_runs_total, record.earned_runs or 0, 'earned_runs_total')
            player.walks_allowed_total = safe_subtract(player.walks_allowed_total, record.walks_allowed or 0, 'walks_allowed_total')
            player.strikeouts_total = safe_subtract(player.strikeouts_total, record.strikeouts_pitched or 0, 'strikeouts_total')
            player.home_runs_allowed_total = safe_subtract(player.home_runs_allowed_total, record.home_runs_allowed or 0, 'home_runs_allowed_total')
            player.pitches = safe_subtract(player.pitches, record.pitches or 0, 'pitches')
            player.strikes = safe_subtract(player.strikes, record.strikes or 0, 'strikes')
            player.hit_by_pitch_allowed = safe_subtract(player.hit_by_pitch_allowed, record.hit_by_pitch_allowed or 0, 'hit_by_pitch_allowed')
            player.batters_faced = safe_subtract(player.batters_faced, record.batters_faced or 0, 'batters_faced')
        else:
            # 打击数据
            player.at_bats_total = safe_subtract(player.at_bats_total, record.at_bats or 0, 'at_bats_total')
            player.runs_total = safe_subtract(player.runs_total, record.runs or 0, 'runs_total')
            player.hits_total = safe_subtract(player.hits_total, record.hits or 0, 'hits_total')
            player.rbi_total = safe_subtract(player.rbi_total, record.rbi or 0, 'rbi_total')
            player.walks_total = safe_subtract(player.walks_total, record.walks or 0, 'walks_total')
            player.strikeouts_batting_total = safe_subtract(player.strikeouts_batting_total, record.strikeouts or 0, 'strikeouts_batting_total')
            player.doubles = safe_subtract(player.doubles, record.doubles or 0, 'doubles')
            player.triples = safe_subtract(player.triples, record.triples or 0, 'triples')
            player.home_runs_batting = safe_subtract(player.home_runs_batting, record.home_runs_batting or 0, 'home_runs_batting')
            player.stolen_bases = safe_subtract(player.stolen_bases, record.stolen_bases or 0, 'stolen_bases')
            player.hit_by_pitch = safe_subtract(player.hit_by_pitch, record.hit_by_pitch or 0, 'hit_by_pitch')
            player.caught_stealing = safe_subtract(player.caught_stealing, record.caught_stealing or 0, 'caught_stealing')
            player.sacrifice_flys = safe_subtract(player.sacrifice_flys, record.sacrifice_flys or 0, 'sacrifice_flys')
            player.sacrifice_hits = safe_subtract(player.sacrifice_hits, record.sacrifice_hits or 0, 'sacrifice_hits')
            player.total_bases = safe_subtract(player.total_bases, record.total_bases or 0, 'total_bases')
        
        # 重新计算球员的统计字段
        player.update_calculated_fields()
        
        # 删除比赛记录
        db.session.delete(record)
        db.session.commit()
        
        return jsonify({
            'message': '比赛记录删除成功',
            'player_name': player.name,
            'opponent': record.opponent,
            'game_date': record.game_date.strftime('%Y-%m-%d')
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400

@app.route('/import_pdf')
def import_pdf_page():
    """PDF批量导入页面"""
    return render_template('import_pdf.html')

@app.route('/api/pdf/parse/<path:filepath>')
def api_parse_pdf(filepath):
    """解析单个PDF文件（不写入数据库）"""
    import os
    import urllib.parse

    decoded = urllib.parse.unquote(filepath)
    full_path = os.path.join('data', decoded)
    full_path = os.path.normpath(full_path)
    if not full_path.startswith('data'):
        return jsonify({'error': '无效路径'}), 400
    if not os.path.exists(full_path):
        return jsonify({'error': '文件不存在'}), 404

    try:
        from pdf_parser import parse_pdf
        result = parse_pdf(full_path)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pdf/import_all', methods=['POST'])
@admin_required
def api_import_all_pdfs():
    """批量导入所有PDF"""
    dry_run = request.json.get('dry_run', False) if request.json else False
    try:
        from import_pdfs import import_all_pdfs
        results = import_all_pdfs(dry_run=dry_run)
        return jsonify({'results': results, 'dry_run': dry_run})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/pdf/import_one', methods=['POST'])
@admin_required
def api_import_one_pdf():
    """导入单个PDF"""
    data = request.json or {}
    filepath = data.get('filepath')
    if not filepath:
        return jsonify({'error': '缺少 filepath'}), 400

    import os
    full_path = os.path.join('data', filepath)
    full_path = os.path.normpath(full_path)
    if not full_path.startswith('data'):
        return jsonify({'error': '无效路径'}), 400
    if not os.path.exists(full_path):
        return jsonify({'error': '文件不存在'}), 404

    try:
        from pdf_parser import parse_pdf
        from import_pdfs import import_game_record
        parsed = parse_pdf(full_path)
        if 'error' in parsed:
            return jsonify({'error': parsed['error']}), 400
        result = import_game_record(parsed, dry_run=False)
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/upload_pdf')
@admin_required
def upload_pdf_page():
    """PDF上传导入页面"""
    return render_template('upload_pdf.html')

@app.route('/api/pdf/upload', methods=['POST'])
@admin_required
def api_upload_pdf():
    """上传PDF文件并解析导入比赛数据"""
    if 'file' not in request.files:
        return jsonify({'error': '未找到上传文件'}), 400

    file = request.files['file']
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': '只支持PDF文件'}), 400

    # 保存上传的文件到临时目录
    upload_dir = os.path.join(PROJECT_ROOT, 'data', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)

    from werkzeug.utils import secure_filename
    safe_name = secure_filename(file.filename)
    if not safe_name:
        safe_name = 'upload.pdf'
    filepath = os.path.join(upload_dir, safe_name)
    file.save(filepath)

    try:
        from pdf_parser import parse_pdf
        from import_pdfs import import_game_record
        parsed = parse_pdf(filepath)

        if 'error' in parsed:
            return jsonify({'error': parsed['error']}), 400

        # 先返回解析预览，不直接导入
        batting_preview = []
        for b in parsed.get('my_team_batting', []):
            batting_preview.append({
                'name': b['name'],
                'jersey_number': b.get('jersey_number'),
                'position': b.get('position'),
                'at_bats': b['at_bats'],
                'runs': b['runs'],
                'hits': b['hits'],
                'rbi': b['rbi'],
                'walks': b['walks'],
                'strikeouts': b['strikeouts'],
                'doubles': b.get('doubles', 0),
                'triples': b.get('triples', 0),
                'home_runs': b.get('home_runs', 0),
                'stolen_bases': b.get('stolen_bases', 0),
            })

        pitching_preview = []
        for p in parsed.get('my_team_pitching', []):
            pitching_preview.append({
                'name': p['name'],
                'jersey_number': p.get('jersey_number'),
                'innings_pitched': p['innings_pitched'],
                'hits_allowed': p['hits_allowed'],
                'runs_allowed': p['runs_allowed'],
                'earned_runs': p['earned_runs'],
                'walks_allowed': p['walks_allowed'],
                'strikeouts': p['strikeouts'],
                'home_runs_allowed': p['home_runs_allowed'],
                'pitches': p.get('pitches', 0),
                'strikes': p.get('strikes', 0),
                'batters_faced': p.get('batters_faced', 0),
                'win': p.get('win', False),
                'loss': p.get('loss', False),
                'save': p.get('save', False),
            })

        return jsonify({
            'status': 'parsed',
            'filepath': filepath,
            'game_date': parsed.get('game_date'),
            'opponent': parsed.get('opponent'),
            'batting': batting_preview,
            'pitching': pitching_preview,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'解析PDF失败: {str(e)}'}), 500


@app.route('/api/pdf/confirm_import', methods=['POST'])
@admin_required
def api_confirm_import():
    """确认导入已解析的PDF数据"""
    data = request.json or {}
    filepath = data.get('filepath')
    if not filepath:
        return jsonify({'error': '缺少文件路径'}), 400

    if not os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404

    try:
        from pdf_parser import parse_pdf
        from import_pdfs import import_game_record
        parsed = parse_pdf(filepath)
        if 'error' in parsed:
            return jsonify({'error': parsed['error']}), 400

        result = import_game_record(parsed, dry_run=False)
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # 从环境变量获取端口，Render 会自动注入 PORT 变量，如果没有则默认 5000
    port = int(os.environ.get("PORT", 5000))
    # 必须设置 host='0.0.0.0' 才能让外网访问
    # use_reloader=False 避免 Windows 上的 I/O 问题
    app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False)