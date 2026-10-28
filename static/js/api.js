/**
 * POWER ARENA — 统一 API 层
 * ============================================================
 * 这是前端调用后端的**唯一推荐入口**。新代码请一律用 api.* / fetchJson()。
 *
 * 职责：
 *  1. 自动注入 CSRF token（X-CSRFToken header）——所有非安全方法必带
 *  2. 统一解析 JSON 响应
 *  3. 统一错误对象 ApiError { message, status, code, data }
 *  4. 同时接管原生 window.fetch 与 jQuery.$.ajax，
 *     使既有调用点无需改动也能带上 CSRF（向后兼容）
 *
 * 用法：
 *   const players = await api.get('/api/players');
 *   await api.post('/api/game_records', { player_id: 7, ... });
 *
 * 错误处理：
 *   try { ... } catch (e) {
 *     if (e instanceof ApiError) toast(e.message, 'error');
 *     else toast('网络异常，请稍后再试', 'error');
 *   }
 */
(function (global) {
    'use strict';

    // ---------------------------------------------------------------
    // CSRF
    // ---------------------------------------------------------------
    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? (meta.getAttribute('content') || '') : '';
    }

    function isSafeMethod(method) {
        const m = (method || 'GET').toUpperCase();
        return m === 'GET' || m === 'HEAD' || m === 'OPTIONS';
    }

    // ---------------------------------------------------------------
    // 统一错误类型
    // ---------------------------------------------------------------
    class ApiError extends Error {
        constructor(message, status, code, data) {
            super(message);
            this.name = 'ApiError';
            this.status = status || 0;
            this.code = code || null;
            this.data = data || null;
        }
    }

    /** 非 JSON 错误响应（如 CSRF 拦截的 HTML 400）转成人话 */
    function httpFallbackMessage(status) {
        switch (status) {
            case 400: return '请求被拒绝（400），缺少或无效的 CSRF token';
            case 401: return '请先登录管理员账号';
            case 403: return '没有权限执行该操作';
            case 404: return '请求的资源不存在（404）';
            case 405: return '请求方法不被允许（405）';
            case 429: return '操作过于频繁，请稍后再试';
            default:
                if (status >= 500) return '服务器内部错误（' + status + '）';
                return '请求失败（HTTP ' + status + '）';
        }
    }

    /** 从后端响应体里抽出可读的错误信息 */
    function extractError(data, status) {
        if (data && typeof data === 'object') {
            if (typeof data.error === 'string' && data.error) {
                return { message: data.error, code: data.code || null };
            }
            if (data.error && typeof data.error === 'object') {
                return {
                    message: data.error.message || httpFallbackMessage(status),
                    code: data.error.code || null,
                };
            }
            if (typeof data.message === 'string' && data.message) {
                return { message: data.message, code: data.code || null };
            }
        }
        return { message: httpFallbackMessage(status), code: null };
    }

    // ---------------------------------------------------------------
    // 核心请求函数
    // ---------------------------------------------------------------
    async function fetchJson(url, options) {
        options = options || {};
        const method = (options.method || 'GET').toUpperCase();

        const headers = Object.assign({}, options.headers || {});

        // body 是普通对象 → 自动 JSON 化并补 Content-Type
        let body = options.body;
        if (body && typeof body === 'object' && !(body instanceof FormData)
            && !(body instanceof Blob) && !(body instanceof ArrayBuffer)) {
            headers['Content-Type'] = headers['Content-Type'] || 'application/json';
            body = JSON.stringify(body);
        }

        // 非安全方法 → 强制带 CSRF
        if (!isSafeMethod(method)) {
            const token = csrfToken();
            if (!token) {
                throw new ApiError('页面缺少 CSRF token，无法提交写操作', 0, 'CSRF_TOKEN_MISSING');
            }
            headers['X-CSRFToken'] = token;
        }

        let resp;
        try {
            resp = await fetch(url, {
                method: method,
                headers: headers,
                body: body,
                credentials: 'same-origin',   // 必须带 session cookie
            });
        } catch (netErr) {
            throw new ApiError('网络异常，请检查连接后重试', 0, 'NETWORK_ERROR', null);
        }

        const contentType = resp.headers.get('Content-Type') || '';
        let data = null;
        if (contentType.indexOf('application/json') !== -1) {
            data = await resp.json().catch(() => null);
        }

        if (!resp.ok) {
            const info = extractError(data, resp.status);
            throw new ApiError(info.message, resp.status, info.code, data);
        }

        return data;
    }

    // ---------------------------------------------------------------
    // 语义化快捷方法
    // ---------------------------------------------------------------
    const api = {
        request: fetchJson,
        get: (url, params) => {
            if (params && Object.keys(params).length) {
                const qs = new URLSearchParams();
                Object.keys(params).forEach(function (k) {
                    if (params[k] !== undefined && params[k] !== null && params[k] !== '') {
                        qs.append(k, params[k]);
                    }
                });
                const q = qs.toString();
                if (q) url += (url.indexOf('?') === -1 ? '?' : '&') + q;
            }
            return fetchJson(url, { method: 'GET' });
        },
        post: (url, body) => fetchJson(url, { method: 'POST', body: body }),
        put: (url, body) => fetchJson(url, { method: 'PUT', body: body }),
        patch: (url, body) => fetchJson(url, { method: 'PATCH', body: body }),
        del: (url, body) => fetchJson(url, { method: 'DELETE', body: body }),
    };

    // ---------------------------------------------------------------
    // 接管原生 fetch —— 让既有的裸 fetch 调用也能带上 CSRF
    // ---------------------------------------------------------------
    const _origFetch = global.fetch ? global.fetch.bind(global) : null;
    if (_origFetch) {
        global.fetch = function (input, init) {
            init = init || {};
            let method = init.method || 'GET';
            if (typeof input !== 'string' && input && input.method) method = input.method;
            if (!isSafeMethod(method)) {
                const token = csrfToken();
                if (token) {
                    let headers;
                    try {
                        headers = new Headers(init.headers || {});
                    } catch (e) {
                        headers = init.headers;
                    }
                    if (headers && typeof headers.set === 'function' && !headers.has('X-CSRFToken')) {
                        headers.set('X-CSRFToken', token);
                        init.headers = headers;
                    }
                }
            }
            return _origFetch(input, init);
        };
    }

    // ---------------------------------------------------------------
    // 接管 jQuery.$.ajax —— 同理
    // ---------------------------------------------------------------
    function installJqueryHook() {
        const jq = global.jQuery || global.$;
        if (!jq || !jq.ajaxSetup || jq.__powerArenaCsrfHooked) return;
        jq.__powerArenaCsrfHooked = true;
        jq.ajaxSetup({
            beforeSend: function (xhr, settings) {
                const method = (settings.type || 'GET').toUpperCase();
                if (!isSafeMethod(method)) {
                    const token = csrfToken();
                    if (token) xhr.setRequestHeader('X-CSRFToken', token);
                }
            }
        });
    }
    installJqueryHook();
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', installJqueryHook);
    }

    // ---------------------------------------------------------------
    // 导出
    // ---------------------------------------------------------------
    global.fetchJson = fetchJson;
    global.api = api;
    global.ApiError = ApiError;
    global.getCsrfToken = csrfToken;
})(window);
