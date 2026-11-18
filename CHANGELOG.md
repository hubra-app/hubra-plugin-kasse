# Kasse

## Unreleased

- Date, date-and-time and time fields use Hubra's date pickers: dd.mm.yyyy, a calendar that starts on Monday and 24-hour times, whatever the browser language; typed dates like 1.2.26 work too. Needs Hubra 0.2.6 or later.

## 1.2.0

- **The Strichliste goes to Finanzen as open items**: settling hands each member's open amount over with `finance.open_item.add` (hubra#337). With Finanzen › Einstellungen › Kleine Posten sammeln on, it waits for the member's next collected invoice, together with booking fees and the rest; with it off it gets an invoice of its own straight away, as before, due after the Strichliste's payment term. A deleted invoice puts its ticks back on the tab and takes the open item back, so nothing is billed twice. A settled tick is one with a settle date (it may have no invoice yet). On a Hubra without open items it invoices as before. Needs Hubra 0.2.6 or later for open items.
- The QR sheet no longer imports a private helper Hubra removed (it failed on Hubra main).
- **Links kept by hand.** Club schemas have no foreign keys, so the `ondelete` rules never ran: a deleted invoice now puts its ticks back on the open tab and unbills its order lines (`invoice.deleted`), deleting an order deletes its items and lines, deleting a product unlinks its ticks, and the daily job `kasse-purge-orphans` clears links to invoices, transactions, products and orders that are gone.
- **Four eyes on expense claims.** Nobody approves, rejects or pays their own claim: a treasurer's own claim needs another member with the right (`OWN_CLAIM`, also for admins). The Spesen list says so on one's own claim.
- **Decided claims stay on record.** Only the member who handed in a claim can withdraw it, and only before it is decided; the treasurer rejects instead of deleting. Approved, rejected and paid claims, with their receipt, stay.
- **Paying a claim books through core's contract** `finance.transaction.create` instead of writing the transactions table directly (checks, closed fiscal years, audit entry). Needs Hubra 0.2.6 or later. On an older Hubra paying answers 503 `HUBRA_TOO_OLD`.
- **The QR sheet's codes always point at the club app** (`FRONTEND_BASE_URL` and the club's address), never at a link from the request; `?link=` is gone.
- **Security (audit 2026-11-11).** A receipt is taken only when its first bytes show a JPEG, PNG, GIF, WebP, HEIC or PDF; the type the browser sends no longer counts, so an SVG or HTML file can't pose as a photo and run script when the treasurer opens it. Receipts stored before with another type only leave as a plain download. Paying a claim, settling the tab and billing an order now hold their rows until done, so two clicks at once can't book or invoice twice, and a tick made during a settle waits for the next one. The audit log now also records products added, repriced or deleted, ticks put on or taken off another member's tab, and orders changed, closed or reopened. The supplier list (CSV) can't carry spreadsheet formulas.
- Money fields like the rest of the app: the expense claim amount takes numbers only; CHF prefix, 2 decimals, no arrows.
- **Products are consumables in Inventory.** Each Strichliste product gets an item of the type *Verbrauchsmaterial* in Inventory, which counts the stock: every tick takes from it, a tick taken back puts it back. The product form sets stock, reorder level and unit; the product list shows the stock and *Knapp*. A product renamed in either place is renamed in the other; one deleted in Inventory leaves the tab. Products from before get their item from the job `kasse-link-items`. Only through Inventory's contracts; without Inventory (or with one older than the stock counts) the tab works as before.
- **The Strichliste in Finanzen has three parts:** *Abrechnen* (open amounts, settling), *Produkte* and *Einstellungen* (the category and payment term the invoices get when settling, and the QR codes for the fridge). New `GET`/`PUT /tab/settings`; settling without a category or term takes these.
- Run `flask db upgrade` after updating (`kasse_products.item_id`).

## 1.1.0

- Gives the standard roles access when a club first switches it on (`role_defaults`, docs/roles.md in hubra-app/hubra): Mitglied Ansehen, Kassier/in Alles. Roles without access don't see it; their own data from it stays on their profile. Needs Hubra 0.2.5 or later.
- Dashboard widgets: **Meine Strichliste** (what the member has on the tab and isn't billed yet) and **Offene Spesen** (claims not paid out yet, with their total; needs `kasse.claims.read`).
- Managing the tab's products, printing the QR sheet and settling the tab
  moved into Finanzen › Rechnungen › Strichliste (`/app/finance/tab-settle`).
  Members still tick on the Kasse page. Needs a Hubra with plugin sub-tabs
  under Rechnungen; older versions show it as a page tab of its own.
- Everyone's expense claims moved into Finanzen › Buchungen › Spesen
  (`/app/finance/expenses`), where the treasurer approves and pays them. On
  the Kasse page members still hand in and follow their own.
- Paying an expense claim works again on Hubra with the books moved into the
  Finances plugin. The expense is written to the transactions table directly
  instead of through a finance service that core no longer has.

## 1.0.0

First version. Money between members and the club outside the membership fee:

- **Expense claims (Spesen)**: a member hands in the amount, a receipt photo or PDF and where to pay it. The treasurer approves or rejects with a reason, and paying books the expense in the finances with the claim linked to it. The member hears about each step in the bell. Receipts are kept encrypted in Hubra's file store.
- **Tab (Strichliste)**: members tap drinks or materials in the app, or scan a QR code at the fridge. A tick can be taken back for 15 minutes. The treasurer sees what is open per member and settles the tab: each member gets one invoice. A printable sheet has a QR code for each product.
- **Collective orders**: club clothing or merchandise with prices, sizes and a deadline. Members order in their sizes until the deadline. The board gets the list for the supplier (also as CSV), closes the order and bills it: each member gets one invoice.
- A card on the member's account page shows what is open on their tab.
