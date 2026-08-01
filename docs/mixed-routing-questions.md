# Mixed-routing questions (SQL + prose)

Questions that require **both** knowledge-base halves in one turn: a precise
fact only the relational DB has (minute, score, referee, lineup) plus a
"how was it seen / what was the story" clause only the prose index has.
Questions where prose happens to contain the number too (e.g. "who won the
final and was it controversial?") can legitimately resolve with prose alone,
so they make weaker routing tests.

Intended as seed material for the offline-evaluation ground-truth set.

## Verified live (2026-08-01)

Each of these routed to `execute_sql` **and** `search_prose` in a single turn.

1. **What was the score when Argentina lost in the group stage, and how big
   an upset was that considered?**
   SQL: Saudi Arabia 2–1 (fixtures). Prose: "biggest upset" framing
   (main article, Group stage).
2. **In what minutes did Japan score against Spain, and what was
   controversial about the winning goal?**
   SQL: goal minutes (events). Prose: ball-over-the-line VAR story
   (controversies, Match incidents).
3. **Who refereed the final, and were there any officiating controversies at
   the tournament?**
   SQL: `fixture__referee` (fixtures). Prose: Officiating section
   (main article).

## Candidates (corpus material exists on both sides; not yet run)

4. **How many goals did Mbappé score in the final and in what minutes — and
   how was his performance written about afterwards?**
   SQL: events. Prose: final article, Match / Post-match.
5. **Which teams played the opening match and what was the score — and what
   happened at the opening ceremony?**
   SQL: fixtures. Prose: opening ceremony article.
6. **Did Ronaldo start Portugal's knockout matches, and what was the story
   around his benching?**
   SQL: lineups / events. Prose: knockout stage article.
7. **Who finished top of Iran's group, and what protests surrounded the
   Iranian team?**
   SQL: standings. Prose: controversies, Iranian protests.
8. **What was the score in the third-place match, and how was Croatia's
   tournament regarded?**
   SQL: fixtures. Prose: knockout stage article, Match for third place.
