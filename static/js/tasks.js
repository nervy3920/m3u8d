// 任务列表渲染逻辑
window.renderTaskList = (tasks) => {
    const containerId = `${window.currentPageType}Tasks`;
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

    const html = tasks.map(task => createTaskCard(task)).join('');
    container.innerHTML = html;
};

function createTaskCard(task) {
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
    
    // 标题显示逻辑：优先显示自定义名称，否则显示文件名，最后显示默认
    let title = task.custom_name;
    if (!title) {
        title = task.url.split('/').pop().split('?')[0] || '未命名任务';
    }

    let actions = '';
    if (task.status === 'downloading' || task.status === 'pending') {
        actions += `<button class="btn-sm-custom btn-danger-custom" onclick="stopTask(${task.id})"><i class="bi bi-stop-circle"></i> 停止</button>`;
    } else if (task.status === 'failed' || task.status === 'cancelled') {
        actions += `<button class="btn-sm-custom btn-primary-custom" onclick="retryTask(${task.id})"><i class="bi bi-arrow-clockwise"></i> 重试</button>`;
    }

    if (task.status === 'completed') {
        actions += `<button class="btn-sm-custom btn-play" onclick="playVideo('${task.file_path ? task.file_path.replace(/\\/g, '\\\\') : ''}', '${task.url}')"><i class="bi bi-play-fill"></i> 播放</button>`;
        actions += `<a href="/api/download/${task.id}" class="btn-sm-custom btn-download" target="_blank"><i class="bi bi-download"></i> 下载</a>`;
    }
    actions += `<button class="btn-sm-custom btn-info-custom" onclick="showTaskDetail(${task.id})"><i class="bi bi-info-circle"></i> 详情</button>`;
    if (task.status !== 'downloading') {
        actions += `<button class="btn-sm-custom btn-danger-custom" onclick="deleteTask(${task.id})"><i class="bi bi-trash"></i> 删除</button>`;
    }

    // 详细进度信息
    let detailsInfo = '';
    if (task.status === 'downloading') {
        detailsInfo = `
            <div class="d-flex justify-content-between mt-1 small text-muted">
                <span><i class="bi bi-speedometer2"></i> ${task.speed || '-'}</span>
                <span><i class="bi bi-hourglass-split"></i> ${task.eta || '-'}</span>
                <span><i class="bi bi-file-earmark"></i> ${task.downloaded_size || '-'} / ${task.total_size || '-'}</span>
            </div>
        `;
    }

    return `
        <div class="task-card ${task.status === 'completed' ? 'completed' : (task.status === 'failed' ? 'failed' : '')}">
            <div class="task-header">
                <div class="task-info">
                    <h5 class="text-truncate" style="max-width: 500px;" title="${title}">${title}</h5>
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
                ${detailsInfo}
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
}

// 任务操作函数
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

window.retryTask = async (id) => {
    if (confirm('确定要重试该任务吗？')) {
        try {
            await api.retryTask(id);
            showToast('任务已重新开始', 'success');
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