document.addEventListener('DOMContentLoaded', () => {
    // Clear any existing session to ensure the application always starts from the login page
    localStorage.removeItem("tr_user");

    const loginForm = document.getElementById('loginForm');
    const passwordInput = document.getElementById('password');
    const togglePasswordIcon = document.getElementById('togglePassword');

    // 1. Toggle Password Visibility
    togglePasswordIcon.addEventListener('click', () => {
        const isPassword = passwordInput.getAttribute('type') === 'password';
        passwordInput.setAttribute('type', isPassword ? 'text' : 'password');
        
        if (isPassword) {
            togglePasswordIcon.classList.remove('fa-eye');
            togglePasswordIcon.classList.add('fa-eye-slash');
        } else {
            togglePasswordIcon.classList.remove('fa-eye-slash');
            togglePasswordIcon.classList.add('fa-eye');
        }
    });

    // Helper to display error message
    const showError = (message) => {
        // Remove existing error banner if any
        const existingBanner = document.querySelector('.error-banner');
        if (existingBanner) existingBanner.remove();

        const banner = document.createElement('div');
        banner.className = 'error-banner';
        banner.style.cssText = 'background-color: rgba(239, 68, 68, 0.1); border: 1px solid rgb(239, 68, 68); color: rgb(239, 68, 68); padding: 12px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; text-align: center;';
        banner.textContent = message;

        loginForm.insertAdjacentElement('beforebegin', banner);
    };

    // Helper to display success message
    const showSuccess = (message) => {
        const existingBanner = document.querySelector('.error-banner');
        if (existingBanner) existingBanner.remove();

        const banner = document.createElement('div');
        banner.className = 'error-banner';
        banner.style.cssText = 'background-color: rgba(34, 197, 94, 0.1); border: 1px solid rgb(34, 197, 94); color: rgb(34, 197, 94); padding: 12px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; text-align: center;';
        banner.textContent = message;

        loginForm.insertAdjacentElement('beforebegin', banner);
    };

    // 2. Handle Form Submission
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const email = document.getElementById('email').value.trim();
        const password = passwordInput.value;

        const submitBtn = loginForm.querySelector('.submit-btn');
        const originalBtnText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Signing In...';

        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email, password })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Login failed. Please check your credentials.');
            }

            showSuccess('Login successful! Redirecting...');
            
            // Save user details to localStorage
            localStorage.setItem('tr_user', JSON.stringify(data.user));

            setTimeout(() => {
                window.location.href = '/home';
            }, 1000);

        } catch (error) {
            showError(error.message);
            submitBtn.disabled = false;
            submitBtn.textContent = originalBtnText;
        }
    });
});