import { useCallback, useEffect, useState } from 'react';

import { api } from '../lib/api';
import { cellText, fieldOf, objectOf, type RefContext } from '../lib/format';
import type { Actor, Meta, RecordItem, Team } from '../lib/types';
import { RecordForm, type RefOption } from './RecordForm';
import { Alert, Button, Card, Empty, INPUT_CLASS, Modal } from './ui';

const PAGE_SIZE = 20;

export function RecordList({
  objectName,
  meta,
  ctx,
  users,
  teams,
  canAssign,
  refOptions,
  onOpen,
}: {
  objectName: string;
  meta: Meta;
  ctx: RefContext;
  users: Actor[];
  teams: Team[];
  canAssign: boolean;
  refOptions: Record<string, RefOption[]>;
  onOpen: (id: string) => void;
}) {
  const object = objectOf(meta, objectName);
  const [rows, setRows] = useState<RecordItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<RecordItem | null>(null);

  const load = useCallback(async () => {
    if (!object) {
      return;
    }
    setBusy(true);
    try {
      const result = await api.list(object.name, {
        q: keyword,
        order: 'desc',
        page,
        limit: PAGE_SIZE,
        include_deleted: includeDeleted,
        ...filters,
      });
      setRows(result.data);
      setTotal(result.total);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [object, keyword, page, filters, includeDeleted]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setPage(1);
    setFilters({});
    setKeyword('');
  }, [objectName]);

  if (!object) {
    return <Empty text='未知对象类型' />;
  }

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const filterFields = object.fields.filter((field) => field.filterable);
  const canCreate = canAssign || object.name !== 'users';

  return (
    <div className='flex h-full flex-col gap-3'>
      <Card
        title={object.label + '（共 ' + total + ' 条）'}
        extra={
          <div className='flex gap-2'>
            <Button onClick={() => void load()} disabled={busy}>
              {busy ? '加载中…' : '刷新'}
            </Button>
            {canCreate ? <Button tone='primary' onClick={() => setCreating(true)}>新建{object.singular}</Button> : null}
          </div>
        }
      >
        {error ? <Alert text={error} /> : null}
        <div className='flex flex-wrap items-end gap-3'>
          <div className='min-w-[220px] flex-1'>
            <span className='mb-1 block text-xs text-slate-400'>关键字</span>
            <input
              className={INPUT_CLASS}
              value={keyword}
              placeholder='按名称、邮箱、ID 搜索'
              onChange={(event) => {
                setKeyword(event.target.value);
                setPage(1);
              }}
            />
          </div>
          {filterFields.map((field) => (
            <div key={field.name} className='min-w-[140px]'>
              <span className='mb-1 block text-xs text-slate-400'>{field.label}</span>
              <select
                className={INPUT_CLASS}
                value={filters[field.name] ?? ''}
                onChange={(event) => {
                  const value = event.target.value;
                  setPage(1);
                  setFilters((prev) => {
                    const next = { ...prev };
                    if (value) {
                      next[field.name] = value;
                    } else {
                      delete next[field.name];
                    }
                    return next;
                  });
                }}
              >
                <option value=''>全部</option>
                {field.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
                {field.options.length === 0 ? <option value=''>（无枚举）</option> : null}
              </select>
            </div>
          ))}
          {canAssign ? (
            <div className='min-w-[140px]'>
              <span className='mb-1 block text-xs text-slate-400'>负责人</span>
              <select
                className={INPUT_CLASS}
                value={filters.owner_id ?? ''}
                onChange={(event) => {
                  const value = event.target.value;
                  setPage(1);
                  setFilters((prev) => {
                    const next = { ...prev };
                    if (value) {
                      next.owner_id = value;
                    } else {
                      delete next.owner_id;
                    }
                    return next;
                  });
                }}
              >
                <option value=''>全部</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.name || user.id}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          {canAssign ? (
            <label className='flex items-center gap-2 pb-1 text-xs text-slate-400'>
              <input
                type='checkbox'
                checked={includeDeleted}
                onChange={(event) => {
                  setIncludeDeleted(event.target.checked);
                  setPage(1);
                }}
              />
              显示已删除
            </label>
          ) : null}
        </div>
      </Card>

      <Card className='flex min-h-0 flex-1 flex-col'>
        <div className='scroll-thin flex-1 overflow-auto'>
          <table className='w-full border-collapse text-sm'>
            <thead>
              <tr className='border-b border-slate-800 text-left text-xs text-slate-400'>
                {object.list_fields.map((name) => (
                  <th key={name} className='whitespace-nowrap px-2 py-2 font-medium'>
                    {fieldOf(object, name)?.label ?? name}
                  </th>
                ))}
                <th className='whitespace-nowrap px-2 py-2 font-medium'>负责人</th>
                <th className='whitespace-nowrap px-2 py-2 font-medium'>更新时间</th>
                <th className='whitespace-nowrap px-2 py-2 font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className='border-b border-slate-800/60 hover:bg-slate-800/40'>
                  {object.list_fields.map((name) => (
                    <td key={name} className='px-2 py-2 align-top text-slate-200'>
                      {cellText(fieldOf(object, name), row[name], ctx)}
                    </td>
                  ))}
                  <td className='px-2 py-2 align-top text-slate-300'>
                    {ctx.userNames[String(row.owner_id ?? '')] ?? row.owner_id ?? '—'}
                  </td>
                  <td className='whitespace-nowrap px-2 py-2 align-top text-slate-400'>
                    {cellText(fieldOf(object, 'updated_at'), row.updated_at, ctx)}
                  </td>
                  <td className='whitespace-nowrap px-2 py-2 align-top'>
                    <span className='flex gap-1'>
                      <Button tone='ghost' onClick={() => onOpen(row.id)}>
                        详情
                      </Button>
                      <Button tone='ghost' onClick={() => setEditing(row)}>
                        编辑
                      </Button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && !busy ? <Empty text='没有匹配的记录' /> : null}
        </div>
        <div className='mt-3 flex items-center justify-between text-xs text-slate-400'>
          <span>
            第 {page} / {pages} 页
          </span>
          <span className='flex gap-2'>
            <Button tone='ghost' disabled={page <= 1} onClick={() => setPage(page - 1)}>
              上一页
            </Button>
            <Button tone='ghost' disabled={page >= pages} onClick={() => setPage(page + 1)}>
              下一页
            </Button>
          </span>
        </div>
      </Card>

      {creating ? (
        <Modal title={'新建' + object.singular} onClose={() => setCreating(false)}>
          <RecordForm
            object={object}
            value={null}
            refOptions={refOptions}
            users={users}
            teams={teams}
            canAssign={canAssign}
            onCancel={() => setCreating(false)}
            onSaved={() => {
              setCreating(false);
              void load();
            }}
          />
        </Modal>
      ) : null}

      {editing ? (
        <Modal title={'编辑' + object.singular} onClose={() => setEditing(null)}>
          <RecordForm
            object={object}
            value={editing}
            refOptions={refOptions}
            users={users}
            teams={teams}
            canAssign={canAssign}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              void load();
            }}
          />
        </Modal>
      ) : null}
    </div>
  );
}