[Back to Screener](https://quantpedia.com/screener)

# Time Series Momentum Effect

Bookmark

Share

[delete](https://www.linkedin.com/shareArticle?mini=true&url=https%3A%2F%2Fquantpedia.com%2Fstrategies%2Ftime-series-momentum-effect)[delete](https://twitter.com/intent/tweet?text=Time%20Series%20Momentum%20Effect%20https%3A%2F%2Fquantpedia.com%2Fstrategies%2Ftime-series-momentum-effect)[delete](https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fquantpedia.com%2Fstrategies%2Ftime-series-momentum-effect)[delete](mailto:?to=&subject=Time%20Series%20Momentum%20Effect&body=Time%20Series%20Momentum%20Effect%20https%3A%2F%2Fquantpedia.com%2Fstrategies%2Ftime-series-momentum-effect)

### Quantpedia is The Encyclopedia of Quantitative Trading Strategies

We've already analyzed tens of thousands of financial research papers and identified more than1000 attractive trading systems together with thundreds of related academic papers.

[Browse Strategies](https://quantpedia.com/screener)

- Unlock Screener & 300+ Advanced Charts
- Browse 1000+ uncommon trading strategy ideas
- Get new strategies on bi-weekly basis
- Explore 2000+ academic research papers
- View 800+ out-of-sample backtests
- Design multi-factor multi-asset portfolios

[Get subscription](https://quantpedia.com/pricing)

Traditional cross-sectional momentum is a popular and very well-documented anomaly. [Traditional momentum](https://quantpedia.com/strategies/asset-class-momentum-rotational-system/) uses a universe of assets to pick past winners, and it predicts that those winners will continue to outperform their peers in the future as well. However, recent academic research shows that we do not need the whole universe of assets to exploit the momentum effect.

A new version of this anomaly (Time Series Momentum) shows that each security's (or asset's) own past return is a future predictor. [The past 12-month excess return of each instrument is a positive predictor of its future return.](https://quantpedia.com/strategies/12-month-cycle-in-cross-section-of-stocks-returns/) A diversified portfolio of time-series momentum across all assets is remarkably stable and robust, yielding a high Sharpe ratio with little correlation to passive benchmarks.

An additional advantage is that time-series momentum returns appear to be largest when the stock market's returns are most extreme; hence, time-series momentum may be a hedge for extreme events.

## Fundamental reason

Academic research states that the time-series momentum effect is consistent with behavioral theories of investors' initial under-reaction and delayed over-reaction applied to information dissemination.

## Get Premium Strategy Ideas & Pro Reporting

- Unlock Screener & 300+ Advanced Charts
- Browse 1000+ unique strategies
- Get new strategies on bi-weekly basis
- Explore 2000+ academic research papers
- View 800+ out-of-sample backtests
- Design multi-factor multi-asset portfolios

[Get subscription](https://quantpedia.com/pricing)

## Keywords

[momentum](https://quantpedia.com/strategy-tags/momentum) [factor investing](https://quantpedia.com/strategy-tags/factor-investing) [smart beta](https://quantpedia.com/strategy-tags/smart-beta)

#### Market Factors

Equities

Bonds

Commodities

Currencies

#### Confidence in Anomaly's Validity

Strong

#### Period of Rebalancing

Monthly

#### Number of Traded Instruments

58

#### Complexity Evaluation

Moderate

#### Financial instruments

Futures

CFDs

#### Backtest period from source paper

1965 – 2009

#### Indicative Performance

20.7%

#### Notes to Indicative Performance

per annum, estimated alpha (using Fama&French factors) , annualized (geometrically) monthly return of 1,26%, data from Table 3 Panel A

#### Estimated Volatility

15.74%

#### Notes to Estimated Volatility

estimated from t-statistic 7.55, data from Table 3 Panel A

#### Maximum Drawdown

-33.87%

#### Notes to Maximum drawdown

not stated

#### Sharpe Ratio

1.31

#### Regions

Global

## Simple trading strategy

The investment universe consists of 24 commodity futures, 12 cross-currency pairs (with nine underlying currencies), nine developed equity indices, and 13 developed government bond futures.

Every month, the investor considers whether the excess return of each asset over the past 12 months is positive or negative and goes long on the contract if it is positive and short if negative. The position size is set to be inversely proportional to the instrument’s volatility. A univariate GARCH model is used to estimated ex-ante volatility in the source paper. However, other simple models could probably be easily used with good results (for example, the easiest one would be using historical volatility instead of estimated volatility). The portfolio is rebalanced monthly.

## Hedge for stocks during bear markets

Yes – Most of the research papers about momentum/trend-following strategies in futures mention the negative correlation of this strategy against equity market risk; therefore, the strategy can be used as a hedge/diversification to equity market risk factor during bear markets.

## Out-of-sample strategy implementation in QuantConnect (chart, statistics & code)

QuantConnect Shared Backtest Result - 118 Time Series Momentum Effect

- CHARTS
- CODE
- [CLONE](https://www.quantconnect.com/terminal/clone/32414426/35af8fcbe77b92bfcbbf7f5c17db636d/clone-of%3A-118-Time-Series-Momentum-Effect) 0

## Strategy Equity

1M3M1YALL

* * *

Sharpe Ratio0.3

Drawdown34%

Sortino Ratio0.4

PSR0.2%

Turnover8.4%

CAGR7.19%

Win Rate69%

Loss Rate31%

Info. Ratio-0.1

Total Orders16,410

https://quantpedia.com/strategies/time-series-momentum-effect/

Sharpe Ratio0.3

CAGR7.19%

Drawdown34%

Win Rate69%

Sortino Ratio0.4

Loss Rate31%

Probabilistic SR0.2%

Information Ratio-0.1

Turnover8.4%

Total Orders16,410

* * *

## Drawdown

1M3M1YALL

## Asset Sales Volume

1M3M1YALL

## Portfolio Margin

1M3M1YALL

## Exposure

1M3M1YALL

## Portfolio Turnover

1M3M1YALL

## Capacity

1M3M1YALL

## Win Rate

1M3M1YALL

## Rolling Sharpe Ratio

1M3M1YALL

main.pyresearch.ipynb

```
# https://quantpedia.com/strategies/time-series-momentum-effect/
#
# The investment universe consists of 24 commodity futures, 12 cross-currency pairs (with 9 underlying currencies), 9 developed equity indices, and 13 developed
# government bond futures.
# Every month, the investor considers whether the excess return of each asset over the past 12 months is positive or negative and goes long on the contract if it is
# positive and short if negative. The position size is set to be inversely proportional to the instrument’s volatility. A univariate GARCH model is used to estimated
# ex-ante volatility in the source paper. However, other simple models could probably be easily used with good results (for example, the easiest one would be using
# historical volatility instead of estimated volatility). The portfolio is rebalanced monthly.
#
# QC implementation changes:
#   - instead of GARCH model volatility, we have used simple historical volatility.

from math import sqrt
from AlgorithmImports import *
import numpy as np
import pandas as pd

class TimeSeriesMomentum(QCAlgorithm):

    def Initialize(self) -> None:
        self.SetStartDate(2000, 1, 1)
        self.SetCash(10_000_000)

        self.symbols: List[str] = [\
            "CME_S1",   # Soybean Futures, Continuous Contract\
            "CME_W1",   # Wheat Futures, Continuous Contract\
            "CME_SM1",  # Soybean Meal Futures, Continuous Contract\
            "CME_BO1",  # Soybean Oil Futures, Continuous Contract\
            "CME_C1",   # Corn Futures, Continuous Contract\
            "CME_O1",   # Oats Futures, Continuous Contract\
            "CME_LC1",  # Live Cattle Futures, Continuous Contract\
            "CME_FC1",  # Feeder Cattle Futures, Continuous Contract\
            "CME_LN1",  # Lean Hog Futures, Continuous Contract\
            "CME_GC1",  # Gold Futures, Continuous Contract\
            "CME_SI1",  # Silver Futures, Continuous Contract\
            "CME_PL1",  # Platinum Futures, Continuous Contract\
            "CME_CL1",  # Crude Oil Futures, Continuous Contract\
            "CME_HG1",  # Copper Futures, Continuous Contract\
            "CME_LB1",  # Random Length Lumber Futures, Continuous Contract\
            "CME_NG1",  # Natural Gas (Henry Hub) Physical Futures, Continuous Contract\
            "CME_PA1",  # Palladium Futures, Continuous Contract\
            "CME_RR1",  # Rough Rice Futures, Continuous Contract\
            "CME_DA1",  # Class III Milk Futures\
            "CME_RB1",  # Gasoline Futures, Continuous Contract\
            "CME_KW1",  # Wheat Kansas, Continuous Contract\
\
            "ICE_CC1",  # Cocoa Futures, Continuous Contract\
            "ICE_CT1",  # Cotton No. 2 Futures, Continuous Contract\
            "ICE_KC1",  # Coffee C Futures, Continuous Contract\
            "ICE_O1",   # Heating Oil Futures, Continuous Contract\
            "ICE_OJ1",  # Orange Juice Futures, Continuous Contract\
            "ICE_SB1",  # Sugar No. 11 Futures, Continuous Contract\
            "ICE_RS1",  # Canola Futures, Continuous Contract\
            "ICE_GO1",  # Gas Oil Futures, Continuous Contract\
            "ICE_WT1",  # WTI Crude Futures, Continuous Contract\
\
            "CME_AD1", # Australian Dollar Futures, Continuous Contract #1\
            "CME_BP1", # British Pound Futures, Continuous Contract #1\
            "CME_CD1", # Canadian Dollar Futures, Continuous Contract #1\
            "CME_EC1", # Euro FX Futures, Continuous Contract #1\
            "CME_JY1", # Japanese Yen Futures, Continuous Contract #1\
            "CME_MP1", # Mexican Peso Futures, Continuous Contract #1\
            "CME_NE1", # New Zealand Dollar Futures, Continuous Contract #1\
            "CME_SF1", # Swiss Franc Futures, Continuous Contract #1\
\
            "ICE_DX1",      # US Dollar Index Futures, Continuous Contract #1\
            "CME_NQ1",      # E-mini NASDAQ 100 Futures, Continuous Contract #1\
            "EUREX_FDAX1",  # DAX Futures, Continuous Contract #1\
            "CME_ES1",      # E-mini S&P 500 Futures, Continuous Contract #1\
            "EUREX_FSMI1",  # SMI Futures, Continuous Contract #1\
            "EUREX_FSTX1",  # STOXX Europe 50 Index Futures, Continuous Contract #1\
            "LIFFE_FCE1",   # CAC40 Index Futures, Continuous Contract #1\
            "LIFFE_Z1",     # FTSE 100 Index Futures, Continuous Contract #1\
            "SGX_NK1",      # SGX Nikkei 225 Index Futures, Continuous Contract #1\
            "CME_MD1",      # E-mini S&P MidCap 400 Futures\
\
            "CME_TY1",      # 10 Yr Note Futures, Continuous Contract #1\
            "CME_FV1",      # 5 Yr Note Futures, Continuous Contract #1\
            "CME_TU1",      # 2 Yr Note Futures, Continuous Contract #1\
            "ASX_XT1",     # 10 Year Commonwealth Treasury Bond Futures, Continuous Contract #1   # 'Settlement price' instead of 'settle' on quandl.\
            "ASX_YT1",     # 3 Year Commonwealth Treasury Bond Futures, Continuous Contract #1    # 'Settlement price' instead of 'settle' on quandl.\
            "EUREX_FGBL1",  # Euro-Bund (10Y) Futures, Continuous Contract #1\
            "EUREX_FBTP1", # Long-Term Euro-BTP Futures, Continuous Contract #1\
            "EUREX_FGBM1",  # Euro-Bobl Futures, Continuous Contract #1\
            "EUREX_FGBS1",  # Euro-Schatz Futures, Continuous Contract #1\
            "SGX_JB1",      # SGX 10-Year Mini Japanese Government Bond Futures\
            "LIFFE_R1"      # Long Gilt Futures, Continuous Contract #1\
            "MX_CGB1",     # Ten-Year Government of Canada Bond Futures, Continuous Contract #1    # 'Settlement price' instead of 'settle' on quandl.\
        ]

        self.period: int = 12 * 21
        self.SetWarmUp(self.period, Resolution.Daily)

        self.targeted_volatility: float = .1
        self.vol_target_period: int = 60
        self.leverage_cap: int = 4
        leverage: int = 20

        # Daily rolled data.
        self.data: Dict[str, RollingWindow] = {}

        for symbol in self.symbols:
            # Back adjusted and spliced data import.
            data: Security = self.AddData(QuantpediaFutures, symbol, Resolution.Daily)

            data.SetFeeModel(CustomFeeModel())
            data.SetLeverage(leverage)

            self.data[symbol] = RollingWindow[float](self.period)

        self.recent_month: int = -1
        self.Settings.MinimumOrderMarginPortfolioPercentage = 0.
        self.settings.daily_precise_end_time = False

    def OnData(self, slice: Slice) -> None:
        custom_data_last_update_date: Dict[str, datetime.date] = QuantpediaFutures.get_last_update_date()

        # Store daily data.
        for symbol in self.symbols:
            if slice.contains_key(symbol) and slice[symbol]:
                price = slice[symbol].Value
                self.data[symbol].Add(price)

        if self.recent_month == self.Time.month:
            return
        self.recent_month = self.Time.month

        # Performance and volatility data.
        performance_volatility: Dict[str, Tuple[float, float]] = {}
        daily_returns: Dict[str, float] = {}

        for symbol in self.symbols:
            if self.data[symbol].IsReady:
                # check if data is still coming
                if self.Securities[symbol].GetLastData() and self.time.date() > custom_data_last_update_date[symbol]:
                    self.liquidate(symbol)
                    continue

                back_adjusted_prices: np.ndarray = np.array([x for x in self.data[symbol]])
                performance: float = back_adjusted_prices[0] / back_adjusted_prices[-1] - 1
                daily_rets: np.ndarray = back_adjusted_prices[:-1] / back_adjusted_prices[1:] - 1

                back_adjusted_prices: np.ndarray = back_adjusted_prices[:self.vol_target_period]
                daily_rets: np.ndarray = back_adjusted_prices[:-1] / back_adjusted_prices[1:] - 1
                volatility_3M: float = np.std(daily_rets) * sqrt(252)
                daily_returns[symbol] = daily_rets[::-1][:self.vol_target_period]

                performance_volatility[symbol] = (performance, volatility_3M)

        if len(performance_volatility) == 0: return

        # Performance sorting.
        long: List[str] = [x[0] for x in performance_volatility.items() if x[1][0] > 0]
        short: List[str] = [x[0] for x in performance_volatility.items() if x[1][0] < 0]

        weight_by_symbol: Dict[str, float] = {}

        # Volatility weighting long and short leg separately.
        ls_leverage: List[float] = [] # long and short leverage

        for sym_i, symbols in enumerate([long, short]):
            total_volatility: float = sum([1/performance_volatility[x][1] for x in symbols])

            # Inverse volatility weighting.
            weights: np.ndarray = np.array([(1/performance_volatility[x][1]) / total_volatility for x in symbols])
            weights_sum: float = sum(weights)
            weights: float = weights/weights_sum

            df: DataFrame = pd.DataFrame()
            i: int = 0
            for symbol in symbols:
                df[str(symbol)] = [x for x in daily_returns[symbol]]
                weight_by_symbol[symbol] = weights[i] if sym_i == 0 else -weights[i]
                i += 1

            # volatility targeting
            portfolio_vol: float = np.sqrt(np.dot(weights.T, np.dot(df.cov() * 252, weights.T)))
            leverage: float = self.targeted_volatility / portfolio_vol
            leverage: float = min(self.leverage_cap, leverage) # cap max leverage
            ls_leverage.append(leverage)

        # Trade execution.
        invested: List[str] = [x.Key.Value for x in self.Portfolio if x.Value.Invested]
        for symbol in invested:
            if symbol not in long + short:
                self.Liquidate(symbol)

        for symbol, w in weight_by_symbol.items():
            if slice.contains_key(symbol) and slice[symbol]:
                if w >= 0:
                    self.SetHoldings(symbol, w*ls_leverage[0])
                else:
                    self.SetHoldings(symbol, w*ls_leverage[1])

# Quantpedia data.
# NOTE: IMPORTANT: Data order must be ascending (datewise)
class QuantpediaFutures(PythonData):
    _last_update_date: Dict[Symbol, datetime.date] = {}

    @staticmethod
    def get_last_update_date() -> Dict[Symbol, datetime.date]:
       return QuantpediaFutures._last_update_date

    def GetSource(self, config, date, isLiveMode):
        return SubscriptionDataSource("data.quantpedia.com/backtesting_data/futures/{0}.csv".format(config.Symbol.Value), SubscriptionTransportMedium.RemoteFile, FileFormat.Csv)

    def Reader(self, config, line, date, isLiveMode):
        data = QuantpediaFutures()
        data.Symbol = config.Symbol

        if not line[0].isdigit(): return None
        split = line.split(';')

        data.Time = datetime.strptime(split[0], "%d.%m.%Y") + timedelta(days=1)
        data['back_adjusted'] = float(split[1])
        data['spliced'] = float(split[2])
        data.Value = float(split[1])

        if config.Symbol.Value not in QuantpediaFutures._last_update_date:
            QuantpediaFutures._last_update_date[config.Symbol.Value] = datetime(1,1,1).date()
        if data.Time.date() > QuantpediaFutures._last_update_date[config.Symbol.Value]:
            QuantpediaFutures._last_update_date[config.Symbol.Value] = data.Time.date()

        return data

# Custom fee model.
class CustomFeeModel(FeeModel):
    def GetOrderFee(self, parameters: OrderFeeParameters) -> OrderFee:
        fee: float = parameters.Security.Price * parameters.Order.AbsoluteQuantity * 0.00005
        return OrderFee(CashAmount(fee, "USD"))
```

CLONE PROJECT

# 118 Time Series Momentum Effect

[CLONE](https://www.quantconnect.com/terminal/clone/32414426/35af8fcbe77b92bfcbbf7f5c17db636d/clone-of%3A-118-Time-Series-Momentum-Effect) 0

![](https://cdn.quantconnect.com/i/tu/articles-cta-logo.svg)

## Related video

Skewness/Lottery Trading Strategies - Quantpedia Explains (Trading Strategies) - YouTube

Tap to unmute

[Skewness/Lottery Trading Strategies - Quantpedia Explains (Trading Strategies)](https://www.youtube.com/watch?v=vjW6QvEKSFs) [Quantpedia](https://www.youtube.com/channel/UC_YubnldxzNjLkIkEoL-FXg)

![thumbnail-image](https://yt3.ggpht.com/Dnqlcgxvc_Y01ELug8eUbdXYwCgJt0BOY427zmwwWqCXvdI_96bmI3P63ILn2fTNR2gI0iGU=s68-c-k-c0x00ffffff-no-rj)

Quantpedia3.36K subscribers

[Watch on](https://www.youtube.com/watch?v=vjW6QvEKSFs)

## Related picture

[![Time Series Momentum Effect](https://quantpedia.com/next-api/images/screener/time-series-momentum-effect/image?pictureStamp=Bv_Mmg0eOHyGsFP6mjz5SQ-XbBs=&w=3840&q=75)](https://quantpedia.com/next-api/images/screener/time-series-momentum-effect/image?pictureStamp=Bv_Mmg0eOHyGsFP6mjz5SQ-XbBs=)

## Source paper

### Moskowitz, Ooi, Pedersen: Time Series Momentum

[http://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf](http://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf)

Abstract: We document significant "time series momentum" in equity index, currency, commodity, and bond futures for each of the 58 liquid instruments we consider. We find persistence in returns for 1 to 12 months that partially reverses over longer horizons, consistent with sentiment theories of initial under-reaction and delayed over-reaction. A diversified portfolio of time series momentum strategies across all asset classes delivers substantial abnormal returns with little exposure to standard asset pricing factors, and performs best during extreme markets. We show that the returns to time series momentum are closely linked to the trading activities of speculators and hedgers, where speculators appear to profit from it at the expense of hedgers.

## Other papers

- ### Baltas, Kosowski: Trend-following and Momentum Strategies in Futures Markets


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=1968996](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=1968996)

Abstract: Abstract: Constructing a time-series momentum strategy involves the volatility-adjusted aggregation of univariate strategies and therefore relies heavily on the efficiency of the volatility estimator and on the quality of the momentum trading signal. Using a dataset with intra-day quotes of 12 futures contracts from November 1999 to October 2009, we investigate these dependencies and their relation to timeseries momentum profitability and reach a number of novel findings. First, momentum trading signals generated by fitting a linear trend on the asset price path maximise the out-of-sample performance while minimizing the portfolio turnover, hence dominating the ordinary momentum trading signal in literature, the sign of past return. Second, the results show strong momentum patterns at the monthly frequency of rebalancing, relatively strong momentum patterns at the weekly frequency and relatively weak momentum patterns at the daily frequency. In fact, significant reversal effects are documented at the very short-term horizon. Finally, regarding the volatility-adjusted aggregation of univariate strategies, the Yang-Zhang range estimator constitutes the optimal choice for volatility estimation in terms of maximizing efficiency and minimizing the bias and the ex-post portfolio turnover.

- ### Baltas, Kosowski: Improving Time-Series Momentum Strategies: The Role of Trading Signals and Volatility Estimators


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2140091](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2140091)

Abstract: Abstract: Constructing a time-series momentum strategy involves the volatility-adjusted aggregation of uni- variate strategies and therefore relies heavily on the efficiency of the volatility estimator and on the quality of the momentum trading signal. Using a dataset with intra-day quotes of 12 futures contracts from November 1999 to October 2009, we investigate these dependencies and their relation to time-series momentum profitability and reach a number of novel findings. Momentum trading signals generated by fitting a linear trend on the asset price path maximise the out-of-sample performance while minimizing the portfolio turnover, hence dominating the ordinary momentum trading signal in literature, the sign of past return. Regarding the volatility-adjusted aggregation of univariate strategies, the Yang-Zhang range estimator constitutes the optimal choice for volatility estimation in terms of maximizing efficiency and minimizing the bias and the ex-post portfolio turnover.

- ### Baltas, Kosowski: MOMENTUM STRATEGIES IN FUTURES MARKETS AND TREND-FOLLOWING FUNDS


[https://workspace.imperial.ac.uk/business-school/Public/RiskLab/wp11.pdf](https://workspace.imperial.ac.uk/business-school/Public/RiskLab/wp11.pdf)

Abstract: Abstract: In this paper we study time-series momentum strategies in futures markets and their relationship to commodity trading advisors (CTAs). First, we construct one of the most comprehensive sets of time-series momentum portfolios by extending existing studies in three dimensions: time-series (1974-2002), cross-section (71 contracts) and frequency domain (monthly, weekly, daily). Our timeseries momentum strategies achieve Sharpe ratios of above 1.20 and provide important diversification benefits due to their counter-cyclical behaviour. We find that monthly, weekly and daily strategies exhibit low cross-correlation, which indicates that they capture distinct return continuation phenomena. Second, we provide evidence that CTAs follow time-series momentum strategies, by showing that time-series momentum strategies have high explanatory power in the time-series of CTA returns. Third, based on this result, we investigate whether there exist capacity constraints in time-series momentum strategies, by running predictive regressions of momentum strategy performance on lagged capital flows into the CTA industry. Consistent with the view that futures markets are relatively liquid, we do not find evidence of capacity constraints and this result is robust to different asset classes. Our results have important implications for hedge fund studies and investors.

- ### Hurst, Ooi, Pedersen: A Century of Evidence on Trend - Following Investing


[http://www.scribd.com/doc/110704069/A-Century-of-Evidence-on-Trend-Following-AQR](http://www.scribd.com/doc/110704069/A-Century-of-Evidence-on-Trend-Following-AQR)

Abstract: Abstract: We study the performance of trend-following investing across global markets since 1903, extending the existing evidence by more than 80 years. We fnd that trend-following has delivered strong positive returns and realized a low correlation to traditional asset classes each decade for more than a century. We analyze trend-following returns through various economic environments and highlight the diversifcation benefits the strategy has historically provided in equity bear markets.Finally, we evaluate the recent environment for the strategy in the context of these long-term results.

- ### Du Plesis, Hallerbach, Spreij: Demystifying momentum: Time-series and cross-sectional momentum, volatility and dispersion


[http://www.science.uva.nl/onderwijs/thesis/centraal/files/f233479199.pdf](http://www.science.uva.nl/onderwijs/thesis/centraal/files/f233479199.pdf)

Abstract: Abstract: Variations of several momentum strategies are examined in an asset-allocation setting as well as for a set of industry portfolios. Simple models of momentum returns are considered. The difference between time-series momentum and cross-sectional momentum, with particular regard to the sources of profit for each, is clarified both theoretically and empirically. Theoretical and empirical grounds for the efficacy of volatility weighting are provided and the relationship of momentum with cross-sectional dispersion and volatility is examined.

- ### Maymin, Maymin, Fisher: Momentum's Hidden Sensitivity to the Starting Day


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=1899000](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=1899000)

Abstract: Abstract: We show that the profitability of time-series momentum strategies on commodity futures across their entire history is strongly sensitive to the starting day. Using daily returns with 252-day formation periods and 21-day holding periods, the Sharpe ratio depends on whether one starts on the first day, the second day, and so on, until the twenty first day. This sensitivity is higher for shorter trading periods. The same results also hold in simulation of independent and identically lognormally distributed returns, showing that this is not only an empirical pattern but a fundamental issue with momentum strategies. Portfolio managers should be aware of this latent risk: starting trading the same strategy on the same underlying but one day later could, even after many decades, turn a successful strategy into an unsuccessful one.

- ### Hurst, Ooi, Pedersen: Demystifying Managed Future


[http://pages.stern.nyu.edu/~lpederse/papers/DemystifyingManagedFutures.pdf](http://pages.stern.nyu.edu/~lpederse/papers/DemystifyingManagedFutures.pdf)

Abstract: Abstract: We show that the returns of Managed Futures funds and CTAs can be explained by simple trend-following strategies, specifically time series momentum strategies. We discuss the economic intuition behind these st rategies, including the potential sources of profit due to initial under-reaction and delayed over-reaction to news. We show empirically that these trend-following strategies explain Managed Futures returns. Indeed, time series momentum strategies produce large correlations and high R-squares with Managed Futures indices and individual manager returns, including the largest and most successful managers. While the largest Managed Futures managers have realized significant alphas to traditional long-only benchmarks, controlling for time series momentum strategies drives their alphas to zero. Finally, we consider a number of implementation issues relevant to time series momentum strategies, including risk management, risk allocation across asset classes and trend horizons, portfolio rebalancing frequency, transaction costs, and fees.

- ### Zhou, Zhu: An Equilibrium Model of Moving-Average Predictability and Time-Series Momentum


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2326650](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326650)

Abstract: Abstract: In an equilibrium model with rational informed investors and technical investors, we show that the moving average of past market prices can forecast the future price, explaining the strong predictive power found in many empirical studies. Our model can also explain the time series momentum that the market prices tend to be positively correlated in the short-run and negatively correlated in the long-run.

- ### Hutchinson, O'Brien: Is This Time Different? Trend Following and Financial Crises


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2375733](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2375733)

Abstract: Abstract: Following large positive returns in 2008, CTAs received increased attention and allocations from institutional investors. Subsequent performance has been below its long term average. This has occurred in a period following the largest financial crisis since the great depression. In this paper, using almost a century of data, we investigate what typically happens to the core strategy pursued by these funds in global financial crises. We also examine the time series behaviour of the markets traded by CTAs during these crisis periods. Our results show that in an extended period following financial crises trend following average returns are less than half those earned in no-crisis periods. Evidence from regional crises shows a similar pattern. We also find that futures markets do not display the strong time series return predictability prevalent in no-crisis periods, resulting in relatively weak returns for trend following strategies in the four years immediately following the start of a financial crisis.

- ### Dudler, Gmuer, Malamud: Risk Adjusted Time Series Momentum


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2457647](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2457647)

Abstract: Abstract: We introduce a new class of momentum strategies that are based on the long-term averages of risk-adjusted returns and test these strategies on a universe of 64 liquid futures contracts. We show that this risk adjusted momentum strategy outperforms the time series momentum strategy of Ooi, Moskowitz and Pedersen (2012) for almost all combinations of holding- and look-back periods. We construct measures of momentum-specific volatility (risk), (both within and across asset classes) and show that these volatility measures can be used both for risk management and it momentum timing. We find that momentum risk management significantly increases Sharpe ratios, but at the same time leads to more pronounced negative skewness and tail risk; by contrast, combining risk management with momentum timing practically eliminates the negative skewness of momentum returns and significantly reduces tail risk. In addition, momentum risk management leads to a much lower exposure to market, value, and momentum factors. As a result, risk-managed momentum returns offer much higher diversification benefits than the standard momentum returns.

- ### Hutchinson, O'Brien: Trend Following and Macroeconomic Risk


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2550718](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2550718)

Abstract: Abstract: We examine the relationship between the returns of trend following and macroeconomic risk. Our results demonstrate that macroeconomic factors do have a statistically significant relationship with trend following, when we allow for the dynamic exposures of the strategy. We find that this time varying risk exposure allows trend following to generate positive returns across a wide range of bond and equity market cycles. Prior research has documented that the majority of cross sectional momentum returns are derived from macroeconomic risk exposures. However, the same is not true for trend following where at least half of performance comes from the unexplained components of futures returns. When we relate performance to the conditional volatility of macroeconomic variables, our results show that trend following generates higher returns in periods where economic uncertainty is low.

- ### Goyal, Jegadeesh: Cross-Sectional and Time-Series Tests of Return Predictability: What Is the Difference?


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2610288](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2610288)

Abstract: Abstract: We analyze the differences between past-return based strategies that differ in conditioning on past returns in excess of zero (time-series strategy, TS) and past returns in excess of the cross-sectional average (cross-sectional strategy, CS). We find that the return difference between these two strategies is mainly due to time-varying long positions that the TS strategy takes in the aggregate market and, consequently, do not have any implications for the behavior of individual asset prices. However, TS and CS strategies based on financial ratios as predictors are sometimes different due to asset selection.

- ### Levine, Pedersen: Which Trend Is Your Friend?


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2603731](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2603731)

Abstract: Abstract: Managed-futures funds (sometimes called CTAs) trade predominantly on trends. There are several ways of identifying trends, either using heuristics or statistical measures often called “filters.” Two important statistical measures of price trends are time series momentum and moving average crossovers. We show both empirically and theoretically that these trend indicators are closely connected. In fact, they are equivalent representations in their most general forms, and they also capture many other types of filters such as the HP filter, the Kalman filter, and all other linear filters. Further, we show how trend filters can be equivalently represented as functions of past prices vs. past returns. Our results unify and broaden a range of trend-following strategies and we discuss the implications for investors.

- ### Georgopoulou, Wang: The Trend is Your Friend: Time-Series Momentum Strategies Across Equity and Commodity Markets


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2618243](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2618243)

Abstract: Abstract: Using a dataset of 67 equity and commodity indices from 1969 to 2013, this study documents a significant time-series momentum effect across international equity and commodity markets. This paper further documents that international mutual funds have a tendency to buy instruments that have been performing well in recent months, but they do not systematically sell those that have been performing poorly in the same periods. We also find that a diversified long-short momentum portfolio realizes its largest profits in extreme market conditions, but the market interventions by central banks in recent years seem to challenge the performance of such portfolios.

- ### Dudler, Gmur, Malamud: Momentum and Risk Adjustment


[http://www.iijournals.com/doi/pdfplus/10.3905/jai.2015.2015.1.044](http://www.iijournals.com/doi/pdfplus/10.3905/jai.2015.2015.1.044)

Abstract: Abstract: The goal of this article is therefore to study this inefficiency within the time series momentum (TSMOM) strategies introduced in an important article by Moscowitz, Ooi, and Pedersen \[2012\]. To this end, we introduce a new class of momentum strategies, risk-adjusted time series momentum (RAMOM) strategies, which are based on averages of past futures returns, normalized by their volatility. We test these strategies on a universe of 64 liquid futures contracts and demonstrate that RAMOM strategies outperform the TSMOM strategies of Moscowitz, Ooi, and Pedersen \[2012\] for short-, medium-, and long-term momentum strategies. Additionally, RAMOM trading signals have another useful and important feature: They are naturally less dependent on high volatility. In other words, standard TSMOM strategies tend to positively correlate (see, e.g., Hurst et al. \[2013\]) with a long-straddle position (long-call, long-put) and, as a result, perform better in volatile market environments. As we show, this is much less the case for the RAMOM returns because, by risk-adjusting the trading signals according to volatility, we render RAMOM returns more sensitive to new information precisely at the time when volatility is low. As a result, outperformance of RAMOM relative to TSMOM tends to be negatively related to volatility.

- ### Baltas: Trend-Following, Risk-Parity and the Influence of Correlations


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2673124](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2673124)

Abstract: Abstract: Trend-following strategies take long positions in assets with positive past returns and short positions in assets with negative past returns. They are typically constructed using futures contracts across all asset classes, with weights that are inversely proportional to volatility, and have historically exhibited great diversification features especially during dramatic market downturns. However, following an impressive performance in 2008, the trend-following strategy has failed to generate strong returns in the post-crisis period, 2009-2013. This period has been characterised by a large degree of co-movement even across asset classes, with the investable universe being roughly split into the so-called Risk-On and Risk-Off subclasses. We examine whether the inverse-volatility weighting scheme, which effectively ignores pairwise correlations, can turn out to be suboptimal in an environment of increasing correlations. By extending the conventionally long-only risk-parity (equal risk contribution) allocation, we construct a long-short trend-following strategy that makes use of risk-parity principles. Not only do we significantly enhance the performance of the strategy, but we also show that this enhancement is mainly driven by the performance of the more sophisticated weighting scheme in extreme average correlation regimes.

- ### Kim, Tse, Wald: Time Series Momentum and Volatility Scaling


[http://world-finance-conference.com/papers\_wfc2/468.pdf](http://world-finance-conference.com/papers_wfc2/468.pdf)

Abstract: Abstract: Moskowitz, Ooi, and Pedersen (2012) show that time series momentum delivers a large and significant alpha for a diversified portfolio of various international futures contracts over the 1985 to 2009 period. Although we confirm these results with similar data, we find that their results are driven by the volatility-scaled returns (or the so-called risk parity approach to asset allocation) rather than by time series momentum. The alpha of time series momentum monthly returns drops from 1.27% with volatility-scaled weights to 0.41% without volatility scaling, which is significantly lower than the cross-sectional momentum alpha of 0.95%. Using volatility-scaled positions, the cumulative return of a time series momentum strategy is higher that that of the buy-and-hold strategy; however, timeseriesmomentuman buy-and-hold offer similar cumulative returns if they are not scaled by volatility. The superior performance of the time series momentum strategy also vanishes in the more recent post-crisis period of 2009 to 2013.

- ### Blocher, Cooper, Molyboga: Benchmarking Commodity Investments


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2744766](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2744766)

Abstract: Abstract: While much is known about the financialization of commodities, less is known about how to profitably invest in commodities. Existing studies of Commodity Trading Advisors (CTAs) do not adequately address this question because only 19% of CTAs invest solely in commodities, despite their name. We compare a novel four-factor asset pricing model to existing benchmarks used to evaluate CTAs. Only our four-factor model prices both commodity spot and term risk premia. Overall, our four-factor model prices commodity risk premia better than the Fama-French three-factor model prices equity risk premia, and thus is an appropriate benchmark to evaluate commodity investment vehicles.

- ### Ferreira, Silva, Yen: Information ratio analysis of momentum strategies


[http://arxiv.org/abs/1402.3030](http://arxiv.org/abs/1402.3030)

Abstract: Abstract: In the past 20 years, momentum or trend following strategies have become an established part of the investor toolbox. We introduce a new way of analyzing momentum strategies by looking at the information ratio (IR, average return divided by standard deviation). We calculate the theoretical IR of a momentum strategy, and show that if momentum is mainly due to the positive autocorrelation in returns, IR as a function of the portfolio formation period (look-back) is very different from momentum due to the drift (average return). The IR shows that for look-back periods of a few months, the investor is more likely to tap into autocorrelation. However, for look-back periods closer to 1 year, the investor is more likely to tap into the drift. We compare the historical data to the theoretical IR by constructing stationary periods. The empirical study finds that there are periods/regimes where the autocorrelation is more important than the drift in explaining the IR (particularly pre-1975) and others where the drift is more important (mostly after 1975). We conclude our study by applying our momentum strategy to 100 plus years of the Dow-Jones Industrial Average. We report damped oscillations on the IR for look-back periods of several years and model such oscilations as a reversal to the mean growth rate.

- ### Hamill, Rattray, Hemert: Trend Following: Equity and Bond Crisis Alpha


[http://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2831926](http://papers.ssrn.com/sol3/papers.cfm?abstract_id=2831926)

Abstract: Abstract: We study time-series momentum (trend-following) strategies in bonds, commodities, currencies and equity indices between 1960 and 2015. We find that momentum strategies performed consistently both before and after 1985, periods which were marked by strong bear and bull markets in bonds respectively. We document a number of important risk properties. First, that returns are positively skewed, which we argue is intuitive by drawing a parallel between momentum strategies and a long option straddle strategy. Second, performance was particularly strong in the worst equity and bond market environments, giving credence to the claim that trend-following can provide equity and bond crisis alpha. Putting restrictions on the strategy to prevent it being long equities or long bonds has the potential to further enhance the crisis alpha, but reduces the average return. Finally, we examine how performance has varied across momentum strategies based on returns with different lags and applied to different asset classes.

- ### Peltomaki, Agerback, Gudmundsen-Sinclair: The Long and Short of Trend Followers


[https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2836389](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2836389)

Abstract: Abstract: We propose the use of short and long portfolios of trend-following strategies to analyze their risk and return characteristics. We find that their exposures are time-varying, depend on the market state, and that returns to their long and short sides in the same asset are not comparable. In addition, we present evidence for occasional long-biased discretion by CTA managers. Our findings are in line with the adaptive markets hypothesis, and the main lesson of our study is that the long and short sides should be differentiated in the analysis of dynamic investment strategies.

- ### Till: What are the Sources of Return for CTAs and Commodity Indices? A Brief Survey of Relevant Research


[http://www.oxfordstrat.com/coasdfASD32/uploads/2016/03/Sources-of-Return-for-CTAs.pdf](http://www.oxfordstrat.com/coasdfASD32/uploads/2016/03/Sources-of-Return-for-CTAs.pdf)

Abstract: Abstract: This survey paper will discuss the (potential) structural sources of return for both CTAs and commodity indices based on a review of empirical research articles from both academics and practitioners. The paper specifically covers (a) the long-term return sources for both managed futures programs and for commodity indices; (b) the investor expectations and the portfolio context for futures strategies; and (c) how to benchmark these strategies.

- ### Hoffman, Kaminski: The TAMING of the SKEW


[http://www.valuewalk.com/wp-content/uploads/2016/06/The\_Taming\_of\_the\_Skew\_\_\_Campbell\_\_Company.pdf](http://www.valuewalk.com/wp-content/uploads/2016/06/The_Taming_of_the_Skew___Campbell__Company.pdf)

Abstract: Abstract: Investors are often concerned about the negative skewness, or left-tail asymmetry, of equity returns. In response, they seek risk-mitigating strategies to provide offsetting returns when equity markets fall. Due to their association with positive skewness, trend-following strategies are popular candidates for risk-mitigation or crisis-offset. This paper explores how a trend-following portfolio can achieve positive skewness, and finds that time variation in risk is the primary factor. In fact, any portfolio with a positive Sharpe ratio can achieve positive skewness simply by varying the level of risk taken through time.

- ### Hurst, Ooi, Pedersen: A Century of Evidence on Trend-Following Investing


[https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2993026](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2993026)

Abstract: Abstract: In this article, the authors study the performance of trend-following investing across global markets since 1880, extending the existing evidence by more than 100 years using a novel data set. They find that in each decade since 1880, time series momentum has delivered positive average returns with low correlations to traditional asset classes. Further, time-series momentum has performed well in 8 out of 10 of the largest crisis periods over the century, defined as the largest drawdowns for a 60/40 stock/bond portfolio. Lastly, time series momentum has performed well across different macro environments, including recessions and booms, war and peacetime, high- and low-interest rate regimes, and high- and low-inflation periods.

- ### Cook, Hoyle, Sargaison, Taylor, Hemert: The Best Strategies for the Worst Crises


[https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=2986753](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2986753)

Abstract: Abstract:Hedging equity portfolios against the risk of large drawdowns is notoriously difficult and expensive. Holding, and continuously rolling, at-the-money put options on the S&amp;P 500 is a very costly, if reliable, strategy to protect against market sell-offs. Holding ‘safe-haven’ US Treasury bonds, while providing a positive and predictable long-term yield, is generally an unreliable crisis-hedge strategy, since the post-2000 negative bond-equity correlation is a historical rarity. Long gold and long credit protection portfolios appear to sit between puts and bonds in terms of both cost and reliability. In contrast to these passive investments, we investigate two dynamic strategies that appear to have generated positive performance in both the long-run but also particularly during historical crises: futures time-series momentum and quality stock factors. Futures momentum has parallels with long option straddle strategies, allowing it to benefit during extended equity sell-offs. The quality stock strategy takes long positions in highest-quality and short positions in lowest-quality company stocks, benefitting from a ‘flight-to-quality’ effect during crises. These two dynamic strategies historically have uncorrelated return profiles, making them complementary crisis risk hedges. We examine both strategies and discuss how different variations may have performed in crises, as well as normal times, over the years 1985 to 2016.

- ### Jusselin, Lezmi, Malongo, Masselin, Roncalli, Dao: Understanding the Momentum Risk Premium: An In-Depth Journey Through Trend-Following Strategies


[https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=3042173](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3042173)

Abstract: Abstract:Momentum risk premium is one of the most important alternative risk premia. Since it is considered a market anomaly, it is not always well understood. Many publications on this topic are therefore based on backtesting and empirical results. However, some academic studies have developed a theoretical framework that allows us to understand the behavior of such strategies. In this paper, we extend the model of Bruder and Gaussel (2011) to the multivariate case. We can find the main properties found in academic literature, and obtain new theoretical findings on the momentum risk premium. In particular, we revisit the payoff of trend-following strategies, and analyze the impact of the asset universe on the risk/return profile. We also compare empirical stylized facts with the theoretical results obtained from our model. Finally, we study the hedging properties of trend-following strategies.

- ### Fan, Li, Liu: Risk Adjusted Momentum Strategies: A Comparison between Constant and Dynamic Volatility Scaling Approaches


[https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=3076715](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3076715)

Abstract: Abstract:We compare the performance of two volatility scaling methods in momentum strategies: (i) the constant volatility scaling approach of Barroso and Santa-Clara (2015), and (ii) the dynamic volatility scaling method of Daniel and Moskowitz (2016). We perform momentum strategies based on these two approaches in an asset pool consisting of 55 global liquid futures contracts, and further compare these results to the time series momentum and buy-and-hold strategies. We find that the momentum strategy based on the constant volatility scaling method is the most efficient approach with an annual return of 15.3%.

- ### Huang, Li, Wang, Zhou: Time-Series Momentum: Is It There?


[https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=3165284](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3165284)

Abstract: Abstract:Time-series momentum (TSM) refers to the predictability of the past 12-month return on the next one-month return, and is the focus of several recent influential studies. This paper shows, however, that asset-by-asset time-series regressions reveal little evidence of TSM, both in- and out-of-sample. In a pooled regression, the typically used t-statistic can over-reject the no predictability hypothesis, and three versions of bootstrap-corrected t-statistics show that there is no evidence of TSM. From an investment perspective, although the TSM strategy is known to be profitable, its performance is virtually the same as that of a similar strategy that is based on historical mean and does not require predictability. Overall, the evidence of TSM is weak, particularly for the large cross section of assets.

- ### Cho, Ham, Kim, Ryu: Time-Series Momentum in the Chinese Commodity Futures Market


[https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=3311479](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3311479)

Abstract: Abstract:This study examines time-series momentum in the Chinese commodity futures market. The findings show that a time-series momentum strategy performs best with a one-month look-back period and a one-month holding period. Furthermore, this strategy outperforms passive long and cross-sectional momentum strategies in the Chinese futures market based on Sharpe ratios, risk-adjusted excess returns, and cumulative returns. But highly volatile market characteristic with many speculative investors limits the period in which time-series momentum is maintained. Our findings suggest that the anomaly is observed in international asset markets, including Chinese commodity futures, and support the implication that speculators profit from time-series momentum strategy is the expense of hedgers.

- ### Cheng, Struck: Time-Series Momentum: A Monte-Carlo Approach


[https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=3345849](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3345849)

Abstract: Abstract:This paper develops a Monte-Carlo backtesting procedure for risk premia strategies and employs it to study Time-Series Momentum (TSM). Relying on time-series models, empirical residual distributions and copulas we overcome two key drawbacks of conventional backtesting procedures. We create 10,000 paths of different TSM strategies based on the S&amp;P 500 and a cross-asset class futures portfolio. The simulations reveal a probability distribution which shows that strategies that outperform Buy-and-Hold in-sample using historical backtests may out-of- sample i) exhibit sizable tail risks, ii) under-perform or outperform. Our results are robust to using different time-series models, time periods, asset classes, and risk measures.

- ### Babu, Levine, Ooi, Pedersen, Stamelos: Time-Series Momentum Works Everywhere


[https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=3386035](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3386035)

Abstract: Abstract: We provide new out-of-sample evidence on trend-following investing by studying its performance for 82 securities not previously examined and 16 long-short equity factors. Specifically, we study the performance of time series momentum for emerging market equity index futures, fixed income swaps, emerging market currencies, exotic commodity futures, credit default swap indices, volatility futures, and long-short equity factors. We find that time series momentum has worked across these asset classes and across several trend horizons. We examine the co-movement of trends across asset classes and factors, the performance during different market environments, and discuss the implications for investors.

- ### Yang, Qian, Belton: Protecting the Downside of Trend When It's Not Your Friend


[https://www.iijournalseprint.com/JPM/Panagora/Jul19ProtectingtheDownsideofTrend73f/index.html?page=2](https://www.iijournalseprint.com/JPM/Panagora/Jul19ProtectingtheDownsideofTrend73f/index.html?page=2) [https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=3421108](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3421108)

Abstract: Simple trend-following strategies have been documented as cost-effective, transparent alternatives to the hedge-fund style Managed Futures strategies. While largely capturing the returns of the Managed Futures industry, those simple strategies may periodically suffer significant losses due to over-simplified trend signals and under-diversified portfolio construction. In this article, the authors show that trend-following strategies with moderate sophistication and better diversification can significantly reduce the downside risk of simple trend-following strategies without sacrificing much upside potential. The authors therefore recommend investors who seek the benefits of cost-effective trend-following strategies to consider adding reasonable complexity to the strategies.

- ### Liu, Lu, Wang: Asymmetry, Tail Risk and Time Series Momentum


[https://papers.ssrn.com/sol3/papers.cfm?abstract\_id=3573878](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3573878)

Abstract: Similar to the cross-sectional momentum crashes, the time series momentum experiences deep and persistent drawdowns in the stressed time of slumps in the upward momentum, rebounds in the downward momentum, and long time sideways market. We measure the upside and downside risk using the upper and lower partial moments, which are derived from the individual asset’s daily return. The time series momentum reversals are partly forecasted by the asymmetric structure of the tail-distributed upside and downside risk. An implementable systematic rule-based decision function is designed to manage the signals given by the time series momentum. Its empirical application on the Chinese commodity futures markets documents improvements in terms of both the Sharpe ratio and the Sortino ratio from 2008 to 2019. These results are robust across the time series momentum with different looking back windows.

- ### Kestner, Lars N., Replicating CTA Positioning: An Improved Method


[https://ssrn.com/abstract=3674828](https://ssrn.com/abstract=3674828)

Abstract: Analysis of systematic strategies is a current topic of focus, centering on the impact these strategies have on various financial markets. Risk parity, option overwriting, volatility targeted equity indices, and trend following strategies receive the majority of this attention. In this paper, we focus on the dynamic trading of trend following strategies and detail an improved method for estimating their actions across markets. A simple replication model employed on 16 futures markets explains over 75% of the variation in a trend following benchmark. This replication model is able to estimate trend follower positions without lag. Using estimates of total funds allocated to trend following managers, we can use our replication model to estimate positions by specific market and the expected trading flows when individual markets move.

- ### Xu, Dezhong and Li, Bin and Singh, Tarlok and Park, Jung Chul: Cross-Asset Time-Series Momentum Strategy: A New Suggestion


[https://ssrn.com/abstract=4231887](https://ssrn.com/abstract=4231887)

Abstract: We propose a new investment strategy, the improved cross-asset time-series momentum (I-XTSM) strategy, to improve investment performance. Using data on 25 investment portfolios and common commodities for the period from January 1990 to April 2021, we find that the I-XTSM strategy increases profitability substantially in the stock market and avoids momentum collapse effectively. We also document that its profitability is driven by the predictive power of the industrial metal assets’ past signals. Even after considering market exposure, the I-XTSM presents a superior performance and explains the excess profits of other momentum strategies.

- ### Zakamulin, Valeriy and Giner, Javier: Optimal Trend-Following With Transaction Costs


[https://ssrn.com/abstract=4282126](https://ssrn.com/abstract=4282126)

Abstract: Despite trend-following investing's widespread popularity, optimal trend-following with transaction costs remains poorly understood. Existing studies on the subject are limited and use a theoretical approach that is difficult to solve. In this paper, we propose a new, more practical model that strikes a balance between theoretical simplicity and practical relevance. Our model reduces trading costs and produces a solution that is comparable to the popular simple moving average crossover rule. By using our model, traders can justify using the crossover rule in practice. We also provide historical simulations that demonstrate the effectiveness of our model, supporting our theoretical findings. In short, our paper provides a practical and effective solution to the problem of optimal trend-following with transaction costs.

- ### Safari, Sara A. and Schmidhuber, Christof: Trends and Reversion in Financial Markets on Time Scales from Minutes to Decades


[https://doi.org/10.48550/arXiv.2501.16772](https://doi.org/10.48550/arXiv.2501.16772)

Abstract: We empirically analyze the reversion of financial market trends with time horizons ranging from minutes to decades. The analysis covers equities, interest rates, currencies and commodities and combines 14 years of futures tick data, 30 years of daily futures prices, 330 years of monthly asset prices, and yearly financial data since medieval times.Across asset classes, we find that markets are in a trending regime on time scales that range from a few hours to a few years, while they are in a reversion regime on shorter and longer time scales. In the trending regime, weak trends tend to persist, which can be explained by herding behavior of investors. However, in this regime trends tend to revert before they become strong enough to be statistically significant, which can be interpreted as a return of asset prices to their intrinsic value. In the reversion regime, we find the opposite pattern: weak trends tend to revert, while those trends that become statistically significant tend to persist.Our results provide a set of empirical tests of theoretical models of financial markets. We interpret them in the light of a recently proposed lattice gas model, where the lattice represents the social network of traders, the gas molecules represent the shares of financial assets, and efficient markets correspond to the critical point. If this model is accurate, the lattice gas must be near this critical point on time scales from 1 hour to a few days, with a correlation time of a few years.

- ### Valeyre, Sebastien: Breaking the Trend: How to Avoid Cherry-Picked Signals


[https://arxiv.org/abs/2504.10914](https://arxiv.org/abs/2504.10914)

Abstract: Our empirical results, illustrated in Fig.5, show an impressive fit with the pretty complex theoritical Sharpe formula of a Trend following strategy depending on the parameter of the signal, which was derived by Grebenkov and Serror (2014). That empirical fit convinces us that a mean-reversion process with only one time scale is enough to model, in a pretty precise way, the reality of the trend-following mechanism at the average scale of CTAs and as a consequence, using only one simple EMA, appears optimal to capture the trend. As a consequence, using a complex basket of different complex indicators as signal, do not seem to be so rational or optimal and exposes to the risk of cherry-picking.

- ### Etienne, Alban and Ohana, Jean-Jacques and Benhamou, Eric and Guez, Béatrice and Setrouk, Ethan and Jacquot, Thomas: Revisiting the Structure of Trend Premia: When Diversification Hides Redundancy


[https://arxiv.org/abs/2510.23150](https://arxiv.org/abs/2510.23150)

Abstract: Recent work has emphasized the diversification benefits of combining trend signals across multiple horizons, with the medium-term window-typically six months to one year-long viewed as the "sweet spot" of trend-following. This paper revisits this conventional view by reallocating exposure dynamically across horizons using a Bayesian optimization framework designed to learn the optimal weights assigned to each trend horizon at the asset level. The common practice of equal weighting implicitly assumes that all assets benefit equally from all horizons; we show that this assumption is both theoretically and empirically suboptimal. We first optimize the horizon-level weights at the asset level to maximize the informativeness of trend signals before applying Bayesian graphical models-with sparsity and turnover control-to allocate dynamically across assets. The key finding is that the medium-term band contributes little incremental performance or diversification once short- and long-term components are included. Removing the 125-day layer improves Sharpe ratios and drawdown efficiency while maintaining benchmark correlation. We then rationalize this outcome through a minimum-variance formulation, showing that the medium-term horizon largely overlaps with its neighboring horizons. The resulting "barbell" structure-combining short- and long-term trends-captures most of the performance while reducing model complexity. This result challenges the common belief that more horizons always improve diversification and suggests that some forms of time-scale diversification may conceal unnecessary redundancy in trend premia.

- ### Kjaer, Christian: On the Anatomy of Trend


[https://ssrn.com/abstract=5957236](https://ssrn.com/abstract=5957236)

Abstract: We present a theoretical framework for analyzing the performance of time-series momentum (trend-following) strategies when the underlying asset follows a general stationary Gaussian process. We derive closed-form expressions for the unconditional expected log payoff, decomposing the performance into a drift component related to the expected position and a timing component related to the alignment of the trend signal and the subsequent return of the underlying. Extending the analysis to conditional performance, we show that the conditional expected payoff preserves the characteristics from the unconditional: a conditional expected position component and a conditional timing component. We derive exact asymptotic limits for the conditional payoff in "deep crash" scenarios over a fixed horizon and show that even with i.i.d. returns, the conditional expected return is positive if the drawdown period is larger than one day. Finally, we show that a sufficiently long and severe drawdown always yields positive trend performance-irrespective of the underlying autocorrelation structure. We also characterize the role of the lookback parameter, revealing a trade-off between expected returns and hedge effectiveness. Empirical analysis of 103 assets over 25 years confirms the key theoretical predictions with rigorous statistical significance. We document a strongly convex conditional payoff profile ("smile"), quantify the "cost of convexity".


Share

[delete](https://www.linkedin.com/shareArticle?mini=true&url=https%3A%2F%2Fquantpedia.com%2Fstrategies%2Ftime-series-momentum-effect)[delete](https://twitter.com/intent/tweet?text=Time%20Series%20Momentum%20Effect%20https%3A%2F%2Fquantpedia.com%2Fstrategies%2Ftime-series-momentum-effect)[delete](https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fquantpedia.com%2Fstrategies%2Ftime-series-momentum-effect)[delete](mailto:?to=&subject=Time%20Series%20Momentum%20Effect&body=Time%20Series%20Momentum%20Effect%20https%3A%2F%2Fquantpedia.com%2Fstrategies%2Ftime-series-momentum-effect)

* * *

### Browse Next Strategies

- [Short Interest Effect - Long-Short Version](https://quantpedia.com/strategies/short-interest-effect-long-short-version)
- [Momentum in Mutual Fund Returns](https://quantpedia.com/strategies/momentum-in-mutual-fund-returns)
- [Term Structure Effect in Commodities](https://quantpedia.com/strategies/term-structure-effect-in-commodities)
- [Dispersion Trading](https://quantpedia.com/strategies/dispersion-trading)
- [Momentum Effect in Stocks in Small Portfolios](https://quantpedia.com/strategies/momentum-effect-in-stocks-in-small-portfolios)
- [Momentum Factor Effect in Stocks](https://quantpedia.com/strategies/momentum-factor-effect-in-stocks)

We are using cookies to give you the best experience on our website. To learn more, see our [Privacy Policy](https://quantpedia.com/privacy-policy)

Accept