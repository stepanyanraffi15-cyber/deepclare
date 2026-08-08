---
name: classify_page_type
version: 1
---

You are sorting the pages of one uploaded bundle for an Armenian import customs
submission. The bundle may hold a single document or several documents scanned into one
file — most often a commercial invoice together with a CMR road consignment note. Each
document is read afterwards from **only** the pages you assign to it, which is what stops
a consignee from the consignment note landing on the invoice, or an invoice line landing
on the consignment note.

{{page_count}} page images are attached, in order. The manifest below describes each one
by its 1-based page number and by a hint: the role that was declared for the file the
page came from.

PAGES (JSON, one entry per attached image, in order):
{{page_manifest}}

## What each label means

**invoice** — a commercial or proforma invoice page. Look for: a seller and a buyer, an
itemised goods table (descriptions, quantities, unit prices, amounts), an invoice number,
a currency, delivery terms (the incoterm naming who bears carriage and risk, and to which
place).

**consignment_note** — a CMR international road consignment note. Look for: sender in box
1, consignee in box 2, the carrier, the places of loading and delivery, vehicle
registration plates, the number and kind of packages, gross weight; laid out as numbered
boxes and usually titled "CMR".

**other** — a page carrying none of the above: a cover sheet, a packing list, a
certificate, a bank or customs form, a blank page.

## How to decide

- Decide from what is printed on the page in front of you. A page may be the second or
  third page of a multi-page document; classify a continuation page by the document it
  continues, not by whether it repeats a title block.
- The hint is a weak prior, not an answer. Where the content of the page clearly
  disagrees with the hint, follow the content.
- A row charging for freight, delivery or any other service does not change what a page
  is. A page carrying such a row is still an invoice page.
- Use **other** only for a page with no goods rows, no party details and no transport
  details. Know what that label does: a page you call other, which came from a file
  declared to be an invoice or a consignment note, is still read as part of that
  document. Dropping a real goods-bearing page loses goods from a customs declaration,
  which is worse than carrying one stray page into a reader. So calling a genuine invoice
  page other does not remove it — it only removes your judgement from the record.
- You are not transcribing anything on this call. Do not read values off the pages, do
  not translate, do not summarise, do not correct what you see. Page numbers and labels
  only.

## Output contract

Return exactly {{page_count}} verdicts, one per attached page, in page order. Each
verdict has:

- `page` — the page's 1-based number, echoed exactly as it appears in the manifest above.
- `page_type` — exactly one of `invoice`, `consignment_note`, `other`.

Every page gets a verdict. There is no confidence field and no way to abstain: a page you
are unsure about still gets the label its content best supports. Never merge two pages
into one verdict, never leave a page out, and never return a page number that is not in
the manifest.
