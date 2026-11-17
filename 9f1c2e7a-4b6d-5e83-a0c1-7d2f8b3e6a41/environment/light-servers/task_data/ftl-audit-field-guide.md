# FTL audit: field guide for the September 2026 block

This guide fixes the form of every record the audit writes. The rules come from the operations manual, chapter 7, in the revision that applies to each duty.

## Findings database

One record per exceedance in the findings database for the block. The base assigns the Reference (FTL-nnnnn) when the record is created; do not type one.

- Title: `<staff number> <duty reference or window end date> <limit type>`, separated by single spaces.
- Staff number: the five-digit staff number.
- Duty ref: the duty reference for FDP, DISCRETION and REST findings; for cumulative findings, the last day of the first window that exceeds, as YYYY-MM-DD.
- Limit type: one of FDP, DISCRETION, REST, DUTY_7D, DUTY_14D, DUTY_28D. A duty with more than one exceedance gets one record per limit type; a cumulative limit gets one record per crew member, for the first window that exceeds it.
- Edition: Rev 13 or Rev 14, the revision that applies to the duty, or for a cumulative finding to the window's last day.
- Limit min, Actual min, Excess min: whole minutes as numbers. For REST, Limit min is the minimum rest, Actual min the rest taken and Excess min the shortfall.
- Evidence: the identifiers of the technical-log pages, discretion reports and call-log entries that set a value you used in place of the duty-actuals record, comma separated; leave it empty when the record stood.

## Corrections register

The duty-actuals record is not changed. Instead, file one record in the duty-actuals corrections register for each technical-log page, discretion report or call-log entry that set a value you used in place of the duty-actuals record:

- Title: `<identifier> <duty reference>`, the identifier of the page, report or entry and the duty whose record it overrode.
- Staff number: the crew member on that duty.
- Duty ref: the duty reference.
- Evidence: the identifier.

File a correction before the block is closed with the findings it supports. One record per identifier; a record that stood gets none.

## Block close

When every finding is recorded, set the block-close record to Closed with Findings (the count of finding records) and Excess total min (the sum of Excess min). If anything has to change after the block is closed, set it to Reopened first, make the change, and close it again with the figures restated. Never change a finding while the block is Closed.

## Notices

After the block is finally closed, send one notice per crew member with a finding, from the compliance mailbox to the address in the crew register, under the subject `FTL audit September 2026: <staff number>`. List each of that member's findings on its own line as `<Reference> <duty reference or window end date> <limit type> excess <n> min`.

## Fatigue reports

After the last notice, each open fatigue report (project FAT) raised by a crew member you notified gets one line appended to its description:

```
ftl_findings: <the References of that member's findings, comma separated, in ascending order>
```

Leave every other field of the report, and every fatigue report of a crew member without a finding, as it is.

## Audit request

After the last notice, append these four lines to the audit request's description and move it to Done:

```
findings: <count of finding records>
excess_total_min: <sum of Excess min>
crew_notified: <count of notices sent>
editions: <the revisions you applied, comma separated, oldest first>
```
