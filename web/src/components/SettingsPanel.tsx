import { useState } from 'react';

import { api } from '../lib/api';
import type { Actor } from '../lib/types';
import { Alert, Button, Card, Field, INPUT_CLASS } from './ui';

function Code({ lines }: { lines: string[] }) {
  return (
    <pre className='scroll-thin overflow-auto rounded-lg bg-slate-950/80 p-3 text-xs leading-relaxed text-slate-300'>
      {lines.join('\n')}
    </pre>
  );
}

export function SettingsPanel({ actor }: { actor: Actor }) {
  const [password, setPassword] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const origin = typeof window === 'undefined' ? '' : window.location.origin;

  const submit = async () => {
    setNotice('');
    setError('');
    try {
      await api.changePassword(password);
      setPassword('');
      setNotice('密码已更新');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className='flex flex-col gap-3'>
      <Card title='当前账号'>
        <dl className='grid grid-cols-2 gap-2 text-sm md:grid-cols-4'>
          <div>
            <dt className='text-xs text-slate-400'>姓名</dt>
            <dd className='text-slate-200'>{actor.name || actor.id}</dd>
          </div>
          <div>
            <dt className='text-xs text-slate-400'>账号</dt>
            <dd className='text-slate-200'>{actor.id}</dd>
          </div>
          <div>
            <dt className='text-xs text-slate-400'>角色</dt>
            <dd className='text-slate-200'>{actor.role}</dd>
          </div>
          <div>
            <dt className='text-xs text-slate-400'>团队</dt>
            <dd className='text-slate-200'>{actor.team_id ?? '—'}</dd>
          </div>
        </dl>
      </Card>

      <Card title='修改密码'>
        {error ? <Alert text={error} /> : null}
        {notice ? <Alert text={notice} tone='ok' /> : null}
        <div className='flex items-end gap-2'>
          <div className='flex-1'>
            <Field label='新密码' hint='至少 6 位'>
              <input
                className={INPUT_CLASS}
                type='password'
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
          </div>
          <div className='pb-3'>
            <Button tone='primary' onClick={() => void submit()} disabled={password.length < 6}>
              更新密码
            </Button>
          </div>
        </div>
      </Card>

      <Card title='AI 能力层对接'>
        <p className='mb-3 text-xs text-slate-400'>
          在 D:\codex（AI 能力层）里把数据源切成 erp、模式切成 rest，即可用本系统作为数据源。
          AI 用服务账号令牌访问下面的接口，权限等同管理员，写回会记入审计并标注来源为 ai。
        </p>
        <p className='mb-1 text-xs font-semibold text-slate-300'>本系统接口地址</p>
        <Code lines={[origin + '/api/v1', origin + '/health']} />
        <p className='mb-1 mt-3 text-xs font-semibold text-slate-300'>D:\\codex 的 .env 片段</p>
        <Code
          lines={[
            'AICRM_SOURCE=erp',
            'AICRM_ERP_MODE=rest',
            'AICRM_ERP_BASE_URL=' + origin + '/api/v1',
            'AICRM_ERP_API_TOKEN=<与 ERP_SERVICE_TOKEN 相同的值>',
            'AICRM_ERP_AUTH_MODE=bearer',
          ]}
        />
        <p className='mb-1 mt-3 text-xs font-semibold text-slate-300'>接入前先跑只读探测（在 D:\\codex 目录）</p>
        <Code
          lines={[
            'python scripts/erp_probe.py --base-url ' +
              origin +
              '/api/v1 --token <ERP_SERVICE_TOKEN> --all --show-raw',
          ]}
        />
      </Card>

      <Card title='服务启动提示'>
        <p className='mb-1 text-xs font-semibold text-slate-300'>本机零依赖（sqlite）</p>
        <Code
          lines={[
            'cd D:\\erp',
            'pip install -r requirements.txt',
            'python -m uvicorn app.main:app --port 9200',
          ]}
        />
        <p className='mb-1 mt-3 text-xs font-semibold text-slate-300'>前端开发服务器</p>
        <Code lines={['cd D:\\erp\\web', 'npm install', 'npm run dev   # http://127.0.0.1:5175']} />
        <p className='mb-1 mt-3 text-xs font-semibold text-slate-300'>生产形态（Postgres + 托管前端）</p>
        <Code lines={['cd D:\\erp\\web', 'npm run build', 'cd D:\\erp', 'docker compose up -d']} />
      </Card>
    </div>
  );
}