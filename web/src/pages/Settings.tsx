import { useEffect, useState } from 'react';
import { api } from '../api';

interface Settings {
  payments_test_mode: boolean;
  payments_test_vk_id: number;
  moneta_test_mode: boolean;
  moneta_mnt_id: string;
  order_ttl_minutes: number;
}

export default function Settings() {
  const [data, setData] = useState<Settings | null>(null);
  const [testVk, setTestVk] = useState('');
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setError('');
    try {
      const d = await api<Settings>('/admin/settings');
      setData(d);
      setTestVk(String(d.payments_test_vk_id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    }
  };

  useEffect(() => { load(); }, []);

  const save = async (patch: Record<string, unknown>) => {
    setBusy(true);
    setError('');
    setNote('');
    try {
      const d = await api<Settings>('/admin/settings', {
        method: 'PUT', body: JSON.stringify(patch),
      });
      setData(d);
      setNote('Сохранено');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBusy(false);
    }
  };

  if (!data) return <div className="muted" style={{ padding: 40 }}>Загрузка… {error}</div>;

  return (
    <div>
      <h2>⚙ Настройки</h2>
      {error && <div className="error">{error}</div>}
      {note && <div className="ok-note">{note}</div>}

      <div className="card">
        <h3>Тест-режим</h3>
        <p className="muted">
          Включён — заказы принимает только тестовый vk_id (остальным «оплата недоступна»).
          Переключение действует сразу, без рестарта.
        </p>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <span className={`badge ${data.payments_test_mode ? 'off' : 'on'}`}>
            {data.payments_test_mode ? 'ВКЛЮЧЁН (блокирует всех, кроме тестера)' : 'выключен'}
          </span>
          <button className={data.payments_test_mode ? 'primary' : 'danger'}
                  disabled={busy}
                  onClick={() => save({ payments_test_mode: !data.payments_test_mode })}>
            {data.payments_test_mode ? 'Выключить (открыть оплату всем)' : 'Включить тест-режим'}
          </button>
        </div>
        <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'end' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            Тестовый vk_id
            <input value={testVk} onChange={(e) => setTestVk(e.target.value)}
                   style={{ width: 140 }} />
          </label>
          <button disabled={busy}
                  onClick={() => save({ payments_test_vk_id: Number(testVk) || 0 })}>
            Сохранить
          </button>
        </div>
      </div>

      <div className="card">
        <h3>MONETA</h3>
        <div className="kv">
          <span className="k">Режим кабинета</span>
          <span>{data.moneta_test_mode ? '🟡 Тестовый (demo.moneta.ru)' : '🟢 Прод (payanyway.ru)'}</span>
          <span className="k">MNT_ID</span>
          <span className="mono">{data.moneta_mnt_id || '—'}</span>
          <span className="k">TTL заказа</span>
          <span>{data.order_ttl_minutes} мин.</span>
        </div>
        <p className="muted" style={{ marginBottom: 0 }}>
          Учётные данные MONETA и режим кабинета меняются в <code>.env</code> шлюза
          (требуют рестарта).
        </p>
      </div>
    </div>
  );
}
