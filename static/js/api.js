// 配置
const API_BASE = '/api';

// API 交互
const api = {
    async initSystem(password) {
        const res = await fetch(`${API_BASE}/init`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        if (!res.ok) throw new Error((await res.json()).error || '初始化失败');
        return await res.json();
    },

    async login(password) {
        const res = await fetch(`${API_BASE}/auth`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        if (!res.ok) throw new Error((await res.json()).message || '登录失败');
        return await res.json();
    },

    async checkAuth() {
        try {
            const res = await fetch(`${API_BASE}/check-auth`);
            const data = await res.json();
            return data; // 返回完整对象 { authenticated: bool, initialized: bool }
        } catch (e) {
            return { authenticated: false, initialized: false };
        }
    },

    async logout() {
        await fetch(`${API_BASE}/logout`, { method: 'POST' });
    },

    async getStats() {
        const res = await fetch(`${API_BASE}/stats`);
        return await res.json();
    },

    /**
     * 获取任务，支持 status 与分页参数
     * getTasks(status='', page=1, per_page=20)
     * 返回 { tasks: [...], pagination: {...} }
     */
    async getTasks(status = '', page = 1, per_page = 20) {
        let url = `${API_BASE}/tasks?page=${page}&per_page=${per_page}`;
        if (status) url += `&status=${encodeURIComponent(status)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error((await res.json()).error || '获取任务失败');
        return await res.json();
    },

    /**
     * 创建任务：兼容单个和批量
     * - createTask(url, name)  (单个)
     * - createTask({ text: 'line1\nline2' }) (批量)
     */
    async createTask(urlOrPayload, name) {
        let body;
        if (typeof urlOrPayload === 'string') {
            // 如果包含换行或竖线，使用 text 字段批量提交
            if (urlOrPayload.includes('\n') || urlOrPayload.includes('|')) {
                body = { text: urlOrPayload };
            } else {
                body = { url: urlOrPayload, name: name || '' };
            }
        } else if (typeof urlOrPayload === 'object' && urlOrPayload !== null) {
            body = urlOrPayload;
        } else {
            throw new Error('无效的参数');
        }

        const res = await fetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error((await res.json()).error || '创建任务失败');
        return await res.json();
    },

    async stopTask(taskId) {
        const res = await fetch(`${API_BASE}/tasks/${taskId}/stop`, { method: 'POST' });
        if (!res.ok) throw new Error((await res.json()).error || '停止任务失败');
        return await res.json();
    },

    async retryTask(taskId) {
        const res = await fetch(`${API_BASE}/tasks/${taskId}/retry`, { method: 'POST' });
        if (!res.ok) throw new Error((await res.json()).error || '重试任务失败');
        return await res.json();
    },

    async deleteTask(taskId, deleteFile = true) {
        const res = await fetch(`${API_BASE}/tasks/${taskId}?delete_file=${deleteFile}`, { method: 'DELETE' });
        if (!res.ok) throw new Error((await res.json()).error || '删除任务失败');
        return await res.json();
    },

    /**
     * 批量删除任务
     * ids: array of ids
     * deleteFile: boolean
     */
    async batchDelete(ids, deleteFile = true) {
        const res = await fetch(`${API_BASE}/tasks/batch-delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids, delete_file: deleteFile })
        });
        if (!res.ok) throw new Error((await res.json()).error || '批量删除失败');
        return await res.json();
    },

    async getTaskLogs(taskId) {
        const res = await fetch(`${API_BASE}/tasks/${taskId}/logs`);
        return await res.json();
    },

    async getTask(taskId) {
        const res = await fetch(`${API_BASE}/tasks/${taskId}`);
        if (!res.ok) throw new Error('获取任务详情失败');
        return await res.json();
    },

    async getSettings() {
        const res = await fetch(`${API_BASE}/settings`);
        if (!res.ok) throw new Error('获取设置失败');
        return await res.json();
    },

    async updateSettings(settings) {
        const res = await fetch(`${API_BASE}/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        if (!res.ok) throw new Error((await res.json()).error || '更新设置失败');
        return await res.json();
    },

    async generateApiKey() {
        const res = await fetch(`${API_BASE}/settings/apikey`, { method: 'POST' });
        if (!res.ok) throw new Error('生成 API Key 失败');
        return await res.json();
    },

    async parseUniversal(url, useSelenium = false) {
        const res = await fetch(`${API_BASE}/parse/universal`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, use_selenium: useSelenium })
        });
        if (!res.ok) throw new Error((await res.json()).error || '解析失败');
        return await res.json();
    },

    async parseBatch(urls, useSelenium = false) {
        const res = await fetch(`${API_BASE}/parse/batch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls, use_selenium: useSelenium })
        });
        if (!res.ok) throw new Error((await res.json()).error || '批量解析失败');
        return await res.json();
    }
};