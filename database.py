from datetime import datetime, timezone
import random

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from sqlalchemy.ext.hybrid import hybrid_property

db = SQLAlchemy()

DEFAULT_POSITIONS = [
    '投手', '捕手', '一垒手', '二垒手', '三垒手', '游击手',
    '左外野手', '中外野手', '右外野手'
]

FIELDER_PROFILE_DEFAULTS = {
    'at_bats_total': 0,
    'runs_total': 0,
    'hits_total': 0,
    'rbi_total': 0,
    'walks_total': 0,
    'strikeouts_batting_total': 0,
    'batting_average': 0.0,
    'on_base_percentage': 0.0,
    'slugging_percentage': 0.0,
    'ops': 0.0,
    'doubles': 0,
    'triples': 0,
    'home_runs_batting': 0,
    'total_bases': 0,
    'hit_by_pitch': 0,
    'stolen_bases': 0,
    'caught_stealing': 0,
    'sacrifice_flys': 0,
    'sacrifice_hits': 0,
    'errors_fielding': 0,
    'passed_balls': 0,
}

PITCHER_PROFILE_DEFAULTS = {
    'innings_pitched_total': 0.0,
    'hits_allowed_total': 0,
    'runs_allowed_total': 0,
    'earned_runs_total': 0,
    'walks_allowed_total': 0,
    'strikeouts_total': 0,
    'home_runs_allowed_total': 0,
    'pitches': 0,
    'strikes': 0,
    'hit_by_pitch_allowed': 0,
    'batters_faced': 0,
    'era': 0.0,
    'whip': 0.0,
    'strike_percentage': 0.0,
    'wild_pitches': 0,
}

LEGACY_FIELDER_FIELDS = [
    'at_bats_total', 'runs_total', 'hits_total', 'rbi_total', 'walks_total',
    'strikeouts_batting_total', 'doubles', 'triples', 'home_runs_batting',
    'total_bases', 'hit_by_pitch', 'stolen_bases', 'caught_stealing',
    'sacrifice_flys', 'sacrifice_hits', 'errors_fielding', 'passed_balls',
]

LEGACY_PITCHER_FIELDS = [
    'innings_pitched_total', 'hits_allowed_total', 'runs_allowed_total',
    'earned_runs_total', 'walks_allowed_total', 'strikeouts_total',
    'home_runs_allowed_total', 'pitches', 'strikes', 'hit_by_pitch_allowed',
    'batters_faced', 'wild_pitches',
]


# 创建球员-位置关联表（多对多关系）
player_positions = db.Table(
    'player_positions',
    db.Column('player_id', db.Integer, db.ForeignKey('players.id'), primary_key=True),
    db.Column('position_id', db.Integer, db.ForeignKey('positions.id'), primary_key=True)
)


class Position(db.Model):
    """守备位置表"""
    __tablename__ = 'positions'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False, unique=True)
    description = db.Column(db.String(100))

    def __repr__(self):
        return self.name


class Player(db.Model):
    """球员主表：只保留基础资料和角色信息。比赛汇总拆到档案表里。"""
    __tablename__ = 'players'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    jersey_number = db.Column(db.String(10), nullable=False)
    primary_position = db.Column(db.String(50))
    _is_pitcher = db.Column('is_pitcher', db.Boolean, default=False)
    birth_date = db.Column(db.Date)
    join_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    contact_phone = db.Column(db.String(20))

    positions = db.relationship(
        'Position',
        secondary=player_positions,
        lazy='subquery',
        backref=db.backref('players', lazy=True)
    )
    fielder_profile = db.relationship(
        'FielderProfile',
        back_populates='player',
        uselist=False,
        cascade='all, delete-orphan',
        lazy='selectin'
    )
    pitcher_profile = db.relationship(
        'PitcherProfile',
        back_populates='player',
        uselist=False,
        cascade='all, delete-orphan',
        lazy='selectin'
    )

    @hybrid_property
    def is_pitcher(self):
        return bool(self._is_pitcher)

    @is_pitcher.setter
    def is_pitcher(self, value):
        self._is_pitcher = bool(value)

    @is_pitcher.expression
    def is_pitcher(cls):
        return cls._is_pitcher

    @property
    def player_type(self):
        return 'pitcher' if self.is_pitcher else 'fielder'

    def ensure_fielder_profile(self):
        if not self.fielder_profile:
            self.fielder_profile = FielderProfile()
        return self.fielder_profile

    def ensure_pitcher_profile(self):
        if not self.pitcher_profile:
            self.pitcher_profile = PitcherProfile()
        return self.pitcher_profile

    def apply_player_type(self, player_type):
        normalized = str(player_type or '').strip().lower()
        self._is_pitcher = normalized in {'pitcher', '投手', 'true', '1'}
        self.ensure_fielder_profile()
        if self._is_pitcher:
            self.ensure_pitcher_profile()
        self.normalize_positions()

    def set_positions_by_names(self, position_names):
        normalized_names = []
        for name in position_names or []:
            value = (name or '').strip()
            if value and value not in normalized_names:
                normalized_names.append(value)

        self.positions.clear()
        for pos_name in normalized_names:
            pos_obj = Position.query.filter_by(name=pos_name).first()
            if not pos_obj:
                pos_obj = Position(name=pos_name)
                db.session.add(pos_obj)
            self.positions.append(pos_obj)

    def normalize_positions(self):
        pitcher_position = Position.query.filter_by(name='投手').first()
        current_positions = list(self.positions)
        filtered_positions = [pos for pos in current_positions if pos.name != '投手']

        if self.is_pitcher:
            pitcher_entry = pitcher_position or next(
                (pos for pos in current_positions if pos.name == '投手'),
                None
            )
            if pitcher_entry:
                filtered_positions.insert(0, pitcher_entry)
            self.positions = filtered_positions
            self.ensure_pitcher_profile()
        else:
            self.positions = filtered_positions

        if not self.primary_position or all(pos.name != self.primary_position for pos in self.positions):
            if self.positions:
                self.primary_position = self.positions[0].name
            else:
                self.primary_position = '投手' if self.is_pitcher else '未指定'

        self.ensure_fielder_profile()

    def update_calculated_fields(self):
        if self.fielder_profile:
            self.fielder_profile.update_calculated_fields()
        if self.pitcher_profile:
            self.pitcher_profile.update_calculated_fields()

    def get_positions_string(self):
        if not self.positions:
            return self.primary_position or '未指定'
        return ', '.join([pos.name for pos in self.positions])

    def get_batting_stats(self):
        return {
            '打数': self.at_bats_total,
            '得分': self.runs_total,
            '安打': self.hits_total,
            '打点': self.rbi_total,
            '保送': self.walks_total,
            '三振': self.strikeouts_batting_total,
            '打击率': f"{self.batting_average:.3f}",
            '上垒率': f"{self.on_base_percentage:.3f}"
        }

    def get_pitching_stats(self):
        return {
            '局数': self.innings_pitched_total,
            '被打安打': self.hits_allowed_total,
            '被得分': self.runs_allowed_total,
            '自责分': self.earned_runs_total,
            '保送': self.walks_allowed_total,
            '三振': self.strikeouts_total,
            '被打本垒打': self.home_runs_allowed_total,
            '防御率': f"{self.era:.2f}",
            'WHIP': f"{self.whip:.2f}"
        }

    def to_dict(self):
        data = {
            'id': self.id,
            'name': self.name,
            'jersey_number': self.jersey_number,
            'primary_position': self.primary_position,
            'positions': [pos.name for pos in self.positions],
            'positions_string': self.get_positions_string(),
            'is_pitcher': self.is_pitcher,
            'player_type': self.player_type,
            'has_fielder_profile': self.fielder_profile is not None,
            'has_pitcher_profile': self.pitcher_profile is not None,

            # 兼容旧前端的扁平字段
            'at_bats_total': self.at_bats_total,
            'runs_total': self.runs_total,
            'hits_total': self.hits_total,
            'rbi_total': self.rbi_total,
            'walks_total': self.walks_total,
            'strikeouts_batting_total': self.strikeouts_batting_total,
            'doubles': self.doubles,
            'triples': self.triples,
            'home_runs_batting': self.home_runs_batting,
            'stolen_bases': self.stolen_bases,
            'hit_by_pitch': self.hit_by_pitch,
            'caught_stealing': self.caught_stealing,
            'sacrifice_flys': self.sacrifice_flys,
            'sacrifice_hits': self.sacrifice_hits,
            'total_bases': self.total_bases,
            'errors_fielding': self.errors_fielding,
            'passed_balls': self.passed_balls,
            'batting_average': self.batting_average,
            'on_base_percentage': self.on_base_percentage,
            'slugging_percentage': self.slugging_percentage,
            'ops': self.ops,
            'position': self.primary_position,
            'home_runs': self.home_runs_batting,

            'fielder_profile': self.fielder_profile.to_dict() if self.fielder_profile else None,
            'pitcher_profile': self.pitcher_profile.to_dict() if self.pitcher_profile else None,
        }

        if self.pitcher_profile:
            data.update({
                'innings_pitched_total': self.innings_pitched_total,
                'hits_allowed_total': self.hits_allowed_total,
                'runs_allowed_total': self.runs_allowed_total,
                'earned_runs_total': self.earned_runs_total,
                'walks_allowed_total': self.walks_allowed_total,
                'strikeouts_total': self.strikeouts_total,
                'home_runs_allowed_total': self.home_runs_allowed_total,
                'pitches': self.pitches,
                'strikes': self.strikes,
                'hit_by_pitch_allowed': self.hit_by_pitch_allowed,
                'batters_faced': self.batters_faced,
                'wild_pitches': self.wild_pitches,
                'era': self.era,
                'whip': self.whip,
                'strike_percentage': self.strike_percentage,
            })

        return data


class FielderProfile(db.Model):
    """场员/野手档案：负责打击和守备汇总。"""
    __tablename__ = 'fielder_profiles'

    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), primary_key=True)
    at_bats_total = db.Column(db.Integer, default=0)
    runs_total = db.Column(db.Integer, default=0)
    hits_total = db.Column(db.Integer, default=0)
    rbi_total = db.Column(db.Integer, default=0)
    walks_total = db.Column(db.Integer, default=0)
    strikeouts_batting_total = db.Column(db.Integer, default=0)

    batting_average = db.Column(db.Float, default=0.0)
    on_base_percentage = db.Column(db.Float, default=0.0)
    slugging_percentage = db.Column(db.Float, default=0.0)
    ops = db.Column(db.Float, default=0.0)

    doubles = db.Column(db.Integer, default=0)
    triples = db.Column(db.Integer, default=0)
    home_runs_batting = db.Column(db.Integer, default=0)
    total_bases = db.Column(db.Integer, default=0)
    hit_by_pitch = db.Column(db.Integer, default=0)
    stolen_bases = db.Column(db.Integer, default=0)
    caught_stealing = db.Column(db.Integer, default=0)
    sacrifice_flys = db.Column(db.Integer, default=0)
    sacrifice_hits = db.Column(db.Integer, default=0)
    errors_fielding = db.Column(db.Integer, default=0)
    passed_balls = db.Column(db.Integer, default=0)

    player = db.relationship('Player', back_populates='fielder_profile')

    def update_calculated_fields(self):
        self.at_bats_total = self.at_bats_total or 0
        self.hits_total = self.hits_total or 0
        self.walks_total = self.walks_total or 0
        self.hit_by_pitch = self.hit_by_pitch or 0
        self.sacrifice_flys = self.sacrifice_flys or 0
        self.doubles = self.doubles or 0
        self.triples = self.triples or 0
        self.home_runs_batting = self.home_runs_batting or 0

        if self.at_bats_total > 0:
            self.batting_average = round(self.hits_total / self.at_bats_total, 3)
        else:
            self.batting_average = 0.0

        singles = self.hits_total - self.doubles - self.triples - self.home_runs_batting
        singles = max(singles, 0)
        self.total_bases = singles + (self.doubles * 2) + (self.triples * 3) + (self.home_runs_batting * 4)

        if self.at_bats_total > 0:
            self.slugging_percentage = round(self.total_bases / self.at_bats_total, 3)
        else:
            self.slugging_percentage = 0.0

        plate_appearances = self.at_bats_total + self.walks_total + self.hit_by_pitch + self.sacrifice_flys
        if plate_appearances > 0:
            numerator = self.hits_total + self.walks_total + self.hit_by_pitch
            self.on_base_percentage = round(numerator / plate_appearances, 3)
        else:
            self.on_base_percentage = 0.0

        self.ops = round(self.on_base_percentage + self.slugging_percentage, 3)

    def to_dict(self):
        return {
            'player_id': self.player_id,
            **{field: getattr(self, field) for field in FIELDER_PROFILE_DEFAULTS}
        }


class PitcherProfile(db.Model):
    """投手档案：负责投球汇总。"""
    __tablename__ = 'pitcher_profiles'

    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), primary_key=True)
    innings_pitched_total = db.Column(db.Float, default=0.0)
    hits_allowed_total = db.Column(db.Integer, default=0)
    runs_allowed_total = db.Column(db.Integer, default=0)
    earned_runs_total = db.Column(db.Integer, default=0)
    walks_allowed_total = db.Column(db.Integer, default=0)
    strikeouts_total = db.Column(db.Integer, default=0)
    home_runs_allowed_total = db.Column(db.Integer, default=0)
    pitches = db.Column(db.Integer, default=0)
    strikes = db.Column(db.Integer, default=0)
    hit_by_pitch_allowed = db.Column(db.Integer, default=0)
    batters_faced = db.Column(db.Integer, default=0)
    era = db.Column(db.Float, default=0.0)
    whip = db.Column(db.Float, default=0.0)
    strike_percentage = db.Column(db.Float, default=0.0)
    wild_pitches = db.Column(db.Integer, default=0)

    player = db.relationship('Player', back_populates='pitcher_profile')

    def update_calculated_fields(self):
        self.innings_pitched_total = self.innings_pitched_total or 0.0
        self.hits_allowed_total = self.hits_allowed_total or 0
        self.walks_allowed_total = self.walks_allowed_total or 0
        self.earned_runs_total = self.earned_runs_total or 0
        self.pitches = self.pitches or 0
        self.strikes = self.strikes or 0

        if self.innings_pitched_total > 0:
            self.era = round((self.earned_runs_total * 9) / self.innings_pitched_total, 2)
            self.whip = round(
                (self.walks_allowed_total + self.hits_allowed_total) / self.innings_pitched_total,
                2
            )
        else:
            self.era = 0.0
            self.whip = 0.0

        if self.pitches > 0:
            self.strike_percentage = round((self.strikes / self.pitches) * 100, 1)
        else:
            self.strike_percentage = 0.0

    def to_dict(self):
        return {
            'player_id': self.player_id,
            **{field: getattr(self, field) for field in PITCHER_PROFILE_DEFAULTS}
        }


class GameRecord(db.Model):
    """单场比赛记录表"""
    __tablename__ = 'game_records'

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)
    game_date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    opponent = db.Column(db.String(100))
    is_pitching_record = db.Column(db.Boolean, default=False)

    # 打击记录字段
    at_bats = db.Column(db.Integer, default=0)
    runs = db.Column(db.Integer, default=0)
    hits = db.Column(db.Integer, default=0)
    rbi = db.Column(db.Integer, default=0)
    walks = db.Column(db.Integer, default=0)
    strikeouts = db.Column(db.Integer, default=0)
    doubles = db.Column(db.Integer, default=0)
    triples = db.Column(db.Integer, default=0)
    home_runs_batting = db.Column(db.Integer, default=0)
    total_bases = db.Column(db.Integer, default=0)
    hit_by_pitch = db.Column(db.Integer, default=0)
    stolen_bases = db.Column(db.Integer, default=0)
    caught_stealing = db.Column(db.Integer, default=0)
    sacrifice_flys = db.Column(db.Integer, default=0)
    sacrifice_hits = db.Column(db.Integer, default=0)

    # 投手记录字段
    pitches = db.Column(db.Integer, default=0)
    strikes = db.Column(db.Integer, default=0)
    hit_by_pitch_allowed = db.Column(db.Integer, default=0)
    batters_faced = db.Column(db.Integer, default=0)
    wild_pitches = db.Column(db.Integer, default=0)
    innings_pitched = db.Column(db.Float, default=0.0)
    hits_allowed = db.Column(db.Integer, default=0)
    runs_allowed = db.Column(db.Integer, default=0)
    earned_runs = db.Column(db.Integer, default=0)
    walks_allowed = db.Column(db.Integer, default=0)
    strikeouts_pitched = db.Column(db.Integer, default=0)
    home_runs_allowed = db.Column(db.Integer, default=0)

    # 守备预留字段
    errors_fielding = db.Column(db.Integer, default=0)
    passed_balls = db.Column(db.Integer, default=0)

    # 比赛结果
    win = db.Column(db.Boolean, default=False)
    loss = db.Column(db.Boolean, default=False)
    save = db.Column(db.Boolean, default=False)

    player = db.relationship('Player', backref=db.backref('game_records', lazy=True))


def _build_profile_proxy(profile_attr, field_name, default_value, ensure_method):
    def getter(self):
        profile = getattr(self, profile_attr)
        if not profile:
            return default_value
        value = getattr(profile, field_name, default_value)
        return default_value if value is None else value

    def setter(self, value):
        profile = getattr(self, ensure_method)()
        setattr(profile, field_name, default_value if value is None else value)

    return property(getter, setter)


for _field_name, _default in FIELDER_PROFILE_DEFAULTS.items():
    setattr(Player, _field_name, _build_profile_proxy('fielder_profile', _field_name, _default, 'ensure_fielder_profile'))

for _field_name, _default in PITCHER_PROFILE_DEFAULTS.items():
    setattr(Player, _field_name, _build_profile_proxy('pitcher_profile', _field_name, _default, 'ensure_pitcher_profile'))


def sync_stats_from_game_records():
    """
    从 GameRecord 重新聚合统计数据到 FielderProfile 和 PitcherProfile。
    作为唯一数据源，确保数据一致性。
    """
    from collections import defaultdict

    all_records = GameRecord.query.all()
    if not all_records:
        return

    player_stats = defaultdict(lambda: {
        'batting': {
            'at_bats': 0, 'runs': 0, 'hits': 0, 'rbi': 0, 'walks': 0,
            'strikeouts': 0, 'doubles': 0, 'triples': 0, 'home_runs': 0,
            'stolen_bases': 0, 'hit_by_pitch': 0, 'caught_stealing': 0,
            'sacrifice_flys': 0, 'sacrifice_hits': 0, 'total_bases': 0
        },
        'pitching': {
            'innings_pitched': 0.0, 'hits_allowed': 0, 'runs_allowed': 0,
            'earned_runs': 0, 'walks_allowed': 0, 'strikeouts': 0,
            'home_runs_allowed': 0, 'pitches': 0, 'strikes': 0,
            'hit_by_pitch_allowed': 0, 'batters_faced': 0, 'wild_pitches': 0
        },
        'is_pitcher': False,
    })

    for record in all_records:
        pid = record.player_id
        stats = player_stats[pid]

        if record.is_pitching_record:
            stats['is_pitcher'] = True
            p = stats['pitching']
            p['innings_pitched'] += record.innings_pitched or 0
            p['hits_allowed'] += record.hits_allowed or 0
            p['runs_allowed'] += record.runs_allowed or 0
            p['earned_runs'] += record.earned_runs or 0
            p['walks_allowed'] += record.walks_allowed or 0
            p['strikeouts'] += record.strikeouts_pitched or 0
            p['home_runs_allowed'] += record.home_runs_allowed or 0
            p['pitches'] += record.pitches or 0
            p['strikes'] += record.strikes or 0
            p['hit_by_pitch_allowed'] += record.hit_by_pitch_allowed or 0
            p['batters_faced'] += record.batters_faced or 0
            p['wild_pitches'] += record.wild_pitches or 0
        else:
            b = stats['batting']
            b['at_bats'] += record.at_bats or 0
            b['runs'] += record.runs or 0
            b['hits'] += record.hits or 0
            b['rbi'] += record.rbi or 0
            b['walks'] += record.walks or 0
            b['strikeouts'] += record.strikeouts or 0
            b['doubles'] += record.doubles or 0
            b['triples'] += record.triples or 0
            b['home_runs'] += record.home_runs_batting or 0
            b['stolen_bases'] += record.stolen_bases or 0
            b['hit_by_pitch'] += record.hit_by_pitch or 0
            b['caught_stealing'] += record.caught_stealing or 0
            b['sacrifice_flys'] += record.sacrifice_flys or 0
            b['sacrifice_hits'] += record.sacrifice_hits or 0

    for player_id, stats in player_stats.items():
        player = db.session.get(Player, player_id)
        if not player:
            continue

        if not player.fielder_profile:
            player.fielder_profile = FielderProfile()

        fp = player.fielder_profile
        b = stats['batting']
        fp.at_bats_total = b['at_bats']
        fp.runs_total = b['runs']
        fp.hits_total = b['hits']
        fp.rbi_total = b['rbi']
        fp.walks_total = b['walks']
        fp.strikeouts_batting_total = b['strikeouts']
        fp.doubles = b['doubles']
        fp.triples = b['triples']
        fp.home_runs_batting = b['home_runs']
        fp.stolen_bases = b['stolen_bases']
        fp.hit_by_pitch = b['hit_by_pitch']
        fp.caught_stealing = b['caught_stealing']
        fp.sacrifice_flys = b['sacrifice_flys']
        fp.sacrifice_hits = b['sacrifice_hits']
        fp.update_calculated_fields()

        if stats['is_pitcher']:
            if not player.pitcher_profile:
                player.pitcher_profile = PitcherProfile()

            pp = player.pitcher_profile
            p = stats['pitching']
            pp.innings_pitched_total = p['innings_pitched']
            pp.hits_allowed_total = p['hits_allowed']
            pp.runs_allowed_total = p['runs_allowed']
            pp.earned_runs_total = p['earned_runs']
            pp.walks_allowed_total = p['walks_allowed']
            pp.strikeouts_total = p['strikeouts']
            pp.home_runs_allowed_total = p['home_runs_allowed']
            pp.pitches = p['pitches']
            pp.strikes = p['strikes']
            pp.hit_by_pitch_allowed = p['hit_by_pitch_allowed']
            pp.batters_faced = p['batters_faced']
            pp.wild_pitches = p['wild_pitches']
            pp.update_calculated_fields()

    db.session.commit()


def init_db(app):
    """初始化数据库并执行兼容迁移。"""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        init_positions()
        migrate_legacy_player_stats()
        sync_stats_from_game_records()


def init_positions():
    """初始化位置数据"""
    for pos_name in DEFAULT_POSITIONS:
        position = Position.query.filter_by(name=pos_name).first()
        if not position:
            db.session.add(Position(name=pos_name))
    db.session.commit()


def _get_table_columns(table_name):
    inspector = inspect(db.engine)
    try:
        return {column['name'] for column in inspector.get_columns(table_name)}
    except Exception:
        return set()


def _get_table_names():
    inspector = inspect(db.engine)
    try:
        return set(inspector.get_table_names())
    except Exception:
        return set()


def _row_has_non_zero_value(row, field_names):
    for field_name in field_names:
        value = row.get(field_name)
        if value is None:
            continue
        if isinstance(value, (int, float)) and value != 0:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def _copy_legacy_fields(profile, row, field_names):
    changed = False
    for field_name in field_names:
        if field_name not in row:
            continue
        value = row.get(field_name)
        if value is None:
            continue
        if getattr(profile, field_name, None) != value:
            setattr(profile, field_name, value)
            changed = True
    return changed


def _normalize_player_role_and_positions(player):
    changed = False
    pitcher_position = Position.query.filter_by(name='投手').first()
    current_positions = list(player.positions)

    if player.is_pitcher:
        if pitcher_position and all(pos.id != pitcher_position.id for pos in current_positions):
            current_positions.insert(0, pitcher_position)
            player.positions = current_positions
            changed = True
    else:
        filtered_positions = [pos for pos in current_positions if pos.name != '投手']
        if len(filtered_positions) != len(current_positions):
            player.positions = filtered_positions
            changed = True

        if player.primary_position == '投手':
            player.primary_position = filtered_positions[0].name if filtered_positions else '未指定'
            changed = True

        if not player.primary_position:
            player.primary_position = filtered_positions[0].name if filtered_positions else '未指定'
            changed = True

    if player.is_pitcher and not player.primary_position:
        player.primary_position = current_positions[0].name if current_positions else '投手'
        changed = True

    return changed


def _copy_legacy_fields_if_empty(profile, row, field_names):
    """仅当 profile 字段为 0/None 时才从 legacy 列复制，避免覆盖已有正确数据。"""
    changed = False
    for field_name in field_names:
        if field_name not in row:
            continue
        value = row.get(field_name)
        if value is None or value == 0:
            continue
        current = getattr(profile, field_name, None)
        if current is None or current == 0:
            setattr(profile, field_name, value)
            changed = True
    return changed


def _zero_out_legacy_columns():
    """将 players 表中的 legacy 统计列清零，防止反复覆盖 profile 数据。"""
    available_columns = _get_table_columns('players')
    legacy_fields = [f for f in LEGACY_FIELDER_FIELDS + LEGACY_PITCHER_FIELDS if f in available_columns]
    # 也包括计算字段（这些不在 LEGACY_*_FIELDS 里但也存在）
    calc_fields = ['batting_average', 'on_base_percentage', 'slugging_percentage', 'era', 'whip']
    legacy_fields += [f for f in calc_fields if f in available_columns]

    if not legacy_fields:
        return

    set_clauses = ', '.join(f'{f} = 0' for f in legacy_fields)
    db.session.execute(text(f"UPDATE players SET {set_clauses}"))


def migrate_legacy_player_stats():
    """
    将旧 `players` 表里的累计统计迁移到投手/场员档案表中。
    仅在 profile 为空/零值时迁移（首次迁移），然后清零 legacy 列，
    确保幂等且不会覆盖后续通过 GameRecord 聚合的正确数据。
    """
    if 'players' not in _get_table_names():
        return

    available_columns = _get_table_columns('players')
    select_columns = ['id', 'primary_position', 'is_pitcher']
    select_columns += [field for field in LEGACY_FIELDER_FIELDS if field in available_columns]
    select_columns += [field for field in LEGACY_PITCHER_FIELDS if field in available_columns]

    if not select_columns:
        return

    rows = db.session.execute(
        text(f"SELECT {', '.join(select_columns)} FROM players")
    ).mappings().all()

    migrated_players = 0
    for row in rows:
        player = db.session.get(Player, row['id'])
        if not player:
            continue

        inferred_is_pitcher = bool(row.get('is_pitcher'))
        if not inferred_is_pitcher:
            inferred_is_pitcher = any(pos.name == '投手' for pos in player.positions) or row.get('primary_position') == '投手'

        changed = False
        if player._is_pitcher != inferred_is_pitcher:
            player._is_pitcher = inferred_is_pitcher
            changed = True

        changed = _normalize_player_role_and_positions(player) or changed

        if not player.fielder_profile:
            player.fielder_profile = FielderProfile()
            changed = True

        if player.is_pitcher and not player.pitcher_profile:
            player.pitcher_profile = PitcherProfile()
            changed = True

        if _row_has_non_zero_value(row, LEGACY_FIELDER_FIELDS):
            profile = player.ensure_fielder_profile()
            changed = _copy_legacy_fields_if_empty(profile, row, LEGACY_FIELDER_FIELDS) or changed

        if _row_has_non_zero_value(row, LEGACY_PITCHER_FIELDS):
            profile = player.ensure_pitcher_profile()
            changed = _copy_legacy_fields_if_empty(profile, row, LEGACY_PITCHER_FIELDS) or changed

        player.update_calculated_fields()

        if changed:
            migrated_players += 1

    if migrated_players:
        db.session.commit()

    # 清零 legacy 列，防止下次启动时覆盖 profile 数据
    _zero_out_legacy_columns()
    db.session.commit()


def add_sample_data():
    """添加示例球员数据"""
    if Player.query.count() > 0:
        return

    positions_dict = {}
    for pos_name in DEFAULT_POSITIONS:
        position = Position.query.filter_by(name=pos_name).first()
        if position:
            positions_dict[pos_name] = position

    sample_players = [
        {'name': '张三', 'jersey_number': '18', 'player_type': 'pitcher', 'positions': ['投手']},
        {'name': '李四', 'jersey_number': '10', 'player_type': 'fielder', 'positions': ['左外野手', '中外野手'], 'primary_position': '左外野手'},
        {'name': '王五', 'jersey_number': '6', 'player_type': 'fielder', 'positions': ['游击手', '三垒手'], 'primary_position': '游击手'},
        {'name': '赵六', 'jersey_number': '2', 'player_type': 'fielder', 'positions': ['捕手'], 'primary_position': '捕手'},
    ]

    created_players = []
    for payload in sample_players:
        player = Player(
            name=payload['name'],
            jersey_number=payload['jersey_number'],
            primary_position=payload.get('primary_position'),
            join_date=datetime.now(timezone.utc).date()
        )
        player.apply_player_type(payload['player_type'])
        positions = [positions_dict[pos] for pos in payload['positions'] if pos in positions_dict]
        player.positions = positions
        player.normalize_positions()
        db.session.add(player)
        created_players.append(player)

    db.session.flush()

    for player in created_players:
        if player.is_pitcher:
            player.innings_pitched_total = round(random.uniform(20, 100), 1)
            player.hits_allowed_total = random.randint(20, 80)
            player.runs_allowed_total = random.randint(10, 40)
            player.earned_runs_total = random.randint(8, 35)
            player.walks_allowed_total = random.randint(5, 30)
            player.strikeouts_total = random.randint(10, 120)
            player.home_runs_allowed_total = random.randint(0, 8)
            player.pitches = random.randint(150, 800)
            player.strikes = random.randint(80, player.pitches)
            player.batters_faced = random.randint(40, 250)
        else:
            player.at_bats_total = random.randint(20, 120)
            player.runs_total = random.randint(5, 40)
            player.hits_total = random.randint(5, player.at_bats_total)
            player.rbi_total = random.randint(0, 35)
            player.walks_total = random.randint(0, 25)
            player.strikeouts_batting_total = random.randint(0, 40)
            player.doubles = random.randint(0, 10)
            player.triples = random.randint(0, 4)
            player.home_runs_batting = random.randint(0, 8)
            player.hit_by_pitch = random.randint(0, 5)
            player.stolen_bases = random.randint(0, 12)

        player.update_calculated_fields()

    db.session.commit()
