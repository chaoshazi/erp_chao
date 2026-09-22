import { clearToken, readToken } from './session';
import type { Actor, AuditEntry, ListResponse, Meta, RecordItem, Stats, Team } from './types';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = readToken();
  if (token) {
    headers.set('Authorization', 'Bearer ' + token);
  }
  if (init?.body) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch('/api' + path, { ...init, headers });
  if (response.status === 401) {
    clearToken();
    throw new ApiError(401, '登录已过期，请重新登录');
  }
  if (!response.ok) {
    let detail = '请求失败（HTTP ' + response.status + '）';
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') {
        detail = body.detail;
      }
    } catch {
      detail = detail;
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function query(objectType: string, params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== false) {
      search.set(key, String(value));
    }
  });
  const text = search.toString();
  return '/v1/' + objectType + (text ? '?' + text : '');
}

export const api = {
  login: (email: string, password: string) =>
    request<{ token: string; expires_at: number; user: Actor & { email: string } }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<Actor>('/auth/me'),
  changePassword: (password: string) =>
    request<{ detail: string }>('/auth/password', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  meta: () => request<Meta>('/v1/meta'),
  stats: () => request<Stats>('/v1/stats/overview'),
  audit: (limit = 100) => request<{ data: AuditEntry[] }>('/v1/audit?limit=' + limit),
  teams: () => request<{ data: Team[] }>('/v1/teams'),
  createTeam: (name: string) =>
    request<Team>('/v1/teams', { method: 'POST', body: JSON.stringify({ name }) }),
  updateTeam: (id: string, name: string) =>
    request<Team>('/v1/teams/' + id, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteTeam: (id: string) => request<Team>('/v1/teams/' + id, { method: 'DELETE' }),
  list: (objectType: string, params: Record<string, string | number | boolean | undefined>) =>
    request<ListResponse>(query(objectType, params)),
  get: (objectType: string, id: string) =>
    request<{ data: RecordItem }>('/v1/' + objectType + '/' + id),
  create: (objectType: string, payload: Record<string, unknown>) =>
    request<{ data: RecordItem }>('/v1/' + objectType, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  update: (objectType: string, id: string, payload: Record<string, unknown>) =>
    request<{ data: RecordItem }>('/v1/' + objectType + '/' + id, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  remove: (objectType: string, id: string) =>
    request<{ data: RecordItem }>('/v1/' + objectType + '/' + id, { method: 'DELETE' }),
};