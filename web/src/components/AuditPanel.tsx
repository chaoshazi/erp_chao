import { useEffect, useState } from 'react';

import { api } from '../lib/api';
import { formatDateTime } from '../lib/format';
import type { AuditEntry } from '../lib/types';
import { Alert, Badge, Button, Card, Empty, JsonView, Modal } from './ui';

export function AuditPanel() {
  const [rows, setRows] = useState<AuditEntry[]>([]);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState<AuditEntry | null>(null);

  useEffect(() => {
    api
      .audit(200)
      .then((result) => setRows(result.data))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <div className='flex flex-col gap-3'>
      <Card title={'审计日志（最近 ' + rows.length + ' 条）'}>
        {error ? <Alert text={error} /> : null}
        <p className='mb-3 text-xs text-slate-500'>
          记录每一次写操作：人工修改与 AI 写回都在这里，AI 写回的来源标记为 ai。
        </p>
        {rows.length === 0 ? (
          <Empty text='还没有写操作记录' />
        ) : (
          <table className='w-full border-collapse text-sm'>
            <thead>
              <tr className='border-b border-slate-800 text-left text-xs text-slate-400'>
                <th className='px-2 py-2 font-medium'>时间</th>
                <th className='px-2 py-2 font-medium'>来源</th>
                <th className='px-2 py-2 font-medium'>操作者</th>
                <th className='px-2 py-2 font-medium'>对象</th>
                <th className='px-2 py-2 font-medium'>记录</th>
                <th className='px-2 py-2 font-medium'>动作</th>
                <th className='px-2 py-2 font-medium'>详情</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className='border-b border-slate-800/60'>
                  <td className='whitespace-nowrap px-2 py-2 text-slate-400'>
                    {formatDateTime(row.at)}
                  </td>
                  <td className='px-2 py-2'>
                    <Badge tone={row.source === 'ai' ? 'negotiation' : 'contacted'}>
                      {row.source === 'ai' ? 'AI 写回' : '人工'}
                    </Badge>
                  </td>
                  <td className='px-2 py-2 text-slate-300'>
                    {row.actor_id}
                    {row.on_behalf_of ? '（代 ' + row.on_behalf_of + '）' : ''}
                  </td>
                  <td className='px-2 py-2 text-slate-300'>{row.object_type}</td>
                  <td className='px-2 py-2 text-slate-400'>{row.record_id ?? '—'}</td>
                  <td className='px-2 py-2 text-slate-300'>
                    {row.method} {row.path}
                  </td>
                  <td className='px-2 py-2'>
                    <Button tone='ghost' onClick={() => setDetail(row)}>
                      查看
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {detail ? (
        <Modal title={'审计详情 #' + detail.id} onClose={() => setDetail(null)}>
          <p className='mb-2 text-xs text-slate-400'>
            幂等键：{detail.idempotency_key ?? '无'} · 操作者类型：{detail.actor_kind}
          </p>
          <h3 className='mb-1 text-xs font-semibold text-slate-300'>变更前</h3>
          {detail.before ? <JsonView value={detail.before} /> : <Empty text='无' />}
          <h3 className='mb-1 mt-3 text-xs font-semibold text-slate-300'>变更后</h3>
          {detail.after ? <JsonView value={detail.after} /> : <Empty text='无' />}
        </Modal>
      ) : null}
    </div>
  );
}