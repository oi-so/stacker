# Astro Stacker Release Review

レビュー日: 2026-07-04

対象: `src/astro_stacker`, `README.md`, `ARCHITECTURE.md`, `PROJECT_OVERVIEW.md`, `docs/*.md`

## 総評

現行コードは、初期設計の「Provider で処理段階を積む」「float32 に寄せる」「median/sigma で memmap を使う」
という方向へかなり進んでいます。一方で、README と古い設計文書は将来機能を実装済みのように見せる記述が残り、
コード側にもリリース前に潰したいクラッシュ経路、画像処理の正しさ、テスト実行性の問題があります。

結論として、現状は「開発版としては動くが、一般リリースには P0/P1 の修正が必要」です。

Critical は今回確認した範囲ではありません。High はリリース前に必ず直すべき問題、Medium は初回ベータ前に
優先して直したい問題、Low は通常利用では致命的でない問題として分類しています。

## 重要バグ

### High: QThread worker が成功時に `finished` を二重 emit する (修正済み)

根拠: `src/astro_stacker/ui/main_window.py:69-76`

`PipelineWorker.run()` は try ブロック内で `self.finished.emit()` し、さらに finally でも emit します。
`thread.quit`, `worker.deleteLater`, ログ接続が二重に発火しうるため、タイミング次第で終了処理や UI 更新が不安定になります。

修正案:

```python
try:
    self.func(self.progress.emit, lambda: self.cancel_requested)
except Exception as exc:
    logger.exception("Pipeline failed")
    self.failed.emit(exc)
finally:
    self.finished.emit()
```

### High: モノクロ 1ch 画像の位置合わせ warp が Bayer 専用処理に落ちる (カラーモードごとに処理を分離)

根拠: `src/astro_stacker/alignment/transform.py:30-64`, `src/astro_stacker/io/fits_loader.py:105-107`

FITS などの 2D 画像は `(H, W, 1)` に変換されますが、`ImageTransformer.apply_transform()` は
RGB 以外の 3D 画像を Bayer 分割として扱います。モノクロ FITS の位置合わせ結果が数学的に誤ります。

修正案:

- `image.ndim == 2` または `image.shape[-1] == 1` は通常の単チャンネル warp にする。
- Bayer 専用処理は `AstroImage.info.color_mode == ColorMode.BAYER` を見られる provider 側に寄せる。

### High: sigma clipping の UI 設定が実処理に渡らない

根拠: `src/astro_stacker/project/settings.py:22-26`, `src/astro_stacker/ui/dialogs.py:199-220`,
`src/astro_stacker/stacking/combiner.py:64-65`, `src/astro_stacker/stacking/combiner.py:264-327`

`StackingSettings.sigma` と `iterations` は UI で設定できますが、`ImageCombiner.combine()` は `_sigma_clip()` に
sigma を渡しておらず、iterations も未使用です。再現性と UI 信頼性に直結します。

修正案:

- `combine(..., settings: StackingSettings)` か `sigma`, `iterations` 引数を追加する。
- 反復 sigma clip の仕様を固定し、ドキュメントとテストを揃える。

### High: tests が CI 可能な pytest になっていない

根拠: `tests/test_stacking/test_combiner.py` は import 時に `test_align_and_stack_actual_images()` を直接実行し、
`method="mean"` を渡します。現行 enum は `StackingMethod.AVERAGE` であり、絶対パス保存も含みます。
`tests/test_io/loader_test.py` と `tests/test_alignment/*.py` も `AstroImage.load()` 前提や絶対パスがあります。

修正案:

- 実験スクリプトを `scripts/` へ移動する。
- pytest は小さな synthetic FITS/NumPy 配列だけで完結させる。
- `AstroImage.load()` 前提を `ImageManager.get_image()` に更新する。

### Medium: FITS WCS の型契約が崩れている

根拠: `src/astro_stacker/io/image_data.py:36-49`, `src/astro_stacker/io/fits_loader.py:54-79`

`AstroImageInfo.wcs` は `WCSData` 型ですが、FITS ローダーは astropy `WCS` オブジェクトを代入しています。
JSON 化、型チェック、UI 表示、将来の project 保存で破綻します。

修正案:

- `WCSData` に抽出できる値だけ入れる。
- astropy `WCS` を保持するなら別フィールドに分離する。

### Medium: 空スタック・全 alignment 失敗時のエラーが後段まで遅れる

根拠: `src/astro_stacker/pipeline/stacking_pipeline.py:18-28`,
`src/astro_stacker/stacking/combiner.py:56-65`, `src/astro_stacker/stacking/combiner.py:207`, `272`

位置合わせ失敗フレームはスキップされます。全フレームが失敗した場合、median/sigma は `images[0]` で
`IndexError`、average/add は `ValueError("No images provided")` になります。

修正案:

- `StackingPipeline.run()` で対象フレーム 0 件をユーザー向け `ValueError` にする。
- combiner の入口でも method 共通で空リスト検証を行う。

### Medium: プレビューが UI スレッドで重い処理を実行する

根拠: `src/astro_stacker/ui/main_window.py:331-347`, `src/astro_stacker/core/provider.py:120-147`

フレーム選択時にロード、位置合わせ warp、Debayer、binning、QImage 化が同期実行されます。
大型 RAW/FITS では UI フリーズします。

修正案:

- プレビュー専用 worker とキャンセル可能な最新リクエスト方式を入れる。
- 先に低解像度 preview を作り、full resolution は明示操作にする。

### Medium: 一時 memmap の保存先と容量管理が設定に接続されていない

根拠: `src/astro_stacker/project/project.py:26-29`, `src/astro_stacker/stacking/combiner.py:129-155`

`AppSettings.temp_directory` は存在しますが、median/sigma clip の `_build_memmap()` には渡されません。
数百から数千枚ではシステム temp を圧迫します。

修正案:

- `Project.app_settings.temp_directory` を `ImageCombiner` へ渡す。
- 事前に必要容量を見積もり、空き容量不足なら処理前に止める。

### Medium: 画像 shape/dtype の入力検証が不足している

根拠: `src/astro_stacker/stacking/combiner.py:81-86`, `180`, `src/astro_stacker/calibration/calibration.py:55-69`

異なる解像度、RGB/mono 混在、master と light の shape 不一致が後段の NumPy broadcast/代入例外になります。

修正案:

- ファイル追加時または pipeline 開始時に light/master の shape と color mode を検証する。
- ユーザーに対象ファイル名付きでエラーを返す。

### Medium: cache 実装に相互上書き経路がある

根拠: `src/astro_stacker/cache/manager.py:39-86`, `src/astro_stacker/cache/models.py:19-25`

`CachePaths` には `alignment.json` と `quality.json` があるのに、`CacheManager.save_quality()` は
`self.paths.alignment` へ保存しています。使い始めると alignment cache を壊します。

修正案:

- `save_quality/load_quality` は `self.paths.quality` を使う。
- `AlignmentCache` / `QualityCache` と `CacheManager` の重複 API を整理する。

### Low: 画像表示で sigma=0 のとき NaN が出る

根拠: `src/astro_stacker/ui/viewer/image_viewer.py:178-186`

一定値画像では `arr / (stretch * sigma)` がゼロ除算になります。

修正案:

- `sigma <= 1e-8` の場合は min/max またはゼロ画像へフォールバックする。

## Qt / GUI レビュー

- pipeline は QThread に逃がしており、基本方針は良いです。
- worker の二重 finished emit は早急に直すべきです。
- `Project` と `ImageManager` は worker と UI の共有状態です。処理中 UI を disable しているため大きな競合は避けていますが、
  プレビューと worker が同じ `ImageManager` を同時に触る余地はあります。
- progress はフレーム単位/チャンク単位で、頻度は現実的です。
- キャンセルは cooperative で、`ThreadPoolExecutor` に投入済みの星検出は即停止しません。

## メモリ・性能レビュー

- `ImageManager` は枚数ベース LRU で、巨大画像のメモリ上限としては不十分です。
- mean/add は accumulator だけなので比較的軽いですが、入力ロードが provider/cache に依存します。
- median/sigma clip は memmap でメモリを抑えていますが、ディスク容量は `N * frame_size` 必要です。
- sigma clip の各チャンクは `copy=True` で読み込むため、チャンクサイズ 512MB 近くまでメモリを使います。
- alignment の `ThreadPoolExecutor(max_workers=os.cpu_count()-1)` は RAW decode と星検出でメモリスパイクしやすいです。

## 画像処理の正しさ

- RAW を線形 Bayer として読む方針は良いです。
- Debayer 後の値域が `0..1` になるため、標準/FITS の `0..65535` 系と混ざる時は正規化方針を明示する必要があります。
- sigma clipping は1回の mean/std 判定で、median/MAD ベースではありません。宇宙線や衛星軌跡には弱い場合があります。
- `np.nanmean()` は全フレーム除外ピクセルで NaN を返す可能性があります。
- FWHM 計測不能時に品質スコアが極端に大きくなるため、品質選別実装前に修正が必要です。

## 設計・アーキテクチャ差分

- `ARCHITECTURE.md` / `PROJECT_OVERVIEW.md` は `AstroImage.load()/unload()` を前提にしていますが、現行コードは
  `ImageManager` にロード責務を寄せています。
- README は Plate Solve、Drizzle、彗星/天体基準、比較明、重み付きスタックなどを実装済み風に記述していましたが、
  現行コードでは多くが未実装です。
- `docs/SPEC.md` は現行実装に近いですが、median/sigma の制限説明が古く、memmap 容量面の注意が不足していました。
- `docs/specification.md` は古い仕様メモで、存在しないクラス名や未配線という古い説明が残っています。

## テスト不足

- Unit test: combiner, calibration, debayer, transform, loader の synthetic test が不足。
- Integration test: small FITS/PNG を生成して ProcessingPipeline を最後まで通す test が必要。
- GUI test: dialog 設定反映、worker 成功/失敗/キャンセル、プレビューの smoke test が不足。
- 現環境では `python -m pytest -q` は pytest 未導入で実行不可でした。
- `python -m compileall -q src tests` は成功しました。

## 優先改善事項

- P0: QThread worker finished 二重 emit 修正、テストを import 時副作用なしに修正。
- P1: 1ch FITS warp 修正、sigma/iterations を処理へ接続、空スタックのユーザー向けエラー、shape 検証。
- P2: temp directory/容量見積もり、バイト数ベース LRU、プレビュー非同期化、cache API 整理。
- P3: BEST 参照画像、品質スコア改善、Plate Solve/Drizzle/クロップ/ホットピクセル除去。

## コード品質

- 良い点: Provider による段階合成、float32 統一、memmap 導入、logging 使用は方向性が良いです。
- 改善点: 長い UI クラス、古い実験 test、設定値の未使用、cache API 重複、ドキュメントとの乖離があります。
- 型ヒントは主要箇所にありますが、Provider 周辺と UI callback はまだ薄いです。
- コメントは一部有用ですが、古い設計コメントが実装とズレています。

## 最終評価

- 設計: 7/10
- 保守性: 5/10
- 拡張性: 7/10
- 可読性: 6/10
- 性能: 6/10
- Python らしさ: 6/10

P0/P1 を潰せば、初回ベータとしては十分見えるところまで来ています。一般ユーザー向けリリースでは、
テストとドキュメント整合性がまだ最大のリスクです。
