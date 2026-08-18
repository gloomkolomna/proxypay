import { useState } from 'react';
import { api } from '../api';

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [busy, setBusy] = useState(false);

  const check = async () => {
    setBusy(true);
    try {
      await api('/auth/me');
      onLoggedIn();
    } catch {
      window.location.href = '/pay/api/auth/vk-login';
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-box card">
      <h2>💳 ProxyPay</h2>
      <p className="muted">Панель управления платёжным шлюзом</p>
      <button className="btn primary" onClick={check} disabled={busy}>
        {busy ? 'Проверяем…' : 'Войти через VK ID'}
      </button>
    </div>
  );
}
