# 2024 상반기 수정판 백테스트 요약_dollar

## 전략 (비용 차감, committed capital 기준)

| 지표 | 값 |
|---|---|
| Days | 124 |
| TotalReturnPct | -0.96 |
| RfReturnPct | 2.61 |
| ExcessReturnPct | -3.52 |
| AnnReturnPct | -1.94 |
| AnnVolPct | 2.3 |
| Sharpe | -3.11 |
| MaxDrawdownPct | -2.62 |
| Beta | -0.033 |
| Beta_t | -1.87 |
| AlphaAnnPct | -6.41 |
| Alpha_t | -1.98 |

## 전략 (비용 미차감)

| 지표 | 값 |
|---|---|
| Days | 124 |
| TotalReturnPct | -0.63 |
| RfReturnPct | 2.61 |
| ExcessReturnPct | -3.19 |
| AnnReturnPct | -1.28 |
| AnnVolPct | 2.3 |
| Sharpe | -2.83 |
| MaxDrawdownPct | -2.39 |
| Beta | -0.033 |
| Beta_t | -1.87 |
| AlphaAnnPct | -5.74 |
| Alpha_t | -1.76 |

## 전략 (fully-invested 자본 기준, 비용 차감)

| 지표 | 값 |
|---|---|
| Days | 124 |
| TotalReturnPct | -0.87 |
| RfReturnPct | 2.61 |
| ExcessReturnPct | -3.29 |
| AnnReturnPct | -1.77 |
| AnnVolPct | 8.06 |
| Sharpe | -0.83 |
| MaxDrawdownPct | -6.86 |
| Beta | -0.078 |
| Beta_t | -1.69 |
| AlphaAnnPct | -4.91 |
| Alpha_t | -0.5 |

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
| Pairs | 45 |
| TotalTrades | 147 |
| AvgTradesPerPair | 3.3 |
| WinRate | 0.571 |
| AvgHoldDays | 21.0 |
| PairsPositive | 17 |
| ForcedCloses | 23 |
| BestPair | EL-KVUE 6.957% |
| WorstPair | PARA-DIS -49.788% |
| Params | sizing=dollar lookback=30 entry=2.0 exit=0.0 stop_z=0.0 cost=5.0bps capital=10000 |
