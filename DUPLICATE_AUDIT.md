# Cross-source duplicate review — 10 September 2026

Read-only comparison of the production `/events` catalogue (89 canonical records). No records,
subscriptions, watchlists, or alerts were merged or deleted. Candidate IDs are a snapshot, not
instructions for an automatic merge.

| Event IDs | Concert | Finding |
| --- | --- | --- |
| 80 / 36 | Young K | Same performance time; punctuation and Star Theatre full venue name differ. |
| 75 / 32 | brb. half/lives | Same performance time; Singapore title suffix and SCAPE venue wording differ. |
| 50 / 29 | Khalid | Same performance time; Singapore suffix and Star Theatre full venue name differ. |
| 48 / 31 | Queens of the Stone Age | Same performance time; Singapore suffix and Star Theatre full venue name differ. |
| 46 / 21 | 5 Seconds of Summer, December 3 | Same title and performance time; Star Theatre venue wording differs. |
| 45 / 16 | 5 Seconds of Summer, November 16 | Same title and performance time; Star Theatre venue wording differs. |
| 73 / 40 | Mahiru | ONE-MAN LIVE TOUR versus ONE-MAN ASIA TOUR. Requires provider review despite matching date and venue. |
| 57 / 26 | Song Dongye | Bilingual versus English title, but Esplanade Theatre Studio and Esplanade Theatre are distinct halls. Do not assume equivalence. |

The matcher now recognizes two exact venue aliases: The Star Theatre's full complex name and
SCAPE's optional “The”. Existing punctuation/year/Singapore-suffix handling covers compatible
titles. Tests require equal performance timestamps and preserve different dates and distinct halls.
These rules improve matching of newly encountered source listings; they intentionally do not rewrite
already-linked listing identities or historical alert keys.

Cleaning up existing duplicates is separate work: confirm provider performance IDs and details,
choose a surviving event, and reconcile watch/alert references in one reviewed transaction. Fuzzy
automatic merging, a dashboard, and extra caching infrastructure remain deferred.
