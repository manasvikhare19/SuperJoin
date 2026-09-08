# Non-Financial Generalization Dataset: Climate Science & Physical Indicators

This directory contains an independent non-financial test dataset designed to verify that the fact extraction, normalization, and relationship reasoning pipelines are fully domain-agnostic.

## Included Documents

1. **`01-climate-change-indicators-summary.pdf`**
   - **Publisher**: National Oceanic and Atmospheric Administration (NOAA)
   - **Published**: March 2024
   - **Coverage**: Global atmospheric greenhouse gas concentrations, mean surface temperature anomalies, cryospheric satellite observations, and renewable power infrastructure metrics for 2023.

2. **`02-wmo-global-climate-report.pdf`**
   - **Publisher**: World Meteorological Organization (WMO)
   - **Published**: April 2024
   - **Coverage**: Consolidated meteorological synthesis covering atmospheric CO2 measurements (2022 and 2023), surface temperature anomalies, Antarctic sea ice extent, and global renewable power installations (2022 and 2023).

## Physical Units & Metrics Evaluated

- **Atmospheric Concentrations**: `ppm` (parts per million), `ppb` (parts per billion)
- **Temperature Anomalies**: `°C` (degrees Celsius relative to 1850–1900 baseline)
- **Surface Area Extent**: `million sq km` (satellite cryosphere extent)
- **Power Capacity**: `GW` (gigawatts of renewable energy additions)

## Test Coverage

Automated tests in `tests/test_non_financial_generalization.py` verify:
- **Domain-Agnostic Extraction**: Extraction of physical numbers, non-financial entities, and scientific units without hardcoded rules.
- **Physical Unit Dimensional Guardrail**: Rejection of cross-dimensional comparisons (e.g. `ppm` vs `°C`) as `UNRELATED` rather than false contradictions.
- **Cross-Document Corroboration**: Multi-source corroboration of identical scientific observations (e.g. 421.5 ppm CO2 in 2023 across NOAA and WMO).
- **Temporal Distinction**: Classification of multi-year observational shifts (2022 vs 2023) as `TEMPORALLY_DISTINCT`.
