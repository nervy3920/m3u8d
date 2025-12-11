document.addEventListener('DOMContentLoaded', () => {
    // 初始化表单
    const initForm = document.getElementById('initForm');
    if (initForm) {
        initForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const pwd = document.getElementById('initPassword').value;
            const pwdConfirm = document.getElementById('initPasswordConfirm').value;
            const btn = e.target.querySelector('button');
            const spinner = document.getElementById('initSpinner');
            const btnText = document.getElementById('initBtnText');
            const errorDiv = document.getElementById('initError');

            if (pwd !== pwdConfirm) {
                errorDiv.textContent = '两次输入的密码不一致';
                errorDiv.classList.remove('d-none');
                return;
            }

            try {
                btn.disabled = true;
                spinner.classList.remove('d-none');
                btnText.textContent = '初始化中...';
                errorDiv.classList.add('d-none');

                await api.initSystem(pwd);
                
                // 初始化成功后自动登录
                await api.login(pwd);
                window.location.href = '/new';
            } catch (err) {
                errorDiv.textContent = err.message;
                errorDiv.classList.remove('d-none');
            } finally {
                btn.disabled = false;
                spinner.classList.add('d-none');
                btnText.textContent = '初始化系统';
            }
        });
    }

    // 登录表单
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
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
                window.location.href = '/new';
            } catch (err) {
                errorDiv.textContent = err.message;
                errorDiv.classList.remove('d-none');
            } finally {
                btn.disabled = false;
                spinner.classList.add('d-none');
                btnText.textContent = '登录';
            }
        });
    }
});