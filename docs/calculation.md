# Calculation

## Definitions

- **Actuation**: one increment of a camera body's shutter counter.
- **Range**: the inclusive span of shutter counts a body covers, `last − first + 1`. The same rule is used for the year and for every folder.
- **Body**: camera model plus serial number. Each body has its own odometer.

## Year total

For each included body: `last in-year count − first in-year count + 1`. The year total is the sum over included bodies.

## Attribution

Each folder gives one range per body. For each body, every actuation in the year's range is credited to exactly one bucket:

1. Find every folder range that contains the actuation.
2. If there is none, it is **unattributed** (deleted photos, albums stored elsewhere).
3. If there is one, that folder gets it.
4. If there are several, the **narrowest range wins**. A short personal detour inside a long business shoot is therefore credited to the personal folder, and the reverse also holds. Ties go to Personal.

A folder's effective label is its own, or the nearest labelled ancestor's.

```
business %  =  actuations credited to Business folders ÷ year total
```

Because every actuation lands in one bucket, Business + Personal + Unclassified + Unattributed always equals the year total. Unattributed actuations count against the business share, which is the conservative position.

## Estimated bodies

A body with no shutter count has no ranges. Its year total is its file count, and each folder is credited with the files it holds.

## Warnings

- **Overlap**: two folders' ranges intersect for the same body. Shown with the shared amount so you can check the narrowest-wins result.
- **Counter moved less than the file count**: the body took frames without advancing the counter (for example electronic shutter on some models).
- **Estimated body** included in the total.
