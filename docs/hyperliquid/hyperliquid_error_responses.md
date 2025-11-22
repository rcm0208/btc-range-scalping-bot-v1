# Error responses（主要なもの）

バッチ応答はリクエスト配列と同じ長さのエラー配列となる。バッチ全体が事前検証で失敗する場合は1件のみ返る。

| Source | Type                              | Message (例)                                             |
| ------ | --------------------------------- | -------------------------------------------------------- |
| Order  | Tick                              | Price must be divisible by tick size.                    |
| Order  | MinTradeNtl                       | Order must have minimum value of $10.                    |
| Order  | PerpMargin                        | Insufficient margin to place order.                      |
| Order  | ReduceOnly                        | Reduce only order would increase position.               |
| Order  | BadAloPx                          | Post only order would have immediately matched, bbo was… |
| Order  | IocCancel                         | Order could not immediately match.                       |
| Order  | BadTriggerPx                      | Invalid TP/SL price.                                     |
| Order  | MarketOrderNoLiquidity            | No liquidity for market order.                           |
| Order  | PositionIncreaseAtOpenInterestCap | OI capped.                                               |
| Order  | PositionFlipAtOpenInterestCap     | OI capped.                                               |
| Order  | TooAggressiveAtOpenInterestCap    | Price too aggressive at OI cap.                          |
| Order  | OpenInterestIncrease              | OI increase too fast.                                    |
| Order  | Oracle                            | Price too far from oracle.                               |
| Order  | PerpMaxPosition                   | Exceeds margin tier limit at current leverage.           |
| Cancel | MissingOrder                      | Order was never placed / already canceled / filled.      |

Spot専用・リファラル系は省略。詳細は必要に応じて原文参照。
