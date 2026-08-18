import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

interface Receipt {
  tax_code: string;
  payment_method: string;
  payment_object: string;
}

interface Game {
  game_id: string;
  name: string;
  description_prefix: string;
  webhook_url: string;
  success_url: string;
  fail_url: string;
  receipt: Receipt;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  api_key?: string;
  webhook_secret?: string;
}

const EMPTY_FORM = {
  game_id: '', name: '', description_prefix: '',
  webhook_url: '', success_url: '', fail_url: '',
  tax_code: '1105', payment_method: 'full_payment', payment_object: 'commodity',
  is_active: true,
};

type FormState = typeof EMPTY_FORM;

export default function Games() {
  const [items, setItems] = useState<Game[]>([]);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [secrets, setSecrets] = useState<Record<string, Game>>({});

  const load = useCallback(async () => {
    setError('');
    try {
      const d = await api<{ items: Game[] }>('/admin/games');
      setItems(d.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const startCreate = () => {
    setForm(EMPTY_FORM);
    setEditing(null);
    setShowForm(true);
    setNote('');
  };

  const startEdit = (g: Game) => {
    setForm({
      game_id: g.game_id, name: g.name, description_prefix: g.description_prefix,
      webhook_url: g.webhook_url, success_url: g.success_url, fail_url: g.fail_url,
      tax_code: g.receipt.tax_code, payment_method: g.receipt.payment_method,
      payment_object: g.receipt.payment_object, is_active: g.is_active,
    });
    setEditing(g.game_id);
    setShowForm(true);
    setNote('');
  };

  const submit = async () => {
    setError('');
    setNote('');
    const payload = {
      name: form.name, description_prefix: form.description_prefix,
      webhook_url: form.webhook_url, success_url: form.success_url,
      fail_url: form.fail_url, is_active: form.is_active,
      receipt: {
        tax_code: form.tax_code, payment_method: form.payment_method,
        payment_object: form.payment_object,
      },
    };
    try {
      if (editing) {
        await api(`/admin/games/${editing}`, { method: 'PUT', body: JSON.stringify(payload) });
        setNote(`Игра ${editing} обновлена`);
      } else {
        const created = await api<Game>('/admin/games', {
          method: 'POST',
          body: JSON.stringify({ game_id: form.game_id, ...payload }),
        });
        setSecrets((s) => ({ ...s, [created.game_id]: created }));
        setNote(`Игра ${created.game_id} создана — секреты показаны ниже (сохраните их в .env игры)`);
      }
      setShowForm(false);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка');
    }
  };

  const reveal = async (gameId: string) => {
    setError('');
    try {
      if (secrets[gameId]) {
        setSecrets((s) => { const c = { ...s }; delete c[gameId]; return c; });
        return;
      }
      const g = await api<Game>(`/admin/games/${gameId}?reveal=true`);
      setSecrets((s) => ({ ...s, [gameId]: g }));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка');
    }
  };

  const rotate = async (gameId: string, which: 'api_key' | 'webhook_secret') => {
    if (!window.confirm(`Ротировать ${which} у игры ${gameId}? Старый ключ перестанет работать немедленно.`)) return;
    setError('');
    try {
      const r = await api<{ new_value: string }>(`/admin/games/${gameId}/rotate`, {
        method: 'POST', body: JSON.stringify({ which }),
      });
      setSecrets((s) => ({ ...s, [gameId]: { ...s[gameId], [which]: r.new_value } as Game }));
      setNote(`Новый ${which} для ${gameId} выдан`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка');
    }
  };

  const remove = async (gameId: string) => {
    if (!window.confirm(`Удалить игру ${gameId}? Возможно только если у неё нет заказов.`)) return;
    setError('');
    try {
      await api(`/admin/games/${gameId}`, { method: 'DELETE' });
      setNote(`Игра ${gameId} удалена`);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка');
    }
  };

  return (
    <div>
      <h2>🎮 Игры</h2>
      {error && <div className="error">{error}</div>}
      {note && <div className="ok-note">{note}</div>}

      <div style={{ marginBottom: 12 }}>
        <button className="primary" onClick={startCreate}>＋ Добавить игру</button>
      </div>

      {showForm && (
        <div className="card">
          <h3>{editing ? `Редактирование: ${editing}` : 'Новая игра'}</h3>
          <div className="form-grid">
            {!editing && (
              <label className="full">game_id (^[a-z0-9_]+$)
                <input value={form.game_id}
                       onChange={(e) => setForm({ ...form, game_id: e.target.value })}
                       placeholder="dragons" />
              </label>
            )}
            <label>Название
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label>Префикс описания (выписка)
              <input value={form.description_prefix}
                     onChange={(e) => setForm({ ...form, description_prefix: e.target.value })}
                     placeholder="[Драконы]" />
            </label>
            <label className="full">Webhook URL (куда слать уведомления)
              <input value={form.webhook_url}
                     onChange={(e) => setForm({ ...form, webhook_url: e.target.value })}
                     placeholder="http://127.0.0.1:8001/api/payment/webhook" />
            </label>
            <label className="full">Success URL — страница статуса оплаты в игре
              <input value={form.success_url}
                     onChange={(e) => setForm({ ...form, success_url: e.target.value })}
                     placeholder="https://belovolovhome.ru/dragons/payment/status" />
            </label>
            <label className="full">Fail URL — куда попасть при неудаче (обычно та же страница статуса)
              <input value={form.fail_url}
                     onChange={(e) => setForm({ ...form, fail_url: e.target.value })}
                     placeholder="https://belovolovhome.ru/dragons/payment/status" />
            </label>
            <label>Налоговая ставка (tax_code)
              <input value={form.tax_code}
                     onChange={(e) => setForm({ ...form, tax_code: e.target.value })} />
            </label>
            <label>payment_method / payment_object
              <div style={{ display: 'flex', gap: 6 }}>
                <input value={form.payment_method}
                       onChange={(e) => setForm({ ...form, payment_method: e.target.value })} />
                <input value={form.payment_object}
                       onChange={(e) => setForm({ ...form, payment_object: e.target.value })} />
              </div>
            </label>
            <label>Активна
              <input type="checkbox" checked={form.is_active}
                     onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
            </label>
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button className="primary" onClick={submit}>{editing ? 'Сохранить' : 'Создать'}</button>
            <button onClick={() => setShowForm(false)}>Отмена</button>
          </div>
          <p className="muted" style={{ marginBottom: 0, marginTop: 12 }}>
            После оплаты шлюз редиректит игрока на Success/Fail URL с параметром
            <code> ?txn=…</code>. Страница статуса игры опрашивает публичный
            <code> GET /pay/status/&#123;txn&#125;</code> (без подписи, минимум полей),
            показывает результат и ведёт игрока обратно в сообщество/бота.
          </p>
        </div>
      )}

      <div className="card">
        <table>
          <thead>
            <tr><th>game_id</th><th>Название</th><th>Активна</th><th>Webhook</th><th>Действия</th></tr>
          </thead>
          <tbody>
            {items.map((g) => (
              <tr key={g.game_id}>
                <td className="mono">{g.game_id}</td>
                <td>{g.name}</td>
                <td><span className={`badge ${g.is_active ? 'on' : 'off'}`}>
                  {g.is_active ? 'да' : 'нет'}</span></td>
                <td className="muted mono" style={{ maxWidth: 260, wordBreak: 'break-all' }}>
                  {g.webhook_url}
                </td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button onClick={() => startEdit(g)}>✏️</button>{' '}
                  <button onClick={() => reveal(g.game_id)}>
                    {secrets[g.game_id] ? '🙈 Скрыть' : '🔑 Секреты'}
                  </button>{' '}
                  <button onClick={() => rotate(g.game_id, 'api_key')}>♻ api_key</button>{' '}
                  <button onClick={() => rotate(g.game_id, 'webhook_secret')}>♻ secret</button>{' '}
                  <button className="danger" onClick={() => remove(g.game_id)}>🗑</button>
                  {secrets[g.game_id] && (
                    <div style={{ marginTop: 6 }}>
                      <div className="secret">api_key:
                        <code>{secrets[g.game_id].api_key}</code></div>
                      <div className="secret">webhook_secret:
                        <code>{secrets[g.game_id].webhook_secret}</code></div>
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={5} className="muted" style={{ textAlign: 'center', padding: 24 }}>
                Игр пока нет — добавьте первую
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
