# Source Collection

[Step 1 build guide](../docs/build/01-source-collection.md) · [Source manifest](source-manifest.json)

The six-family split was frozen on November 13, 2026. Each family has a public SAP and at least one authentic unpopulated shell. Both partitions cover tables, figures, and listings. The manifest retains inTandem3 and DEVOTE as reserve sources because their authentic shells have yet to be verified. APRIL and TAPS-2 replaced them in the selected corpus.

| Partition | Trial family | Selected shells |
| --- | --- | --- |
| Development | ANB020-004 (`NCT03469934`) | FEV1 table, mean eosinophil profile, spirometry listing |
| Development | TARVA (`NCT02128555`) | Table S4, MOXFQ outcomes at 26 and 52 weeks |
| Development | APRIL (`ISRCTN12368131`) | Appendix Table 3, continuous patient-reported outcomes |
| Held out | MARCH-PFIC (`NCT03905330`) | Serum bile acid table and subject-level listing |
| Held out | E-SEE (`ISRCTN11079129`) | ASQ:SE-2 summary table and mean profile figure |
| Held out | TAPS-2 (`NCT03975894`) | Table 4, birthweight row and supporting headers |

MARCH-PFIC's paired SAP version is inferred from the shared protocol amendment, project code, bundle, and matching planned outputs. The two shell documents have their own version dates. [MARCH-PFIC SAP and shells](https://cdn.clinicaltrials.gov/large-docs/30/NCT03905330/SAP_001.pdf)

## Calibration family

Start with **NCT03469934 (ANB020-004)**. It has a continuous FEV1 summary table, a mean eosinophil profile figure, and a subject-level spirometry listing. The PDF's front page ties the three shell documents to the same SAP date. The table and listing share an endpoint, while the figure exercises a different analysis population. The manifest records both section-local and printed CSR page numbers because numbering restarts in each section. [ClinicalTrials.gov statistical methods bundle](https://cdn.clinicaltrials.gov/large-docs/34/NCT03469934/SAP_001.pdf)

The calibration manifest also includes the original PDF's SHA-256 checksum and inclusive, one-based `pdf_pages` ranges for intake.

For any bundle that contains both SAP text and shell pages, put the selected shell pages on the input side and restrict the evidence collection to the selected SAP text. This prevents the agent from citing the shell itself as evidence. Preserve the original page numbering in the provenance record. The manifest links to the public copies and records the known redistribution status. The original calibration PDF was checked during [Step 2](../benchmark/README.md). The figure includes illustrative points, with final axes and time points left to the actual study data.

## Annotation handoff

The [benchmark](../benchmark/README.md) covers all six selected families. One [constructed FEV1 challenge](shells/anb020-004-fev1-challenge.md) stays with ANB020-004 in development. Team ownership, any additional review requirements, and demo format still need to be recorded.
