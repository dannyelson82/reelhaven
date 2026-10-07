// Thin fetch wrapper for the ReelHaven API.
//
// Paths are relative ("api/v1/..."), so the UI works behind a reverse proxy
// sub-path or code-server's port proxy. State-changing requests carry the
// CSRF token from the readable `reelhaven_csrf` cookie (double-submit).

const API_BASE = 'api/v1';
const CSRF_COOKIE = 'reelhaven_csrf';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryAfter: number | null;

  constructor(status: number, code: string, retryAfter: number | null) {
    super(code);
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

function readCookie(name: string): string | null {
  for (const part of document.cookie.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return decodeURIComponent(rest.join('='));
  }
  return null;
}

let lastCsrfToken: string | null = null;

/** Remember the token from /auth/state, for when the cookie can't be read. */
export function rememberCsrfToken(token: string): void {
  lastCsrfToken = token;
}

function errorCode(body: unknown): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return 'validation_error';
  }
  return 'unknown_error';
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body !== undefined) headers.set('Content-Type', 'application/json');
  if (method !== 'GET' && method !== 'HEAD') {
    const token = readCookie(CSRF_COOKIE) ?? lastCsrfToken;
    if (token) headers.set('X-CSRF-Token', token);
  }
  const response = await fetch(`${API_BASE}/${path}`, {
    ...init,
    method,
    headers,
    credentials: 'same-origin',
  });
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const retry = response.headers.get('Retry-After');
    throw new ApiError(response.status, errorCode(body), retry ? Number(retry) : null);
  }
  return body as T;
}

export const json = (value: unknown): string => JSON.stringify(value);

/** Plain-language text for API error codes shown to the user. */
export function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Could not reach ReelHaven. Is it running?';
  switch (error.code) {
    case 'invalid_credentials':
      return 'Wrong username or password.';
    case 'too_many_attempts':
      return `Too many failed attempts. Try again in ${error.retryAfter ?? 'a few'} seconds.`;
    case 'setup_already_done':
      return 'An admin account already exists. Reload the page to log in.';
    case 'wrong_current_password':
      return 'Your current password is not correct.';
    case 'csrf_failed':
      return 'Your page is out of date. Reload and try again.';
    case 'not_authenticated':
      return 'Please log in again.';
    case 'path_not_allowed':
      return 'That folder is outside the media folder or not allowed.';
    case 'not_a_folder':
      return 'Please choose a folder, not a file.';
    case 'choose_a_subfolder':
      return 'Choose a folder inside the media folder, not the media folder itself.';
    case 'path_overlaps_library':
      return 'That folder is already part of another library (or contains one).';
    case 'name_taken':
      return 'Another library already uses that name.';
    case 'media_root_missing':
      return 'The media folder (/media) is not mounted. Check the container settings.';
    case 'folder_unreadable':
      return "ReelHaven doesn't have permission to read that folder.";
    case 'plan_changed':
      return 'The library changed since the dry run. Run it again and check the new numbers.';
    case 'nothing_to_do':
      return 'There is nothing to change in this file.';
    case 'already_queued':
      return 'This file is already waiting to be processed.';
    case 'unsupported_container':
      return "This file type can't be remuxed yet (only MKV, MP4, M4V and MOV).";
    case 'file_not_readable':
      return "This file couldn't be read, so it can't be processed.";
    case 'restore_failed':
      return "The file couldn't be restored. It may have been moved or deleted outside ReelHaven.";
    case 'test_run_required':
      return 'Re-encoding a whole library needs a test run with its current profile first (Test run tab). You can still re-encode single files.';
    case 'validation_error':
      return 'Some of the values are not valid.';
    default:
      return `Something went wrong (${error.code}).`;
  }
}
