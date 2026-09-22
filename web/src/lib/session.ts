const TOKEN_KEY = 'erp.token';
const USER_KEY = 'erp.user';

export function readToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? '';
}

export function saveToken(token: string, user: unknown): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user ?? {}));
}

export function readUser(): { name?: string; role?: string } {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) ?? '{}') as { name?: string; role?: string };
  } catch {
    return {};
  }
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}