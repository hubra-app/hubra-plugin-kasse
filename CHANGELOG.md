# Kasse

## 1.1.0

- Gives the standard roles access when a club first switches it on (`role_defaults`, docs/roles.md in hubra-app/hubra): Mitglied Ansehen, Kassier/in Alles. Roles without access don't see it; their own data from it stays on their profile. Needs Hubra 0.2.5 or later.

## Unreleased

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
