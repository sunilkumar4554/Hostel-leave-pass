function setupLogin(role) {
  const form = document.getElementById('login-form');
  const alertId = 'alert';
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideAlert(alertId);
    const button = form.querySelector('button[type="submit"]');
    setButtonLoading(button, true, 'Signing in…');
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      const result = await api('/api/login', { method: 'POST', body: { ...data, role } });
      showAlert(alertId, result.message, 'success');
      window.location.href = destinationForRole(role);
    } catch (error) {
      showAlert(alertId, error.message);
    } finally {
      setButtonLoading(button, false);
    }
  });
}

function setupRegistration() {
  const form = document.getElementById('register-form');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideAlert('alert');
    const button = form.querySelector('button[type="submit"]');
    setButtonLoading(button, true, 'Creating account…');
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      const result = await api('/api/register', { method: 'POST', body: data });
      showAlert('alert', result.message, 'success');
      window.location.href = '/student-dashboard.html';
    } catch (error) {
      showAlert('alert', error.message);
    } finally {
      setButtonLoading(button, false);
    }
  });
}

function setupForgotPassword() {
  const emailField = document.getElementById('reset-email');
  const otpForm = document.getElementById('otp-form');
  const resetForm = document.getElementById('reset-form');
  otpForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideAlert('alert');
    const button = otpForm.querySelector('button');
    setButtonLoading(button, true, 'Sending…');
    try {
      const result = await api('/api/auth/forgot-password', { method: 'POST', body: { email: emailField.value } });
      showAlert('alert', result.message, 'success');
      document.getElementById('reset-otp').focus();
    } catch (error) { showAlert('alert', error.message); }
    finally { setButtonLoading(button, false); }
  });
  resetForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    hideAlert('alert');
    const button = resetForm.querySelector('button');
    setButtonLoading(button, true, 'Resetting…');
    try {
      const result = await api('/api/auth/reset-password', { method: 'POST', body: {
        email: emailField.value, otp: document.getElementById('reset-otp').value,
        new_password: document.getElementById('new-password').value,
      } });
      showAlert('alert', result.message, 'success');
      window.setTimeout(() => { window.location.href = '/student-login.html'; }, 1000);
    } catch (error) { showAlert('alert', error.message); }
    finally { setButtonLoading(button, false); }
  });
}
