# Astro Stacker Project Guide

この文書は、現行コードを基準にした開発者向けガイドです。`ARCHITECTURE.md` と
`PROJECT_OVERVIEW.md` には初期設計や将来像も含まれるため、実装を変更するときは本書と
`docs/SPEC.md` を優先して確認してください。

## アーキテクチャ概要

Astro Stacker は PySide6 製 GUI と、天体画像処理用の pipeline/core モジュールで構成されます。
処理の中心は `FrameProvider` で、画像の取得、キャリブレーション、Debayer、位置合わせを
デコレータとして積み重ねます。

主要レイヤー:

- `io`: ファイル形式ごとのメタデータ読み込み、ピクセル読み込み、保存、LRU メモリ管理。
- `project`: フレーム一覧、設定、マスターフレーム、処理結果、位置合わせセッションを保持。
- `core`: Provider プロトコルと、キャリブレーションや Debayer の provider 実装。
- `calibration`: マスターフレーム生成と light frame への補正適用。
- `alignment`: 星検出結果から変換行列を推定し、画像へ warp を適用。
- `stacking`: mean/median/add/sigma clipping による合成。
- `pipeline`: 上記処理の順序制御。
- `ui`: PySide6 ウィジェット、QThread worker、プロジェクト操作。
- `cache`: 品質・位置合わせキャッシュの実験的実装。現行 UI/pipeline では主経路ではない。

## データフロー

1. `ProjectController.add_file()` が `load_info(path)` で `AstroImage` を作成する。
2. `Project` が light/dark/flat/flat-dark/bias の各リストを保持する。
3. `ImageManagerProvider` が `ImageManager.get_image()` 経由で必要時にピクセルを読み込む。
4. `ProcessingPipeline` が補正フレームから master を作り、必要に応じて FITS 保存する。
5. `CalibratedFrameProvider` が light frame に dark/bias/flat 補正を適用する。
6. `AlignmentPipeline` が星検出、品質計算、astroalign による変換推定を行う。
7. `StackingPipeline` が `AlignedFrameProvider` と `ImageCombiner` で有効フレームを合成する。
8. 結果は `Project.result.stacked_image` に入り、`stacked*.fits` として自動保存される。

## モジュール責務

### `io`

`load_info()` はメタデータのみを読む入口です。`load_image()` は `np.float32` かつ非負値へ統一します。
RAW は線形 Bayer プレーン、FITS は channels-last、標準画像は Pillow 配列を作業範囲へ変換します。

注意点:

- `AstroImage` 自体には `load()` / `unload()` はありません。ピクセル管理は `ImageManager` の責務です。
- `ImageManager` は画像枚数ベースの LRU です。バイト数や空きメモリ量では制御していません。
- FITS/RAW/標準画像で shape とチャンネル表現が混ざるため、処理前に `(H, W)` / `(H, W, 1)` / `(H, W, 3)` を確認してください。

### `project`

`Project` は状態コンテナです。処理設定は `Project.settings`、出力は `Project.result`、補正 master は
`Project.master_calibration_frames` に入ります。位置合わせ済みかどうかは
`AlignmentSignature` と `alignment_session_id` で判定します。

### `core` Provider

Provider は `get_image(AstroImage) -> np.ndarray` だけを約束する薄い境界です。

代表的な積み方:

```python
provider = ImageManagerProvider(manager)
provider = CalibratedFrameProvider(provider, calibrator)
provider = DebayerFrameProvider(provider)
provider = AlignedFrameProvider(provider, ImageTransformer())
```

原則:

- Provider は入力 `AstroImage` の状態を必要以上に変更しない。
- 画像配列を破壊的に変更する処理は、必ず `copy=True` または新規配列で扱う。
- 新しい処理段階は pipeline に直接混ぜず、まず provider として表現できるか検討する。

### `calibration`

`MasterFrameBuilder` は `ImageCombiner` を使って master を生成します。`Calibrator` は
`sub_frame` を減算し、正規化済み flat で除算します。

注意点:

- dark/bias/flat の shape が light と一致する前提です。現状は明示検証が弱いです。
- flat 平均がゼロまたは非有限値の場合は flat 補正をスキップします。
- flat-dark と bias の二重減算に注意して、master 生成側と適用側の責務を混ぜないでください。

### `alignment`

`AlignmentPipeline` は参照フレームを選び、各 light frame を並列に `process_frame()` します。
星検出は `photutils.DAOStarFinder`、変換推定は `astroalign.find_transform()` です。

注意点:

- `ReferenceMode.BEST` は未実装です。
- 失敗フレームはログ出力され、スタック対象から外れます。
- 位置合わせセッションが混ざると `NEW_ONLY` ではエラーになります。

### `stacking`

`ImageCombiner` は有効フレームだけを処理します。mean/add は逐次 accumulator、median/sigma clip は
一時 memmap に全フレームを積んでから行チャンクで処理します。

注意点:

- 一時ファイル容量は概ね `枚数 * 高さ * 幅 * チャンネル * 4 bytes` です。
- `StackingSettings.sigma` と `iterations` は現状 combiner に渡っていません。
- 入力 shape の明示検証が不足しているため、異なるサイズが混ざると NumPy 代入エラーになります。

### `ui`

重い pipeline は `PipelineWorker` を `QThread` に移して実行します。UI 更新は Qt signal 経由です。

注意点:

- プレビューはメインスレッドで読み込みと変換を行うため、大型画像では UI が固まります。
- `Project` と `ImageManager` は worker と UI の両方から参照されます。処理中に UI 操作を止める前提です。
- 進捗 signal はフレーム単位またはチャンク単位に抑え、画素単位では送らないでください。

## 命名規則

- 画像リスト: `light_frames`, `darks`, `flats`, `flat_darks`, `biases`
- マスター種別: `master_dark`, `master_flat`, `master_flat_dark`, `master_bias`
- Provider: `*FrameProvider`
- Pipeline: `*Pipeline`
- 設定: `*Settings`
- 結果データ: `*Data`, `*Result`

## 設計思想

- ピクセル配列は原則 `np.float32`。
- RAW は自動輝度、WB、ガンマを避け、線形 Bayer として扱う。
- 大量画像は遅延読み込みし、中間結果は必要に応じて memmap へ逃がす。
- UI は長時間処理を直接実行しない。
- 位置合わせ結果は画像ではなく `TransformData` として保持する。
- 将来機能は既存 pipeline に直接分岐を増やすより、Provider/Settings/Result を通して追加する。

## 拡張方針

### 新しいスタック手法

1. `StackingMethod` に列挙値を追加する。
2. `ImageCombiner.combine()` から専用メソッドへ分岐する。
3. `StackingSettings` に必要パラメータを追加する。
4. `StackingSettingsDialog` で UI 入力を追加する。
5. 小さな合成配列で unit test、大きめ配列で memmap/キャンセル test を追加する。

### 新しい補正処理

1. 破壊的変更を避けた関数として実装する。
2. Provider 化できる場合は `core.provider` に追加する。
3. `ProcessingPipeline` には順序制御だけを置く。
4. 入力 shape、dtype、NaN/Inf の扱いを明示する。

### Plate Solve / Drizzle

未実装モジュールは存在します。追加時は、結果データ型、設定型、UI 表示、キャッシュ形式を先に決めてから
pipeline に接続してください。外部コマンドや大きな中間ファイルを使う場合は、キャンセルと後始末を必須にします。

## 注意点

- README には将来構想が含まれていた履歴があります。リリース文言では「実装済み」と「予定」を分けてください。
- `docs/specification.md` は古い仕様メモです。現行実装の確認には `docs/SPEC.md` と本書を使ってください。
- tests 配下には手元ファイルや絶対パスに依存するスクリプトが含まれています。CI 用 test と実験スクリプトは分離してください。
- 保存された FITS は channels-first、読み込み後は channels-last へ戻す方針です。
- `cache` は将来活用前にパス分離と schema 検証を見直してください。
