document.addEventListener('DOMContentLoaded', () => {
    const signupForm = document.getElementById('signupForm');
    const passwordInput = document.getElementById('password');
    const confirmPasswordInput = document.getElementById('confirmPassword');
    const togglePasswordIcons = document.querySelectorAll('.toggle-password');

    // 1. Toggle Password Visibility for both inputs
    togglePasswordIcons.forEach(icon => {
        icon.addEventListener('click', () => {
            const targetId = icon.getAttribute('data-target');
            const targetInput = document.getElementById(targetId);
            if (!targetInput) return;

            const isPassword = targetInput.getAttribute('type') === 'password';
            targetInput.setAttribute('type', isPassword ? 'text' : 'password');

            // Toggle icon classes
            if (isPassword) {
                icon.classList.remove('fa-eye-slash');
                icon.classList.add('fa-eye');
            } else {
                icon.classList.remove('fa-eye');
                icon.classList.add('fa-eye-slash');
            }
        });
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

        signupForm.insertAdjacentElement('beforebegin', banner);
    };

    // Helper to display success message
    const showSuccess = (message) => {
        const existingBanner = document.querySelector('.error-banner');
        if (existingBanner) existingBanner.remove();

        const banner = document.createElement('div');
        banner.className = 'error-banner'; // reuse placeholder clean styling
        banner.style.cssText = 'background-color: rgba(34, 197, 94, 0.1); border: 1px solid rgb(34, 197, 94); color: rgb(34, 197, 94); padding: 12px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; text-align: center;';
        banner.textContent = message;

        signupForm.insertAdjacentElement('beforebegin', banner);
    };

    // 2. Handle Form Submission
    signupForm.addEventListener('submit', async (event) => {
        event.preventDefault();

        const fullName = document.getElementById('fullName').value.trim();
        const companyName = document.getElementById('companyName').value.trim();
        const email = document.getElementById('email').value.trim();
        const password = passwordInput.value;
        const confirmPassword = confirmPasswordInput.value;
        const agreeTerms = document.getElementById('agreeTerms').checked;

        if (password !== confirmPassword) {
            showError("Passwords do not match!");
            return;
        }

        if (!agreeTerms) {
            showError("You must agree to the Terms of Service and Privacy Policy.");
            return;
        }

        const submitBtn = signupForm.querySelector('.submit-btn');
        const originalBtnText = submitBtn.textContent;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Signing Up...';

        try {
            const response = await fetch('/api/signup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    fullName,
                    companyName,
                    email,
                    password
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Signup failed. Please try again.');
            }

            showSuccess('Registration successful! Redirecting to login page...');
            setTimeout(() => {
                window.location.href = '/login';
            }, 1500);

        } catch (error) {
            showError(error.message);
            submitBtn.disabled = false;
            submitBtn.textContent = originalBtnText;
        }
    });
});