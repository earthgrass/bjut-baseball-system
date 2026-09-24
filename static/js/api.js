/**
 * POWER ARENA — 统一 fetch 封装 (Phase E0)
 *
 * 自动：
 * - 从 <meta name="csrf-token"> 读取 CSRF token，对所有非 GET/HEAD/OPTIONS 自动加 X-CSRFToken header
 * - 解析 JSON 响应
 * - 非 2xx 抛出 Error（含后端 error 消息）
 *
 * 用法：
 *   const data = await fetchJson('/api/players');
 *   const created = await fetchJson('/api/players', { method: 'POST', body: { ... } });
 */
(function (global) {
    'use strict';

    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function isSafeMethod(method) {
        const m = (method || 'GET').toUpperCase();
        return m === 'GET' || m === 'HEAD' || m === 'OPTIONS';
    }

    async function fetchJson(url, options) {
        options = options || {};
        const method = (options.method || 'GET').toUpperCase();

        const headers = Object.assign({}, options.headers || {});

        // 默认 JSON content-type 当 body 是对象
        let body = options.body;
        if (body && typeof body === 'object' && !(body instanceof FormData)) {
            headers['Content-Type'] = headers['Content-Type'] || 'application/json';
            body = JSON.stringify(body);
        }

        // 非安全方法必须带 CSRF
        if (!isSafeMethod(method)) {
            const token = getCsrfToken();
            if (!token) {
                throw new Error('CSRF token not found in page');
            }
            headers['X-CSRFToken'] = token;
        }

        const resp = await fetch(url, {
            method: method,
            headers: headers,
            body: body,
            credentials: 'same-origin',  // 必须带 session cookie
        });

        let data = null;
        const contentType = resp.headers.get('Content-Type') || '';
        if (contentType.includes('application/json')) {
            data = await resp.json().catch(() => null);
        }

        if (!resp.ok) {
            const msg = (data && data.error) || `HTTP ${resp.status}`;
            const err = new Error(msg);
            err.status = resp.status;
            err.data = data;
            throw err;
        }

        return data;
    }

    global.fetchJson = fetchJson;
})(window);