import type { FieldMeta, Meta, ObjectMeta } from './types';

export type RefContext = {
  recordTitles: Record<string, string>;
  teamNames: Record<string, string>;
  userNames: Record<string, string>;
};

export function objectOf(meta: Meta | null, name: string): ObjectMeta | null {
  if (!meta) {
    return null;
  }
  return meta.objects.find((item) => item.name === name) ?? null;
}

export function fieldOf(object: ObjectMeta | null, name: string): FieldMeta | null {
  if (!object) {
    return null;
  }
  return object.fields.find((item) => item.name === name) ?? null;
}

export function optionLabel(field: FieldMeta | null, value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  const text = String(value);
  if (!field) {
    return text;
  }
  const found = field.options.find((item) => item.value === text);
  return found ? found.label : text;
}

export function formatDateTime(value: unknown): string {
  if (!value) {
    return '—';
  }
  const text = String(value);
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text;
  }
  const pad = (num: number) => String(num).padStart(2, '0');
  return (
    date.getFullYear() +
    '-' +
    pad(date.getMonth() + 1) +
    '-' +
    pad(date.getDate()) +
    ' ' +
    pad(date.getHours()) +
    ':' +
    pad(date.getMinutes())
  );
}

export function formatMoney(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return String(value);
  }
  return num.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

export function cellText(
  field: FieldMeta | null,
  value: unknown,
  ctx: RefContext,
  options: { truncate?: number } = {},
): string {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  const limit = options.truncate ?? 48;
  const text = String(value);
  if (!field) {
    return text.length > limit ? text.slice(0, limit) + '…' : text;
  }
  if (field.kind === 'enum') {
    return optionLabel(field, value);
  }
  if (field.name === 'owner_id') {
    return ctx.userNames[text] ?? text;
  }
  if (field.name === 'team_id') {
    return ctx.teamNames[text] ?? text;
  }
  if (field.kind === 'ref') {
    return ctx.recordTitles[text] ?? text;
  }
  if (field.kind === 'decimal') {
    return formatMoney(value);
  }
  if (field.kind === 'datetime') {
    return formatDateTime(value);
  }
  if (field.kind === 'date') {
    return text.slice(0, 10);
  }
  if (field.kind === 'bool') {
    return value === true || value === 1 || value === 'true' ? '是' : '否';
  }
  return text.length > limit ? text.slice(0, limit) + '…' : text;
}

export function ownerName(ctx: RefContext, value: unknown): string {
  if (!value) {
    return '未分配';
  }
  const text = String(value);
  return ctx.userNames[text] ?? text;
}

export function teamName(ctx: RefContext, record: { team_ids?: string[] }): string {
  const first = (record.team_ids ?? [])[0];
  if (!first) {
    return '—';
  }
  return ctx.teamNames[first] ?? first;
}