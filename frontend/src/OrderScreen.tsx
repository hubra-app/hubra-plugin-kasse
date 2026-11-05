import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ActionIcon, Anchor, Button, Group, NumberInput, Paper, Stack, Table, Text, Title } from '@mantine/core'
import { IconArrowLeft, IconDownload, IconLock, IconLockOpen, IconPencil, IconReceipt2, IconTrash } from '@tabler/icons-react'
import { ConfirmModal, ErrorBanner, Field, LoadingSpinner, MarkdownRenderer, Modal, PageHead, useT } from '@hubra/plugin-sdk'
import {
  QK,
  billOrder,
  closeOrder,
  deleteOrder,
  errorText,
  getOptions,
  getOrder,
  orderMine,
  saveFile,
  type Options,
  type Order,
} from './api'
import { CategoryField, chf, useAction } from './common'
import { OrderModal, OrderStatus } from './OrdersTab'

const key = (itemId: number, size: string | null) => `${itemId}|${size ?? ''}`

/** One collective order: what I order, and for the board the list and billing. */
export function OrderScreen() {
  const { t } = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const id = Number(useParams().id)
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const order = useQuery({ queryKey: QK.order(id), queryFn: () => getOrder(id), enabled: id > 0 })
  const [qty, setQty] = useState<Record<string, number>>({})
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [billing, setBilling] = useState(false)
  const { busy, run } = useAction()
  const manage = !!options.data?.can.orders
  const o = order.data

  useEffect(() => {
    if (!o) return
    const next: Record<string, number> = {}
    for (const line of o.mine ?? []) next[key(line.itemId, line.size)] = line.qty
    setQty(next)
  }, [o])

  const myTotal = useMemo(() => {
    if (!o) return 0
    return o.items.reduce((sum, item) => {
      const sizes = item.sizes.length ? item.sizes : [null]
      return sum + sizes.reduce((s, size) => s + (qty[key(item.id!, size)] ?? 0) * item.price, 0)
    }, 0)
  }, [o, qty])

  const refresh = () => qc.invalidateQueries({ queryKey: QK.all })

  if (order.isLoading || options.isLoading) return <LoadingSpinner />
  if (order.error || !o) return <ErrorBanner message={errorText(order.error)} onRetry={() => order.refetch()} />

  const save = () =>
    run(
      () =>
        orderMine(
          o.id,
          Object.entries(qty)
            .filter(([, n]) => n > 0)
            .map(([k, n]) => {
              const [itemId, size] = k.split('|')
              return { itemId: Number(itemId), size: size || null, qty: n }
            }),
        ),
      t('kasse.orders.savedMine'),
    ).then(refresh)

  return (
    <>
      <PageHead
        title={o.title}
        desc={o.supplier ?? undefined}
        back={
          <Anchor component="button" size="sm" onClick={() => navigate('/app/kasse/orders')}>
            <Group gap={4}>
              <IconArrowLeft size={14} /> {t('kasse.tabs.orders')}
            </Group>
          </Anchor>
        }
        actions={
          manage ? (
            <Group gap="xs">
              {o.status !== 'billed' && (
                <>
                  <ActionIcon variant="default" size="lg" aria-label={t('kasse.edit')} onClick={() => setEditing(true)}>
                    <IconPencil size={16} />
                  </ActionIcon>
                  <ActionIcon variant="default" size="lg" aria-label={t('kasse.delete')} onClick={() => setDeleting(true)}>
                    <IconTrash size={16} />
                  </ActionIcon>
                </>
              )}
            </Group>
          ) : undefined
        }
      />
      <Stack gap="lg">
        <Group gap="sm">
          <OrderStatus order={o} />
        </Group>
        {o.description && (
          <Paper withBorder p="md" radius="md">
            <MarkdownRenderer content={o.description} />
          </Paper>
        )}

        <Paper withBorder p="md" radius="md">
          <Title order={4} mb="sm">
            {t('kasse.orders.myOrderTitle')}
          </Title>
          <Stack gap="md">
            {o.items.map((item) => {
              const sizes = item.sizes.length ? item.sizes : [null]
              return (
                <div key={item.id}>
                  <Group justify="space-between" mb={6}>
                    <Text fw={600}>{item.name}</Text>
                    <Text size="sm" c="dimmed">
                      {chf(item.price)}
                    </Text>
                  </Group>
                  <Group gap="xs" wrap="wrap">
                    {sizes.map((size) => (
                      <NumberInput
                        key={size ?? '-'}
                        label={size ?? undefined}
                        aria-label={size ? `${item.name} ${size}` : item.name}
                        value={qty[key(item.id!, size)] ?? 0}
                        onChange={(n) => setQty((old) => ({ ...old, [key(item.id!, size)]: Number(n) || 0 }))}
                        min={0}
                        max={99}
                        disabled={!o.open}
                        w={size ? 78 : 110}
                      />
                    ))}
                  </Group>
                </div>
              )
            })}
          </Stack>
          <Group justify="space-between" mt="md" wrap="wrap">
            <Text fw={700}>{t('kasse.orders.myTotal', { amount: chf(myTotal) })}</Text>
            {o.open ? (
              <Button onClick={save} loading={busy}>
                {t('kasse.orders.saveMine')}
              </Button>
            ) : (
              <Text size="sm" c="dimmed">
                {o.status === 'billed' ? t('kasse.orders.onInvoice') : t('kasse.orders.noChanges')}
              </Text>
            )}
          </Group>
        </Paper>

        {manage && <OrderAdmin order={o} options={options.data} onBill={() => setBilling(true)} onChange={refresh} />}
      </Stack>

      {editing && <OrderModal order={o} onClose={() => setEditing(false)} onDone={refresh} />}
      {billing && <BillModal order={o} options={options.data} onClose={() => setBilling(false)} onDone={refresh} />}
      <ConfirmModal
        open={deleting}
        title={t('kasse.orders.deleteTitle')}
        body={t('kasse.orders.deleteBody', { title: o.title })}
        confirmLabel={t('kasse.delete')}
        onClose={() => setDeleting(false)}
        onConfirm={async () => {
          if (await run(() => deleteOrder(o.id))) {
            refresh()
            navigate('/app/kasse/orders')
          }
          setDeleting(false)
        }}
      />
    </>
  )
}

function OrderAdmin({ order, onBill, onChange }: { order: Order; options: Options | undefined; onBill: () => void; onChange: () => void }) {
  const { t } = useT()
  const { busy, run } = useAction()
  const safe = order.title.replace(/[^\p{L}\p{N}]+/gu, '-').slice(0, 60) || 'order'

  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" mb="sm" wrap="wrap">
        <div>
          <Title order={4}>{t('kasse.orders.forSupplier')}</Title>
          <Text size="sm" c="dimmed">
            {t('kasse.orders.statsTotal', { people: order.people, pieces: order.pieces, amount: chf(order.total) })}
          </Text>
        </div>
        <Group gap="xs">
          <Button variant="default" leftSection={<IconDownload size={16} />} onClick={() => run(() => saveFile(`/orders/${order.id}/list.csv`, `${safe}.csv`))}>
            CSV
          </Button>
          {order.status === 'open' && (
            <Button variant="default" leftSection={<IconLock size={16} />} loading={busy} onClick={() => run(() => closeOrder(order.id), t('kasse.orders.closedToast')).then(onChange)}>
              {t('kasse.orders.close')}
            </Button>
          )}
          {order.status === 'closed' && (
            <>
              <Button variant="default" leftSection={<IconLockOpen size={16} />} loading={busy} onClick={() => run(() => closeOrder(order.id, true)).then(onChange)}>
                {t('kasse.orders.reopen')}
              </Button>
              <Button leftSection={<IconReceipt2 size={16} />} disabled={!order.people} onClick={onBill}>
                {t('kasse.orders.bill')}
              </Button>
            </>
          )}
        </Group>
      </Group>
      {!order.summary?.length ? (
        <Text size="sm" c="dimmed">
          {t('kasse.orders.nobody')}
        </Text>
      ) : (
        <Stack gap="md">
          <Table verticalSpacing={6}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('kasse.orders.item')}</Table.Th>
                <Table.Th>{t('kasse.orders.size')}</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>{t('kasse.orders.qty')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {order.summary.map((row) => (
                <Table.Tr key={`${row.itemId}-${row.size}`}>
                  <Table.Td>{row.itemName}</Table.Td>
                  <Table.Td>{row.size ?? '–'}</Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>{row.qty}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          <Table.ScrollContainer minWidth={480}>
            <Table verticalSpacing={6}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('kasse.orders.member')}</Table.Th>
                  <Table.Th>{t('kasse.orders.item')}</Table.Th>
                  <Table.Th>{t('kasse.orders.size')}</Table.Th>
                  <Table.Th style={{ textAlign: 'right' }}>{t('kasse.orders.qty')}</Table.Th>
                  <Table.Th style={{ textAlign: 'right' }}>{t('kasse.total')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {(order.lines ?? []).map((line) => (
                  <Table.Tr key={line.id}>
                    <Table.Td>{line.memberName}</Table.Td>
                    <Table.Td>{line.itemName}</Table.Td>
                    <Table.Td>{line.size ?? '–'}</Table.Td>
                    <Table.Td style={{ textAlign: 'right' }}>{line.qty}</Table.Td>
                    <Table.Td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>{chf(line.total)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Stack>
      )}
    </Paper>
  )
}

function BillModal({ order, options, onClose, onDone }: { order: Order; options: Options | undefined; onClose: () => void; onDone: () => void }) {
  const { t } = useT()
  const { busy, run } = useAction()
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [dueDays, setDueDays] = useState<number | string>(30)
  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (await run(() => billOrder(order.id, { categoryId, dueDays: Number(dueDays) || 30 }), t('kasse.orders.billedToast', { count: order.people }))) {
      onDone()
      onClose()
    }
  }
  return (
    <Modal
      open
      onClose={onClose}
      onSubmit={submit}
      title={t('kasse.orders.bill')}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('kasse.cancel')}
          </Button>
          <Button type="submit" loading={busy}>
            {t('kasse.orders.billButton', { count: order.people })}
          </Button>
        </>
      }
    >
      <Text size="sm">{t('kasse.orders.billBody', { count: order.people, amount: chf(order.total) })}</Text>
      <Group grow align="flex-start">
        <CategoryField value={categoryId} onChange={setCategoryId} options={options} />
        <Field label={t('kasse.dueDays')}>
          <NumberInput value={dueDays} onChange={setDueDays} min={0} max={365} />
        </Field>
      </Group>
    </Modal>
  )
}
