import { useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ActionIcon, Anchor, Badge, Button, FileInput, Group, NumberInput, Paper, Select, Stack, Text, TextInput, Textarea } from '@mantine/core'
import { IconCheck, IconPaperclip, IconPlus, IconReceipt, IconShoppingBag, IconTrash, IconBeer, IconX, IconCash } from '@tabler/icons-react'
import {
  ConfirmModal,
  EmptyState,
  ErrorBanner,
  Field,
  LoadingSpinner,
  Modal,
  PageHead,
  Seg,
  Tabs,
  useT,
} from '@hubra/plugin-sdk'
import {
  QK,
  allClaims,
  decideClaim,
  deleteClaim,
  errorText,
  formatDay,
  getOptions,
  myClaims,
  openFile,
  payClaim,
  submitClaim,
  todayIso,
  type Claim,
  type ClaimStatus,
  type Options,
} from './api'
import { CategoryField, chf, useAction } from './common'
import { TabTab } from './TabTab'
import { OrdersTab } from './OrdersTab'

type TabId = 'claims' | 'tab' | 'orders'

/** Kasse: expense claims, the tab and collective orders. */
export function KasseScreen() {
  const { t } = useT()
  const navigate = useNavigate()
  const location = useLocation()
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  const part = location.pathname.split('/app/kasse')[1]?.replace(/^\//, '').split('/')[0] ?? ''
  const tabs = [
    { id: 'claims', label: t('kasse.tabs.claims'), icon: <IconReceipt size={16} /> },
    { id: 'tab', label: t('kasse.tabs.tab'), icon: <IconBeer size={16} /> },
    { id: 'orders', label: t('kasse.tabs.orders'), icon: <IconShoppingBag size={16} /> },
  ]
  const active = (tabs.find((tb) => tb.id === part)?.id ?? 'claims') as TabId

  if (options.isLoading) return <LoadingSpinner />
  if (options.error) return <ErrorBanner message={errorText(options.error)} onRetry={() => options.refetch()} />

  return (
    <>
      <PageHead title={t('kasse.title')} desc={t('kasse.desc')} />
      <Tabs
        tabs={tabs}
        activeTab={active}
        onTabChange={(id) => navigate(id === 'claims' ? '/app/kasse' : `/app/kasse/${id}`)}
      />
      {active === 'claims' && <ClaimsTab options={options.data} view="mine" />}
      {active === 'tab' && <TabTab options={options.data} />}
      {active === 'orders' && <OrdersTab options={options.data} />}
    </>
  )
}

// ── Expense claims ───────────────────────────────────────────────────────────

const STATUS_COLOR: Record<ClaimStatus, string> = {
  submitted: 'blue',
  approved: 'violet',
  rejected: 'red',
  paid: 'green',
}

export function StatusBadge({ status }: { status: ClaimStatus }) {
  const { t } = useT()
  return (
    <Badge variant="light" color={STATUS_COLOR[status]} style={{ textTransform: 'none', flexShrink: 0 }}>
      {t(`kasse.claims.status.${status}`)}
    </Badge>
  )
}

/**
 * The expense claims. On the Kasse page (`mine`) a member hands in and follows
 * their own; in Finanzen (`club`) the treasurer approves and pays everyone's.
 */
function ClaimsTab({ options, view }: { options: Options | undefined; view: 'mine' | 'club' }) {
  const { t } = useT()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const treasurer = view === 'club' && !!options?.can.claimsRead
  const [show, setShow] = useState<'mine' | 'open' | 'all'>(treasurer ? 'open' : 'mine')
  const claims = useQuery({
    queryKey: QK.claims(show),
    queryFn: () => (show === 'mine' ? myClaims() : allClaims(show)),
  })
  const [adding, setAdding] = useState(false)
  const [rejecting, setRejecting] = useState<Claim | null>(null)
  const [paying, setPaying] = useState<Claim | null>(null)
  const [deleting, setDeleting] = useState<Claim | null>(null)
  const { run } = useAction()
  const refresh = () => qc.invalidateQueries({ queryKey: QK.all })
  // Approving and paying happen in Finanzen, with everyone's claims in view.
  const canDecide = view === 'club' && !!options?.can.claims
  const total = (claims.data ?? []).filter((c) => c.status !== 'rejected' && c.status !== 'paid').reduce((s, c) => s + c.amount, 0)

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap">
        {treasurer ? (
          <Seg
            options={[
              { value: 'open', label: t('kasse.claims.open') },
              { value: 'all', label: t('kasse.claims.all') },
            ]}
            value={show}
            onChange={(v) => setShow(v as typeof show)}
          />
        ) : (
          <Text size="sm" c="dimmed">
            {t('kasse.claims.hint')}
          </Text>
        )}
        {view === 'mine' && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
            {t('kasse.claims.new')}
          </Button>
        )}
      </Group>
      {view === 'mine' && options?.can.claimsRead && (
        <Text size="sm" c="dimmed">
          {t('kasse.claims.inFinance')}{' '}
          <Anchor component="button" size="sm" onClick={() => navigate('/app/finance/expenses')}>
            {t('kasse.claims.openFinance')}
          </Anchor>
        </Text>
      )}
      {show === 'open' && total > 0 && (
        <Text size="sm" c="dimmed">
          {t('kasse.claims.openTotal', { amount: chf(total) })}
        </Text>
      )}
      {claims.error ? (
        <ErrorBanner message={errorText(claims.error)} onRetry={() => claims.refetch()} />
      ) : claims.isLoading ? (
        <LoadingSpinner />
      ) : !claims.data?.length ? (
        <EmptyState
          icon={<IconReceipt size={28} />}
          title={show === 'open' ? t('kasse.claims.noneOpen') : t('kasse.claims.none')}
          description={t('kasse.claims.noneHint')}
        />
      ) : (
        <Stack gap="xs">
          {claims.data.map((c) => (
            <Paper key={c.id} withBorder p="sm" radius="md">
              <Group justify="space-between" align="flex-start" wrap="nowrap" gap="sm">
                <div style={{ minWidth: 0, flex: 1 }}>
                  <Group gap={8} wrap="wrap">
                    <Text fw={600}>{c.title}</Text>
                    <StatusBadge status={c.status} />
                  </Group>
                  <Text size="sm" c="dimmed">
                    {[show !== 'mine' ? c.memberName : null, formatDay(c.spentOn), c.iban ? `IBAN ${c.iban.replace(/(.{4})/g, '$1 ').trim()}` : null]
                      .filter(Boolean)
                      .join(' · ')}
                  </Text>
                  {c.notes && <Text size="sm">{c.notes}</Text>}
                  {c.decisionNote && (
                    <Text size="sm" c={c.status === 'rejected' ? 'red' : 'dimmed'}>
                      {c.decidedByName ? `${c.decidedByName}: ` : ''}
                      {c.decisionNote}
                    </Text>
                  )}
                  {c.status === 'paid' && c.paidAt && (
                    <Text size="sm" c="dimmed">
                      {t('kasse.claims.paidOn', { date: formatDay(c.paidAt) })}
                    </Text>
                  )}
                </div>
                <Stack gap={6} align="flex-end" style={{ flexShrink: 0 }}>
                  <Text fw={700} style={{ whiteSpace: 'nowrap' }}>
                    {chf(c.amount)}
                  </Text>
                  <Group gap={4} wrap="nowrap">
                    {c.hasReceipt && (
                      <ActionIcon
                        variant="subtle"
                        color="gray"
                        aria-label={t('kasse.claims.receipt')}
                        onClick={() => run(() => openFile(`/claims/${c.id}/receipt?inline=1`))}
                      >
                        <IconPaperclip size={16} />
                      </ActionIcon>
                    )}
                    {canDecide && c.status === 'submitted' && c.memberId !== options?.memberId && (
                      <>
                        <Button
                          size="xs"
                          variant="light"
                          color="green"
                          leftSection={<IconCheck size={14} />}
                          onClick={() => run(() => decideClaim(c.id, true), t('kasse.claims.approved')).then(refresh)}
                        >
                          {t('kasse.claims.approve')}
                        </Button>
                        <Button size="xs" variant="light" color="red" leftSection={<IconX size={14} />} onClick={() => setRejecting(c)}>
                          {t('kasse.claims.reject')}
                        </Button>
                      </>
                    )}
                    {canDecide && c.status === 'approved' && c.memberId !== options?.memberId && (
                      <Button size="xs" leftSection={<IconCash size={14} />} onClick={() => setPaying(c)}>
                        {t('kasse.claims.pay')}
                      </Button>
                    )}
                    {canDecide && c.memberId === options?.memberId && (c.status === 'submitted' || c.status === 'approved') && (
                      <Text size="xs" c="dimmed">
                        {t('kasse.claims.ownByOther')}
                      </Text>
                    )}
                    {c.status === 'submitted' && c.memberId === options?.memberId && (
                      <ActionIcon variant="subtle" color="red" aria-label={t('kasse.delete')} onClick={() => setDeleting(c)}>
                        <IconTrash size={16} />
                      </ActionIcon>
                    )}
                  </Group>
                </Stack>
              </Group>
            </Paper>
          ))}
        </Stack>
      )}
      {adding && <ClaimModal onClose={() => setAdding(false)} onDone={refresh} />}
      {rejecting && <RejectModal claim={rejecting} onClose={() => setRejecting(null)} onDone={refresh} />}
      {paying && <PayModal claim={paying} options={options} onClose={() => setPaying(null)} onDone={refresh} />}
      <ConfirmModal
        open={!!deleting}
        title={t('kasse.claims.deleteTitle')}
        body={deleting ? `${deleting.title} · ${chf(deleting.amount)}` : ''}
        confirmLabel={t('kasse.delete')}
        onClose={() => setDeleting(null)}
        onConfirm={async () => {
          if (deleting) await run(() => deleteClaim(deleting.id))
          setDeleting(null)
          refresh()
        }}
      />
    </Stack>
  )
}

function ClaimModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { t } = useT()
  const { busy, run } = useAction()
  const [v, setV] = useState({ title: '', amount: '', spentOn: todayIso(), iban: '', notes: '' })
  const [receipt, setReceipt] = useState<File | null>(null)
  const set = (key: keyof typeof v, value: string) => setV((old) => ({ ...old, [key]: value }))

  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (await run(() => submitClaim(v, receipt), t('kasse.claims.submitted'))) {
      onDone()
      onClose()
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      onSubmit={submit}
      title={t('kasse.claims.new')}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('kasse.cancel')}
          </Button>
          <Button type="submit" loading={busy} disabled={!v.title.trim() || !v.amount}>
            {t('kasse.claims.submit')}
          </Button>
        </>
      }
    >
      <Field label={t('kasse.claims.what')}>
        <TextInput value={v.title} onChange={(e) => set('title', e.currentTarget.value)} placeholder={t('kasse.claims.example')} data-autofocus />
      </Field>
      <Group grow align="flex-start">
        <Field label={t('kasse.amount')}>
          <NumberInput
            value={v.amount}
            onChange={(x) => set('amount', x === '' ? '' : String(x))}
            min={0}
            decimalScale={2}
            thousandSeparator="’"
            prefix="CHF "
            hideControls
          />
        </Field>
        <Field label={t('kasse.claims.spentOn')}>
          <TextInput type="date" value={v.spentOn} max={todayIso()} onChange={(e) => set('spentOn', e.currentTarget.value)} />
        </Field>
      </Group>
      <Field label={t('kasse.claims.receipt')} hint={t('kasse.claims.receiptHint')}>
        <FileInput
          aria-label={t('kasse.claims.receipt')}
          value={receipt}
          onChange={setReceipt}
          accept="image/*,application/pdf"
          placeholder={t('kasse.claims.receiptPick')}
          leftSection={<IconPaperclip size={16} />}
          clearable
        />
      </Field>
      <Field label={t('kasse.claims.iban')} hint={t('kasse.claims.ibanHint')}>
        <TextInput value={v.iban} onChange={(e) => set('iban', e.currentTarget.value)} placeholder="CH93 0076 2011 6238 5295 7" />
      </Field>
      <Field label={t('kasse.notes')}>
        <Textarea value={v.notes} onChange={(e) => set('notes', e.currentTarget.value)} autosize minRows={2} />
      </Field>
    </Modal>
  )
}

function RejectModal({ claim, onClose, onDone }: { claim: Claim; onClose: () => void; onDone: () => void }) {
  const { t } = useT()
  const { busy, run } = useAction()
  const [note, setNote] = useState('')
  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (await run(() => decideClaim(claim.id, false, note), t('kasse.claims.rejected'))) {
      onDone()
      onClose()
    }
  }
  return (
    <Modal
      open
      onClose={onClose}
      onSubmit={submit}
      title={t('kasse.claims.rejectTitle', { title: claim.title })}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('kasse.cancel')}
          </Button>
          <Button type="submit" color="red" loading={busy} disabled={!note.trim()}>
            {t('kasse.claims.reject')}
          </Button>
        </>
      }
    >
      <Field label={t('kasse.claims.why')}>
        <Textarea value={note} onChange={(e) => setNote(e.currentTarget.value)} autosize minRows={2} data-autofocus />
      </Field>
    </Modal>
  )
}

function PayModal({
  claim,
  options,
  onClose,
  onDone,
}: {
  claim: Claim
  options: Options | undefined
  onClose: () => void
  onDone: () => void
}) {
  const { t } = useT()
  const { busy, run } = useAction()
  const [categoryId, setCategoryId] = useState<number | null>(null)
  const [method, setMethod] = useState(claim.iban ? 'IBAN' : 'Cash')
  const [paidOn, setPaidOn] = useState(todayIso())
  const submit = async (e?: FormEvent) => {
    e?.preventDefault()
    if (await run(() => payClaim(claim.id, { categoryId, method, paidOn }), t('kasse.claims.paid'))) {
      onDone()
      onClose()
    }
  }
  return (
    <Modal
      open
      onClose={onClose}
      onSubmit={submit}
      title={t('kasse.claims.payTitle', { amount: chf(claim.amount), name: claim.memberName ?? '' })}
      footer={
        <>
          <Button variant="default" onClick={onClose}>
            {t('kasse.cancel')}
          </Button>
          <Button type="submit" loading={busy}>
            {t('kasse.claims.payBook')}
          </Button>
        </>
      }
    >
      <Text size="sm" c="dimmed">
        {claim.iban ? t('kasse.claims.payTo', { iban: claim.iban }) : t('kasse.claims.payCash')}
      </Text>
      <Group grow align="flex-start">
        <Field label={t('kasse.claims.method')}>
          <Select
            data={['IBAN', 'Cash', 'Twint'].map((m) => ({ value: m, label: t(`kasse.method.${m}`) }))}
            value={method}
            onChange={(m) => m && setMethod(m)}
            allowDeselect={false}
          />
        </Field>
        <Field label={t('kasse.claims.paidOnField')}>
          <TextInput type="date" value={paidOn} onChange={(e) => setPaidOn(e.currentTarget.value)} />
        </Field>
      </Group>
      <CategoryField value={categoryId} onChange={setCategoryId} options={options} hint={t('kasse.claims.categoryHint')} />
    </Modal>
  )
}

/** Everyone's expense claims, as a sub-tab of Finanzen › Buchungen (/app/finance/expenses). */
export function ClaimsFinanceTab() {
  const options = useQuery({ queryKey: QK.options, queryFn: getOptions })
  if (options.isLoading) return <LoadingSpinner />
  if (options.error) return <ErrorBanner message={errorText(options.error)} onRetry={() => options.refetch()} />
  return <ClaimsTab options={options.data} view="club" />
}
