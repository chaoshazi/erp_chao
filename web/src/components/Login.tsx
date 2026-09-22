import { useState } from 'react';

import { api } from '../lib/api';
import { saveToken } from '../lib/session';
import { Alert, Button, Field, INPUT_CLASS } from './ui';

export function Login({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState('admin@example.com');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (busy) {
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await api.login(email.trim(), password);
      saveToken(result.token, result.user);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className='flex h-full items-center justify-center p-6'>
      <div className='w-full max-w-sm rounded-xl border border-slate-800 bg-slate-900/60 p-6'>
        <h1 className='mb-1 text-lg font-semibold text-slate-100'>ERP 管理系统</h1>
        <p className='mb-5 text-xs text-slate-500'>用 ERP 账号登录，管理物料、采购、销售、库存与往来账。</p>
        {error ? <Alert text={error} /> : null}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <Field label='邮箱'>
            <input
              className={INPUT_CLASS}
              value={email}
              autoComplete='username'
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>
          <Field label='密码'>
            <input
              className={INPUT_CLASS}
              type='password'
              value={password}
              autoComplete='current-password'
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <Button tone='primary' onClick={() => void submit()} disabled={busy}>
            {busy ? '登录中…' : '登录'}
          </Button>
        </form>
        <p className='mt-4 text-xs text-slate-500'>
          初始管理员由 ERP_BOOTSTRAP_ADMIN_EMAIL / ERP_BOOTSTRAP_ADMIN_PASSWORD 决定。
        </p>
      </div>
    </div>
  );
}