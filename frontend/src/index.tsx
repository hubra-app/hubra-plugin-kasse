import { registerPlugin } from '@hubra/plugin-sdk'
import { IconReceipt } from '@tabler/icons-react'
import { ClaimsFinanceTab, KasseScreen } from './KasseScreen'
import { OrderScreen } from './OrderScreen'
import { TabCard } from './TabCard'
import { TabSettleFinanceTab } from './TabTab'
import translations from './translations.json'

registerPlugin({
  id: 'kasse',
  // Every member hands in claims, ticks and orders; the API decides the rest.
  routes: [
    { path: 'kasse', module: 'kasse', component: KasseScreen },
    { path: 'kasse/tab', module: 'kasse', component: KasseScreen },
    { path: 'kasse/orders', module: 'kasse', component: KasseScreen },
    { path: 'kasse/orders/:id', module: 'kasse', component: OrderScreen },
  ],
  // Everyone's claims, for approving and paying, sit in Finanzen next to
  // the other bookings; members hand theirs in on the Kasse page.
  tabs: [
    {
      screen: 'finance',
      id: 'expenses',
      label: 'kasse.tabs.claims',
      module: 'kasse',
      perm: 'kasse.claims.read',
      group: 'bookings',
      component: ClaimsFinanceTab,
    },
    // Products, open amounts and settling the tab, which makes the invoices.
    {
      screen: 'finance',
      id: 'tab-settle',
      label: 'kasse.tabs.tab',
      module: 'kasse',
      perm: 'kasse.tab.update',
      group: 'invoices',
      component: TabSettleFinanceTab,
    },
  ],
  slots: [{ slot: 'account.cards', module: 'kasse', component: TabCard }],
  // The nav entry in hubra_kasse/__init__.py names this icon.
  icons: { receipt: IconReceipt },
  translations,
})
