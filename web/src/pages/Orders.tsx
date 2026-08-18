import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

export interface OrderRow {
  id: number;
  transaction_id: string;
  game_id: string;
  vk_id: number;
  amount_kop: number;
  amount_rub: string;
  description: string;
  receipt_email: string | null;
  status: string;
  moneta_operation_id: string | null;
  created_at: string | null;
  completed_at: string | null;
  expires_at: string | null;
}

const STATUSES = ['', 'pending', 'success', 'cancelled', 'failed'];
const STATUS_LABEL: Record<string, string> = {
  pending: 'Ожидание', success: 'Успех', cancelled: 'Отменён', failed: 'Ошибка',
};

export default function Orders() {
  const [items, setItems] = useState<OrderRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [gameId, setGameId] = useState('');
  const [games, setGames] = useState<{ game_id: string; name: string }[]>([]);
  const [status, setStatus] = useState('');
  const [vkId, setVkId] = useState('');
  const [txn, setTxn] = useState('');
  const [error, setError] = useState('');
  const perPage = 50;

  useEffect(() => {
    api<{ items: { game_id: string; name: string }[] }>('/admin/games')
      .then((d) => setGames(d.items))
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setError('');
    const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
    if (gameId) params.set('game_id', gameId);
    if (status) params.set('status', status);
    if (vkId) params.set('vk_id', vkId);
    if (txn) params.set('txn', txn);
    try {
      const d = await api<{ total: number; items: OrderRow[] }>(`/admin/orders?${params}`);
      setItems(d.items);
      setTotal(d.total);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    }
  }, [page, gameId, status, vkId, txn]);

  useEffect(() => { load(); }, [load]);

  const pages = Math.max(1, Math.ceil(total / perPage));

  return (
    <div>
      <h2>🧾 Заказы <span className="muted" style={{ fontSize: 14 }}>({total})</span></h2>
      <div className="card">
        <div className="filters">
          <label>Игра
            <select value={gameId} onChange={(e) => { setGameId(e.target.value); setPage(1); }}>
              <option value="">Все</option>
              {games.map((g) => <option key={g.game_id} value={g.game_id}>{g.name}</option>)}
            </select>
          </label>
          <label>Статус
            <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{s ? STATUS_LABEL[s] : 'Все'}</option>
              ))}
            </select>
          </label>
          <label>vk_id
            <input value={vkId} onChange={(e) => { setVkId(e.target.value); setPage(1); }}
                   placeholder="123456" style={{ width: 110 }} />
          </label>
          <label>txn
            <input value={txn} onChange={(e) => { setTxn(e.target.value); setPage(1); }}
                   placeholder="20260818-…" style={{ width: 140 }} />
          </label>
          <button onClick={load}>Обновить</button>
        </div>
        {error && <div className="error">{error}</div>}
        <table>
          <thead>
            <tr>
              <th>txn</th><th>Игра</th><th>vk_id</th><th>Сумма</th>
              <th>Статус</th><th>Создан</th><th>Завершён</th>
            </tr>
          </thead>
          <tbody>
            {items.map((o) => (
              <tr key={o.id} className="clickable"
                  onClick={() => { window.location.hash = `#/orders/${o.transaction_id}`; }}>
                <td className="mono">{o.transaction_id}</td>
                <td>{o.game_id}</td>
                <td>{o.vk_id}</td>
                <td>{o.amount_rub} ₽</td>
                <td><span className={`badge ${o.status}`}>{STATUS_LABEL[o.status] ?? o.status}</span></td>
                <td className="muted">{o.created_at}</td>
                <td className="muted">{o.completed_at}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={7} className="muted" style={{ textAlign: 'center', padding: 24 }}>
                Нет заказов
              </td></tr>
            )}
          </tbody>
        </table>
        <div className="pagination">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>←</button>
          <span className="muted">стр. {page} / {pages}</span>
          <button disabled={page >= pages} onClick={() => setPage(page + 1)}>→</button>
        </div>
      </div>
    </div>
  );
}
