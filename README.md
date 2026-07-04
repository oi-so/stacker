# Astro Stacker

Astro Stacker は、天体写真のライトフレームとキャリブレーションフレームを読み込み、
星基準の位置合わせ、補正、スタック、保存を行う Python / PySide6 製デスクトップアプリです。

この README は現行実装を基準にしています。開発者向けの詳細は `PROJECT_GUIDE.md`、リリース前レビューは
`RELEASE_REVIEW.md`、処理仕様は `docs/SPEC.md` を参照してください。

## 現在実装済み

- PySide6 GUI
- Light / Dark / Flat / Flat Dark / Bias フレームの追加と有効/無効切り替え
- RAW / FITS / PNG / JPEG / TIFF の読み込み
- FITS / TIFF / PNG / JPEG の保存
- RAW の線形 Bayer プレーン読み込み
- `np.float32` ベースの内部処理
- Dark / Bias / Flat / Flat Dark からのマスターフレーム生成
- マスター FITS の自動保存と再利用
- photutils による星検出
- astroalign による星基準位置合わせ
- Average / Median / Add / Sigma Clipping スタック
- Median / Sigma Clipping 用の一時 memmap 処理
- スタック結果の `stacked*.fits` 自動保存
- 画像プレビュー、ズーム、検出星の表示
- QThread による pipeline の非同期実行
- Python logging を GUI ログパネルへ表示

## 未実装または制限あり

- Plate Solve
- Drizzle
- クロップ範囲選択
- ホットピクセル除去
- 比較明合成
- 彗星や小惑星などの天体基準位置合わせ
- 重み付きスタック
- 露出差の正規化 / inverse variance weighting
- EXIF / WCS メタデータの完全継承
- 言語切り替えの即時反映
- プロジェクトファイルの完全保存/復元
- Sigma Clipping の繰り返し回数反映
- 参照画像の「最高品質」自動選択

## 対応ファイル形式

入力:

- RAW: `.arw`, `.cr2`, `.cr3`, `.nef`, `.raf` など rawpy 対応形式
- FITS: `.fits`, `.fit`, `.fts`
- 標準画像: `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`

出力:

- FITS
- TIFF
- PNG
- JPEG

## 基本フロー

1. Light フレームを追加する。
2. 必要に応じて Dark / Flat / Flat Dark / Bias を追加する。
3. 使用するフレームにチェックを入れる。
4. 「位置合わせ」または「スタック」を実行する。
5. スタック完了後、Light フレームのフォルダに `stacked.fits`, `stacked2.fits` のように自動保存される。
6. 「保存」から任意形式で別名保存できる。

## 開発環境

Python 3.12 以上を想定しています。

```bash
python -m pip install -e ".[dev]"
python -m astro_stacker
```

または:

```bash
astro-stacker
```

## 開発者向けメモ

- 現行のロード責務は `AstroImage.load()` ではなく `ImageManager.get_image()` にあります。
- 画像配列は原則 `np.float32` かつ非負値です。
- Median / Sigma Clipping はメモリ節約のため一時 memmap を使いますが、ディスク容量はフレーム総量分必要です。
- `docs/specification.md` は古い仕様メモです。現行仕様は `docs/SPEC.md` を優先してください。
- `tests/` には手元画像や絶対パスに依存する実験スクリプトが残っています。CI 用テスト整備はリリース前課題です。

## ライセンス

MIT
