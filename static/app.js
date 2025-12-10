// 配置
const API_BASE = '/api';
const REFRESH_INTERVAL = 2000; // 2秒刷新一次

// 状态
let state = {
    isAuthenticated: false,
    currentPage: 'new', // new, downloading, completed, all
    refreshTimer: null,
    currentTaskId: null // 用于详情模态框
};

// 工具函数
const formatSize = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const formatDate = (isoString) => {
    if (!isoString) return '-';
    return new Date(isoString).toLocaleString();
};

const showToast = (message, type = 'info') => {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) return;

    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-white bg-${type} border-0`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    toastContainer.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl);
    toast.show();

    toastEl.addEventListener('hidden.bs.toast', () => {
        toastEl.remove();
    });
};

// API 交互
const api = {
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
            return data.authenticated;
        } catch (e) {
            return false;
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

    async deleteTask(taskId, deleteFile = true) {
        const res = await fetch(`${API_BASE}/tasks/${taskId}?delete_file=${deleteFile}`, { method: 'DELETE' });
        if (!res.ok) throw new Error((await res.json()).error || '删除任务失败');
        return await res.json();
    },

    async getTaskLogs(taskId) {
        const res = await fetch(`${API_BASE}/tasks/${taskId}/logs`);
        return await res.json();
    }
};

// UI 逻辑
const ui = {
    init() {
        this.bindEvents();
        this.checkLoginStatus();
    },

    bindEvents() {
        // 登录表单
        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const pwd = document.getElementById('password').value;
            const btn = e.target.querySelector('button');
            const spinner = document.getElementById('loginSpinner');
            const btnText = document.getElementById('loginBtnText');
            const errorDiv = document.getElementById('loginError');

            try {
                btn.disabled = true;
                spinner.classList.remove('d-none');
                btnText.textContent = '登录中...';
                errorDiv.classList.add('d-none');

                await api.login(pwd);
                state.isAuthenticated = true;
                this.showMainApp();
            } catch (err) {
                errorDiv.textContent = err.message;
                errorDiv.classList.remove('d-none');
            } finally {
                btn.disabled = false;
                spinner.classList.add('d-none');
                btnText.textContent = '登录';
            }
        });

        // 侧边栏导航
        document.querySelectorAll('.sidebar-menu a').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = e.currentTarget.dataset.page;
                this.switchPage(page);
            });
        });

        // 新建任务表单
        document.getElementById('newTaskForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const urlInput = document.getElementById('taskUrl');
            const nameInput = document.getElementById('taskName');
            const btn = e.target.querySelector('button');

            try {
                btn.disabled = true;
                const originalText = btn.innerHTML;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 创建中...';
                
                await api.createTask(urlInput.value, nameInput.value);
                showToast('任务创建成功', 'success');
                urlInput.value = '';
                nameInput.value = '';
                this.switchPage('downloading');
            } catch (err) {
                showToast(err.message, 'danger');
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-download"></i> 开始下载';
            }
        });

        // 模态框关闭时清除定时器（如果需要）
        const taskDetailModal = document.getElementById('taskDetailModal');
        if (taskDetailModal) {
            taskDetailModal.addEventListener('hidden.bs.modal', () => {
                state.currentTaskId = null;
            });
        }
    },

    async checkLoginStatus() {
        const isAuth = await api.checkAuth();
        if (isAuth) {
            state.isAuthenticated = true;
            this.showMainApp();
        } else {
            this.showLoginPage();
        }
    },

    showLoginPage() {
        document.getElementById('loginPage').classList.remove('d-none');
        document.getElementById('mainApp').classList.add('d-none');
        this.stopRefreshTimer();
    },

    showMainApp() {
        document.getElementById('loginPage').classList.add('d-none');
        document.getElementById('mainApp').classList.remove('d-none');
        this.switchPage('new');
        this.startRefreshTimer();
    },

    switchPage(page) {
        state.currentPage = page;
        
        // 更新侧边栏激活状态
        document.querySelectorAll('.sidebar-menu a').forEach(link => {
            link.classList.toggle('active', link.dataset.page === page);
        });

        // 隐藏所有页面
        document.querySelectorAll('.page-content').forEach(el => el.classList.add('d-none'));
        
        // 显示目标页面
        const targetPage = document.getElementById(`page${page.charAt(0).toUpperCase() + page.slice(1)}`);
        if (targetPage) targetPage.classList.remove('d-none');

        // 更新标题
        const titles = {
            'new': '新建任务',
            'downloading': '下载中',
            'completed': '已完成',
            'all': '所有任务'
        };
        document.getElementById('pageTitle').textContent = titles[page];

        // 立即刷新数据
        this.refreshData();
    },

    startRefreshTimer() {
        if (state.refreshTimer) clearInterval(state.refreshTimer);
        this.refreshData();
        state.refreshTimer = setInterval(() => this.refreshData(), REFRESH_INTERVAL);
    },

    stopRefreshTimer() {
        if (state.refreshTimer) {
            clearInterval(state.refreshTimer);
            state.refreshTimer = null;
        }
    },

    async refreshData() {
        if (!state.isAuthenticated) return;

        try {
            // 1. 更新统计信息
            const stats = await api.getStats();
            this.updateStats(stats);

            // 2. 根据当前页面更新任务列表
            if (state.currentPage !== 'new') {
                let status = '';
                if (state.currentPage === 'downloading') status = 'downloading';
                if (state.currentPage === 'completed') status = 'completed';
                
                const data = await api.getTasks(status);
                this.renderTaskList(data.tasks);
            }

            // 3. 如果详情模态框打开，更新日志
            if (state.currentTaskId) {
                this.refreshTaskLogs(state.currentTaskId);
            }

        } catch (err) {
            console.error('刷新数据失败:', err);
            if (err.message && err.message.includes('401')) {
                state.isAuthenticated = false;
                this.showLoginPage();
            }
        }
    },

    updateStats(stats) {
        // 侧边栏统计
        const setText = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        setText('sidebarTotal', stats.total);
        setText('sidebarDownloading', stats.downloading);
        setText('sidebarCompleted', stats.completed);

        // 顶部卡片统计
        setText('statTotal', stats.total);
        setText('statDownloading', stats.downloading);
        setText('statCompleted', stats.completed);
        setText('statFailed', stats.failed);
    },

    renderTaskList(tasks) {
        const containerId = `${state.currentPage}Tasks`;
        const container = document.getElementById(containerId);
        if (!container) return;

        if (tasks.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <i class="bi bi-inbox"></i>
                    <h4>暂无任务</h4>
                    <p>当前列表没有任务数据</p>
                </div>
            `;
            return;
        }

        const html = tasks.map(task => this.createTaskCard(task)).join('');
        container.innerHTML = html;
    },

    createTaskCard(task) {
        const statusColors = {
            'pending': 'secondary',
            'downloading': 'primary',
            'completed': 'success',
            'failed': 'danger',
            'cancelled': 'warning'
        };
        const statusText = {
            'pending': '等待中',
            'downloading': '下载中',
            'completed': '已完成',
            'failed': '失败',
            'cancelled': '已取消'
        };

        const color = statusColors[task.status] || 'secondary';
        const progress = task.progress || 0;
        
        let actions = '';
        if (task.status === 'downloading' || task.status === 'pending') {
            actions += `<button class="btn-sm-custom btn-danger-custom" onclick="stopTask(${task.id})"><i class="bi bi-stop-circle"></i> 停止</button>`;
        }
        if (task.status === 'completed') {
            actions += `<button class="btn-sm-custom btn-play" onclick="playVideo('${task.file_path ? task.file_path.replace(/\\/g, '\\\\') : ''}', '${task.url}')"><i class="bi bi-play-fill"></i> 播放</button>`;
            actions += `<a href="/api/download/${task.id}" class="btn-sm-custom btn-download" target="_blank"><i class="bi bi-download"></i> 下载</a>`;
        }
        actions += `<button class="btn-sm-custom btn-info-custom" onclick="showTaskDetail(${task.id})"><i class="bi bi-info-circle"></i> 详情</button>`;
        if (task.status !== 'downloading') {
            actions += `<button class="btn-sm-custom btn-danger-custom" onclick="deleteTask(${task.id})"><i class="bi bi-trash"></i> 删除</button>`;
        }

        return `
            <div class="task-card ${task.status === 'completed' ? 'completed' : (task.status === 'failed' ? 'failed' : '')}">
                <div class="task-header">
                    <div class="task-info">
                        <h5 class="text-truncate" style="max-width: 500px;" title="${task.url}">${task.url.split('/').pop().split('?')[0] || '未命名任务'}</h5>
                        <div class="task-url text-truncate" style="max-width: 500px;">${task.url}</div>
                    </div>
                    <span class="task-badge bg-${color}-subtle text-${color} border border-${color}-subtle">
                        ${statusText[task.status]}
                    </span>
                </div>
                
                <div class="task-progress">
                    <div class="d-flex justify-content-between mb-1">
                        <small class="text-muted">${progress.toFixed(1)}%</small>
                        <small class="text-muted">${task.status === 'downloading' ? '下载中...' : ''}</small>
                    </div>
                    <div class="progress">
                        <div class="progress-bar bg-${color} progress-bar-striped ${task.status === 'downloading' ? 'progress-bar-animated' : ''}" 
                             role="progressbar" style="width: ${progress}%"></div>
                    </div>
                </div>

                <div class="task-meta">
                    <div class="task-meta-item">
                        <i class="bi bi-clock"></i> ${formatDate(task.created_at)}
                    </div>
                    ${task.file_size ? `
                    <div class="task-meta-item">
                        <i class="bi bi-hdd"></i> ${formatSize(task.file_size)}
                    </div>
                    ` : ''}
                    ${task.duration ? `
                    <div class="task-meta-item">
                        <i class="bi bi-film"></i> ${task.duration}
                    </div>
                    ` : ''}
                </div>

                <div class="task-actions">
                    ${actions}
                </div>
            </div>
        `;
    },

    async refreshTaskLogs(taskId) {
        const logsData = await api.getTaskLogs(taskId);
        const logContainer = document.getElementById('taskLogs');
        if (logContainer) {
            logContainer.innerHTML = logsData.logs.map(log => 
                `<div class="log-line"><span class="text-muted">[${new Date(log.timestamp).toLocaleTimeString()}]</span> ${log.message}</div>`
            ).join('');
            // 自动滚动到底部
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }
};

// 全局函数 (用于 HTML onclick)
window.logout = async () => {
    if (confirm('确定要退出登录吗？')) {
        await api.logout();
        state.isAuthenticated = false;
        ui.showLoginPage();
    }
};

window.stopTask = async (id) => {
    if (confirm('确定要停止该任务吗？')) {
        try {
            await api.stopTask(id);
            showToast('任务已停止', 'success');
            ui.refreshData();
        } catch (err) {
            showToast(err.message, 'danger');
        }
    }
};

window.deleteTask = async (id) => {
    // 创建一个自定义的确认对话框
    const confirmModal = document.createElement('div');
    confirmModal.className = 'modal fade';
    confirmModal.id = 'deleteConfirmModal';
    confirmModal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">删除确认</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <p>确定要删除该任务吗？</p>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="deleteFileCheck" checked>
                        <label class="form-check-label" for="deleteFileCheck">
                            同时删除已下载的文件
                        </label>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="button" class="btn btn-danger" id="confirmDeleteBtn">删除</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(confirmModal);

    const modal = new bootstrap.Modal(confirmModal);
    modal.show();

    document.getElementById('confirmDeleteBtn').onclick = async () => {
        const deleteFile = document.getElementById('deleteFileCheck').checked;
        try {
            await api.deleteTask(id, deleteFile);
            showToast('任务已删除', 'success');
            ui.refreshData();
            modal.hide();
        } catch (err) {
            showToast(err.message, 'danger');
        }
    };

    confirmModal.addEventListener('hidden.bs.modal', () => {
        confirmModal.remove();
    });
};

window.showTaskDetail = async (id) => {
    state.currentTaskId = id;
    const modalEl = document.getElementById('taskDetailModal');
    const modal = new bootstrap.Modal(modalEl);
    
    // 先获取任务详情
    try {
        const res = await fetch(`${API_BASE}/tasks/${id}`);
        const data = await res.json();
        const task = data.task;

        const content = document.getElementById('taskDetailContent');
        content.innerHTML = `
            <div class="row mb-4">
                <div class="col-md-6">
                    <h6>基本信息</h6>
                    <table class="table table-sm table-borderless">
                        <tr><td class="text-muted" width="80">ID:</td><td>${task.id}</td></tr>
                        <tr><td class="text-muted">状态:</td><td>${task.status}</td></tr>
                        <tr><td class="text-muted">创建时间:</td><td>${formatDate(task.created_at)}</td></tr>
                        <tr><td class="text-muted">完成时间:</td><td>${formatDate(task.completed_at)}</td></tr>
                    </table>
                </div>
                <div class="col-md-6">
                    <h6>文件信息</h6>
                    <table class="table table-sm table-borderless">
                        <tr><td class="text-muted" width="80">大小:</td><td>${formatSize(task.file_size || 0)}</td></tr>
                        <tr><td class="text-muted">时长:</td><td>${task.duration || '-'}</td></tr>
                        <tr><td class="text-muted">路径:</td><td class="text-break">${task.file_path || '-'}</td></tr>
                    </table>
                </div>
                <div class="col-12 mt-2">
                    <h6>来源 URL</h6>
                    <div class="p-2 bg-light rounded text-break font-monospace small">${task.url}</div>
                </div>
                ${task.error_message ? `
                <div class="col-12 mt-3">
                    <div class="alert alert-danger mb-0">
                        <strong>错误信息:</strong> ${task.error_message}
                    </div>
                </div>
                ` : ''}
            </div>
            <h6>任务日志</h6>
            <div id="taskLogs" class="log-container">
                <div class="text-center text-muted">加载日志中...</div>
            </div>
        `;

        modal.show();
        ui.refreshTaskLogs(id);

    } catch (err) {
        showToast('获取详情失败: ' + err.message, 'danger');
    }
};

window.playVideo = (filePath, url) => {
    if (!filePath) return;
    const filename = filePath.split(/[\\/]/).pop();
    const videoUrl = `/videos/${encodeURIComponent(filename)}`;
    
    const videoPlayer = document.getElementById('videoPlayer');
    videoPlayer.src = videoUrl;
    
    const modalEl = document.getElementById('videoPlayerModal');
    const modal = new bootstrap.Modal(modalEl);
    modal.show();
    
    // 监听模态框关闭事件，停止播放
    const handleHidden = () => {
        videoPlayer.pause();
        videoPlayer.src = '';
        modalEl.removeEventListener('hidden.bs.modal', handleHidden);
    };
    modalEl.addEventListener('hidden.bs.modal', handleHidden);
    
    // 尝试自动播放
    videoPlayer.play().catch(e => console.log('Auto play prevented'));
};

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    ui.init();
});