# Notation

The current v0 API currently uses some nonstandard notation. Relevant standardization will be batched into a breaking v1 API change.

| Abbreviation | Full name             | Explanation                                                                                |
| :----------- | :-------------------- | :----------------------------------------------------------------------------------------- |
| Px           | Price                 |                                                                                            |
| Sz           | Size                  | In units of coin, i.e. base currency                                                       |
| Szi          | Signed size           | Positive for long, negative for short                                                      |
| Ntl          | Notional              | USD amount, Px \* Sz                                                                       |
| Side         | Side of trade or book | B = Bid = Buy, A = Ask = Short. Side is aggressing side for trades.                        |
| Asset        | Asset                 | An integer representing the asset being traded. See below for explanation                  |
| Tif          | Time in force         | GTC = good until canceled, ALO = add liquidity only (post only), IOC = immediate or cancel |
