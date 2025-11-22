# Asset IDs

Perpetual endpoints expect an integer for `asset`, which is the index of the coin found in the `meta` info response. E.g. `BTC = 0` on mainnet.

メモ:
- 今回はBTCUSDTパーペチュアルのみを mainnet 固定で運用するため、`assetIndex=0` をハードコードしてよい。
- テストネットや他銘柄に対応する場合は、`meta` の `universe` から取得する実装に切り替える。
