#!/usr/bin/env python3
"""
使用 sqlite3 直接迁移旧数据库：
1. 备份原数据库
2. 创建 fielder_profiles / pitcher_profiles
3. 把 players 表中的累计数据迁到新档案表
4. 规范投手/场员的角色与位置
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / 'instance' / 'baseball_players.db'

FIELDER_FIELDS = [
    'at_bats_total', 'runs_total', 'hits_total', 'rbi_total', 'walks_total',
    'strikeouts_batting_total', 'doubles', 'triples', 'home_runs_batting',
    'total_bases', 'hit_by_pitch', 'stolen_bases', 'caught_stealing',
    'sacrifice_flys', 'sacrifice_hits', 'errors_fielding', 'passed_balls',
]

PITCHER_FIELDS = [
    'innings_pitched_total', 'hits_allowed_total', 'runs_allowed_total',
    'earned_runs_total', 'walks_allowed_total', 'strikeouts_total',
    'home_runs_allowed_total', 'pitches', 'strikes', 'hit_by_pitch_allowed',
    'batters_faced', 'wild_pitches',
]


def backup_database() -> Path:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = DB_PATH.with_name(f'{DB_PATH.stem}.backup_{timestamp}{DB_PATH.suffix}')
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


def ensure_tables(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fielder_profiles (
            player_id INTEGER PRIMARY KEY,
            at_bats_total INTEGER DEFAULT 0,
            runs_total INTEGER DEFAULT 0,
            hits_total INTEGER DEFAULT 0,
            rbi_total INTEGER DEFAULT 0,
            walks_total INTEGER DEFAULT 0,
            strikeouts_batting_total INTEGER DEFAULT 0,
            batting_average REAL DEFAULT 0,
            on_base_percentage REAL DEFAULT 0,
            slugging_percentage REAL DEFAULT 0,
            ops REAL DEFAULT 0,
            doubles INTEGER DEFAULT 0,
            triples INTEGER DEFAULT 0,
            home_runs_batting INTEGER DEFAULT 0,
            total_bases INTEGER DEFAULT 0,
            hit_by_pitch INTEGER DEFAULT 0,
            stolen_bases INTEGER DEFAULT 0,
            caught_stealing INTEGER DEFAULT 0,
            sacrifice_flys INTEGER DEFAULT 0,
            sacrifice_hits INTEGER DEFAULT 0,
            errors_fielding INTEGER DEFAULT 0,
            passed_balls INTEGER DEFAULT 0,
            FOREIGN KEY(player_id) REFERENCES players(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pitcher_profiles (
            player_id INTEGER PRIMARY KEY,
            innings_pitched_total REAL DEFAULT 0,
            hits_allowed_total INTEGER DEFAULT 0,
            runs_allowed_total INTEGER DEFAULT 0,
            earned_runs_total INTEGER DEFAULT 0,
            walks_allowed_total INTEGER DEFAULT 0,
            strikeouts_total INTEGER DEFAULT 0,
            home_runs_allowed_total INTEGER DEFAULT 0,
            pitches INTEGER DEFAULT 0,
            strikes INTEGER DEFAULT 0,
            hit_by_pitch_allowed INTEGER DEFAULT 0,
            batters_faced INTEGER DEFAULT 0,
            era REAL DEFAULT 0,
            whip REAL DEFAULT 0,
            strike_percentage REAL DEFAULT 0,
            wild_pitches INTEGER DEFAULT 0,
            FOREIGN KEY(player_id) REFERENCES players(id)
        )
        """
    )


def has_non_zero(values: dict[str, object], fields: list[str]) -> bool:
    for field in fields:
        value = values.get(field)
        if isinstance(value, (int, float)) and value != 0:
            return True
    return False


def calculate_fielder_metrics(values: dict[str, object]) -> dict[str, float | int]:
    at_bats = int(values.get('at_bats_total') or 0)
    hits = int(values.get('hits_total') or 0)
    walks = int(values.get('walks_total') or 0)
    hit_by_pitch = int(values.get('hit_by_pitch') or 0)
    sacrifice_flys = int(values.get('sacrifice_flys') or 0)
    doubles = int(values.get('doubles') or 0)
    triples = int(values.get('triples') or 0)
    home_runs = int(values.get('home_runs_batting') or 0)

    singles = max(hits - doubles - triples - home_runs, 0)
    total_bases = singles + doubles * 2 + triples * 3 + home_runs * 4
    plate_appearances = at_bats + walks + hit_by_pitch + sacrifice_flys

    batting_average = round(hits / at_bats, 3) if at_bats > 0 else 0.0
    slugging_percentage = round(total_bases / at_bats, 3) if at_bats > 0 else 0.0
    on_base_percentage = round((hits + walks + hit_by_pitch) / plate_appearances, 3) if plate_appearances > 0 else 0.0
    ops = round(on_base_percentage + slugging_percentage, 3)

    return {
        'total_bases': total_bases,
        'batting_average': batting_average,
        'slugging_percentage': slugging_percentage,
        'on_base_percentage': on_base_percentage,
        'ops': ops,
    }


def calculate_pitcher_metrics(values: dict[str, object]) -> dict[str, float]:
    innings = float(values.get('innings_pitched_total') or 0.0)
    earned_runs = int(values.get('earned_runs_total') or 0)
    walks_allowed = int(values.get('walks_allowed_total') or 0)
    hits_allowed = int(values.get('hits_allowed_total') or 0)
    pitches = int(values.get('pitches') or 0)
    strikes = int(values.get('strikes') or 0)

    era = round((earned_runs * 9) / innings, 2) if innings > 0 else 0.0
    whip = round((walks_allowed + hits_allowed) / innings, 2) if innings > 0 else 0.0
    strike_percentage = round((strikes / pitches) * 100, 1) if pitches > 0 else 0.0

    return {
        'era': era,
        'whip': whip,
        'strike_percentage': strike_percentage,
    }


def migrate() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f'数据库不存在: {DB_PATH}')

    backup_path = backup_database()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    ensure_tables(cursor)

    pitcher_position = cursor.execute(
        "SELECT id FROM positions WHERE name = '投手' LIMIT 1"
    ).fetchone()
    pitcher_position_id = pitcher_position['id'] if pitcher_position else None

    players = cursor.execute("SELECT * FROM players ORDER BY id").fetchall()
    migrated_fielder_profiles = 0
    migrated_pitcher_profiles = 0
    normalized_roles = 0

    for player in players:
        player_data = dict(player)
        player_id = player_data['id']

        position_rows = cursor.execute(
            """
            SELECT positions.name
            FROM player_positions
            JOIN positions ON positions.id = player_positions.position_id
            WHERE player_positions.player_id = ?
            """,
            (player_id,),
        ).fetchall()
        position_names = [row['name'] for row in position_rows]

        is_pitcher = bool(player_data.get('is_pitcher'))
        if not is_pitcher:
            is_pitcher = player_data.get('primary_position') == '投手' or '投手' in position_names

        if is_pitcher:
            cursor.execute(
                "UPDATE players SET is_pitcher = 1, primary_position = '投手' WHERE id = ?",
                (player_id,),
            )
            if pitcher_position_id is not None:
                cursor.execute(
                    "DELETE FROM player_positions WHERE player_id = ? AND position_id != ?",
                    (player_id, pitcher_position_id),
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO player_positions (player_id, position_id) VALUES (?, ?)",
                    (player_id, pitcher_position_id),
                )
            normalized_roles += 1
        else:
            if pitcher_position_id is not None:
                cursor.execute(
                    "DELETE FROM player_positions WHERE player_id = ? AND position_id = ?",
                    (player_id, pitcher_position_id),
                )
            if player_data.get('primary_position') == '投手':
                replacement = next((name for name in position_names if name != '投手'), '未指定')
                cursor.execute(
                    "UPDATE players SET is_pitcher = 0, primary_position = ? WHERE id = ?",
                    (replacement, player_id),
                )
                normalized_roles += 1

        if has_non_zero(player_data, FIELDER_FIELDS) or not is_pitcher:
            cursor.execute(
                "INSERT OR IGNORE INTO fielder_profiles (player_id) VALUES (?)",
                (player_id,),
            )
            metrics = calculate_fielder_metrics(player_data)
            update_values = {field: int(player_data.get(field) or 0) for field in FIELDER_FIELDS}
            update_values.update(metrics)
            cursor.execute(
                """
                UPDATE fielder_profiles
                SET at_bats_total = :at_bats_total,
                    runs_total = :runs_total,
                    hits_total = :hits_total,
                    rbi_total = :rbi_total,
                    walks_total = :walks_total,
                    strikeouts_batting_total = :strikeouts_batting_total,
                    doubles = :doubles,
                    triples = :triples,
                    home_runs_batting = :home_runs_batting,
                    total_bases = :total_bases,
                    hit_by_pitch = :hit_by_pitch,
                    stolen_bases = :stolen_bases,
                    caught_stealing = :caught_stealing,
                    sacrifice_flys = :sacrifice_flys,
                    sacrifice_hits = :sacrifice_hits,
                    errors_fielding = :errors_fielding,
                    passed_balls = :passed_balls,
                    batting_average = :batting_average,
                    on_base_percentage = :on_base_percentage,
                    slugging_percentage = :slugging_percentage,
                    ops = :ops
                WHERE player_id = :player_id
                """,
                {'player_id': player_id, **update_values},
            )
            migrated_fielder_profiles += 1

        if has_non_zero(player_data, PITCHER_FIELDS) or is_pitcher:
            cursor.execute(
                "INSERT OR IGNORE INTO pitcher_profiles (player_id) VALUES (?)",
                (player_id,),
            )
            metrics = calculate_pitcher_metrics(player_data)
            update_values = {
                'innings_pitched_total': float(player_data.get('innings_pitched_total') or 0.0),
                'hits_allowed_total': int(player_data.get('hits_allowed_total') or 0),
                'runs_allowed_total': int(player_data.get('runs_allowed_total') or 0),
                'earned_runs_total': int(player_data.get('earned_runs_total') or 0),
                'walks_allowed_total': int(player_data.get('walks_allowed_total') or 0),
                'strikeouts_total': int(player_data.get('strikeouts_total') or 0),
                'home_runs_allowed_total': int(player_data.get('home_runs_allowed_total') or 0),
                'pitches': int(player_data.get('pitches') or 0),
                'strikes': int(player_data.get('strikes') or 0),
                'hit_by_pitch_allowed': int(player_data.get('hit_by_pitch_allowed') or 0),
                'batters_faced': int(player_data.get('batters_faced') or 0),
                'wild_pitches': int(player_data.get('wild_pitches') or 0),
                **metrics,
            }
            cursor.execute(
                """
                UPDATE pitcher_profiles
                SET innings_pitched_total = :innings_pitched_total,
                    hits_allowed_total = :hits_allowed_total,
                    runs_allowed_total = :runs_allowed_total,
                    earned_runs_total = :earned_runs_total,
                    walks_allowed_total = :walks_allowed_total,
                    strikeouts_total = :strikeouts_total,
                    home_runs_allowed_total = :home_runs_allowed_total,
                    pitches = :pitches,
                    strikes = :strikes,
                    hit_by_pitch_allowed = :hit_by_pitch_allowed,
                    batters_faced = :batters_faced,
                    wild_pitches = :wild_pitches,
                    era = :era,
                    whip = :whip,
                    strike_percentage = :strike_percentage
                WHERE player_id = :player_id
                """,
                {'player_id': player_id, **update_values},
            )
            migrated_pitcher_profiles += 1

    conn.commit()
    conn.close()

    print(f'数据库备份已创建: {backup_path}')
    print(f'已迁移场员档案: {migrated_fielder_profiles}')
    print(f'已迁移投手档案: {migrated_pitcher_profiles}')
    print(f'已规范角色/位置记录: {normalized_roles}')


if __name__ == '__main__':
    migrate()
