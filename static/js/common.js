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

// 全局 UI 逻辑
const ui = {
    refreshTimer: null,
    currentTaskId: null,

    startRefreshTimer() {
        if (this.refreshTimer) clearInterval(this.refreshTimer);
        this.refreshData();
        this.refreshTimer = setInterval(() => this.refreshData(), 2000);
    },

    stopRefreshTimer() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    },

    async refreshData() {
        try {
            // 1. 更新统计信息
            const stats = await api.getStats();
            this.updateStats(stats);

            // 2. 如果在任务列表页面，更新列表
            if (window.currentPageType && window.renderTaskList) {
                let tasks = [];
                if (window.currentPageType === 'downloading') {
                    const [downloadingData, pendingData] = await Promise.all([
                        api.getTasks('downloading'),
                        api.getTasks('pending')
                    ]);
                    tasks = [...downloadingData.tasks, ...pendingData.tasks];
                    tasks.sort((a, b) => b.id - a.id);
                } else if (window.currentPageType === 'completed') {
                    const data = await api.getTasks('completed');
                    tasks = data.tasks;
                } else if (window.currentPageType === 'all') {
                    const data = await api.getTasks();
                    tasks = data.tasks;
                }
                
                window.renderTaskList(tasks);
            }

            // 3. 如果详情模态框打开，更新日志
            if (this.currentTaskId) {
                this.refreshTaskLogs(this.currentTaskId);
            }

        } catch (err) {
            console.error('刷新数据失败:', err);
            if (err.message && err.message.includes('401')) {
                window.location.href = '/login';
            }
        }
    },

    updateStats(stats) {
        const setText = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        // 侧边栏
        setText('sidebarTotal', stats.total);
        setText('sidebarDownloading', stats.downloading);
        setText('sidebarCompleted', stats.completed);
        // 顶部卡片
        setText('statTotal', stats.total);
        setText('statDownloading', stats.downloading);
        setText('statCompleted', stats.completed);
        setText('statFailed', stats.failed);
    },

    async refreshTaskLogs(taskId) {
        const logsData = await api.getTaskLogs(taskId);
        const logContainer = document.getElementById('taskLogs');
        if (logContainer) {
            // 检查是否滚动到底部
            const isScrolledToBottom = logContainer.scrollHeight - logContainer.clientHeight <= logContainer.scrollTop + 1;
            
            logContainer.innerHTML = logsData.logs.map(log => 
                `<div class="log-line"><span class="text-muted">[${new Date(log.timestamp).toLocaleTimeString()}]</span> ${log.message}</div>`
            ).join('');
            
            // 如果之前在底部，保持在底部
            if (isScrolledToBottom) {
                logContainer.scrollTop = logContainer.scrollHeight;
            }
        }
    },

    async loadSettings() {
        try {
            const settings = await api.getSettings();
            const form = document.getElementById('settingsForm');
            if (!form) return;
            
            for (const [key, value] of Object.entries(settings)) {
                const input = form.elements[key];
                if (input) {
                    if (input.type === 'checkbox') {
                        input.checked = value === 'true';
                        input.dispatchEvent(new Event('change'));
                    } else {
                        input.value = value;
                    }
                }
            }
        } catch (err) {
            showToast('加载设置失败: ' + err.message, 'danger');
        }
    }
};

// 全局函数
window.logout = async () => {
    if (confirm('确定要退出登录吗？')) {
        await api.logout();
        window.location.href = '/login';
    }
};

window.showTaskDetail = async (id) => {
    ui.currentTaskId = id;
    const modalEl = document.getElementById('taskDetailModal');
    const modal = new bootstrap.Modal(modalEl);
    
    try {
        const data = await api.getTask(id);
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

        modalEl.addEventListener('hidden.bs.modal', () => {
            ui.currentTaskId = null;
        }, { once: true });

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
    
    const handleHidden = () => {
        videoPlayer.pause();
        videoPlayer.src = '';
        modalEl.removeEventListener('hidden.bs.modal', handleHidden);
    };
    modalEl.addEventListener('hidden.bs.modal', handleHidden);
    
    videoPlayer.play().catch(e => console.log('Auto play prevented'));
};