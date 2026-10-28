/**
 * POWER ARENA — 全局 Toast
 * ============================================================
 * 全站唯一的提示实现。取代此前散落的 4 套：
 *   - 原生 alert()            → 已移除
 *   - Bootstrap 类 Toast      → 已移除（Bootstrap 已在 phase-D 移除，样式全失效）
 *   - matchup_stats.js 内联版 → 抽到这里
 *
 * 用法：
 *   toast('保存成功', 'success');
 *   toast('请求失败：' + err.message, 'error');
 *
 * 同时保留 showAlert() 别名，供尚未迁移的旧调用点使用。
 */
(function (global) {
    'use strict';

    const STYLES = {
        success: { bg: 'rgba(34, 197, 94, 0.12)',  border: 'rgba(34, 197, 94, 0.35)',  icon: '✓' },
        error:   { bg: 'rgba(239, 68, 68, 0.12)',  border: 'rgba(239, 68, 68, 0.35)',  icon: '✕' },
        warning: { bg: 'rgba(245, 158, 11, 0.12)', border: 'rgba(245, 158, 11, 0.35)', icon: '!' },
        info:    { bg: 'rgba(230, 0, 0, 0.12)',   border: 'rgba(230, 0, 0, 0.35)',   icon: 'i' },
    };

    // 兼容历史调用点用过的别名
    const TYPE_ALIAS = {
        danger: 'error', err: 'error', warn: 'warning', ok: 'success',
    };

    function toast(message, type, duration) {
        const key = TYPE_ALIAS[type] || type;
        const style = STYLES[key] || STYLES.info;
        const ms = duration || 4000;

        // 只保留一个 toast，避免刷屏
        const existing = document.querySelector('.alert-toast');
        if (existing) existing.remove();

        const el = document.createElement('div');
        el.className = 'alert-toast fixed top-5 right-5 z-50 flex items-start gap-3';
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
        el.style.cssText = [
            'background:' + style.bg,
            'border:1px solid ' + style.border,
            'clip-path:polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px))',
            'min-width:300px;max-width:min(90vw,460px);padding:1rem',
            'box-shadow:0 8px 32px rgba(0,0,0,0.35)',
            'color:#fff;font-size:0.875rem;line-height:1.5',
        ].join(';');

        // 用 textContent 注入，避免消息里的 HTML 被执行
        const body = document.createElement('div');
        body.className = 'flex items-start gap-3 flex-1';
        const icon = document.createElement('span');
        icon.className = 'font-bold shrink-0';
        icon.style.color = style.border;
        icon.textContent = style.icon;
        const text = document.createElement('span');
        text.className = 'text-white break-words';
        text.textContent = String(message == null ? '' : message);
        body.appendChild(icon);
        body.appendChild(text);

        const close = document.createElement('button');
        close.type = 'button';
        close.className = 'text-gray-400 hover:text-white ml-auto text-xl leading-none shrink-0';
        close.setAttribute('aria-label', '关闭提示');
        close.textContent = '×';
        close.addEventListener('click', function () { el.remove(); });

        el.appendChild(body);
        el.appendChild(close);
        document.body.appendChild(el);

        if (ms > 0) {
            setTimeout(function () {
                if (el.parentNode) el.remove();
            }, ms);
        }
        return el;
    }

    global.toast = toast;
    global.showAlert = toast;   // 向后兼容旧调用点
})(window);
