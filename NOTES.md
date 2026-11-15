# Build notes

What Claude got wrong during the build, and how it was caught.

## Seed data

- **Prices depreciated too fast.** The first seed run priced a 2025 GMC Hummer EV at $27,495 and a 2020 Dodge Challenger SRT at $8,495. Caught by eyeballing a random sample of rows after seeding, not by any test. Fixed by slowing depreciation from 14% to 9% a year. Prices are still generated per body style, not per model, so they are plausible rather than accurate.
- **Too few new vehicles.** Sampling model years evenly from 2015 to 2027 gave 32 new vehicles out of 300, which no dealership lot looks like. Caught by a count per condition. Fixed by weighting recent model years more heavily.

## SQL validation and chat loop

- **Assumed sqlglot strips comments. It does not.** Claude wrote the validator on the belief that regenerating SQL from the parsed tree drops comments. A test with `/* DROP TABLE vehicles */` inside a SELECT failed: the comment came through. Harmless to the database, but it meant unchecked text was being sent. Fixed with `comments=False`. Caught by the test, written before trusting the assumption.
- **First plan for CTEs was too clever.** The first design allowed `WITH` and tracked CTE names so they would not be mistaken for tables. That has a hole: a CTE named `pg_roles` in an inner scope would make a reference to the real `pg_roles` in an outer scope look safe. Rather than add scope analysis, `WITH` is rejected outright and the model is told to use subqueries. Simpler rule, easier to explain, nothing lost for a one-view database.
- **A test was wrong, not the code.** A chat-loop test read the first tool error from a recorded request, but the recorded request held a reference to a list the loop kept appending to, so it saw the second error. The fake client now snapshots the list.

## First run against the real API

- All 15 spec questions (20 runs across the two roles) behaved as expected, and every number matched a hand-written query on the base table.
- **Answers came back with Markdown bold** (`**3**`), which a plain HTML page would show as literal asterisks. Caught by reading the output, not by a test. Fixed in the system prompt.
- **"On the lot" is a judgment call.** The model counts only `available` vehicles unless asked otherwise, and says so. "How many used trucks under $30,000 over 60 days" is 3 available but 5 across all statuses. Either could be what a manager means; the answer states which one it used.

## Known approximations (not bugs, but worth knowing)

- `body_style` is mapped from the EPA size class, which is about interior volume, not shape. A Dodge Challenger is an EPA "Midsize Car" and so shows as a sedan.
- `combined_mpg` for electric vehicles is the EPA's MPGe figure.
- `trim` is whatever text follows the base model name in the EPA record (for example "Limited AWD"). It is blank for many vehicles.
