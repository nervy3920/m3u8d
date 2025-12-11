let currentM3u8Url = '';
let currentTitle = '';
let dp = null;

document.addEventListener('DOMContentLoaded', () => {
    const parserForm = document.getElementById('parserForm');
    if (parserForm) {
        parserForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const urlInput = document.getElementById('videoPageUrl');
            const btn = e.target.querySelector('button');
            const resultDiv = document.getElementById('parseResult');
            const parsedTitle = document.getElementById('parsedTitle');
            const singleResult = document.getElementById('singleResult');
            const multiResult = document.getElementById('multiResult');
            const urlList = document.getElementById('urlList');
            const previewPlayer = document.getElementById('previewPlayer');

            try {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 解析中...';
                resultDiv.classList.add('d-none');
                singleResult.classList.add('d-none');
                multiResult.classList.add('d-none');
                previewPlayer.classList.add('d-none');
                if (dp) {
                    dp.destroy();
                    dp = null;
                }

                const data = await api.parseUniversal(urlInput.value);
                
                currentTitle = data.title;
                parsedTitle.textContent = data.title;
                resultDiv.classList.remove('d-none');

                if (data.count === 1) {
                    // 单个结果
                    currentM3u8Url = data.results[0];
                    document.getElementById('parsedUrl').textContent = currentM3u8Url;
                    singleResult.classList.remove('d-none');
                } else {
                    // 多个结果
                    multiResult.classList.remove('d-none');
                    urlList.innerHTML = data.results.map((url, index) => `
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

            } catch (err) {
                showToast(err.message, 'danger');
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-search"></i> 开始解析';
            }
        });
    }
});

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