import type { MenuGroup, SupplementCategory } from './types';

const API_BASE = '/api';
const AUTH_TOKEN_KEY = 'auth_token';

export function getStoredToken(): string | null {
  try {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(AUTH_TOKEN_KEY, token);
    else localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // ignore
  }
}

function authHeaders(): Record<string, string> {
  const t = getStoredToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export interface AuthUser {
  id: number;
  phone: string;
  name?: string | null;
  saved_payment_method_id?: string | null;
}

export interface AuthResult {
  success: boolean;
  token?: string;
  user?: AuthUser;
  error?: string;
}

export async function register(phone: string, password: string, name?: string): Promise<AuthResult> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone: phone.trim(), password, name: (name || '').trim() || undefined }),
  });
  const data = await res.json();
  if (data.success && data.token) setStoredToken(data.token);
  return data;
}

export async function login(phone: string, password: string): Promise<AuthResult> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone: phone.trim(), password }),
  });
  const data = await res.json();
  if (data.success && data.token) setStoredToken(data.token);
  return data;
}

export async function getMe(): Promise<{ success: boolean; user?: AuthUser; error?: string }> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: authHeaders(),
  });
  return res.json();
}

export async function linkCard(): Promise<{ success: boolean; confirmation_url?: string; error?: string }> {
  const res = await fetch(`${API_BASE}/payment/link-card`, {
    method: 'POST',
    headers: authHeaders(),
  });
  return res.json();
}

export async function fetchMenu(): Promise<MenuGroup> {
  const res = await fetch(`${API_BASE}/menu`);
  const data = await res.json();
  if (!data.success) throw new Error(data.error || 'Ошибка загрузки меню');
  return data.data;
}

export async function fetchSupplements(): Promise<SupplementCategory[]> {
  const res = await fetch(`${API_BASE}/supplements`);
  const data = await res.json();
  if (!data.success) throw new Error(data.error || 'Ошибка загрузки добавок');
  return data.data;
}

export interface CreateOrderPayload {
  type: string;
  items: Array<{
    menuItemGuid: string;
    menuTypeGuid?: string;
    supplementList: Record<string, number>;
    priceWithDiscount: number;
    quantity: number;
  }>;
  client: { name: string; phone?: string; email?: string };
  paidValue: number;
  telegramUserId?: number;
  comment?: string;
}

export interface CreateOrderResult {
  success: boolean;
  order_id?: string;
  status?: string;
  total?: number;
  message?: string;
  error?: string;
}

export async function createOrder(payload: CreateOrderPayload): Promise<CreateOrderResult> {
  const res = await fetch(`${API_BASE}/order`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export interface PreparePaymentPayload {
  items: Array<{
    menuItemGuid: string;
    menuTypeGuid?: string;
    supplementList: Record<string, number>;
    priceWithDiscount: number;
    quantity: number;
  }>;
  client: { name: string; phone?: string; email?: string };
  comment?: string;
  telegramUserId?: number;
}

export interface CreateInAppPaymentResult {
  success: boolean;
  payment_token?: string;
  confirmation_url?: string;
  error?: string;
}

export async function createInAppPayment(
  payload: PreparePaymentPayload
): Promise<CreateInAppPaymentResult> {
  const res = await fetch(`${API_BASE}/payment/create-inapp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  });
  return res.json();
}
