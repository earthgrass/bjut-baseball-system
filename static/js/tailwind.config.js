/* ====================================================================
 * POWER ARENA — Tailwind 共享配置
 * 由 10 个模板内联的 tailwind.config 合并而来 (Phase D2)
 * 必须在 cdn.tailwindcss.com 之前加载
 * ==================================================================== */

tailwind.config = {
    theme: {
        extend: {
            colors: {
                arena: {
                    bg: '#050505',
                    surface: '#0A0A0A',
                    surface2: '#111111',
                    red: '#E60000',
                    redDark: '#990000',
                    redAccent: '#FF1A1A'
                }
            }
        }
    }
};