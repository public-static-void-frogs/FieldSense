type RequestOptions = RequestInit & { allowMissing?: boolean; timeoutMs?: number };

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export class ApiUnavailableError extends Error {
  constructor(cause?: unknown) {
    super('API is unavailable', { cause });
    this.name = 'ApiUnavailableError';
  }
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
  readResponse: (response: Response) => Promise<T> = (response) => response.json() as Promise<T>,
): Promise<T> {
  // Node's environment supports integration tests; browser builds use Vite's environment.
  const environment =
    import.meta.env ??
    (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env;
  const baseUrl = environment?.VITE_API_BASE_URL;

  if (!baseUrl || !/^https?:\/\//.test(baseUrl)) {
    throw new Error('VITE_API_BASE_URL must contain the full HTTP API URL.');
  }
  const { allowMissing, timeoutMs = 10_000, ...init } = options;
  const signal = AbortSignal.any([
    ...(init.signal ? [init.signal] : []),
    AbortSignal.timeout(timeoutMs),
  ]);
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}${path}`, {
      ...init,
      credentials: 'include',
      signal,
      headers,
    });
    if (response.status === 404 && allowMissing) {
      return null as T;
    }
    if (response.status >= 500 || response.status === 408) {
      throw new ApiUnavailableError();
    }
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => {
        signal.throwIfAborted();
        return null;
      });
      let message = `Request failed (${response.status})`;
      if (body && typeof body === 'object' && 'detail' in body) {
        if (typeof body.detail === 'string') {
          message = body.detail;
        } else if (Array.isArray(body.detail)) {
          message = body.detail.map((error) => error.msg).join('; ');
        }
      }
      throw new ApiError(response.status, message);
    }
    return await readResponse(response);
  } catch (error) {
    if (init.signal?.aborted) {
      throw init.signal.reason;
    }
    if (error instanceof TypeError || (error instanceof Error && error.name === 'TimeoutError')) {
      throw new ApiUnavailableError(error);
    }
    throw error;
  }
}
