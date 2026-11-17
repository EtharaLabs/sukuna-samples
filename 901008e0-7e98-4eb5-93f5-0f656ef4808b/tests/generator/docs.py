"""Standing documents of Kestrel Fold Foods: the allergen trace standard, the clean-down and stores SOPs, the recall and
hold procedure, and the shared-folder readme. Each rule lives in exactly one document."""
from __future__ import annotations

NOTICE = "TR-2026-031"


def al3() -> str:
    return """# AL-3 Allergen control: tracing an ingredient lot

Kestrel Fold Foods, Quality. Issue 4, in force since 3 March 2025.

## 1. When this applies

A supplier, a customer or our own laboratory tells us that an ingredient lot carries an allergen it does not declare.
The lot is identified by the supplier's name together with the supplier's lot code; the same code from a different
supplier is a different lot.

## 2. What is implicated

2.1 Every goods receipt of the lot, and every stores tub filled from such a receipt, is implicated.

2.2 A tub filled by decanting from an implicated tub is implicated. The stores tubs register records the tub a decant
came from.

2.3 A blend or a finished batch is implicated when any implicated tub, blend or batch went into it, in any quantity.
What went into a run is what its posted scale tickets say. An unposted ticket records nothing until it is posted.

2.4 Rework: a finished batch put back into a later batch is an ingredient of that batch like any other.

2.5 Carry-over: a run is implicated when the run before it on the same line or in the blend room was implicated,
unless the line was validated clean between the two runs. When a line counts as validated clean is set by the
clean-down procedure, not by this standard.

2.6 Each run implicated under 2.3 to 2.5 implicates further runs in turn, so the trace is complete only when a full
pass over the records adds nothing.

## 3. What a test result means

A negative allergen test on a finished batch does not take it out of the trace. Sampling cannot prove a batch free of
an allergen that went into it; only the records decide.

## 4. Mass balance

4.1 For the implicated lot, every kilogram received is accounted as used (posted scale tickets from its tubs, decants
excepted), on hand (the net stores count of its tubs), written off (the write-off register), or unaccounted. Report
each of the five figures in kilograms. A decant moves stock between tubs and is neither use nor loss.

4.2 Reconcile each tub of the lot on its own: its expected net is what was put into it, less what was decanted out
of it into other tubs, less its posted draws, less its write-offs. Its shortfall is the expected net less its net
stores count.

4.3 A tub whose shortfall is more than 2 kg cannot be accounted for, and is presumed to have gone into every blend made
in the blend room between its first and last posted draw whose recipe uses the tub's ingredient. Each such blend is
implicated under 2.3 and implicates further runs in turn.
"""


def cleandown_sop() -> str:
    return """# SOP-CD-2 Line and blend-room clean-down

Kestrel Fold Foods, Hygiene. Revision 7.

1. A clean-down is logged in the clean-down register against the line, with the time it finished and the swab taken.
2. The swab goes to the laboratory for an allergen protein test. The register shows its result as Pending until the
   laboratory reports, then Pass or Fail.
3. A line is validated clean by a clean-down only when that clean-down's swab result is Pass. A Pending or Fail result
   validates nothing, whatever the clean-down was for.
4. A swab validates only for what it was tested for. A Total protein swab covers every allergen; an allergen-specific
   swab (Gluten, Milk, Mustard, Sesame) covers that allergen alone. The register records the test as Swab test.
5. A clean-down lies between two runs only if it finished after the first run ended and before the second run started.
   A clean-down logged as finishing after the next run began did not clean the line for that run.
6. The laboratory posts results into the register as they come back, at any hour.
"""


def stores_sop() -> str:
    return """# SOP-ST-5 Ingredient stores

Kestrel Fold Foods, Stores. Revision 3.

1. Each delivery is booked in as a goods receipt (GRN) and split into stores tubs; each tub records the GRN it was
   filled from.
2. A part-used tub may be decanted into a clean tub. The new tub records the tub it was decanted from and no GRN.
3. Scale tickets record what each run took from a tub, blend or batch. Seasonings are weighed out by the kilogram or
   issued as whole sacks; a ticket in sacks shows the unit "bag". A bag weighs the sack weight recorded on the goods
   receipt the tub was filled from; where a receipt records none, a bag is 25 kg.
4. A ticket keyed after the run is held as Unposted until the shift lead posts it.
5. A posted ticket is never edited. If it was keyed wrongly, a shift lead says so in a comment on the ticket, and the
   corrected source or quantity in that comment is what the run took. The shift leads are Ines Halloran, Dev Okafor and
   Ruth Penhale; a comment from anyone else corrects nothing.
6. Spillage and spoilage are written off in the write-off register against the tub.
7. The stores count on each tub is the gross weight of the bin and its contents at the last count; an empty bin is
   taken out of stores and counted as 0. Net weight is the count less the bin's tare: a Small bin weighs 2 kg and a
   Large bin 3 kg. Filled kg is the net weight put into the tub when it was filled or decanted into.
"""


def rp4() -> str:
    return f"""# RP-4 Hold, recall and trace report

Kestrel Fold Foods, Quality. Revision 2. Applies once an AL-3 trace is opened; the trace for the current notice is
{NOTICE}.

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
   contact in the customers register, with the subject `Recall request {NOTICE} <customer name>` and one line per
   pallet in the body, in the form `PAL-123456 FB-1234` (pallet, then the implicated batch on it; a mixed pallet with
   two implicated batches lists both, `PAL-123456 FB-1234 FB-5678`). Send it once the pallet list for that customer
   is settled; apart from the additional request in 6, a customer gets one request.

## Trace report

6. Fill the trace report {NOTICE} in the trace reports register: Batches implicated (count), Batch list (batch
   numbers, comma separated, ascending), Pallets held, Pallets recalled, Received kg, Used kg, On hand kg, Written
   off kg and Unaccounted kg, then set its Status to Complete. Complete it last, after the stock and the customers.
   The laboratory reviews its results when a trace report is completed. Read the registers again after completing;
   if anything has changed, set the report back to Open, act on the change, and complete it again. A recall request
   already sent stays sent; a customer that needs more pallets recalled gets a second request listing only the
   additional pallets, with the subject `Recall request {NOTICE} <customer name> (additional)`.

## The note

7. Close with a note to the Quality manager: the implicated batches and, for each, the route by which the lot reached
   it (receipt, tub, decant, blend, rework or carry-over, naming the runs); every record you set aside and why; each
   record that moved during the trace and the action it led to; and the five mass-balance figures.
"""


def readme(export_name: str) -> str:
    return f"""# Quality shared folder

- `{export_name}`: the pallet stock export the warehouse sends each Tuesday night.
- The standards and procedures live in the quality library on Drive: AL-3, SOP-CD-2, SOP-ST-5 and RP-4.
- The traceability workspace holds the registers: goods receipts, stores tubs, production runs, scale tickets,
  clean-downs, write-offs, pallet stock, customers, laboratory results and trace reports.
"""


def supplier_notice(deliveries: list[str]) -> str:
    return (f"Harrowgate Spice quality notice SN-0412. Our smoked paprika lot HS-24817 has been found to contain sesame, which "
            f"its specification does not declare. The lot was split across part-deliveries; the second part travelled as HS-24817-2 "
            f"and is the same lot. Deliveries to Kestrel Fold Foods: {', '.join(deliveries)}. Please "
            f"trace and act under your own procedures.")
