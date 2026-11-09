import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ActionIcon, Anchor, Badge, Button, Group, NumberInput, Paper, SimpleGrid, Stack, Switch, Table, Text, TextInput, Title, UnstyledButton } from '@mantine/core'
import { IconArrowBackUp, IconBeer, IconPencil, IconPlus, IconQrcode, IconReceipt2, IconTrash } from '@tabler/icons-react'
import { ConfirmModal, EmptyState, ErrorBanner, Field, LoadingSpinner, Modal, useT } from '@hubra/plugin-sdk'
import {
  QK,
  addTick,
  deleteProduct,
  errorText,
  formatDay,
  getOptions,
  getTab,
  listProducts,
  openFile,
  saveProduct,
  settleTab,
  tabMembers,
  undoTick,
  type Options,
  type Product,
} from './api'
import { CategoryField, chf, useAction } from './common'

/** Opens the printable QR sheet; each code points at the Kasse page's tab. */
function useQrSheet() {
  const { i18n } = useT()
  const { run } = useAction()
  return () => {
    const appRoot = window.location.origin + window.location.pathname.split('/app/')[0]
    const link = `${appRoot}/app/kasse/tab?tick=`
    const lang = i18n.language?.startsWith('en') ? 'en' : 'de'
    return run(() => openFile(`/products/qr.pdf?inline=1&lang=${lang}&link=${encodeURIComponent(link)}`))
  }
}

/**
 * The tab (Strichliste) for every member: tick and see what's open. The
 * treasurer manages products and settles it in Finanzen (TabSettleFinanceTab).
 */
export function TabTab({ options }: { options: Options | undefined }) {
  const { t } = useT()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const products = useQuery({ queryKey: QK.products, queryFn: listProducts })
  const tab = useQuery({ queryKey: QK.tab, queryFn: getTab })
  const { busy, run } = useAction()
  const manage = !!options?.can.tab
  const active = (products.data ?? []).filter((p) => p.active)
  const scanned = active.find((p) => String(p.id) === params.get('tick'))
  const refresh = () => qc.invalidateQueries({ queryKey: QK.all })

  const tick = async (p: Product) => {
    const ok = await run(() => addTick(p.id), t('kasse.tab.ticked', { name: p.name }))
    if (ok) refresh()
    if (params.get('tick')) setParams({}, { replace: true })
  }

  if (products.error) return <ErrorBanner message={errorText(products.error)} onRetry={() => products.refetch()} />
  if (products.isLoading || tab.isLoading) return <LoadingSpinner />

  return (
    <Stack gap="lg">
      {scanned && (
        <Paper withBorder p="md" radius="md" style={{ borderColor: 'var(--mantine-color-violet-5)' }}>
          <Group justify="space-between" wrap="wrap">
            <div>
              <Text fw={600}>{t('kasse.tab.scanned', { name: scanned.name })}</Text>
              <Text size="sm" c="dimmed">
                {chf(scanned.price)}
              </Text>
            </div>
            <Group gap="xs">
              <Button variant="default" onClick={() => setParams({}, { replace: true })}>
                {t('kasse.cancel')}
              </Button>
              <Button size="md" loading={busy} onClick={() => tick(scanned)}>
                {t('kasse.tab.tickIt')}
              </Button>
            </Group>
          </Group>
        </Paper>
      )}

      <div>
        <Group justify="space-between" mb="xs" wrap="wrap">
          <Text size="sm" c="dimmed">
            {t('kasse.tab.hint')}
          </Text>
        </Group>
        {manage && (
          <Text size="sm" c="dimmed" mb="xs">
            {t('kasse.tab.inFinance')}{' '}
            <Anchor component="button" size="sm" onClick={() => navigate('/app/finance/tab-settle')}>
              {t('kasse.claims.openFinance')}
            </Anchor>
          </Text>
        )}
        {active.length === 0 ? (
          <EmptyState icon={<IconBeer size={28} />} title={t('kasse.tab.noProducts')} description={manage ? t('kasse.tab.noProductsHint') : undefined} />
        ) : (
          <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} spacing="sm">
            {active.map((p) => (
              <UnstyledButton key={p.id} onClick={() => tick(p)} disabled={busy} aria-label={t('kasse.tab.tickAria', { name: p.name })}>
                <Paper withBorder p="md" radius="md" style={{ textAlign: 'center' }}>
                  <Text fw={600}>{p.name}</Text>
                  <Text size="sm" c="dimmed">
                    {chf(p.price)}
                  </Text>
                </Paper>
              </UnstyledButton>
            ))}
          </SimpleGrid>
        )}
      </div>

      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" mb="xs">
          <Title order={4}>{t('kasse.tab.mine')}</Title>
          <Text fw={700}>{chf(tab.data?.total)}</Text>
        </Group>
        {!tab.data?.ticks.length ? (
          <Text size="sm" c="dimmed">
            {t('kasse.tab.empty')}
          </Text>
        ) : (
          <Stack gap={4}>
            {tab.data.ticks.map((tk) => (
              <Group key={tk.id} justify="space-between" wrap="nowrap">
                <Text size="sm">
                  {tk.qty > 1 ? `${tk.qty} × ` : ''}
                  {tk.name}
                  <Text span size="xs" c="dimmed">
                    {' '}
                    · {formatDay(tk.createdAt)}
                  </Text>
                </Text>
                <Group gap={6} wrap="nowrap">
                  <Text size="sm">{chf(tk.total)}</Text>
                  {tk.canUndo && (
                    <ActionIcon
                      variant="subtle"
                      color="gray"
                      size="sm"
                      aria-label={t('kasse.tab.undo')}
                      onClick={() => run(() => undoTick(tk.id)).then(refresh)}
                    >
                      <IconArrowBackUp size={14} />
                    </ActionIcon>
                  )}
                </Group>
              </Group>
            ))}
            <Text size="xs" c="dimmed" mt={4}>
              {t('kasse.tab.nextInvoice')}
            </Text>
          </Stack>
        )}
      </Paper>

    </Stack>
  )
}

/** Products, open amounts and settling, as a sub-tab of Finanzen › Rechnungen (/app/finance/tab-settle). */
export function TabSettleFinanceTab() {
  const { t } = useT()
  const qc = useQueryClient()
  const qrSheet = useQrSheet()
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const products = useQuery({ queryKey: QK.products, queryFn: listProducts })
  const refresh = () => qc.invalidateQueries({ queryKey: QK.all })

  const error = options.error ?? products.error
  if (error) return <ErrorBanner message={errorText(error)} onRetry={() => (options.error ? options.refetch() : products.refetch())} />
  if (options.isLoading || products.isLoading) return <LoadingSpinner />

  return (
    <Stack gap="lg">
      <Group justify="space-between" wrap="wrap">
        <Text size="sm" c="dimmed">
          {t('kasse.tab.settleHint')}
        </Text>
        {(products.data ?? []).some((p) => p.active) && (
          <Button variant="default" leftSection={<IconQrcode size={16} />} onClick={qrSheet}>
            {t('kasse.tab.qr')}
          </Button>
        )}
      </Group>
      <TabAdmin options={options.data} products={products.data ?? []} onChange={refresh} />
    </Stack>
  )
}

function TabAdmin({ options, products, onChange }: { options: Options | undefined; products: Product[]; onChange: () => void }) {
  const { t } = useT()
  const members = useQuery({ queryKey: QK.tabMembers, queryFn: tabMembers })
  const [form, setForm] = useState<Product | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Product | null>(null)
  const [settling, setSettling] = useState(false)
  const { run } = useAction()
  const open = members.data?.members ?? []
  const total = open.reduce((s, m) => s + m.total, 0)

  return (
    <>
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" mb="xs" wrap="wrap">
          <div>
            <Title order={4}>{t('kasse.tab.open')}</Title>
            <Text size="sm" c="dimmed">
              {members.data?.lastSettled ? t('kasse.tab.lastSettled', { date: formatDay(members.data.lastSettled) }) : t('kasse.tab.neverSettled')}
            </Text>
          </div>
          <Button leftSection={<IconReceipt2 size={16} />} disabled={!open.length} onClick={() => setSettling(true)}>
            {t('kasse.tab.settle')}
          </Button>
        </Group>
        {members.error ? (
          <ErrorBanner message={errorText(members.error)} onRetry={() => members.refetch()} />
        ) : !open.length ? (
          <Text size="sm" c="dimmed">
            {t('kasse.tab.nothingOpen')}
          </Text>
        ) : (
          <Table verticalSpacing={6}>
            <Table.Tbody>
              {open.map((m) => (
                <Table.Tr key={m.memberId}>
                  <Table.Td>{m.memberName}</Table.Td>
                  <Table.Td c="dimmed">{t('kasse.tab.count', { count: m.count })}</Table.Td>
                  <Table.Td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>{chf(m.total)}</Table.Td>
                </Table.Tr>
              ))}
              <Table.Tr>
                <Table.Td fw={700}>{t('kasse.total')}</Table.Td>
                <Table.Td />
                <Table.Td fw={700} style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  {chf(total)}
                </Table.Td>
              </Table.Tr>
            </Table.Tbody>
          </Table>
        )}
      </Paper>

      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" mb="xs">
          <Title order={4}>{t('kasse.tab.products')}</Title>
          <Button variant="light" leftSection={<IconPlus size={16} />} onClick={() => setForm('new')}>
            {t('kasse.tab.newProduct')}
          </Button>
        </Group>
        {!products.length ? (
          <Text size="sm" c="dimmed">
            {t('kasse.tab.noProductsHint')}
          </Text>
        ) : (
          <Table verticalSpacing={6}>
            <Table.Tbody>
              {products.map((p) => (
                <Table.Tr key={p.id} style={p.active ? undefined : { opacity: 0.55 }}>
                  <Table.Td>
                    {p.name}
                    {!p.active && (
                      <Badge ml={8} variant="light" color="gray" style={{ textTransform: 'none' }}>
                        {t('kasse.tab.hidden')}
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td style={{ whiteSpace: 'nowrap' }}>{chf(p.price)}</Table.Td>
                  <Table.Td>
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <ActionIcon variant="subtle" color="gray" aria-label={t('kasse.edit')} onClick={() => setForm(p)}>
                        <IconPencil size={16} />
                      </ActionIcon>
                      <ActionIcon variant="subtle" color="red" aria-label={t('kasse.delete')} onClick={() => setDeleting(p)}>
                        <IconTrash size={16} />
                      </ActionIcon>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>

      {form && <ProductModal product={form === 'new' ? null : form} onClose={() => setForm(null)} onDone={onChange} />}
      {settling && <SettleModal options={options} total={total} people={open.length} onClose={() => setSettling(false)} onDone={onChange} />}
      <ConfirmModal
        open={!!deleting}
        title={t('kasse.tab.deleteProduct')}
        body={t('kasse.tab.deleteProductBody', { name: deleting?.name ?? '' })}
        confirmLabel={t('kasse.delete')}
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          if (deleting) await run(() => deleteProduct(deleting.id))
          setDeleting(null)
          onChange()
        }}
      />
    </>
  )
}

function ProductModal({ product, onClose, onDone }: { product: Product | null; onClose: () => void; onDone: () => void }) {
  const { t } = useT()
  const { busy, run } = useAction()
  const [name, setName] = useState(product?.name ?? '')
  const [price, setPrice] = useState<number | string>(product?.price ?? '')
  const [active, setActive] = useState(product?.active ?? true)
  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (await run(() => saveProduct({ name, price, active }, product?.id), t('kasse.saved'))) {
      onDone()
      onClose()
    }
  }
  return (
    <Modal
      open
      onClose={onClose}
      onSubmit={submit}
      title={product ? t('kasse.tab.editProduct') : t('kasse.tab.newProduct')}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('kasse.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={!name.trim() || price === ''}>
            {t('kasse.save')}
          </Button>
        </>
      }
    >
      <Group grow align="flex-start">
        <Field label={t('kasse.name')}>
          <TextInput value={name} onChange={(e) => setName(e.currentTarget.value)} placeholder={t('kasse.tab.productExample')} data-autofocus />
        </Field>
        <Field label={t('kasse.price')}>
          <NumberInput value={price} onChange={setPrice} min={0} decimalScale={2} fixedDecimalScale step={0.5} leftSection="CHF" leftSectionWidth={44} />
        </Field>
      </Group>
      <Switch checked={active} onChange={(e) => setActive(e.currentTarget.checked)} label={t('kasse.tab.activeLabel')} />
    </Modal>
  )
}

function SettleModal({
  options,
  total,
  people,
  onClose,
  onDone,
}: {
  options: Options | undefined
  total: number
  people: number
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useT()
  const { busy, run } = useAction()
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [dueDays, setDueDays] = useState<number | string>(30)
  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (await run(() => settleTab({ categoryId, dueDays: Number(dueDays) || 30 }), t('kasse.tab.settled', { count: people }))) {
      onDone()
      onClose()
    }
  }
  return (
    <Modal
      open
      onClose={onClose}
      onSubmit={submit}
      title={t('kasse.tab.settle')}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('kasse.cancel')}
          </Button>
          <Button type="submit" loading={busy}>
            {t('kasse.tab.settleButton', { count: people })}
          </Button>
        </>
      }
    >
      <Text size="sm">{t('kasse.tab.settleBody', { count: people, amount: chf(total) })}</Text>
      <Group grow align="flex-start">
        <CategoryField value={categoryId} onChange={setCategoryId} options={options} />
        <Field label={t('kasse.dueDays')}>
          <NumberInput value={dueDays} onChange={setDueDays} min={0} max={365} />
        </Field>
      </Group>
    </Modal>
  )
}
