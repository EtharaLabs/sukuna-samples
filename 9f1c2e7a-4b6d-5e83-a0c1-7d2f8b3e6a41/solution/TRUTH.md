# TRUTH: September 2026 block, E190 Aberdeen flight crew

Seeds: WORLD_SEED=58213, TASK_SEED=7319. In-scope pilots: 28.

Findings: 33; excess total 1305 min; pilots notified 28.
By partition: audio 4, core 11, cumulative 3, discretion 3, edition 2, image 3, late 5, rest 2

| Staff | Duty ref or window end | Limit type | Edition | Limit | Actual | Excess | Evidence | Partition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 31279 | 2026-09-18 | DUTY_14D | Rev 14 | 6600 | 6628 | 28 | - | cumulative |
| 31527 | E9-0911-ABZ-625 | REST | Rev 13 | 720 | 665 | 55 | - | rest |
| 31564 | E9-0920-ABZ-168 | FDP | Rev 14 | 705 | 755 | 50 | - | core |
| 32200 | E9-0920-ABZ-920 | DISCRETION | Rev 14 | 720 | 762 | 42 | CDR-7610 | late |
| 32319 | E9-0922-ABZ-987 | FDP | Rev 14 | 630 | 682 | 52 | - | core |
| 32894 | E9-0924-ABZ-733 | REST | Rev 14 | 886 | 867 | 19 | - | rest |
| 35947 | E9-0920-ABZ-963 | FDP | Rev 14 | 630 | 660 | 30 | - | late |
| 36107 | E9-0918-ABZ-577 | FDP | Rev 14 | 630 | 636 | 6 | - | core |
| 36330 | E9-0923-ABZ-816 | FDP | Rev 14 | 780 | 795 | 15 | TL-86765 | image |
| 37488 | E9-0912-ABZ-179 | FDP | Rev 13 | 780 | 801 | 21 | - | late |
| 37488 | E9-0915-ABZ-153 | REST | Rev 13 | 831 | 728 | 103 | - | late |
| 37712 | E9-0901-ABZ-562 | FDP | Rev 13 | 780 | 787 | 7 | - | core |
| 38571 | E9-0918-ABZ-844 | FDP | Rev 14 | 780 | 821 | 41 | - | core |
| 39638 | E9-0922-ABZ-773 | DISCRETION | Rev 14 | 810 | 819 | 9 | - | discretion |
| 40672 | E9-0914-ABZ-427 | FDP | Rev 13 | 660 | 670 | 10 | - | edition |
| 43699 | E9-0915-ABZ-357 | DISCRETION | Rev 14 | 750 | 773 | 23 | - | edition |
| 43840 | E9-0911-ABZ-467 | FDP | Rev 13 | 780 | 815 | 35 | - | core |
| 44049 | E9-0918-ABZ-262 | FDP | Rev 14 | 630 | 661 | 31 | - | late |
| 44873 | E9-0913-ABZ-283 | FDP | Rev 13 | 720 | 754 | 34 | - | core |
| 45172 | E9-0923-ABZ-939 | FDP | Rev 14 | 720 | 771 | 51 | - | discretion |
| 45175 | 2026-09-24 | DUTY_7D | Rev 14 | 3600 | 3765 | 165 | VN-717 | audio |
| 45175 | E9-0922-ABZ-785 | FDP | Rev 14 | 720 | 775 | 55 | - | core |
| 45175 | E9-0923-ABZ-367 | FDP | Rev 14 | 600 | 625 | 25 | - | core |
| 45269 | E9-0909-ABZ-573 | FDP | Rev 13 | 690 | 716 | 26 | TL-28498 | image |
| 45677 | E9-0921-ABZ-775 | FDP | Rev 14 | 720 | 733 | 13 | VN-119 | audio |
| 45677 | E9-0921-ABZ-775 | REST | Rev 14 | 720 | 667 | 53 | VN-119 | audio |
| 47639 | E9-0904-ABZ-411 | DISCRETION | Rev 13 | 840 | 854 | 14 | CDR-1011 | image |
| 48146 | 2026-09-10 | DUTY_7D | Rev 13 | 3600 | 3625 | 25 | - | cumulative |
| 49130 | 2026-09-07 | DUTY_28D | Rev 13 | 11400 | 11439 | 39 | - | cumulative |
| 49130 | E9-0918-ABZ-755 | FDP | Rev 14 | 780 | 846 | 66 | - | discretion |
| 49301 | 2026-09-12 | DUTY_7D | Rev 13 | 3600 | 3685 | 85 | VN-686 | audio |
| 49580 | E9-0920-ABZ-680 | FDP | Rev 14 | 720 | 753 | 33 | - | core |
| 49946 | E9-0903-ABZ-972 | FDP | Rev 13 | 720 | 764 | 44 | - | core |

## Mid-run world changes

- Trigger a, first close of the block: duty E9-0912-ABZ-179 on-blocks 2026-09-12T20:21Z to 2026-09-12T20:59Z.
- Trigger b, twelfth finding written: staff 43840 address ysolde.ormiston5@fernhollow-air.example to ysolde.ormiston.fh@fernhollow-air.example.
- Trigger c, twentieth finding written: duty E9-0920-ABZ-963 on-blocks 2026-09-20T13:15Z to 2026-09-20T15:35Z.
- Trigger d, second close of the block: discretion report CDR-7610 for duty E9-0920-ABZ-920 is signed.
- Trigger e, first close of the block: staff 36330 address lachlan.abernethy6@fernhollow-air.example to labernethy@crew.fernhollow-air.example.
- Trigger f, second close of the block: duty E9-0918-ABZ-262 on-blocks 2026-09-18T12:01Z to 2026-09-18T15:46Z.
- Never signed: discretion report CDR-6991 for duty E9-0918-ABZ-755.

## Checker set

F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, R09, R10, R11, R12, R13, R14, R15, R16, R17, R18, R19, R20, R21, R22, R24, R25, R26, R27, R28, R29, R30, R31, R32, R33, R34, R35, R36, R37, R38, R39, R40, R43, R44, R45, R46, R47, R48, T01, T02, T03, T04, T05, T06

