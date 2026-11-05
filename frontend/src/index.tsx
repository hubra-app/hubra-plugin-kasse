import { registerPlugin } from '@hubra/plugin-sdk'
import { IconReceipt } from '@tabler/icons-react'
import { KasseScreen } from './KasseScreen'
import { OrderScreen } from './OrderScreen'
import { TabCard } from './TabCard'
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
  slots: [{ slot: 'account.cards', module: 'kasse', component: TabCard }],
  // The nav entry in hubra_kasse/__init__.py names this icon.
  icons: { receipt: IconReceipt },
  translations,
})
