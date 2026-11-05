import { apiFetch, apiFetchRaw } from '@hubra/plugin-sdk'

export interface Options {
  can: { claimsRead: boolean; claims: boolean; tab: boolean; orders: boolean }
  memberId: number
  categories?: { id: number; name: string }[]
}

export type ClaimStatus = 'submitted' | 'approved' | 'rejected' | 'paid'

export interface Claim {
  id: number
  memberId: number | null
  memberName: string | null
  title: string
  amount: number
  spentOn: string
  notes: string | null
  iban: string | null
  hasReceipt: boolean
  receiptName: string | null
  receiptType: string | null
  status: ClaimStatus
  decidedByName: string | null
  decidedAt: string | null
  decisionNote: string | null
  transactionId: number | null
  paidAt: string | null
  createdAt: string
}

export interface Product {
  id: number
  name: string
  price: number
  position: number
  active: boolean
}

export interface Tick {
  id: number
  productId: number | null
  name: string
  price: number
  qty: number
  total: number
  createdAt: string
  canUndo: boolean
}

export interface Tab {
  memberId: number
  total: number
  ticks: Tick[]
}

export interface TabMember {
  memberId: number
  memberName: string | null
  total: number
  count: number
}

export interface OrderItem {
  id?: number
  name: string
  price: number
  sizes: string[]
}

export interface OrderLine {
  id: number
  itemId: number
  itemName: string
  memberId: number | null
  memberName: string | null
  size: string | null
  qty: number
  price: number
  total: number
  invoiceId: number | null
}

export interface Order {
  id: number
  title: string
  description: string | null
  deadline: string
  supplier: string | null
  status: 'open' | 'closed' | 'billed'
  open: boolean
  billedAt: string | null
  items: OrderItem[]
  people: number
  pieces: number
  total: number
  myTotal: number
  mine?: OrderLine[]
  lines?: OrderLine[]
  summary?: { itemId: number; itemName: string; size: string | null; qty: number }[]
}

const BASE = '/app/kasse'
const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const QK = {
  all: ['kasse'] as const,
  options: ['kasse', 'options'] as const,
  claims: (who: string) => ['kasse', 'claims', who] as const,
  products: ['kasse', 'products'] as const,
  tab: ['kasse', 'tab'] as const,
  tabMembers: ['kasse', 'tab-members'] as const,
  orders: ['kasse', 'orders'] as const,
  order: (id: number) => ['kasse', 'order', id] as const,
}

export const getOptions = () => apiFetch<Options>(`${BASE}/options`)

export const myClaims = () => apiFetch<Claim[]>(`${BASE}/claims`)
export const allClaims = (show: 'open' | 'all') => apiFetch<Claim[]>(`${BASE}/claims/all?show=${show}`)
export async function submitClaim(fields: Record<string, string>, receipt: File | null) {
  const form = new FormData()
  for (const [k, v] of Object.entries(fields)) if (v) form.append(k, v)
  if (receipt) form.append('receipt', receipt)
  const res = await apiFetchRaw(`${BASE}/claims`, { method: 'POST', body: form })
  return (await res.json()) as Claim
}
export const deleteClaim = (id: number) => apiFetch<void>(`${BASE}/claims/${id}`, { method: 'DELETE' })
export const decideClaim = (id: number, approve: boolean, note?: string) =>
  apiFetch<Claim>(`${BASE}/claims/${id}/decide`, json('POST', { approve, note }))
export const payClaim = (id: number, body: { categoryId?: number | null; method?: string; paidOn?: string }) =>
  apiFetch<Claim>(`${BASE}/claims/${id}/pay`, json('POST', body))

export const listProducts = () => apiFetch<Product[]>(`${BASE}/products`)
export const saveProduct = (body: Record<string, unknown>, id?: number) =>
  apiFetch<Product>(id ? `${BASE}/products/${id}` : `${BASE}/products`, json(id ? 'PATCH' : 'POST', body))
export const deleteProduct = (id: number) => apiFetch<void>(`${BASE}/products/${id}`, { method: 'DELETE' })

export const getTab = () => apiFetch<Tab>(`${BASE}/tab`)
export const addTick = (productId: number, qty = 1, memberId?: number) =>
  apiFetch<Tab>(`${BASE}/tab`, json('POST', { productId, qty, memberId }))
export const undoTick = (id: number) => apiFetch<Tab>(`${BASE}/tab/${id}`, { method: 'DELETE' })
export const tabMembers = () => apiFetch<{ members: TabMember[]; lastSettled: string | null }>(`${BASE}/tab/members`)
export const settleTab = (body: { categoryId?: number | null; dueDays?: number }) =>
  apiFetch<{ invoices: number; total: number }>(`${BASE}/tab/settle`, json('POST', body))

export const listOrders = () => apiFetch<Order[]>(`${BASE}/orders`)
export const getOrder = (id: number) => apiFetch<Order>(`${BASE}/orders/${id}`)
export const saveOrder = (body: Record<string, unknown>, id?: number) =>
  apiFetch<Order>(id ? `${BASE}/orders/${id}` : `${BASE}/orders`, json(id ? 'PATCH' : 'POST', body))
export const deleteOrder = (id: number) => apiFetch<void>(`${BASE}/orders/${id}`, { method: 'DELETE' })
export const orderMine = (id: number, lines: { itemId: number; size: string | null; qty: number }[]) =>
  apiFetch<Order>(`${BASE}/orders/${id}/mine`, json('PUT', { lines }))
export const closeOrder = (id: number, reopen = false) =>
  apiFetch<Order>(`${BASE}/orders/${id}/close`, json('POST', { reopen }))
export const billOrder = (id: number, body: { categoryId?: number | null; dueDays?: number }) =>
  apiFetch<{ invoices: number; order: Order }>(`${BASE}/orders/${id}/bill`, json('POST', body))

/** Opens a file from the API in a new tab (a receipt, the QR sheet). */
export async function openFile(path: string) {
  // Open the tab first: a browser blocks window.open after an await.
  const tab = window.open('', '_blank')
  const res = await apiFetchRaw(`${BASE}${path}`)
  const url = URL.createObjectURL(await res.blob())
  if (tab) tab.location.href = url
  else window.location.assign(url)
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** Saves a file from the API (the supplier list). */
export async function saveFile(path: string, name: string) {
  const res = await apiFetchRaw(`${BASE}${path}`)
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export function errorText(err: unknown) {
  return err instanceof Error ? err.message : String(err)
}

/** "2026-03-31" as 31.03.2026. */
export function formatDay(iso: string | null | undefined) {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${d}.${m}.${y}`
}

export function todayIso() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
