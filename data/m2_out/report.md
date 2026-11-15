# M2 Neighbour Evidence - results

Evidence label: **Adjusted association from observational satellite data**.

Limits (every output):
- unobserved management (hybrid, nitrogen rate, tillage) can bias the estimates
- greenness and ESI are stress proxies, not yield
- CSB / CDL crop classes can be wrong

gamma = extra effect of the treated arm in drought seasons beyond its effect in normal seasons (neighbours under the same weather).
Expected sign for 'resilience' by treatment: T1 (continuous crop) negative; T2-T5 positive.

## Does the outcome see the drought?

| crop     | outcome      |   drought_coef |     se |       t |   sd_units |    n |   squares | sees_drought   |
|:---------|:-------------|---------------:|-------:|--------:|-----------:|-----:|----------:|:---------------|
| corn     | peak_ndvi    |        -0.0034 | 0.0023 | -1.4848 |    -0.1385 | 1003 |       253 | False          |
| corn     | ndwi_jul_aug |        -0.0045 | 0.0058 | -0.7837 |    -0.0761 | 1003 |       253 | False          |
| corn     | late_ndvi    |        -0.0079 | 0.0092 | -0.8618 |    -0.0723 | 1003 |       253 | False          |
| corn     | ndvi_area    |         0.0077 | 0.4346 |  0.0176 |     0.0018 | 1003 |       253 | False          |
| soybeans | peak_ndvi    |        -0.0079 | 0.0031 | -2.5229 |    -0.2067 |  812 |       260 | True           |
| soybeans | ndwi_jul_aug |         0.0216 | 0.0073 |  2.9581 |     0.2474 |  812 |       260 | True           |
| soybeans | late_ndvi    |        -0.0354 | 0.0088 | -4.0338 |    -0.3683 |  812 |       260 | True           |
| soybeans | ndvi_area    |         0.1153 | 0.5024 |  0.2296 |     0.0218 |  812 |       260 | False          |

## Estimates

none

## Abstentions

- corn T1: drought: arm size (72, 135) < 100
- corn T2: drought: arm size (2, 207) < 100; drought: only 0 squares with both arms inside a square-year; normal: arm size (16, 778) < 100
- corn T3: drought: arm size (3, 206) < 100; drought: only 1 squares with both arms inside a square-year; normal: arm size (15, 779) < 100
- corn T5: drought: arm size (137, 72) < 100
- soybeans T1: drought: arm size (4, 153) < 100; drought: only 0 squares with both arms inside a square-year; normal: arm size (25, 623) < 100
- soybeans T2: drought: arm size (2, 155) < 100; drought: only 1 squares with both arms inside a square-year; normal: arm size (12, 643) < 100
- soybeans T3: drought: arm size (3, 154) < 100; drought: only 1 squares with both arms inside a square-year; normal: arm size (8, 647) < 100; normal: only 1 squares with both arms inside a square-year
- soybeans T5: drought: arm size (153, 4) < 100; drought: only 0 squares with both arms inside a square-year; normal: arm size (630, 25) < 100
