import type { MenuGroup, SupplementCategory } from './types';

const API_BASE = '/api';

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
    headers: { 'Content-Type': 'application/json' },
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

export interface PreparePaymentResult {
  success: boolean;
  payment_token?: string;
  error?: string;
}

export async function preparePayment(
  payload: PreparePaymentPayload
): Promise<PreparePaymentResult> {
  const res = await fetch(`${API_BASE}/payment/prepare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return res.json();
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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return res.json();
}
