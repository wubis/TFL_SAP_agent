# Source Collection

[Step 1 build guide](../docs/build/01-source-collection.md) · [Source manifest](source-manifest.json)

The first pass records six candidate trial families. Two have verified SAP-to-shell pairings, one has an authentic table with a version pairing still to confirm, one has a linked supplement whose contents need inspection, and two currently have a SAP only. The proposed split is three development families and three held-out families. Freeze it once the selected families and shell coverage are confirmed.

## Calibration family

Start with **NCT03469934 (ANB020-004)**. It has a continuous FEV1 summary table, a mean eosinophil profile figure, and a subject-level spirometry listing. The PDF's front page ties the three shell documents to the same SAP date. The table and listing share an endpoint, while the figure exercises a different analysis population. The manifest records both section-local and printed CSR page numbers because numbering restarts in each section. [ClinicalTrials.gov statistical methods bundle](https://cdn.clinicaltrials.gov/large-docs/34/NCT03469934/SAP_001.pdf)

For any bundle that contains both SAP text and shell pages, put the selected shell pages on the input side and restrict the evidence collection to the selected SAP text. This prevents the agent from citing the shell itself as evidence. Preserve the original page numbering in the provenance record. The manifest links to the public copies and records the known redistribution status. The initial verification used indexed PDF text because the workspace could not download the calibration PDF. Check the figure artwork against the original PDF during intake.

## Finish the collection

1. Confirm the exact version pairing for the MARCH-PFIC table and inspect the actual subject-level listing. The listing is indexed in the public bundle. [MARCH-PFIC SAP and shells](https://cdn.clinicaltrials.gov/large-docs/30/NCT03905330/SAP_001.pdf)
2. Open TARVA Additional file 1 and select a continuous-outcome table. Check for authentic shells for inTandem3 and DEVOTE. If authentic coverage is insufficient, record the TA's agreed mix and build clearly labeled, unpopulated fixtures against the identified SAPs. [TARVA published SAP and supplement](https://link.springer.com/article/10.1186/s13063-019-3973-4)
3. Confirm that the held-out families cover tables, figures, and listings. E-SEE provides the first two. A verified listing layout is the main gap. [E-SEE SAP and Appendix A](https://www.york.ac.uk/media/healthsciences/documents/research/public-health/e-see/1_Statistical%20Analysis%20Plan%20%28main%20trial%29.pdf)
4. Record the team's owners for acquisition, annotation, implementation, and evaluation, plus the TA's decisions on shell mix, annotation review, and demo format. Freeze the final split by family before agent development.
