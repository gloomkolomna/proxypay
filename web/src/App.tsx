import { useEffect, useState } from 'react';
import { api } from './api';
import Login from './pages/Login';
import Orders from './pages/Orders';
import OrderDetail from './pages/OrderDetail';
import Logs from './pages/Logs';
import Games from './pages/Games';
import Settings from './pages/Settings';

const NAV = [
  { hash: '#/orders', label: '🧾 Заказы' },
  { hash: '#/games', label: '🎮 Игры' },
  { hash: '#/logs', label: '📜 Журнал' },
  { hash: '#/settings', label: '⚙ Настройки' },
];

function currentHash(): string {
  return window.location.hash || '#/orders';
}

export default function App() {
  const [hash, setHash] = useState(currentHash);
  const [me, setMe] = useState<number | null | 'loading'>('loading');

  useEffect(() => {
    const onHash = () => setHash(currentHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    if (hash === '#/login') return;
    api<{ vk_id: number }>('/auth/me')
      .then((d) => setMe(d.vk_id))
      .catch(() => setMe(null));
  }, [hash]);

  if (hash === '#/login' || me === null) {
    return <Login onLoggedIn={() => { setMe('loading'); window.location.hash = '#/orders'; }} />;
  }
  if (me === 'loading') return <div className="muted" style={{ padding: 40 }}>Загрузка…</div>;

  const orderMatch = hash.match(/^#\/orders\/(.+)$/);

  const logout = async () => {
    try { await api('/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
    setMe(null);
    window.location.hash = '#/login';
  };

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="logo">💳 ProxyPay</div>
        <nav>
          {NAV.map((n) => (
            <a key={n.hash} href={n.hash}
               className={hash === n.hash || (n.hash === '#/orders' && orderMatch) ? 'active' : ''}>
              {n.label}
            </a>
          ))}
          <a href="#/login" onClick={logout}>🚪 Выйти ({me})</a>
        </nav>
      </aside>
      <main className="content">
        {orderMatch
          ? <OrderDetail txn={orderMatch[1]} />
          : hash === '#/games' ? <Games />
          : hash === '#/logs' ? <Logs />
          : hash === '#/settings' ? <Settings />
          : <Orders />}
      </main>
    </div>
  );
}
