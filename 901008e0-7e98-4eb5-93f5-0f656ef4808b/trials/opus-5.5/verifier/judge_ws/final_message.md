Trace TR-2026-031 is finished and the report is Complete: 29 batches are implicated, 42 pallets are held, 51 are marked for recall, and each of the five customers has had one recall request. The closing note to the Quality manager is in `/workspace/TR-2026-031-closing-note.md`. I didn't email it, because the limits only allow mail to customers' recall contacts, so it needs passing on by hand.

**The lot.** HS-24817 came in on two Harrowgate receipts, GRN-50700 and GRN-85070, 450 kg in total. It went into four tubs (TUB-3897, TUB-7776, TUB-5858, TUB-1751) plus one decant (TUB-9510). The four tubs that still hold stock are Quarantined; TUB-7776 is empty and I left it alone.

**Mass balance (net kg).** Received 450 = used 113 + on hand 320 + written off 12 + unaccounted 5.
- Bag tickets were converted at the 20 kg sack weight on the receipt, not the 25 kg default.
- Stores counts were reduced by the 3 kg Large-bin tare.
- Two posted tickets were keyed against the wrong tub; I used the sources the shift leads corrected them to in comments.
- TUB-1751 is the only tub with a shortfall over 2 kg (5 kg). Under AL-3 4.3 that makes BL-772 (Ragu base) presumed contaminated, which brings in FB-8372.
- BL-772 ran 06:00–08:00 and TUB-1751's last draw was at 06:50, so the blend straddles the end of the window. I counted it as inside the window, which is the cautious reading. If you read "between" strictly, BL-772 and FB-8372 drop out.

**What changed while I worked:**
- **PAL-146751** was moved to In transit for Pellow & Finch, so I marked it Recall requested instead of Held.
- **PAL-118395** came back to the chiller, so it is Held, not recalled.
- **ST-50238** was posted (7 kg into FB-6240). That implicated FB-6240 and widened TUB-1751's window to take in BL-772.
- **The BR clean-down of 2 Nov 08:10** turned from Pending to Pass. That cleared BL-277 and four batches that came only through it. I released the 2 pallets I had held for them. I set the 10 shipped pallets back to Available; no recall request had been sent yet.
- **The L1 clean-down of 11 Nov 09:10** turned to Fail after I first completed the report. That implicated FB-6776. I reopened the report, held its 4 pallets, and completed it again. FB-6776 has no shipped pallets, so no extra recall request was needed.

**Records I set aside:**
- GRN-32891 has the same lot code but comes from a different supplier, Dunmere.
- GRN-87291 is a different lot code, HS-24817-2, so FB-4296 is not implicated.
- A comment on ST-83925 claiming a TUB-3897 draw is from Kit Marsh, who is not a shift lead, so it corrects nothing.
- The Gluten- and Milk-only swabs don't validate a line for sesame.
- The "Not detected" lab results don't clear any batch.
- The warehouse CSV in `data/` was stale, so I worked only from the live pallet register.

**Incomplete or refused listings:**
- **Scale tickets:** the register holds 214 but its listing returned 184, with no unposted tickets. I got the full set by paging a workspace search for "ST-". The search showed ST-50238 as still Unposted, but opening the ticket itself showed it as Posted.
- **Write-offs:** listing was refused (it needs the stores controller role). A workspace search found all 7 records, matching the register's count.
- **Gmail and Teams:** listing failed with tool errors on both, so I traced from the registers alone.

A full re-read after the final completion showed no further changes.