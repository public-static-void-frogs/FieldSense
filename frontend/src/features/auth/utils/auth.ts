import { ApiError } from '../../../api/core/http.ts';

export function isUnauthorized(error: unknown) {
  return error instanceof ApiError && error.status === 401;
}

export function returnPath(search: string) {
  const path = new URLSearchParams(search).get('next');
  if (!path || !path.startsWith('/') || path.startsWith('//') || path.includes('\\')) {
    return '/';
  }
  return path;
}
