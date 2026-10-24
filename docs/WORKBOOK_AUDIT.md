# Workbook audit - MINOR_PROJECT_DONE_BY_KRUSHNA.xlsm

The workbook was read with openpyxl (formulas, values, tables) and left unchanged. Findings are compared with the supplied IS 10262:2019 text.

| ID | Location | Severity | Issue | Detail |
|---|---|---|---|---|
| W1 | CALCULATIONS C3/C4 + TABLES | High | Standard deviation S and factor X tables differ from IS 10262:2019 Tables 1-2. | Workbook has S=5 for M65-M80 (IS: 6.0) and X=7 for M35/M40 (IS: 6.5), X=8..11 for M45-M80 (IS: 6.5 up to M60, 8.0 for M65+), X=5 for M20 (IS: 5.5), X=6 for M25 (5.5). |
| W2 | CALCULATIONS C5 | High | Target strength uses fck+1.65S OR fck+X chosen by a flag ('S'), not the larger of both. | IS 10262 cl. 4.2 requires f'ck = the HIGHER of the two. |
| W3 | CALCULATIONS C6 | High | w/c is a hard-coded step function of grade, not read from Fig. 1 / Table 8 and not linked to the target strength or cement grade. | e.g. every grade above M50 gets 0.35 regardless of M55 vs M80. |
| W4 | CALCULATIONS C7-C9 | High | Slump is applied twice. | TABLES J:K already lists 186/191/197/202 kg (which include the slump increase); C8 then multiplies by a further 0/3/6/9 %. For 120 mm: 202 x 1.09 = 220 kg instead of ~202. |
| W5 | CALCULATIONS C7 | Medium | Water content ignores nominal maximum aggregate size and aggregate shape. | IS 10262 Table 4 / Table 7 depend on msa (10/20/40 mm); shape reductions of 10-20 kg apply. |
| W6 | CALCULATIONS C10 | High | Plasticiser dose % is subtracted directly as water reduction. | Dose and water reduction are different quantities (Annex G: 0.5-1.5 % dose gives 15-30 %+ reduction, found by trials). 1 % dose -> 1 % reduction is unsupported. |
| W7 | CALCULATIONS C11-C13 | Medium | Fly ash is carved out of the cement mass, and no 10 % binder increase / durability minimum / maximum-cement check is made. | Acceptable only if intended; but Fly-ash and admixture volumes are then ignored (W8). |
| W8 | CALCULATIONS C17 | High | Absolute-volume equation omits fly ash and admixture volumes. | Aggregate volume is over-estimated whenever fly ash or plasticiser is used. |
| W9 | CALCULATIONS C14-C20 / INPUT B15:B16 | High | One SG/absorption per 'aggregate type' and a manual fine:coarse split (e.g. 50:50). | IS 10262 Tables 5/10 give the coarse fraction from msa, fine-aggregate zone and w/cm (0.01 per 0.05 w/cm). SG of coarse and fine are separate (2.74 / 2.65 in Annexes). |
| W10 | TABLES W:X / INPUT B14 | Medium | Air content table (3/2/1 %) is not the IS value (1.5/1.0/0.8 %) and INPUT!B14 (air) is never used. | C16 reads the TABLES lookup, ignoring the input cell. |
| W11 | CALCULATIONS C21-C22 | Medium | Extra water for dry aggregate is applied to total aggregate with a single absorption (2 % for 'NORMAL'); IS examples use 0.5 % (CA) and 1.0 % (FA), and aggregate masses are not converted to dry masses. | Per Annex A-11: dry mass = SSD/(1+abs), extra water = difference, per aggregate. |
| W12 | OUTPUT B12, B14 | High | Status formula applies VALUE(MID(B2,2,3)) to a NUMERIC target strength. | MID of 78.25 returns '8.2' -> threshold 82 kg/m3, so the 'cement >= grade x 10' test is meaningless (and the rule itself is not in IS 10262). |
| W13 | OUTPUT B17:B18 | Low | Density check sums only some components (admixture excluded) against an arbitrary 2300-2600 window. | Use mass balance + absolute-volume identity; density window is only a plausibility hint. |
| W14 | VBA project | Info | The .xlsm contains a vbaProject.bin whose module list shows only the default Sheet/ThisWorkbook stubs; no custom macro source could be extracted here (no oletools available offline). | VBA functionality could not be inspected in detail - disclosed limitation. |
| R1 | Project report section 4.1 | Medium | Comparison table labels water (191.5, 201, 141 kg) as 'W/C'; the 'Coarse aggregate' of the developed sheet is 1021.67 for M40/75 mm vs IS 1228; the Excel M40 input sheet shows fly ash 0 % but the compared IS example B uses 30 %. | Re-label columns and compare like-for-like inputs before presenting. |
