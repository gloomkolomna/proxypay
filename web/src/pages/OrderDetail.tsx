import { useEffect, useState } from 'react';
import { api } from '../api';
import type { OrderRow } from './Orders';

interface Delivery {
  id: number;
  attempt: number;
  status: string;
  last_response_code: number | null;
  last_error: string;
  next_retry_at: string | null;
  delivered_at: string | null;
}

export default function OrderDetail({ txn }: { txn: string }) {
  const [order, setOrder] = useState<OrderRow | null>(null);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setError('');
    try {
      const d = await api<{ order: OrderRow; deliveries: Delivery[] }>(
        `/admin/orders/${txn}`,
      );
      setOrder(d.order);
      setDeliveries(d.deliveries);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки');
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [txn]);

  const redeliver = async () => {
    setBusy(true);
    setNote('');
    try {
      const r = await api<{ delivery: Delivery }>(`/admin/orders/${txn}/redeliver`, {
        method: 'POST',
      });
      setNote(`Переотправка: ${r.delivery.status} (код ${r.delivery.last_response_code ?? '—'})`);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <h2>🧾 Заказ <span className="mono">{txn}</span></h2>
      <p><a href="#/orders">← К списку</a></p>
      {error && <div className="error">{error}</div>}
      {note && <div className="ok-note">{note}</div>}

      {order && (
        <>
          <div className="card">
            <div className="kv">
              <span className="k">Статус</span>
              <span><span className={`badge ${order.status}`}>{order.status}</span></span>
              <span className="k">Игра</span><span>{order.game_id}</span>
              <span className="k">vk_id</span><span>{order.vk_id}</span>
              <span className="k">Сумма</span><span>{order.amount_rub} ₽ ({order.amount_kop} коп.)</span>
              <span className="k">Описание</span><span>{order.description}</span>
              <span className="k">Email чека</span><span>{order.receipt_email ?? '—'}</span>
              <span className="k">MONETA operation</span>
              <span className="mono">{order.moneta_operation_id ?? '—'}</span>
              <span className="k">Создан</span><span>{order.created_at}</span>
              <span className="k">Истекает</span><span>{order.expires_at}</span>
              <span className="k">Завершён</span><span>{order.completed_at ?? '—'}</span>
            </div>
          </div>

          <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0 }}>Доставки вебхука</h3>
              {order.status === 'success' && (
                <button className="primary" onClick={redeliver} disabled={busy}>
                  {busy ? 'Отправка…' : '🔁 Переотправить вебхук'}
                </button>
              )}
            </div>
            <table style={{ marginTop: 12 }}>
              <thead>
                <tr><th>#</th><th>Попытки</th><th>Статус</th><th>Код</th>
                    <th>След. ретрай</th><th>Доставлен</th><th>Ошибка</th></tr>
              </thead>
              <tbody>
                {deliveries.map((d) => (
                  <tr key={d.id}>
                    <td>{d.id}</td>
                    <td>{d.attempt}</td>
                    <td><span className={`badge ${d.status}`}>{d.status}</span></td>
                    <td>{d.last_response_code ?? '—'}</td>
                    <td className="muted">{d.next_retry_at ?? '—'}</td>
                    <td className="muted">{d.delivered_at ?? '—'}</td>
                    <td className="muted" style={{ maxWidth: 260, wordBreak: 'break-all' }}>
                      {d.last_error}
                    </td>
                  </tr>
                ))}
                {deliveries.length === 0 && (
                  <tr><td colSpan={7} className="muted">Нет доставок</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
