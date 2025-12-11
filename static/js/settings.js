document.addEventListener('DOMContentLoaded', () => {
    // Aria2 开关联动
    const aria2Check = document.getElementById('aria2Enabled');
    const aria2Config = document.getElementById('aria2Config');
    if (aria2Check) {
        aria2Check.addEventListener('change', (e) => {
            if (e.target.checked) {
                aria2Config.classList.remove('d-none');
            } else {
                aria2Config.classList.add('d-none');
            }
        });
    }

    // API 开关联动
    const apiCheck = document.getElementById('apiEnabled');
    const apiConfig = document.getElementById('apiConfig');
    if (apiCheck) {
        apiCheck.addEventListener('change', (e) => {
            if (e.target.checked) {
                apiConfig.classList.remove('d-none');
                // 如果 Key 为空，自动生成一个
                const keyInput = document.getElementById('apiKeyInput');
                // 只有当是用户手动点击触发（e.isTrusted）且 Key 为空时才自动生成
                // 避免加载设置时自动触发
                if (e.isTrusted && !keyInput.value) {
                    document.getElementById('resetApiKeyBtn').click();
                }
            } else {
                apiConfig.classList.add('d-none');
            }
        });
    }

    // 复制 API Key
    const copyBtn = document.getElementById('copyApiKeyBtn');
    if (copyBtn) {
        copyBtn.addEventListener('click', () => {
            const keyInput = document.getElementById('apiKeyInput');
            keyInput.select();
            document.execCommand('copy');
            showToast('API Key 已复制', 'success');
        });
    }

    // 重置 API Key
    const resetBtn = document.getElementById('resetApiKeyBtn');
    if (resetBtn) {
        resetBtn.addEventListener('click', async () => {
            if (confirm('确定要重置 API Key 吗？旧的 Key 将立即失效。')) {
                try {
                    const data = await api.generateApiKey();
                    document.getElementById('apiKeyInput').value = data.api_key;
                    showToast('API Key 已重置', 'success');
                } catch (err) {
                    showToast(err.message, 'danger');
                }
            }
        });
    }

    // 设置表单提交
    const settingsForm = document.getElementById('settingsForm');
    if (settingsForm) {
        settingsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const settings = {};
            
            // 处理 checkbox
            settings['delete_after_download'] = formData.get('delete_after_download') ? 'true' : 'false';
            settings['aria2_enabled'] = formData.get('aria2_enabled') ? 'true' : 'false';
            settings['api_enabled'] = formData.get('api_enabled') ? 'true' : 'false';
            
            // 处理其他字段
            for (let [key, value] of formData.entries()) {
                if (key !== 'delete_after_download' && key !== 'aria2_enabled' && key !== 'api_enabled') {
                    settings[key] = value;
                }
            }

            try {
                const btn = e.target.querySelector('button[type="submit"]');
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 保存中...';

                await api.updateSettings(settings);
                showToast('设置已保存', 'success');
            } catch (err) {
                showToast(err.message, 'danger');
            } finally {
                const btn = e.target.querySelector('button[type="submit"]');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-save"></i> 保存设置';
            }
        });
    }
});