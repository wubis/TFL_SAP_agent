# Source Collection and Provenance

[Project overview](../project-overview.md) · [Next step](02-benchmark-and-schema.md)

**Input** — The proposal's scope and candidate public SAPs and TFL shells.

## What to build

1. Assign owners for data collection, annotation, implementation, and evaluation. Confirm with the TA the acceptable authentic-to-constructed mix, annotation review requirements, and demo format. Start source discovery while those details are pending.
2. Find 6–8 two-arm trial families that collectively cover continuous-outcome summary tables, mean-by-visit figures, and simple subject-level endpoint listings. Confirm the intended SAP version for every shell. Use clearly labeled constructed shells where authentic matches are unavailable, within the agreed mix.
3. Create a source manifest with trial family ID, document ID, source or local path, date, version, linked SAP version, shell type, authenticity, and redistribution status. Keep unpopulated shells and their source documents available for later annotation and retrieval.
4. Assign whole families to development or held-out test. Keep each trial's versions, shells, and constructed variants together. Select one development family for annotation calibration and the first end-to-end run. Aim to cover all three shell types in the held-out set so each can be reported.

## Done when

The manifest contains 6–8 families and identifies the SAP version and provenance for every shell. Each family has exactly one partition, the split is frozen before agent development, and the calibration family is marked.
