# Safe staffing audit: field guide for the October 2026 roster period

This guide fixes the form of every record the audit writes. The rules come from the safe staffing standard SS-4, in the revision that applies to each shift.

## Findings database

One record per exceedance in the findings database for the period. The workspace assigns the Reference (SSF-nnnnn) when the record is created; do not type one.

- Title: `<staff number> <shift reference or window end date> <limit type>`, separated by single spaces.
- Staff number: the five-digit staff number.
- Shift ref: the shift reference for SHIFT, EXTENSION and REST findings; for rolling-hours findings, the last day of the first window that exceeds, as YYYY-MM-DD.
- Limit type: one of SHIFT, EXTENSION, REST, HOURS_7D, HOURS_14D, HOURS_28D. A shift with more than one exceedance gets one record per limit type; a rolling-hours limit gets one record per nurse, for the first window that exceeds it.
- Edition: Rev 6 or Rev 7, the revision that applies to the shift, or for a rolling-hours finding to the window's last day.
- Limit min, Actual min, Excess min: whole minutes as numbers. For REST, Limit min is the minimum rest, Actual min the rest taken and Excess min the shortfall.
- Evidence: the identifiers of the ward timesheet pages, extension authorisations and bleep-log notes that set a value you used in place of the shift-actuals record, comma separated; leave it empty when the record stood.

## Corrections register

The shift-actuals record is not changed. Instead, file one record in the actuals corrections register for each ward timesheet page, extension authorisation or bleep-log note that set a value you used in place of the shift-actuals record:

- Title: `<identifier> <shift reference>`, the identifier of the page, authorisation or note and the shift whose record it overrode.
- Staff number: the nurse on that shift.
- Shift ref: the shift reference.
- Evidence: the identifier.

File a correction before the period is closed with the findings it supports. One record per identifier; a record that stood gets none.

## Period close

When every finding is recorded, set the period-close record to Closed with Findings (the count of finding records) and Excess total min (the sum of Excess min). If anything has to change after the period is closed, set it to Reopened first, make the change, and close it again with the figures restated. Never change a finding while the period is Closed.

## Notices

After the period is finally closed, send one notice per nurse with a finding, from the compliance mailbox to the address in the nurse register, under the subject `Safe staffing audit October 2026: <staff number>`. List each of that nurse's findings on its own line as `<Reference> <shift reference or window end date> <limit type> excess <n> min`.

## Incident reports

After the last notice, each open staffing incident report (project INC) raised by a nurse you notified gets one line appended to its description:

```
staffing_findings: <the References of that nurse's findings, comma separated, in ascending order>
```

Leave every other field of the report, and every incident report of a nurse without a finding, as it is.

## Audit request

After the last notice, append these four lines to the audit request's description and move it to Done:

```
findings: <count of finding records>
excess_total_min: <sum of Excess min>
nurses_notified: <count of notices sent>
editions: <the revisions you applied, comma separated, oldest first>
```
