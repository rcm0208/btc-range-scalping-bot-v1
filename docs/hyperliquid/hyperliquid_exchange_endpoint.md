# Exchange endpoint（Botで使用する部分のみ抜粋）

共通:
- エンドポイント: `POST https://api.hyperliquid.xyz/exchange`
- ヘッダ: `Content-Type: application/json`
- asset: perpの場合は `meta.universe` のインデックス（例: BTCなら `meta` 取得後の index）。ハードコードせず `meta` から取得。
- サイン: すべて署名付き（nonceはmsタイムスタンプ推奨）。
- expiresAfter: 任意。指定するとその時刻以降は拒否され、RateLimit消費5倍になるため乱用しない。

## order（必須）
現物は対象外。perpの成行/指値/TP/SL、post-only(ALO)/IOC/GTCに対応。
```json
{
  "action": {
    "type": "order",
    "orders": [
      {
        "a": <assetIndex>,       // from meta.universe
        "b": true,               // isBuy
        "p": "29792.0",          // price (string), market時は"0"可?
        "s": "0.01",             // size in coin units
        "r": false,              // reduceOnly
        "t": { "limit": { "tif": "Alo" | "Ioc" | "Gtc" } }  // or trigger { isMarket, triggerPx, tpsl: "tp"/"sl" }
        "c": "<cloid-hex-optional>"
      }
    ],
    "grouping": "na" | "normalTpsl" | "positionTpsl"
  },
  "nonce": 0,
  "signature": { ... },
  "expiresAfter": <optional_ms>,
  "vaultAddress": "<optional if acting for subaccount/vault>"
}
```
レスポンス例:
```json
{"status":"ok","response":{"type":"order","data":{"statuses":[{"resting":{"oid":77738308}}]}}}
```

## cancel（必須）
oid指定でキャンセル。
```json
{
  "action": { "type": "cancel", "cancels": [ { "a": <assetIndex>, "o": <oid> } ] },
  "nonce": 0,
  "signature": { ... },
  "expiresAfter": <optional_ms>
}
```

## cancelByCloid（推奨）
cloid指定キャンセル。
```json
{
  "action": { "type": "cancelByCloid", "cancels": [ { "asset": <assetIndex>, "cloid": "<hex>" } ] },
  "nonce": 0,
  "signature": { ... },
  "expiresAfter": <optional_ms>
}
```

## scheduleCancel（推奨: デッドマンスイッチ）
指定時刻(>=現在+5s)で全オープン注文をキャンセル。time未指定でスケジュール解除。1日10回まで。
```json
{ "action": { "type": "scheduleCancel", "time": <ms_optional> }, "nonce": 0, "signature": { ... } }
```

## modify（任意）
既存注文の修正（oidまたはcloid指定）。実装コストと必要性を見て採用。
```json
{ "action": { "type": "modify", "oid": <oid> | "<cloid>", "order": { ...order fields... } }, "nonce": 0, "signature": { ... } }
```

## noop（任意）
nonceを消費するだけの操作。インフライト注文キャンセル代替で使う場合のみ。
```json
{ "action": { "type": "noop" }, "nonce": 0, "signature": { ... } }
```

---
削除したセクション: TWAP発注/キャンセル、reserveRequestWeight、builder/agent承認、HIP-3抽象化、validator voteなど今回のBTCパーペチュアルBotでは不要なもの。必要時に戻せるよう元資料はGit履歴に残っている。
