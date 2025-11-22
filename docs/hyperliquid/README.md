# Hyperliquid API Docs (サマリ)

このディレクトリは Hyperliquid 本番環境での開発に必要なAPI仕様を抜粋・整理したものです。botの実装では本ディレクトリの情報に従います。

## 主なファイル
- `hyperliquid_notation.md`: 用語/略語
- `hyperliquid_asset_ids.md`: assetインデックスの扱い（BTC perpは meta.universe の index=0）
- `hyperliquid_tick_and_lot_size.md`: 価格/サイズ桁数ルール
- `hyperliquid_info_endpoint.md`: Infoエンドポイント（汎用）
- `hyperliquid_info_endpoint_perpetuals.md`: Perp用Info（meta, asset ctx, clearinghouseState 等）
- `hyperliquid_exchange_endpoint.md`: 署名付きアクション（order/cancel/…）
- `hyperliquid_websocket.md`: WSサブスクリプション
- `hyperliquid_nonces_and_api_wallets.md`: nonceとAPIウォレット運用
- `hyperliquid_error_responses.md`: 主なエラー
- `hyperliquid_signing.md`: 署名の注意点
- `hyperliquid_rate_limits_and_user_limits.md`: レート制限

## 運用前提
- 環境: 本番(Mainnet)のみを使用。
- SDK: `hyperliquid-python-sdk` を利用し、署名部分はSDKラッパ経由に統一。
- 鍵: マスター鍵は使わずAPIウォレット(agent)を使用。秘密鍵は `.env` で管理（将来Secrets Managerへ移行可）。
- BTC perp meta (2025-05取得): assetIndex=0, szDecimals=5, maxLeverage=40, marginTableId=56。設定にハードコード可。

## 利用の流れ
1. `hyperliquid_info_endpoint_perpetuals.md` で meta/assetCtx を確認して初期設定を取得。
2. `hyperliquid_exchange_endpoint.md` の order/cancel を実装（署名はSDK利用）。
3. `hyperliquid_websocket.md` の candle/orderUpdates/userEvents などを購読してライブデータ/約定を処理。
4. レート/nonce/エラーの扱いは各該当ファイルを参照し、リトライ・バックオフ・サーキットブレーカを実装。
