# Build notes

What Claude got wrong during the build, and how it was caught.

## Seed data

- **Prices depreciated too fast.** The first seed run priced a 2025 GMC Hummer EV at $27,495 and a 2020 Dodge Challenger SRT at $8,495. Caught by eyeballing a random sample of rows after seeding, not by any test. Fixed by slowing depreciation from 14% to 9% a year. Prices are still generated per body style, not per model, so they are plausible rather than accurate.
- **Too few new vehicles.** Sampling model years evenly from 2015 to 2027 gave 32 new vehicles out of 300, which no dealership lot looks like. Caught by a count per condition. Fixed by weighting recent model years more heavily.

## Known approximations (not bugs, but worth knowing)

- `body_style` is mapped from the EPA size class, which is about interior volume, not shape. A Dodge Challenger is an EPA "Midsize Car" and so shows as a sedan.
- `combined_mpg` for electric vehicles is the EPA's MPGe figure.
- `trim` is whatever text follows the base model name in the EPA record (for example "Limited AWD"). It is blank for many vehicles.
