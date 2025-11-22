# Signing（注意点のみ）

推奨: 公式Python SDKなど既存実装を使用する。誤署名は「User or API Wallet does not exist」「Must deposit before performing actions」などで返るが原因が分かりにくい。

主な落とし穴:
1. 署名スキームが2種ある（`sign_l1_action` vs `sign_user_signed_action`）。注文は後者。
2. msgpackのフィールド順序依存。
3. 数値の末尾ゼロ処理（トレイリングゼロを外す）。
4. アドレスは小文字に正規化して署名/送信。
5. ローカルでrecover成功しても、payload構築がズレていれば本番で失敗する。

デバッグ: SDKの署名処理をステップ実行し、入力payloadと出力署名を比較ログする。
