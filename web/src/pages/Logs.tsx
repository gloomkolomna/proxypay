import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

interface LogRow {
  id: number;
  event: string;
  transaction_id: string | null;
  game_id: string | null;
  actor_vk_id: number | null;
  detail: string;
  created_at: string;
}

export default function Logs() {
  const [items, setItems] = useState<LogRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [event, setEvent] = useState('');
  const [gameId, setGameId] = useState('');
  const [txn, setTxn] = useState('');
  const [error, setError] = useState('');
  const perPage = 100;

  const load = useCallback(async () => {
    setError('');
    const params = new URLSearchParams({ page: String(page), per_page: String(perPage) });
    if (event) params.set('event', event);
    if (gameId) params.set('game_id', gameId);
    if (txn) params.set('transaction_id', txn);
    try {
      const d = await api<{ total: number; items: LogRow[] }>(`/admin/logs?${params}`);
      setItems(d.items);
      setTotal(d.total);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    }
  }, [page, event, gameId, txn]);

  useEffect(() => { load(); }, [load]);

  const pages = Math.max(1, Math.ceil(total / perPage));

  return (
    <div>
      <h2>📜 Журнал <span className="muted" style={{ fontSize: 14 }}>({total})</span></h2>
      <div className="card">
        <div className="filters">
          <label>Событие
            <input value={event} onChange={(e) => { setEvent(e.target.value); setPage(1); }}
                   placeholder="moneta_callback_raw" style={{ width: 200 }} />
          </label>
          <label>Игра
            <input value={gameId} onChange={(e) => { setGameId(e.target.value); setPage(1); }}
                   placeholder="dragons" style={{ width: 120 }} />
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
            <tr><th>Время</th><th>Событие</th><th>txn</th><th>Игра</th><th>Кто</th><th>Детали</th></tr>
          </thead>
          <tbody>
            {items.map((l) => (
              <tr key={l.id}>
                <td className="muted" style={{ whiteSpace: 'nowrap' }}>{l.created_at}</td>
                <td className="mono">{l.event}</td>
                <td className="mono">{l.transaction_id ?? ''}</td>
                <td>{l.game_id ?? ''}</td>
                <td>{l.actor_vk_id ?? ''}</td>
                <td className="muted" style={{ maxWidth: 420, wordBreak: 'break-all' }}>
                  {l.detail}
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={6} className="muted" style={{ textAlign: 'center', padding: 24 }}>
                Пусто
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
