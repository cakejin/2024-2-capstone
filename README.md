# 2024-2 Capstone Project

S&P 500 산업군 내 공적분 페어를 찾아 평균회귀(볼린저 밴드 / z-score) 전략으로 백테스트하는 프로젝트.

## 구성

| 경로 | 내용 |
|---|---|
| `capstone_test_1.ipynb` | 원본 노트북 (2024-12). 페어 선정 + backtrader 백테스트 |
| `csv/stable_pairs.csv` | 2023년 데이터로 선정한 산업군별 50개 페어 |
| `backtest_csv/`, `trades_csv/`, `result/`, `bollinger_band/` | 원본 노트북의 입력 데이터와 산출물 |
| `pairs_backtest.py` | 수정판 백테스트 스크립트 (2026-10 추가). 아래 참고 |
| `results_v2/` | 수정판 산출물 (페어별 표, 일별 수익률, 요약, 그래프) |

## 수정판 백테스트 (`pairs_backtest.py`)

원본 노트북의 다음 문제를 고친 독립 스크립트.

1. 스프레드를 `log(T2) - beta*log(T1)`로 정의하고 beta는 형성 기간 OLS로만 추정 (원본은 단순 종가 차이, 10주:10주).
2. 포지션을 beta 가중 달러 노출로 잡아 페어당 명목이 `capital`로 통일됨 (원본은 주가 수준에 따라 명목이 수십 배 차이).
3. 청산을 z-score 0 복귀로 변경 (원본은 밴드 재진입 즉시 청산, 평균 보유 2.6일).
4. 일별 평가손익을 기록해 수익률, 변동성, Sharpe, MDD, 시장 beta/alpha를 계산.
5. 벤치마크를 S&P 500 단순 비교가 아니라 3개월 T-bill 초과수익과 S&P 500 대비 alpha/beta 회귀로 변경.

정보 유출 방지: 선정/beta는 형성 기간만, z-score는 과거 lookback 일만, 신호는 t일 종가, 체결은 t+1일 시가.
남은 한계: 유니버스가 현재 S&P 500 구성 종목이라 생존 편향이 있음 (yfinance는 상폐 종목 미제공).

```bash
pip install -r requirements.txt
python pairs_backtest.py h1        # 보고서의 50개 페어: 2023 형성 / 2024 상반기 거래
python pairs_backtest.py rolling   # 2015~2024: 12개월 형성 / 6개월 거래 롤링 (전 종목 가격 다운로드, 수 분 소요)
# 옵션: --sizing beta|dollar --lookback 30 --entry 2 --exit 0 --stop-z 0 --capital 10000 --cost-bps 5 --tag _이름
```

`--sizing beta`(기본)는 형성 기간 OLS beta로 두 다리의 달러 비중을 정하고 beta<=0인 페어는 제외한다.
`--sizing dollar`는 beta=1로 두고 1:1 달러 중립으로 잡는다. 두 결과를 함께 보고하는 것을 권장.

가격 데이터는 `data/`에 캐시된다 (git 제외).
