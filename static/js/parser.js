let currentM3u8Url = '';
let currentTitle = '';
let dp = null;
let batchResults = [];

document.addEventListener('DOMContentLoaded', () => {
    const parserForm = document.getElementById('parserForm');
    if (parserForm) {
        parserForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // 判断当前是单条还是批量
            const activeTab = document.querySelector('#parserTabs .nav-link.active');
            const isBatch = activeTab.id === 'batch-tab';
            const useSelenium = document.getElementById('useSelenium').checked;
            const btn = e.target.querySelector('button[type="submit"]');
            const resultDiv = document.getElementById('parseResult');
            
            // 隐藏所有结果区域
            resultDiv.classList.add('d-none');
            document.getElementById('singleParseResult').classList.add('d-none');
            document.getElementById('batchParseResult').classList.add('d-none');
            document.getElementById('singleResult').classList.add('d-none');
            document.getElementById('multiResult').classList.add('d-none');
            document.getElementById('previewPlayer').classList.add('d-none');
            if (dp) {
                dp.destroy();
                dp = null;
            }

            try {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 解析中...';

                if (isBatch) {
                    // 批量解析逻辑
                    const urls = document.getElementById('batchVideoUrls').value.trim();
                    if (!urls) throw new Error('请输入视频链接');

                    const urlList = urls.split('\n').map(u => u.trim()).filter(u => u);
                    if (urlList.length === 0) throw new Error('请输入有效的视频链接');

                    const data = await api.parseBatch(urlList, useSelenium);
                    
                    batchResults = data.results;
                    renderBatchResults(data.results);
                    
                    resultDiv.classList.remove('d-none');
                    document.getElementById('batchParseResult').classList.remove('d-none');

                } else {
                    // 单条解析逻辑
                    const urlInput = document.getElementById('videoPageUrl');
                    if (!urlInput.value.trim()) throw new Error('请输入视频链接');

                    const data = await api.parseUniversal(urlInput.value, useSelenium);
                    
                    currentTitle = data.title;
                    document.getElementById('parsedTitle').textContent = data.title;
                    
                    resultDiv.classList.remove('d-none');
                    document.getElementById('singleParseResult').classList.remove('d-none');

                    if (data.count === 1) {
                        // 单个结果
                        currentM3u8Url = data.results[0];
                        document.getElementById('parsedUrl').textContent = currentM3u8Url;
                        document.getElementById('singleResult').classList.remove('d-none');
                    } else {
                        // 多个结果
                        document.getElementById('multiResult').classList.remove('d-none');
                        document.getElementById('urlList').innerHTML = data.results.map((url, index) => `
                            <div class="list-group-item">
                                <div class="d-flex w-100 justify-content-between align-items-center mb-2">
                                    <h6 class="mb-0 text-truncate">链接 ${index + 1}</h6>
                                    <div class="btn-group btn-group-sm">
                                        <button type="button" class="btn btn-outline-primary" onclick="selectForDownload('${url}')">
                                            <i class="bi bi-download"></i> 下载
                                        </button>
                                        <button type="button" class="btn btn-outline-success" onclick="selectForPreview('${url}')">
                                            <i class="bi bi-play-fill"></i> 预览
                                        </button>
                                    </div>
                                </div>
                                <small class="text-muted text-break font-monospace d-block">${url}</small>
                            </div>
                        `).join('');
                    }
                }

            } catch (err) {
                showToast(err.message, 'danger');
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-search"></i> 开始解析';
            }
        });
    }
});

function renderBatchResults(results) {
    const container = document.getElementById('batchResultList');
    document.getElementById('batchCount').textContent = results.length;
    
    container.innerHTML = results.map((item, index) => {
        let statusHtml = '';
        let actionHtml = '';
        
        if (item.success) {
            statusHtml = `<span class="badge bg-success">成功 (${item.count}个)</span>`;
            // 默认取第一个结果作为下载链接
            const downloadUrl = item.results[0];
            actionHtml = `
                <button class="btn btn-sm btn-outline-primary" onclick="api.createTask('${downloadUrl}', '${item.title}')">
                    <i class="bi bi-download"></i> 下载
                </button>
            `;
        } else {
            statusHtml = `<span class="badge bg-danger">失败</span>`;
            actionHtml = `<small class="text-danger">${item.error}</small>`;
        }

        return `
            <div class="list-group-item">
                <div class="d-flex w-100 justify-content-between align-items-center">
                    <div class="text-truncate me-3">
                        <h6 class="mb-1 text-truncate" title="${item.title || item.url}">${item.title || item.url}</h6>
                        <small class="text-muted">${item.url}</small>
                    </div>
                    <div class="d-flex align-items-center gap-2 flex-shrink-0">
                        ${statusHtml}
                        ${actionHtml}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

window.batchDownloadAll = async () => {
    const successItems = batchResults.filter(r => r.success && r.results.length > 0);
    if (successItems.length === 0) {
        showToast('没有可下载的任务', 'warning');
        return;
    }

    if (!confirm(`确定要添加 ${successItems.length} 个下载任务吗？`)) return;

    try {
        // 构造批量提交文本
        const text = successItems.map(item => `${item.results[0]}|${item.title}`).join('\n');
        await api.createTask({ text });
        showToast(`已添加 ${successItems.length} 个任务`, 'success');
        setTimeout(() => {
            window.location.href = '/downloading';
        }, 1000);
    } catch (err) {
        showToast(err.message, 'danger');
    }
};

// 启动下载
window.startDownload = async () => {
    if (!currentM3u8Url) return;
    try {
        await api.createTask(currentM3u8Url, currentTitle);
        showToast('任务创建成功', 'success');
        setTimeout(() => {
            window.location.href = '/downloading';
        }, 1000);
    } catch (err) {
        showToast(err.message, 'danger');
    }
};

// 预览播放
window.previewVideo = () => {
    if (!currentM3u8Url) return;
    initPlayer(currentM3u8Url);
};

// 多结果列表 - 下载
window.selectForDownload = async (url) => {
    try {
        await api.createTask(url, currentTitle);
        showToast('任务创建成功', 'success');
        setTimeout(() => {
            window.location.href = '/downloading';
        }, 1000);
    } catch (err) {
        showToast(err.message, 'danger');
    }
};

// 多结果列表 - 预览
window.selectForPreview = (url) => {
    initPlayer(url);
    // 滚动到播放器
    document.getElementById('previewPlayer').scrollIntoView({ behavior: 'smooth' });
};

function initPlayer(url) {
    const container = document.getElementById('previewPlayer');
    container.classList.remove('d-none');
    
    if (dp) {
        dp.destroy();
    }

    dp = new DPlayer({
        container: container,
        video: {
            url: url,
            type: 'hls'
        }
    });
    
    dp.play();
}