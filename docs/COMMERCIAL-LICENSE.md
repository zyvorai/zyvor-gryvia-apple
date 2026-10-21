# Gryvia Apple Business-Use License (draft for review by Zyvor AI Labs Private Limited and its counsel)

Gryvia Apple is source-available under the Business Source License 1.1 (`LICENSE`: its Additional Use Grant no longer allows free personal use for versions after v0.4.0). This page describes the paid
grants: a **Personal** plan for one individual and **business and commercial** plans.

## Personal plan

Personal means one individual, for no business, employer or income-producing purpose. It is a one-time payment of
₹420 including GST (about US$4.99), covers that individual's own Macs, and is the lowest-priced plan. It does not
cover business use; use a plan below for that.

## The business grant

On receipt of payment for a business plan below, Zyvor AI Labs Private
Limited ("Licensor") grants the payer ("Licensee", an individual or a single legal entity) a perpetual, worldwide,
non-exclusive, non-transferable licence to:

1. use Gryvia Apple in business and for commercial purposes, on machines the Licensee owns or operates;
2. do so for the version bought and every later version released under the BUSL by Licensor during the paid year;
3. modify the source for the Licensee's own use.

## Plans (all prices include GST)

| Plan | Price | Covers |
|---|---|---|
| Personal | ₹420 one-time (about US$4.99) | One individual, no business use |
| Solo / small team | ₹4,999 per year (about US$59) | One legal entity, up to 5 Macs |
| Team | ₹19,999 per year (about US$239) | One legal entity, up to 25 Macs |
| Larger fleets | by quote | More than 25 Macs or several entities: sales@zyvor.dev |

Payment is by invoice. *[Licensor and counsel to confirm: the grant text above says "perpetual" and these plans are annual, so decide whether the grant is perpetual for the versions released while paid, or lapses.]*

## What it does not cover

- Redistribution, sublicensing, reselling, or hosting Gryvia Apple as a product or service for third parties.
- Removing licence notices (`LICENSE`, SPDX headers).
- More than one legal entity: affiliates and customers need their own grant.
- Any promise about GPU runtime performance. MLX, llama.cpp and other runtimes are configured by the Licensee;
  `TEST_RESULTS.md` lists what was and was not measured.

## Proof and terms

- The invoice or payment receipt is the proof. There are no keys or accounts; the software does not check.
- Provided as is, no warranty, under the same disclaimers as the BUSL. Payments are non-refundable except as
  required by law.
- Questions, receipts, new download links, and larger or multi-entity licences: sales@zyvor.dev.
- Governing law and venue: *[Licensor and counsel to fill in]*. Tax and GST treatment: *[Licensor and counsel to fill in]*.

## Open questions for counsel

- `LICENSE` now has no free personal-use grant for versions after v0.4.0, while v0.4.0 and earlier keep the grant they were published under (it cannot be withdrawn). Counsel to confirm the wording, in particular that BUSL 1.1 still lets anyone copy, modify and make **non-production** use of the source without paying, and how "production" is told apart from personal evaluation.
- Whether the ₹420 one-time grant sold earlier stays perpetual for those payers, and how the annual plans relate to it.
- Whether the Mac-count limits (5 and 25) are the right lines, and how "a Mac" is counted for machines that are rebuilt or shared.
- The exact line between personal and business use for freelancers and employees using Gryvia Apple at work.
- Transferability on a company sale, and what happens to prior payers if terms change.
