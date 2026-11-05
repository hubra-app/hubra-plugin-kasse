import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ActionIcon, Badge, Button, Group, NumberInput, Paper, SimpleGrid, Stack, Text, TextInput, Textarea } from '@mantine/core'
import { IconPlus, IconShoppingBag, IconTrash } from '@tabler/icons-react'
import { EmptyState, ErrorBanner, Field, LoadingSpinner, Modal, useT } from '@hubra/plugin-sdk'
import { QK, errorText, formatDay, listOrders, saveOrder, type Order, type OrderItem, type Options } from './api'
import { chf, useAction } from './common'

export function OrderStatus({ order }: { order: Order }) {
  const { t } = useT()
  const left = Math.round((new Date(order.deadline + 'T23:59:59').getTime() - Date.now()) / 86_400_000)
  if (order.status === 'billed')
    return (
      <Badge variant="light" color="green" style={{ textTransform: 'none' }}>
        {t('kasse.orders.billed')}
      </Badge>
    )
  if (!order.open)
    return (
      <Badge variant="light" color="gray" style={{ textTransform: 'none' }}>
        {t('kasse.orders.closed')}
      </Badge>
    )
  return (
    <Badge variant="light" color={left <= 3 ? 'orange' : 'violet'} style={{ textTransform: 'none' }}>
      {t('kasse.orders.until', { date: formatDay(order.deadline) })}
    </Badge>
  )
}

export function OrdersTab({ options }: { options: Options | undefined }) {
  const { t } = useT()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const orders = useQuery({ queryKey: QK.orders, queryFn: listOrders })
  const [adding, setAdding] = useState(false)
  const manage = !!options?.can.orders

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap">
        <Text size="sm" c="dimmed">
          {t('kasse.orders.hint')}
        </Text>
        {manage && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
            {t('kasse.orders.new')}
          </Button>
        )}
      </Group>
      {orders.error ? (
        <ErrorBanner message={errorText(orders.error)} onRetry={() => orders.refetch()} />
      ) : orders.isLoading ? (
        <LoadingSpinner />
      ) : !orders.data?.length ? (
        <EmptyState icon={<IconShoppingBag size={28} />} title={t('kasse.orders.none')} description={manage ? t('kasse.orders.noneHint') : undefined} />
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          {orders.data.map((o) => (
            <Paper
              key={o.id}
              withBorder
              p="md"
              radius="md"
              style={{ cursor: 'pointer', opacity: o.status === 'billed' ? 0.7 : 1 }}
              onClick={() => navigate(`/app/kasse/orders/${o.id}`)}
            >
              <Group justify="space-between" align="flex-start" wrap="nowrap">
                <Text fw={600}>{o.title}</Text>
                <OrderStatus order={o} />
              </Group>
              <Text size="sm" c="dimmed" lineClamp={2}>
                {o.items.map((i) => i.name).join(', ')}
              </Text>
              <Group justify="space-between" mt="sm">
                <Text size="sm" c="dimmed">
                  {manage ? t('kasse.orders.stats', { people: o.people, pieces: o.pieces }) : ''}
                </Text>
                {o.myTotal > 0 ? (
                  <Badge variant="light" color="green" style={{ textTransform: 'none' }}>
                    {t('kasse.orders.myOrder', { amount: chf(o.myTotal) })}
                  </Badge>
                ) : (
                  o.open && (
                    <Text size="sm" c="violet" fw={600}>
                      {t('kasse.orders.orderNow')}
                    </Text>
                  )
                )}
              </Group>
            </Paper>
          ))}
        </SimpleGrid>
      )}
      {adding && (
        <OrderModal
          order={null}
          onClose={() => setAdding(false)}
          onDone={(o) => {
            qc.invalidateQueries({ queryKey: QK.all })
            navigate(`/app/kasse/orders/${o.id}`)
          }}
        />
      )}
    </Stack>
  )
}

type ItemDraft = { id?: number; name: string; price: number | string; sizes: string }

export function OrderModal({ order, onClose, onDone }: { order: Order | null; onClose: () => void; onDone: (o: Order) => void }) {
  const { t } = useT()
  const { busy, run } = useAction()
  const inTwoWeeks = new Date(Date.now() + 14 * 86_400_000).toISOString().slice(0, 10)
  const [v, setV] = useState({
    title: order?.title ?? '',
    deadline: order?.deadline ?? inTwoWeeks,
    supplier: order?.supplier ?? '',
    description: order?.description ?? '',
  })
  const [items, setItems] = useState<ItemDraft[]>(
    order?.items.map((i: OrderItem) => ({ id: i.id, name: i.name, price: i.price, sizes: i.sizes.join(', ') })) ?? [
      { name: '', price: '', sizes: '' },
    ],
  )
  const set = (key: keyof typeof v, value: string) => setV((old) => ({ ...old, [key]: value }))
  const setItem = (n: number, patch: Partial<ItemDraft>) => setItems((old) => old.map((it, i) => (i === n ? { ...it, ...patch } : it)))
  const ready = v.title.trim() && v.deadline && items.length && items.every((i) => i.name.trim() && i.price !== '')

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    let saved: Order | undefined
    const ok = await run(async () => {
      saved = await saveOrder({ ...v, items: items.map((i) => ({ ...i, sizes: i.sizes })) }, order?.id)
    }, t('kasse.saved'))
    if (ok && saved) {
      onDone(saved)
      onClose()
    }
  }

  return (
    <Modal
      open
      wide
      onClose={onClose}
      onSubmit={submit}
      title={order ? t('kasse.orders.edit') : t('kasse.orders.new')}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('kasse.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={!ready}>
            {t('kasse.save')}
          </Button>
        </>
      }
    >
      <Group grow align="flex-start">
        <Field label={t('kasse.orders.titleField')}>
          <TextInput value={v.title} onChange={(e) => set('title', e.currentTarget.value)} placeholder={t('kasse.orders.example')} data-autofocus />
        </Field>
        <Field label={t('kasse.orders.deadline')}>
          <TextInput type="date" value={v.deadline} onChange={(e) => set('deadline', e.currentTarget.value)} />
        </Field>
      </Group>
      <Field label={t('kasse.orders.supplier')}>
        <TextInput value={v.supplier} onChange={(e) => set('supplier', e.currentTarget.value)} />
      </Field>
      <Field label={t('kasse.orders.description')}>
        <Textarea value={v.description} onChange={(e) => set('description', e.currentTarget.value)} autosize minRows={2} />
      </Field>
      <Field label={t('kasse.orders.items')} hint={t('kasse.orders.itemsHint')}>
        <Stack gap="xs">
          {items.map((it, n) => (
            <Group key={n} gap="xs" align="flex-start" wrap="nowrap">
              <TextInput
                aria-label={t('kasse.name')}
                placeholder={t('kasse.orders.itemExample')}
                value={it.name}
                onChange={(e) => setItem(n, { name: e.currentTarget.value })}
                style={{ flex: 2 }}
              />
              <NumberInput
                aria-label={t('kasse.price')}
                value={it.price}
                onChange={(p) => setItem(n, { price: p })}
                min={0}
                decimalScale={2}
                leftSection="CHF"
                leftSectionWidth={44}
                style={{ flex: 1, minWidth: 110 }}
              />
              <TextInput
                aria-label={t('kasse.orders.sizes')}
                placeholder={t('kasse.orders.sizesExample')}
                value={it.sizes}
                onChange={(e) => setItem(n, { sizes: e.currentTarget.value })}
                style={{ flex: 2 }}
              />
              <ActionIcon
                variant="subtle"
                color="red"
                mt={6}
                aria-label={t('kasse.delete')}
                disabled={items.length === 1}
                onClick={() => setItems((old) => old.filter((_, i) => i !== n))}
              >
                <IconTrash size={16} />
              </ActionIcon>
            </Group>
          ))}
          <Button variant="subtle" leftSection={<IconPlus size={14} />} onClick={() => setItems((old) => [...old, { name: '', price: '', sizes: '' }])} style={{ alignSelf: 'flex-start' }}>
            {t('kasse.orders.addItem')}
          </Button>
        </Stack>
      </Field>
    </Modal>
  )
}
