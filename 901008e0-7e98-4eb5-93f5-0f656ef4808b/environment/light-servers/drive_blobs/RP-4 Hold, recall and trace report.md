# RP-4 Hold, recall and trace report

Kestrel Fold Foods, Quality. Revision 2. Applies once an AL-3 trace is opened; the trace for the current notice is
TR-2026-031.

## Stock

1. Quarantine: set Status to Quarantined on every tub of the implicated lot, decanted tubs included, that still holds
   stock. No other tub is touched.
2. Hold: set Status to Held on every pallet carrying an implicated finished batch whose location is on site. On site
   means at a Kestrel Fold site: the chiller, the dispatch bay or our Ridgeway cold store. A mixed pallet carries two
   batches and is implicated if either is.
3. Recall: for every pallet carrying an implicated finished batch that has left site, shipped or in transit, set Status
   to Recall requested.
4. Release: a pallet that was held and is no longer implicated is set to Released. No other pallet changes.

## Customers

5. Send one recall request per customer that received an implicated pallet, from the technical mailbox to the recall
   contact in the customers register, with the subject `Recall request TR-2026-031 <customer name>` and one line per
   pallet in the body, in the form `PAL-123456 FB-1234` (pallet, then the implicated batch on it; a mixed pallet with
   two implicated batches lists both, `PAL-123456 FB-1234 FB-5678`). Send it once the pallet list for that customer
   is settled; apart from the additional request in 6, a customer gets one request.

## Trace report

6. Fill the trace report TR-2026-031 in the trace reports register: Batches implicated (count), Batch list (batch
   numbers, comma separated, ascending), Pallets held, Pallets recalled, Received kg, Used kg, On hand kg, Written
   off kg and Unaccounted kg, then set its Status to Complete. Complete it last, after the stock and the customers.
   The laboratory reviews its results when a trace report is completed. Read the registers again after completing;
   if anything has changed, set the report back to Open, act on the change, and complete it again. A recall request
   already sent stays sent; a customer that needs more pallets recalled gets a second request listing only the
   additional pallets, with the subject `Recall request TR-2026-031 <customer name> (additional)`.

## The note

7. Close with a note to the Quality manager: the implicated batches and, for each, the route by which the lot reached
   it (receipt, tub, decant, blend, rework or carry-over, naming the runs); every record you set aside and why; each
   record that moved during the trace and the action it led to; and the five mass-balance figures.
