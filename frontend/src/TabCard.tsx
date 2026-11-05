import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Button, Group, Paper, Text } from '@mantine/core'
import { IconBeer } from '@tabler/icons-react'
import { useT } from '@hubra/plugin-sdk'
import { QK, getTab } from './api'
import { chf } from './common'

/** On the member's own page: what is open on their tab. */
export function TabCard() {
  const { t } = useT()
  const navigate = useNavigate()
  const tab = useQuery({ queryKey: QK.tab, queryFn: getTab })
  if (!tab.data?.total) return null
  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" wrap="wrap" gap="sm">
        <Group gap="sm" wrap="nowrap">
          <IconBeer size={22} />
          <div>
            <Text fw={600}>{t('kasse.tab.cardTitle', { amount: chf(tab.data.total) })}</Text>
            <Text size="sm" c="dimmed">
              {t('kasse.tab.nextInvoice')}
            </Text>
          </div>
        </Group>
        <Button variant="light" onClick={() => navigate('/app/kasse/tab')}>
          {t('kasse.tab.show')}
        </Button>
      </Group>
    </Paper>
  )
}
