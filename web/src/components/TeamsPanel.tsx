import { useCallback, useEffect, useState } from 'react';

import { api } from '../lib/api';
import type { Team } from '../lib/types';
import { Alert, Button, Card, Empty, Field, INPUT_CLASS } from './ui';

export function TeamsPanel({ canManage }: { canManage: boolean }) {
  const [teams, setTeams] = useState<Team[]>([]);
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    try {
      const result = await api.teams();
      setTeams(result.data);
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const create = async () => {
    if (!name.trim()) {
      setError('团队名称不能为空');
      return;
    }
    try {
      await api.createTeam(name.trim());
      setName('');
      setNotice('团队已创建');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const rename = async (team: Team) => {
    const next = window.prompt('新的团队名称', team.name);
    if (!next || next.trim() === team.name) {
      return;
    }
    try {
      await api.updateTeam(team.id, next.trim());
      setNotice('团队已更新');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const remove = async (team: Team) => {
    if (!window.confirm('删除团队「' + team.name + '」？成员不会被删除。')) {
      return;
    }
    try {
      await api.deleteTeam(team.id);
      setNotice('团队已删除');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className='flex flex-col gap-3'>
      <Card title={'团队（' + teams.length + '）'}>
        {error ? <Alert text={error} /> : null}
        {notice ? <Alert text={notice} tone='ok' /> : null}
        {canManage ? (
          <div className='mb-3 flex items-end gap-2'>
            <div className='flex-1'>
              <Field label='新团队名称'>
                <input
                  className={INPUT_CLASS}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
            </div>
            <div className='pb-3'>
              <Button tone='primary' onClick={() => void create()}>
                创建团队
              </Button>
            </div>
          </div>
        ) : null}
        {teams.length === 0 ? (
          <Empty text='还没有团队' />
        ) : (
          <table className='w-full border-collapse text-sm'>
            <thead>
              <tr className='border-b border-slate-800 text-left text-xs text-slate-400'>
                <th className='px-2 py-2 font-medium'>团队</th>
                <th className='px-2 py-2 font-medium'>ID</th>
                <th className='px-2 py-2 font-medium'>成员数</th>
                <th className='px-2 py-2 font-medium'>操作</th>
              </tr>
            </thead>
            <tbody>
              {teams.map((team) => (
                <tr key={team.id} className='border-b border-slate-800/60'>
                  <td className='px-2 py-2 text-slate-200'>{team.name}</td>
                  <td className='px-2 py-2 text-slate-400'>{team.id}</td>
                  <td className='px-2 py-2 text-slate-300'>{team.member_count}</td>
                  <td className='px-2 py-2'>
                    {canManage ? (
                      <span className='flex gap-1'>
                        <Button tone='ghost' onClick={() => void rename(team)}>
                          重命名
                        </Button>
                        <Button tone='ghost' onClick={() => void remove(team)}>
                          删除
                        </Button>
                      </span>
                    ) : (
                      <span className='text-xs text-slate-500'>只读</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}