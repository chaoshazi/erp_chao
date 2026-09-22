import { useState } from 'react';

import { api } from '../lib/api';
import type { Actor, FieldMeta, ObjectMeta, RecordItem, Team } from '../lib/types';
import { Alert, Button, Field, INPUT_CLASS } from './ui';

export type RefOption = { value: string; label: string };

function toInputValue(field: FieldMeta, value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  const text = String(value);
  if (field.kind === 'datetime') {
    // datetime-local 需要 YYYY-MM-DDTHH:mm
    return text.slice(0, 16);
  }
  if (field.kind === 'date') {
    return text.slice(0, 10);
  }
  return text;
}

function buildInitial(
  object: ObjectMeta,
  value: RecordItem | null,
  prefill?: Record<string, unknown>,
): Record<string, string> {
  const draft: Record<string, string> = {};
  object.fields.forEach((field) => {
    if (field.kind === 'password') {
      draft[field.name] = '';
      return;
    }
    if (value) {
      draft[field.name] = toInputValue(field, value[field.name]);
      return;
    }
    const preset = prefill?.[field.name];
    draft[field.name] = preset === undefined || preset === null ? '' : String(preset);
  });
  draft.owner_id = value ? String(value.owner_id ?? '') : '';
  draft.team_id = value ? String((value.team_ids ?? [])[0] ?? '') : '';
  return draft;
}

export function RecordForm({
  object,
  value,
  prefill,
  refOptions,
  users,
  teams,
  canAssign,
  onSaved,
  onCancel,
}: {
  object: ObjectMeta;
  value: RecordItem | null;
  prefill?: Record<string, unknown>;
  refOptions: Record<string, RefOption[]>;
  users: Actor[];
  teams: Team[];
  canAssign: boolean;
  onSaved: (record: RecordItem) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    buildInitial(object, value, prefill),
  );
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const editing = value !== null;

  const setField = (name: string, text: string) => {
    setDraft((prev) => ({ ...prev, [name]: text }));
  };

  const submit = async () => {
    if (busy) {
      return;
    }
    const payload: Record<string, unknown> = {};
    object.fields.forEach((field) => {
      const text = (draft[field.name] ?? '').trim();
      if (field.kind === 'password') {
        if (text) {
          payload[field.name] = text;
        }
        return;
      }
      payload[field.name] = text;
    });
    if (canAssign) {
      payload.owner_id = (draft.owner_id ?? '').trim();
      payload.team_id = (draft.team_id ?? '').trim();
    }
    if (editing && value?.version) {
      payload.version = value.version;
    }
    setBusy(true);
    setError('');
    try {
      const result = editing
        ? await api.update(object.name, String(value?.id ?? ''), payload)
        : await api.create(object.name, payload);
      onSaved(result.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const renderInput = (field: FieldMeta) => {
    const text = draft[field.name] ?? '';
    if (field.kind === 'password') {
      return (
        <input
          className={INPUT_CLASS}
          type='password'
          value={text}
          placeholder={editing ? '留空表示不修改密码' : '至少 6 位'}
          onChange={(event) => setField(field.name, event.target.value)}
        />
      );
    }
    if (field.kind === 'bool') {
      return (
        <select
          className={INPUT_CLASS}
          value={text}
          onChange={(event) => setField(field.name, event.target.value)}
        >
          <option value=''>（未设置）</option>
          <option value='true'>是</option>
          <option value='false'>否</option>
        </select>
      );
    }
    if (field.kind === 'enum') {
      return (
        <select
          className={INPUT_CLASS}
          value={text}
          onChange={(event) => setField(field.name, event.target.value)}
        >
          <option value=''>（未设置）</option>
          {field.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
    }
    if (field.kind === 'text') {
      return (
        <textarea
          className={INPUT_CLASS + ' min-h-[90px]'}
          value={text}
          onChange={(event) => setField(field.name, event.target.value)}
        />
      );
    }
    if (field.kind === 'ref' && field.ref && field.ref !== 'any') {
      const options = refOptions[field.ref] ?? [];
      return (
        <select
          className={INPUT_CLASS}
          value={text}
          onChange={(event) => setField(field.name, event.target.value)}
        >
          <option value=''>（未关联）</option>
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
    }
    if (field.kind === 'date') {
      return (
        <input
          className={INPUT_CLASS}
          type='date'
          value={text}
          onChange={(event) => setField(field.name, event.target.value)}
        />
      );
    }
    if (field.kind === 'datetime') {
      return (
        <input
          className={INPUT_CLASS}
          type='datetime-local'
          value={text}
          onChange={(event) => setField(field.name, event.target.value)}
        />
      );
    }
    if (field.kind === 'decimal') {
      return (
        <input
          className={INPUT_CLASS}
          type='number'
          value={text}
          onChange={(event) => setField(field.name, event.target.value)}
        />
      );
    }
    return (
      <input
        className={INPUT_CLASS}
        value={text}
        placeholder={field.ref === 'any' ? '关联记录 ID，例如 lead-0001' : ''}
        onChange={(event) => setField(field.name, event.target.value)}
      />
    );
  };

  return (
    <div>
      {error ? <Alert text={error} /> : null}
      {object.fields.map((field) => (
        <Field
          key={field.name}
          label={field.label + (field.required ? '（必填）' : '')}
          hint={field.kind === 'ref' && field.ref === 'any' ? '填目标记录 ID' : undefined}
        >
          {renderInput(field)}
        </Field>
      ))}
      {canAssign ? (
        <>
          <Field label='负责人'>
            <select
              className={INPUT_CLASS}
              value={draft.owner_id ?? ''}
              onChange={(event) => setField('owner_id', event.target.value)}
            >
              <option value=''>（默认归属创建者/记录归属）</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name || user.id}
                </option>
              ))}
            </select>
          </Field>
          <Field label='归属团队'>
            <select
              className={INPUT_CLASS}
              value={draft.team_id ?? ''}
              onChange={(event) => setField('team_id', event.target.value)}
            >
              <option value=''>（继承记录/创建者团队）</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.name}
                </option>
              ))}
            </select>
          </Field>
        </>
      ) : null}
      <div className='mt-2 flex gap-2'>
        <Button tone='primary' onClick={() => void submit()} disabled={busy}>
          {busy ? '保存中…' : editing ? '保存修改' : '创建'}
        </Button>
        <Button onClick={onCancel}>取消</Button>
      </div>
    </div>
  );
}
