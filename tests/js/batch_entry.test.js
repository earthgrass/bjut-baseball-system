/**
 * 批量录入解析器单元测试 —— Phase R2
 * ============================================================
 * 跑法：node --test tests/js/
 *
 * 覆盖 static/js/batch_entry.js 的纯逻辑（解析 + 姓名映射 + 不变量校验）。
 * 这些是「粘贴 box score → 写入数据库」之间唯一的转换环节，
 * 错了就是静默写错数据，所以必须有单测（规范 §47 Level 1）。
 */
const test = require('node:test');
const assert = require('node:assert');

const mod = require('../../static/js/batch_entry.js');

const PLAYERS = [
    { id: 1, name: '于凯泽', is_pitcher: false },
    { id: 2, name: '仇志豪', is_pitcher: false },
    { id: 3, name: '韩登越', is_pitcher: true },
    { id: 4, name: '白云箫', is_pitcher: true },
];

function parseBatting(text) {
    return mod.parseLines(text, mod.BATTING_REQUIRED, mod.BATTING_OPTIONAL, false);
}

function parsePitching(text) {
    return mod.parseLines(text, mod.PITCHING_REQUIRED, mod.PITCHING_OPTIONAL, true);
}

test.beforeEach(() => {
    mod.setPlayers(PLAYERS);
});

// ====== 正常解析 ======

test('解析一行打击数据', () => {
    const rows = parseBatting('于凯泽 4 1 2 1 0 1');
    assert.strictEqual(rows.length, 1);
    assert.strictEqual(rows[0].ok, true);
    assert.strictEqual(rows[0].name, '于凯泽');
    assert.strictEqual(rows[0].playerId, 1);
    assert.deepStrictEqual(rows[0].values, {
        at_bats: 4, runs: 1, hits: 2, rbi: 1, walks: 0, strikeouts: 1
    });
});

test('解析一行投球数据（含小数局数）', () => {
    const rows = parsePitching('韩登越 3.0 4 1 1 2 5');
    assert.strictEqual(rows.length, 1);
    assert.strictEqual(rows[0].ok, true);
    assert.strictEqual(rows[0].playerId, 3);
    assert.deepStrictEqual(rows[0].values, {
        innings_pitched: 3, hits_allowed: 4, runs_allowed: 1,
        earned_runs: 1, walks_allowed: 2, strikeouts: 5
    });
});

test('局数保留 .1 / .2 形式（与既有数据同口径）', () => {
    const rows = parsePitching('白云箫 1.1 3 5 5 3 2');
    assert.strictEqual(rows[0].ok, true);
    assert.strictEqual(rows[0].values.innings_pitched, 1.1);
});

test('解析多行', () => {
    const rows = parseBatting('于凯泽 4 1 2 1 0 1\n仇志豪 3 0 1 0 1 0');
    assert.strictEqual(rows.length, 2);
    assert.ok(rows.every(r => r.ok));
    assert.strictEqual(rows[1].name, '仇志豪');
});

test('解析可选列', () => {
    const rows = parseBatting('于凯泽 4 1 2 1 0 1 1 0 1');
    assert.strictEqual(rows[0].ok, true);
    assert.strictEqual(rows[0].extra.doubles, 1);
    assert.strictEqual(rows[0].extra.triples, 0);
    assert.strictEqual(rows[0].extra.home_runs_game, 1);
});

test('解析投球可选列', () => {
    const rows = parsePitching('韩登越 3.0 4 1 1 2 5 0 60 40 12 1');
    assert.strictEqual(rows[0].ok, true);
    assert.strictEqual(rows[0].extra.pitches, 60);
    assert.strictEqual(rows[0].extra.strikes, 40);
    assert.strictEqual(rows[0].extra.batters_faced, 12);
    assert.strictEqual(rows[0].extra.wild_pitches, 1);
});

// ====== 跳过的行 ======

test('跳过空行 / 注释行 / 表头行 / 合计行', () => {
    const text = [
        '姓名  AB  R  H  RBI  BB  SO',
        '',
        '# 这是注释',
        '于凯泽 4 1 2 1 0 1',
        '合计  9  3  4  3  3  3',
        '   ',
    ].join('\n');
    const rows = parseBatting(text);
    assert.strictEqual(rows.length, 1);
    assert.strictEqual(rows[0].name, '于凯泽');
    assert.strictEqual(rows[0].ok, true);
});

test('跳过英文表头', () => {
    const rows = parseBatting('Player AB R H RBI BB SO');
    assert.strictEqual(rows.length, 0);
});

// ====== 错误行 ======

test('未知姓名 → 报错', () => {
    const rows = parseBatting('查无此人 4 1 2 1 0 1');
    assert.strictEqual(rows.length, 1);
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /找不到球员/);
});

test('重名 → 报错', () => {
    mod.setPlayers([{ id: 1, name: '同名', is_pitcher: false },
                    { id: 2, name: '同名', is_pitcher: false }]);
    const rows = parseBatting('同名 4 1 2 1 0 1');
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /都叫/);
});

test('场员录投球 → 报错', () => {
    const rows = parsePitching('于凯泽 3.0 4 1 1 2 5');
    assert.strictEqual(rows.length, 1);
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /不是投手/);
});

test('投手录打击 → 允许', () => {
    const rows = parseBatting('韩登越 4 1 2 1 0 1');
    assert.strictEqual(rows[0].ok, true);
});

test('安打超过打数 → 报错', () => {
    const rows = parseBatting('于凯泽 2 1 5 1 0 1');
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /安打 .* 超过打数/);
});

test('安打小于二/三/本垒打之和 → 报错', () => {
    const rows = parseBatting('于凯泽 4 1 2 1 0 1 0 0 3');
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /小于/);
});

test('负数 → 报错', () => {
    const rows = parseBatting('于凯泽 -4 1 2 1 0 1');
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /负数/);
});

test('非数字 → 报错', () => {
    const rows = parseBatting('于凯泽 4 x 2 1 0 1');
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /应该是整数/);
});

test('小数出现在整数列 → 报错', () => {
    const rows = parseBatting('于凯泽 4.5 1 2 1 0 1');
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /应该是整数/);
});

test('数据列不足 → 报错', () => {
    const rows = parseBatting('于凯泽 4 1 2');
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /数据列不足/);
});

test('数据列过多 → 报错', () => {
    const rows = parseBatting('于凯泽 4 1 2 1 0 1 0 0 0 0 0 0 0 0 0');
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /数据列过多/);
});

test('只有姓名 → 报错', () => {
    const rows = parseBatting('于凯泽');
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /缺少数据列/);
});

test('第 2 列不是数字且不像表头 → 报错', () => {
    const rows = parseBatting('于凯泽 看看 1 2 1 0 1');
    assert.strictEqual(rows[0].ok, false);
    assert.match(rows[0].error, /第 2 列/);
});

test('错误行不阻断其它行的解析', () => {
    const rows = parseBatting('查无此人 4 1 2 1 0 1\n于凯泽 4 1 2 1 0 1');
    assert.strictEqual(rows.length, 2);
    assert.strictEqual(rows[0].ok, false);
    assert.strictEqual(rows[1].ok, true);
});

test('错误行记录了行号', () => {
    const rows = parseBatting('于凯泽 4 1 2 1 0 1\n查无此人 4 1 2 1 0 1');
    assert.strictEqual(rows[1].lineNo, 2);
});

// ====== 模板 / 脚本的 DOM id 交叉检查 ======
//
// 这是 JS 与模板之间唯一的契约：一个 id 拼错，页面就会静默失去某个功能
// （没有异常，只是那一块不工作）。浏览器自动化不可用时，这道静态检查
// 能兜住最容易犯的那类集成错误。

const fs = require('node:fs');
const path = require('node:path');

const JS_PATH = path.join(__dirname, '..', '..', 'static', 'js', 'batch_entry.js');
const TEMPLATE_PATH = path.join(__dirname, '..', '..', 'templates', 'batch_entry.html');

// JS 与模板之间的 DOM id 契约。改一处必须改另一处。
// batchForm 由模板自己的 onsubmit="submitBatch()" 绑定，其余由 JS 取用。
const EXPECTED_IDS = [
    'batchForm', 'batchGameDate', 'batchOpponent', 'opponentsList',
    'battingInput', 'pitchingInput',
    'battingPreview', 'battingSummary',
    'pitchingPreview', 'pitchingSummary',
    'batchSubmitBtn', 'batchHint',
];

test('JS 引用的每个 DOM id 都存在于模板中', () => {
    const js = fs.readFileSync(JS_PATH, 'utf8');
    const html = fs.readFileSync(TEMPLATE_PATH, 'utf8');

    // 1. 契约：EXPECTED_IDS 里的每个 id 都必须在模板里
    const missing = EXPECTED_IDS.filter(id => !new RegExp('id="' + id + '"').test(html));
    assert.deepStrictEqual(missing, [], '模板缺少这些 id：' + missing.join(', '));

    // 2. JS 里所有 $('字面量') 都必须在契约里
    const direct = [];
    const re = /\$\('([^']+)'\)/g;
    let m;
    while ((m = re.exec(js)) !== null) direct.push(m[1]);
    const notInContract = direct.filter(id => !EXPECTED_IDS.includes(id));
    assert.deepStrictEqual(notInContract, [], 'JS 引用了契约之外的 id：' + notInContract.join(', '));

    // 3. 模板里的批量录入相关 id 与契约**集合相等**
    //    （模板多出的 id 是孤儿；契约里的 id 已在第 1 步查过必须存在）
    const templateIds = Array.from(html.matchAll(/id="([^"]+)"/g)).map(x => x[1]);
    const isBatchish = id =>
        id.startsWith('batch') || id.endsWith('Preview') || id.endsWith('Summary') ||
        id.endsWith('Input') || id === 'opponentsList';
    const batchishTemplateIds = templateIds.filter(isBatchish).sort();
    assert.deepStrictEqual(
        batchishTemplateIds, EXPECTED_IDS.slice().sort(),
        '模板里的批量录入相关 id 与契约不一致'
    );
});

test('模板引用的脚本存在', () => {
    const html = fs.readFileSync(TEMPLATE_PATH, 'utf8');
    const match = html.match(/filename='js\/([^']+)'/);
    assert.ok(match, '模板里应引用 batch_entry.js');
    const jsPath = path.join(__dirname, '..', '..', 'static', 'js', match[1]);
    assert.ok(fs.existsSync(jsPath), '引用的脚本不存在：' + jsPath);
});
