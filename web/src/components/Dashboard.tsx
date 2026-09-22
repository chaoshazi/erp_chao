import { useEffect, useState } from 'react';

import { api } from '../lib/api';
import { cellText, fieldOf, formatMoney, objectOf, type RefContext } from '../lib/format';
import type { Meta, PipelineRow, Stats } from '../lib/types';
import { Alert, Card, Empty } from './ui';

const CARD_OBJECTS = ['items', 'suppliers', 'customers', 'warehouses'] as const;
const DOC_OBJECTS = ['purchase_orders', 'sales_orders', 'stock_moves', 'invoices'] as const;

function enumLabel(meta: Meta, enumName: string, value: string): string {
  const found = (meta.enums[enumName] ?? []).find((item) => item.value === value);
  return found ? found.label : value || '未设置';
}

function PipelineTable({ meta, enumName, rows }: { meta: Meta; enumName: string; rows: PipelineRow[] }) {
  if (rows.length === 0) {
    return <Empty text='暂无单据' />;
  }
  return (
    <table className='w-full border-collapse text-sm'>
      <thead>
        <tr className='border-b border-slate-800 text-left text-xs text-slate-400'>
          <th className='px-2 py-2 font-medium'>状态</th>
          <th className='px-2 py-2 font-medium'>数量</th>
          <th className='px-2 py-2 font-medium'>金额</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.status} className='border-b border-slate-800/60'>
            <td className='px-2 py-2 text-slate-200'>{enumLabel(meta, enumName, row.status)}</td>
            <td className='px-2 py-2 text-slate-300'>{row.count}</td>
            <td className='px-2 py-2 text-slate-300'>{formatMoney(row.amount)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Dashboard({
  meta,
  ctx,
  onOpenObject,
  onOpen,
}: {
  meta: Meta;
  ctx: RefContext;
  onOpenObject: (objectName: string) => void;
  onOpen: (objectName: string, id: string) => void;
}) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api
      .stats()
      .then(setStats)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  const moves = objectOf(meta, 'stock_moves');
  const renderCards = (names: readonly string[]) => (
    <div className='grid grid-cols-2 gap-3 md:grid-cols-4'>
      {names.map((name) => {
        const object = objectOf(meta, name);
        if (!object) {
          return null;
        }
        return (
          <button
            key={name}
            type='button'
            onClick={() => onOpenObject(name)}
            className='rounded-xl border border-slate-800 bg-slate-900/60 p-4 text-left hover:border-sky-700'
          >
            <p className='text-xs text-slate-400'>{object.label}</p>
            <p className='mt-1 text-2xl font-semibold text-slate-100'>
              {stats ? stats.counts[name] ?? 0 : '—'}
            </p>
          </button>
        );
      })}
    </div>
  );

  return (
    <div className='flex flex-col gap-3'>
      {error ? <Alert text={error} /> : null}
      {renderCards(CARD_OBJECTS)}
      {renderCards(DOC_OBJECTS)}

      <div className='grid grid-cols-2 gap-3 md:grid-cols-4'>
        <Card title='库存金额'>
          <p className='text-2xl font-semibold text-slate-100'>
            {stats ? formatMoney(stats.stock_value) : '—'}
          </p>
          <p className='mt-1 text-xs text-slate-500'>按物料标准成本估算</p>
        </Card>
        <Card title='低库存物料'>
          <p className='text-2xl font-semibold text-amber-300'>
            {stats ? stats.low_stock_count : '—'}
          </p>
          <p className='mt-1 text-xs text-slate-500'>可用库存低于安全库存</p>
        </Card>
        <Card title='未结应收'>
          <p className='text-2xl font-semibold text-emerald-300'>
            {stats ? formatMoney(stats.receivable_open) : '—'}
          </p>
          <p className='mt-1 text-xs text-slate-500'>未结清发票中方向为应收的金额</p>
        </Card>
        <Card title='未结应付'>
          <p className='text-2xl font-semibold text-rose-300'>
            {stats ? formatMoney(stats.payable_open) : '—'}
          </p>
          <p className='mt-1 text-xs text-slate-500'>未结清发票中方向为应付的金额</p>
        </Card>
      </div>

      <div className='grid grid-cols-1 gap-3 md:grid-cols-2'>
        <Card
          title='采购订单状态'
          extra={
            <span className='text-xs text-slate-400'>
              在途 {stats ? stats.open_purchase_orders : '—'} 张 · 合计{' '}
              {stats ? formatMoney(stats.purchase_amount) : '—'}
            </span>
          }
        >
          <PipelineTable meta={meta} enumName='po_status' rows={stats?.purchase_pipeline ?? []} />
        </Card>
        <Card
          title='销售订单状态'
          extra={
            <span className='text-xs text-slate-400'>
              在途 {stats ? stats.open_sales_orders : '—'} 张 · 合计{' '}
              {stats ? formatMoney(stats.sales_amount) : '—'}
            </span>
          }
        >
          <PipelineTable meta={meta} enumName='so_status' rows={stats?.sales_pipeline ?? []} />
        </Card>
      </div>

      <Card title='低库存物料'>
        {!stats || stats.low_stock_items.length === 0 ? (
          <Empty text='没有低于安全库存的物料' />
        ) : (
          <table className='w-full border-collapse text-sm'>
            <thead>
              <tr className='border-b border-slate-800 text-left text-xs text-slate-400'>
                <th className='px-2 py-2 font-medium'>物料编码</th>
                <th className='px-2 py-2 font-medium'>物料名称</th>
                <th className='px-2 py-2 font-medium'>可用库存</th>
                <th className='px-2 py-2 font-medium'>安全库存</th>
              </tr>
            </thead>
            <tbody>
              {stats.low_stock_items.map((item) => (
                <tr
                  key={item.id}
                  className='cursor-pointer border-b border-slate-800/60 hover:bg-slate-800/40'
                  onClick={() => onOpen('items', item.id)}
                >
                  <td className='px-2 py-2 text-slate-300'>{item.sku}</td>
                  <td className='px-2 py-2 text-slate-200'>{item.name}</td>
                  <td className='px-2 py-2 text-amber-300'>{formatMoney(item.balance)}</td>
                  <td className='px-2 py-2 text-slate-400'>{formatMoney(item.safety_stock)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title='最近库存流水'>
        {!stats || stats.recent_moves.length === 0 ? (
          <Empty text='还没有库存流水' />
        ) : (
          <ul className='divide-y divide-slate-800/60'>
            {stats.recent_moves.map((item) => (
              <li
                key={item.id}
                className='cursor-pointer py-2 text-sm hover:bg-slate-800/40'
                onClick={() => onOpen('stock_moves', item.id)}
              >
                <span className='text-slate-200'>
                  {cellText(fieldOf(moves, 'reference'), item.reference, ctx, { truncate: 40 })}
                </span>
                <span className='ml-2 text-xs text-slate-500'>
                  {cellText(fieldOf(moves, 'kind'), item.kind, ctx)} ·{' '}
                  {cellText(fieldOf(moves, 'item_id'), item.item_id, ctx)} ·{' '}
                  {cellText(fieldOf(moves, 'quantity'), item.quantity, ctx)} ·{' '}
                  {String(item.occurred_at ?? '').slice(0, 16).replace('T', ' ')}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}