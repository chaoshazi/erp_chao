import type { ReactNode } from 'react';

type Tone = 'default' | 'primary' | 'danger' | 'ghost';

const BUTTON_TONES: Record<Tone, string> = {
  default: 'bg-slate-700 hover:bg-slate-600 text-slate-100',
  primary: 'bg-sky-600 hover:bg-sky-500 text-white',
  danger: 'bg-rose-600 hover:bg-rose-500 text-white',
  ghost: 'bg-transparent hover:bg-slate-700 text-slate-300',
};

export const INPUT_CLASS =
  'w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100 outline-none focus:border-sky-500';

export function Button({
  children,
  onClick,
  disabled = false,
  tone = 'default',
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: Tone;
  title?: string;
}) {
  return (
    <button
      type='button'
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={
        'rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ' +
        BUTTON_TONES[tone]
      }
    >
      {children}
    </button>
  );
}

export function Card({
  title,
  extra,
  children,
  className = '',
}: {
  title?: string;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={'rounded-xl border border-slate-800 bg-slate-900/60 p-4 ' + className}>
      {(title || extra) && (
        <header className='mb-3 flex items-center justify-between gap-2'>
          {title ? <h2 className='text-sm font-semibold text-slate-200'>{title}</h2> : <span />}
          {extra}
        </header>
      )}
      {children}
    </section>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className='mb-3 block text-sm'>
      <span className='mb-1 block text-slate-300'>{label}</span>
      {children}
      {hint ? <span className='mt-1 block text-xs text-slate-500'>{hint}</span> : null}
    </label>
  );
}

const BADGE_TONES: Record<string, string> = {
  new: 'bg-slate-500/20 text-slate-300',
  contacted: 'bg-sky-500/20 text-sky-300',
  qualified: 'bg-indigo-500/20 text-indigo-300',
  proposal: 'bg-violet-500/20 text-violet-300',
  negotiation: 'bg-amber-500/20 text-amber-300',
  closed_won: 'bg-emerald-500/20 text-emerald-300',
  closed_lost: 'bg-rose-500/20 text-rose-300',
  hot: 'bg-rose-500/20 text-rose-300',
  high: 'bg-amber-500/20 text-amber-300',
  done: 'bg-emerald-500/20 text-emerald-300',
  open: 'bg-sky-500/20 text-sky-300',
  neutral: 'bg-slate-500/20 text-slate-300',
};

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return (
    <span
      className={
        'rounded px-2 py-0.5 text-xs font-medium ' + (BADGE_TONES[tone] ?? BADGE_TONES.neutral)
      }
    >
      {children}
    </span>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className='py-6 text-center text-sm text-slate-500'>{text}</p>;
}

export function Alert({ text, tone = 'error' }: { text: string; tone?: 'error' | 'warn' | 'ok' }) {
  const tones = {
    error: 'border-rose-800 bg-rose-950/60 text-rose-200',
    warn: 'border-amber-800 bg-amber-950/60 text-amber-200',
    ok: 'border-emerald-800 bg-emerald-950/60 text-emerald-200',
  };
  return <div className={'mb-3 rounded-lg border px-3 py-2 text-sm ' + tones[tone]}>{text}</div>;
}

export function JsonView({ value }: { value: unknown }) {
  return (
    <pre className='scroll-thin max-h-80 overflow-auto rounded-lg bg-slate-950/80 p-3 text-xs leading-relaxed text-slate-300'>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function Modal({
  title,
  children,
  footer,
  onClose,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className='fixed inset-0 z-20 flex items-start justify-center overflow-auto bg-slate-950/70 p-6'>
      <div className='w-full max-w-2xl rounded-xl border border-slate-800 bg-slate-900 shadow-xl'>
        <header className='flex items-center justify-between border-b border-slate-800 px-4 py-3'>
          <h2 className='text-sm font-semibold text-slate-200'>{title}</h2>
          <Button tone='ghost' onClick={onClose}>
            关闭
          </Button>
        </header>
        <div className='scroll-thin max-h-[70vh] overflow-auto p-4'>{children}</div>
        {footer ? (
          <footer className='flex justify-end gap-2 border-t border-slate-800 px-4 py-3'>{footer}</footer>
        ) : null}
      </div>
    </div>
  );
}