# 2024 상반기 수정판 백테스트 요약

## 전략 (비용 차감, committed capital 기준)

| 지표 | 값 |
|---|---|
| Days | 124 |
| TotalReturnPct | 2.01 |
| RfReturnPct | 2.61 |
| ExcessReturnPct | -0.57 |
| AnnReturnPct | 4.13 |
| AnnVolPct | 1.96 |
| Sharpe | -0.59 |
| MaxDrawdownPct | -1.0 |
| Beta | -0.058 |
| Beta_t | -4.15 |
| AlphaAnnPct | 0.17 |
| Alpha_t | 0.06 |

## 전략 (비용 미차감)

| 지표 | 값 |
|---|---|
| Days | 124 |
| TotalReturnPct | 2.36 |
| RfReturnPct | 2.61 |
| ExcessReturnPct | -0.23 |
| AnnReturnPct | 4.85 |
| AnnVolPct | 1.97 |
| Sharpe | -0.24 |
| MaxDrawdownPct | -0.93 |
| Beta | -0.058 |
| Beta_t | -4.13 |
| AlphaAnnPct | 0.86 |
| Alpha_t | 0.29 |

## 전략 (fully-invested 자본 기준, 비용 차감)

| 지표 | 값 |
|---|---|
| Days | 124 |
| TotalReturnPct | 1.63 |
| RfReturnPct | 2.61 |
| ExcessReturnPct | -0.92 |
| AnnReturnPct | 3.35 |
| AnnVolPct | 3.62 |
| Sharpe | -0.52 |
| MaxDrawdownPct | -2.48 |
| Beta | -0.09 |
| Beta_t | -3.49 |
| AlphaAnnPct | 0.18 |
| Alpha_t | 0.03 |

## S&P 500 (^GSPC, 가격지수)

| 지표 | 값 |
|---|---|
| Days | 124 |
| TotalReturnPct | 14.48 |
| RfReturnPct | 2.61 |
| ExcessReturnPct | 11.24 |
| AnnReturnPct | 31.63 |
| AnnVolPct | 10.72 |
| Sharpe | 2.13 |
| MaxDrawdownPct | -5.46 |

## 거래 요약

| 지표 | 값 |
|---|---|
| Pairs | 39 |
| TotalTrades | 131 |
| AvgTradesPerPair | 3.4 |
| WinRate | 0.595 |
| AvgHoldDays | 19.8 |
| PairsPositive | 18 |
| ForcedCloses | 15 |
| BestPair | EL-KVUE 11.929% |
| WorstPair | INTC-MU -38.234% |
| Params | sizing=beta lookback=30 entry=2.0 exit=0.0 stop_z=0.0 cost=5.0bps capital=10000 |
