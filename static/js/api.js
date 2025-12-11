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

    async getTasks(status = '') {
        const url = status ? `${API_BASE}/tasks?status=${status}` : `${API_BASE}/tasks`;
        const res = await fetch(url);
        return await res.json();
    },

    async createTask(url, name) {
        const res = await fetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, name })
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

    async parseUniversal(url) {
        const res = await fetch(`${API_BASE}/parse/universal`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        if (!res.ok) throw new Error((await res.json()).error || '解析失败');
        return await res.json();
    }
};