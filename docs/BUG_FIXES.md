# バグ修正記録

## PROJECT_OVERVIEW.md記載済みの修正

### `calibration/calibration.py` `Calibrator.calibrate`

- 症状: `flat = self.master.flat` のように参照を保持したまま補正すると、マスターフラットが破壊的に変更される可能性があった。
- 原因: NumPy配列の参照共有とin-place演算。
- 影響度: 高
- 修正: 入力画像とflatを `astype(..., copy=True)` / `copy=True` で作業配列化し、演算結果を新しい配列として返すようにした。

### `pipeline/processing_pipeline.py` キャリブレーション適用判定

- 症状: `if not CalibratedFrameProvider:` はクラスオブジェクト判定のため常にFalseになる。
- 原因: 設定値ではなくクラス自体を条件にしていた。
- 影響度: 高
- 修正: `AlignmentSettings.calibrate_before_align` と `CALIBRATE_BEFORE_ALIGN` を使う判定へ整理した。

### `stars/quality.py` FWHMのNoneフィルタ

- 症状: NumPy配列に対して `None` 比較すると警告や不安定な挙動につながる。
- 原因: object配列でのNone比較。
- 影響度: 低
- 修正: リスト内包表記で `f is not None` を使ってフィルタする実装を維持した。

## 今回新たに修正した問題

### `calibration/calibration.py` 入力画像のin-place変更

- 症状: `image.astype(np.float32)` がコピーを作らない場合、元画像が変更されうる。
- 原因: `copy=True` 未指定。
- 影響度: 高
- 修正: `calibrated = image.astype(np.float32, copy=True)` とし、最後に `np.clip(..., 0, None)` を適用した。

### `calibration/calibration.py` flat平均ゼロ除算

- 症状: flat平均がゼロまたは非有限値のとき除算でNaN/Infが発生する。
- 原因: `np.mean(flat)` の無条件使用。
- 影響度: 高
- 修正: 平均がゼロ相当ならflat補正をスキップし、警告ログを出す。

### `io/raw_loader.py` RAW読み込みのフレーム間補正差

- 症状: darkよりflatが暗く見えるなど、RAW現像由来の明るさ差が入りうる。
- 原因: rawpy `postprocess` の自動輝度、WB、ガンマがフレームごとに変わる可能性。
- 影響度: 高
- 修正: 通常読み込みは線形Bayerプレーン `raw_image_visible` に統一し、RGB現像用には `no_auto_bright=True`、`bright=1.0`、WB無効、16bit、`gamma=(1,1)` を明示する関数を追加した。

### `io/fits_loader.py` FITS符号なし整数とマスター認識

- 症状: FITSの `BZERO/BSCALE`、`FRAMTYP` の扱いが明示されていなかった。
- 原因: ヘッダー情報をメタデータへ反映していなかった。
- 影響度: 中
- 修正: astropyのスケール処理を有効にし、読み込み後は `float32` 非負値へ変換。`FRAMTYP=master_*` を `AstroImageInfo` へ記録するようにした。

### `io/standard_loader.py` 8bit/16bit値域

- 症状: 8bit画像だけ0から255で、16bit/RAWと値域が異なった。
- 原因: Pillow読み込み値をそのままfloat化していた。
- 影響度: 中
- 修正: 8bit標準画像は16bit作業範囲相当へスケールし、全ローダー出力を `float32` 非負へ統一した。

### `alignment/transform.py` 参照画像の変換行列None

- 症状: 参照フレームは `TransformData.matrix=None` のためwarp時に例外になりうる。
- 原因: identity変換を特別扱いしていなかった。
- 影響度: 高
- 修正: `matrix is None` の場合は変換せず `float32` で返す。

### `core/debayer.py` 1チャンネルBayer配列

- 症状: RAW読み込みが `(H, W, 1)` の場合、OpenCVのBayer変換へ不適切な形状が渡る。
- 原因: チャンネル次元を落としていなかった。
- 影響度: 高
- 修正: `np.squeeze` してからBayer変換し、CFA未指定なら変換せず返す。

### `stacking/combiner.py` 無効フレームの混入

- 症状: UIでチェックを外したフレームもスタック対象になる。
- 原因: `AstroImage.info.enabled` を参照していなかった。
- 影響度: 中
- 修正: `combine()` の入口で有効フレームだけに絞る。

### `pipeline/processing_pipeline.py` テスト用保存とprint

- 症状: パイプライン実行で `test_images/*.tiff` へ副作用保存し、標準出力へデバッグ情報を出していた。
- 原因: 検証コードが残っていた。
- 影響度: 中
- 修正: loggingへ置換し、マスターFITS保存と結果FITS自動保存のみを正式な副作用にした。

## 未修正の既知問題

- Sigma Clippingの繰り返し回数はUIに存在するが、現行 `ImageCombiner` では1回相当の処理のみ。
- 位置合わせのみ実行するボタンはキャリブレーションマスター生成までは行わない。スタック実行時は完全なパイプラインを通る。
- Plate Solve、Drizzle、クロップ、ホットピクセル除去は将来実装。
- Qtプラットフォームプラグインがこのシェル環境で見つからず、ヘッドレスUI起動確認は未完了。
