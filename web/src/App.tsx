import { useCallback, useEffect, useState } from 'react';

import { AuditPanel } from './components/AuditPanel';
import { Dashboard } from './components/Dashboard';
import { Login } from './components/Login';
import { RecordDetail } from './components/RecordDetail';
import { RecordList } from './components/RecordList';
import type { RefOption } from './components/RecordForm';
import { SettingsPanel } from './components/SettingsPanel';
import { TeamsPanel } from './components/TeamsPanel';
import { Alert, Button, Card, Empty } from './components/ui';
import { ApiError, api } from './lib/api';
import type { RefContext } from './lib/format';
import { clearToken, readToken } from './lib/session';
import type { Actor, ListResponse, Meta, RecordItem, Team } from './lib/types';

type Route = { name: string; id: string | null };

function parseHash(): Route {
  const raw = window.location.hash.replace(/^#\/?/, '');
  const [name, id] = raw.split('/');
  return { name: name || 'dashboard', id: id || null };
}

function actorOf(row: RecordItem): Actor {
  return {
    id: row.id,
    name: String(row.name ?? row.id),
    role: String(row.role ?? 'staff'),
    team_id: (row.team_ids ?? [])[0] ?? null,
    kind: 'user',
  };
}

export default function App() {
  const [authed, setAuthed] = useState(() => Boolean(readToken()));
  const [meta, setMeta] = useState<Meta | null>(null);
  const [route, setRoute] = useState<Route>(() => parseHash());
  const [users, setUsers] = useState<Actor[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [ctx, setCtx] = useState<RefContext>({ recordTitles: {}, teamNames: {}, userNames: {} });
  const [refOptions, setRefOptions] = useState<Record<string, RefOption[]>>({});
  const [error, setError] = useState('');

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    if (!authed) {
      setMeta(null);
      return;
    }
    let cancelled = false;
    api
      .meta()
      .then((result) => {
        if (!cancelled) {
          setMeta(result);
        }
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) {
          clearToken();
          setAuthed(false);
          return;
        }
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authed]);

  const loadRefs = useCallback(async () => {
    const safeList = (name: string): Promise<ListResponse> =>
      api
        .list(name, { limit: 200, order: 'desc', page: 1 })
        .catch(() => ({ data: [] as RecordItem[], next_cursor: null, total: 0 }));
    const safeTeams = (): Promise<{ data: Team[] }> =>
      api.teams().catch(() => ({ data: [] as Team[] }));
    const [userRows, teamRows, items, suppliers, customers, warehouses, purchaseOrders, salesOrders] =
      await Promise.all([
        safeList('users'),
        safeTeams(),
        safeList('items'),
        safeList('suppliers'),
        safeList('customers'),
        safeList('warehouses'),
        safeList('purchase_orders'),
        safeList('sales_orders'),
      ]);
    const userNames: Record<string, string> = {};
    userRows.data.forEach((row) => {
      userNames[row.id] = String(row.name ?? row.id);
    });
    const teamNames: Record<string, string> = {};
    teamRows.data.forEach((team) => {
      teamNames[team.id] = team.name;
    });
    const recordTitles: Record<string, string> = {};
    const collect = (rows: RecordItem[], key: string) => {
      rows.forEach((row) => {
        const value = row[key];
        if (typeof value === 'string' && value) {
          recordTitles[row.id] = value;
        }
      });
    };
    collect(items.data, 'name');
    collect(suppliers.data, 'name');
    collect(customers.data, 'name');
    collect(warehouses.data, 'name');
    collect(purchaseOrders.data, 'code');
    collect(salesOrders.data, 'code');
    setUsers(userRows.data.map(actorOf));
    setTeams(teamRows.data);
    setCtx({ recordTitles, teamNames, userNames });
    const byName = (rows: RecordItem[]) =>
      rows.map((row) => ({ value: row.id, label: String(row.name ?? row.id) }));
    setRefOptions({
      items: byName(items.data),
      suppliers: byName(suppliers.data),
      customers: byName(customers.data),
      warehouses: byName(warehouses.data),
      purchase_orders: purchaseOrders.data.map((row) => ({
        value: row.id,
        label: String(row.code ?? row.id),
      })),
      sales_orders: salesOrders.data.map((row) => ({
        value: row.id,
        label: String(row.code ?? row.id),
      })),
      teams: teamRows.data.map((team) => ({ value: team.id, label: team.name })),
      users: userRows.data.map((row) => ({ value: row.id, label: String(row.name ?? row.id) })),
    });
  }, []);

  useEffect(() => {
    if (!authed || !meta) {
      return;
    }
    void loadRefs().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : String(err)),
    );
  }, [authed, meta, route.name, loadRefs]);

  const logout = () => {
    clearToken();
    setAuthed(false);
    window.location.hash = '#/dashboard';
  };

  if (!authed) {
    return <Login onDone={() => setAuthed(true)} />;
  }

  const actor = meta?.actor ?? null;
  const roleLabel = meta && actor ? meta.role_labels[actor.role] ?? actor.role : '';
  const canAssign = Boolean(actor && (actor.kind === 'service' || actor.role === 'admin' || actor.role === 'manager'));
  const isAdmin = Boolean(actor && (actor.kind === 'service' || actor.role === 'admin'));
  const objectNames = (meta?.object_names ?? []).filter((name) => name !== 'users');
  const activeObject = meta ? meta.objects.find((item) => item.name === route.name) : undefined;

  const nav = [
    { key: 'dashboard', label: '仪表盘' },
    ...objectNames.map((name) => ({
      key: name,
      label: meta?.objects.find((item) => item.name === name)?.label ?? name,
    })),
    ...(isAdmin ? [{ key: 'users', label: '用户' }] : []),
    { key: 'teams', label: '团队' },
    ...(isAdmin ? [{ key: 'audit', label: '审计日志' }] : []),
    { key: 'settings', label: '设置 / AI 对接' },
  ];

  let content = <Empty text='加载中…' />;
  if (error) {
    content = <Alert text={error} />;
  } else if (!meta) {
    content = <Empty text='加载中…' />;
  } else if (route.name === 'dashboard') {
    content = (
      <Dashboard
        meta={meta}
        ctx={ctx}
        onOpenObject={(name) => {
          window.location.hash = '#/' + name;
        }}
        onOpen={(name, id) => {
          window.location.hash = '#/' + name + '/' + id;
        }}
      />
    );
  } else if (route.name === 'teams') {
    content = <TeamsPanel canManage={isAdmin} />;
  } else if (route.name === 'audit') {
    content = isAdmin ? <AuditPanel /> : <Empty text='只有管理员可以查看审计日志' />;
  } else if (route.name === 'settings') {
    content = <SettingsPanel actor={meta.actor} />;
  } else if (activeObject) {
    content = route.id ? (
      <RecordDetail
        objectName={activeObject.name}
        recordId={route.id}
        meta={meta}
        ctx={ctx}
        users={users}
        teams={teams}
        canAssign={canAssign}
        refOptions={refOptions}
        onBack={() => {
          window.location.hash = '#/' + activeObject.name;
        }}
        onOpen={(name, id) => {
          window.location.hash = '#/' + name + '/' + id;
        }}
      />
    ) : (
      <RecordList
        objectName={activeObject.name}
        meta={meta}
        ctx={ctx}
        users={users}
        teams={teams}
        canAssign={canAssign}
        refOptions={refOptions}
        onOpen={(id) => {
          window.location.hash = '#/' + activeObject.name + '/' + id;
        }}
      />
    );
  } else {
    content = <Empty text='页面不存在' />;
  }

  return (
    <div className='flex h-full'>
      <aside className='flex w-56 shrink-0 flex-col border-r border-slate-800 bg-slate-900/40 p-3'>
        <h1 className='mb-1 text-base font-semibold text-slate-100'>ERP 管理系统</h1>
        <p className='mb-4 text-xs text-slate-500'>采购 / 销售 / 库存 / 往来一体化管理</p>
        <nav className='flex flex-1 flex-col gap-1'>
          {nav.map((item) => (
            <button
              key={item.key}
              type='button'
              onClick={() => {
                window.location.hash = '#/' + item.key;
              }}
              className={
                'rounded-md px-3 py-2 text-left text-sm transition ' +
                (route.name === item.key
                  ? 'bg-sky-600/20 text-sky-200'
                  : 'text-slate-300 hover:bg-slate-800')
              }
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className='mt-3 border-t border-slate-800 pt-3'>
          <p className='mb-1 text-xs text-slate-400'>
            {meta?.actor.name || meta?.actor.id || '未登录'}
          </p>
          <p className='mb-2 text-xs text-slate-500'>
            {roleLabel}
          </p>
          <Button tone='ghost' onClick={logout}>
            退出登录
          </Button>
        </div>
      </aside>
      <main className='scroll-thin min-w-0 flex-1 overflow-auto p-4'>{content}</main>
    </div>
  );
}

export function AppShellNotice({ text }: { text: string }) {
  return (
    <Card title='提示'>
      <Alert text={text} tone='warn' />
    </Card>
  );
}