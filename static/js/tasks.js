// 任务列表渲染逻辑（支持复选、分页）
window.renderTaskList = (tasks, pagination) => {
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
        // 清空分页
        const pager = document.getElementById('paginationControls');
        if (pager) pager.innerHTML = '';
        return;
    }

    // 获取当前选中的任务ID
    const currentCheckedIds = Array.from(container.querySelectorAll('.task-checkbox:checked')).map(cb => cb.value);

    const html = tasks.map(task => createTaskCard(task)).join('');
    container.innerHTML = html;

    // 恢复选中状态
    if (currentCheckedIds.length > 0) {
        currentCheckedIds.forEach(id => {
            const checkbox = document.getElementById(`taskCheckbox${id}`);
            if (checkbox) {
                checkbox.checked = true;
            }
        });
    }

    // 渲染分页（如果提供）
    if (pagination && document.getElementById('paginationControls')) {
        const pager = document.getElementById('paginationControls');
        const page = pagination.page || 1;
        const total_pages = pagination.total_pages || 1;
        let pagesHtml = '';
        for (let i = 1; i <= total_pages; i++) {
            pagesHtml += `<li class="page-item ${i === page ? 'active' : ''}"><a class="page-link" href="javascript:gotoPage(${i})">${i}</a></li>`;
        }
        pager.innerHTML = pagesHtml;
    }
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
        // 尝试从 file_path 获取文件名
        if (task.file_path) {
            title = task.file_path.split(/[\\/]/).pop();
        } else {
            title = task.url.split('/').pop().split('?')[0] || '未命名任务';
        }
    }

    // 显示提交名与生成名的简短信息（用于详情也可查看完整）
    const generatedName = task.file_path ? (task.file_path.split(/[\\/]/).pop()) : '等待生成...';
    const submittedName = task.custom_name || '未指定 (自动生成)';

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
            <div class="task-header d-flex align-items-start">
                <div class="form-check me-3">
                    <input class="form-check-input task-checkbox" type="checkbox" value="${task.id}" id="taskCheckbox${task.id}">
                </div>
                <div class="task-info flex-grow-1">
                    <h5 class="text-truncate" style="max-width: 500px;" title="${title}">${title}</h5>
                    <div class="small text-muted mb-1">
                        <span class="me-3"><i class="bi bi-tag"></i> 提交名: ${submittedName}</span>
                        <span><i class="bi bi-file-earmark-text"></i> 生成名: ${generatedName}</span>
                    </div>
                    <div class="task-url text-truncate text-muted small" style="max-width: 500px;"><i class="bi bi-link-45deg"></i> ${task.url}</div>
                </div>
                <span class="task-badge bg-${color}-subtle text-${color} border border-${color}-subtle ms-3">
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

// 全选/取消全选
window.toggleSelectAll = (checked) => {
    // 只选择当前可见的任务列表中的复选框
    const containerId = `${window.currentPageType}Tasks`;
    const container = document.getElementById(containerId);
    if (container) {
        const checkboxes = container.querySelectorAll('.task-checkbox');
        // 如果传入了 checked 参数，则强制设置；否则进行反选
        if (typeof checked === 'boolean') {
            checkboxes.forEach(cb => cb.checked = checked);
        } else {
            // 检查是否所有都已选中
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);
            checkboxes.forEach(cb => cb.checked = !allChecked);
        }
    }
};

// 批量删除选中
window.batchDeleteSelected = async () => {
    const checkboxes = document.querySelectorAll('.task-checkbox:checked');
    const ids = Array.from(checkboxes).map(cb => cb.value);

    if (ids.length === 0) {
        showToast('请先选择要删除的任务', 'warning');
        return;
    }

    // 创建一个自定义的确认对话框
    const confirmModal = document.createElement('div');
    confirmModal.className = 'modal fade';
    confirmModal.id = 'batchDeleteConfirmModal';
    confirmModal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">批量删除确认</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <p>确定要删除选中的 ${ids.length} 个任务吗？</p>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="batchDeleteFileCheck" checked>
                        <label class="form-check-label" for="batchDeleteFileCheck">
                            同时删除已下载的文件
                        </label>
                    </div>
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                    <button type="button" class="btn btn-danger" id="confirmBatchDeleteBtn">删除</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(confirmModal);

    const modal = new bootstrap.Modal(confirmModal);
    modal.show();

    document.getElementById('confirmBatchDeleteBtn').onclick = async () => {
        const deleteFile = document.getElementById('batchDeleteFileCheck').checked;
        const btn = document.getElementById('confirmBatchDeleteBtn');
        btn.disabled = true;
        btn.innerHTML = '删除中...';

        try {
            const res = await fetch('/api/tasks/batch-delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids: ids, delete_file: deleteFile })
            });
            
            if (!res.ok) {
                throw new Error('批量删除请求失败');
            }
            
            const data = await res.json();
            if (data.success) {
                showToast(`批量删除完成`, 'success');
                ui.refreshData();
                modal.hide();
            } else {
                showToast(data.error || '批量删除失败', 'danger');
            }
        } catch (err) {
            showToast(err.message, 'danger');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '删除';
        }
    };

    confirmModal.addEventListener('hidden.bs.modal', () => {
        confirmModal.remove();
    });
};