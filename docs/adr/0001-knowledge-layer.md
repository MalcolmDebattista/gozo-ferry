# ADR 0001: Add a knowledge layer for ports, vessels and cancellation reasons

- Status: accepted
- Date: 2026-11-23
- Deciders: the operations manager, the data team
- Session: ARI3217 Session 7, Stages 16 and 17

## Context

Staff want to ask an assistant about cancellations. The operations log (data/gozo_operations_2025.csv, 77 cancelled
crossings in 2025) holds the date, the time, the vessel, the port of departure and the reason, written by whoever
was on duty. It says nothing about what the words mean, and they are not written the same way twice
(`gozo-ask profile`):

- Mġarr is written six ways (Mġarr, Mgarr, mgarr, MGARR, Mgarr Harbour, "Mġarr, Gozo"), and Ċirkewwa four;
- there are 14 reasons, worded freely; none says whether it is weather, technical or operational;
- 29 times are written without a leading zero (5:00 for 05:00).

Asked through the log alone, every staff question goes wrong (`gozo-ask questions --route keyword`):

| Question | Keyword search | Right answer |
|---|---|---|
| How many crossings from Mġarr were cancelled? | 12 for "Mġarr", 22 for "Mgarr": neither | 34 |
| How many cancellations did the weather cause? | 0: no reason says "weather" | 61 |
| Which vessel had the most technical cancellations? | none: no reason says "technical" | MV Ramla (5) |
| How many cancellations were caused by poor visibility? | 2: misses "fog" | 4 |

The data passes every check from Sessions 5 and 6. The problem is meaning, not quality.

The last question is our own. All four visibility cancellations fall on days the wind data (gozo_ferry.csv) records
as sailed, with 2.6 to 5.1 knots of wind: the wind model cannot warn about fog, and without a taxonomy of reasons
nobody could count how often that matters.

## Options considered

1. Do nothing, and improve the assistant's prompt. Rejected: a prompt cannot know that "swell over 3 m" is weather
   or that "Mgarr Harbour" is Mġarr, and a model that guesses gives a different count each time.
2. Clean the log: rewrite the port to one spelling and add a reason-group column. Cheapest, and enough for the first
   three questions. Rejected: it changes what staff wrote, so a mistake in the cleaning cannot be seen or undone; one
   column cannot hold two levels (weather, then wind); and every new log, or a second operator's, needs the same
   cleaning again.
3. A knowledge layer: ports with every spelling, vessels, a taxonomy of reasons and the staff vocabulary, as reviewed
   files of their own, with the log linked to them. Chosen.

## Decision

Keep the operator's knowledge in kg/ as a versioned release of reviewed files, written against an explicit schema
(kg/schema.yaml): ports with every spelling as a label, vessels, the reasons (weather above wind, sea and
visibility; technical; operational) and the staff vocabulary. Release v1.0 covers the 2025 log. Build it into an
RDF graph with rdflib (Stage 17): the reasons as a SKOS concept scheme, the spellings as `skos:altLabel`, the staff
words as `skos:hiddenLabel`, and the questions answered in SPARQL. The log stays as written; the graph keeps what
staff wrote beside what it was taken to mean.

**The key of a cancellation.** The log has no identifier, so one is chosen from the data: **date + scheduled time +
vessel**. A vessel can make one crossing at a time, so the three name one crossing.

- Date + time is not enough: twice in 2025 two vessels were cancelled at the same time, one from each port.
- Date + vessel is not enough: 11 times a vessel lost more than one crossing on the same day.
- Date + time + vessel is unique in all 77 rows (`gozo-ask profile`; `test_the_cancellation_key_is_unique`).
- The port is not part of the key. Its spelling varies, and it follows from the vessel and the time anyway.
- The time is normalised to HH:MM first. Otherwise 5:00 and 05:00 would mint two IRIs for one crossing, and a second
  load would add a duplicate.

Each cancellation's IRI is minted from the key, for example
`https://ari3217.example.org/gozo/cancellation/2025-01-05/0500/dwejra`. Loading twice therefore changes nothing:
`make kg-check` requires the same SHA-256 after a second load.

## Consequences

- A spelling that is not in kg/ports.yaml stops the link with an error, and `make ci` fails. Adding a spelling is a
  reviewed change to the knowledge, not a silent guess.
- Someone must own the taxonomy. Some changes are decisions about meaning, not corrections, and are recorded in
  kg/reasons.yaml: a gale warning counts as wind; heavy swell at the harbour entrance counts as sea state, not as
  operational.
- One more artefact to build, version and check: the graph is derived from the files and the log, and is rebuilt
  whenever either changes. A knowledge release is a git tag that records the store's SHA-256.
- The answers are only as good as the vocabulary: a staff word that is not in kg/synonyms.yaml finds nothing.
- Revisit this decision if the log stays this small and staff agree to pick from fixed lists when they type it: the
  spelling problem would then disappear at the source. Revisit it in the other direction if a second operator's log
  or the port authority's weather notices are added: each makes the case stronger.
