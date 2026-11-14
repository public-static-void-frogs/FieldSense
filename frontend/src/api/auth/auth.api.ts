import type { User } from '../../types/auth/auth.types.ts';
import { request } from '../core/http.ts';

export type LoginInput = { email: string; password: string };
export type RegisterInput = LoginInput & {
  fullName: string;
  farmName?: string;
  latitude?: number;
  longitude?: number;
  location: string;
  language: 'en' | 'uk';
};
export type AccountInput = Pick<User, 'fullName' | 'email'>;

export const authApi = {
  me: (signal?: AbortSignal): Promise<User> => request('/auth/me', { signal }),
  login: (values: LoginInput): Promise<User> =>
    request('/auth/login', { method: 'POST', body: JSON.stringify(values) }),
  register: (values: RegisterInput): Promise<User> =>
    request('/auth/register', { method: 'POST', body: JSON.stringify(values) }),
  logout: (): Promise<{ message: string }> => request('/auth/logout', { method: 'POST' }),
  updateAccount: (values: AccountInput): Promise<User> =>
    request('/auth/me', { method: 'PUT', body: JSON.stringify(values) }),
};
