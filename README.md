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
- Astrometry.net (`solve-field`) によるローカル Plate Solve
- 赤経・赤緯アンカーを使った彗星・小惑星などの移動天体基準スタック
- Average / Median / Add / Sigma Clipping スタック
- Median / Sigma Clipping 用の一時 memmap 処理
- スタック結果の `stacked*.fits` 自動保存
- 画像プレビュー、ズーム、検出星の表示
- QThread による pipeline の非同期実行
- Python logging を GUI ログパネルへ表示

## 未実装または制限あり

- Drizzle
- クロップ範囲選択
- ホットピクセル除去
- 比較明合成
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

## Plate Solve と移動天体スタック

Plate SolveにはPythonパッケージとは別に、ローカルのAstrometry.net本体と撮影画角に合う
indexファイルが必要です。`solve-field` がPATHにない場合は、スタック設定内の
「solve-field」欄に実行ファイルの絶対パスを指定できます。

1. Lightフレームを追加して「位置合わせしてスタック」を選ぶ。
2. スタック設定の「移動天体基準」を選び、「赤経・赤緯 / Plate Solve 設定...」を開く。
3. 位置合わせ参照画像を選択し、その行を選んで「選択画像をPlate Solve」を実行する。
4. 通常は先頭・末尾の「座標点」を有効にして、対象天体の赤経・赤緯を度単位で入力する。
5. 必要なら中間フレームにも座標点を追加し、設定を確定してスタックを開始する。

ツールバーの「Plate Solve」からも、フレーム一覧で現在選択中の1枚を実行できます。
Plate Solveしていないフレームは、恒星位置合わせの変換行列と参照画像のWCSから座標を求めるため、
全画像をPlate Solveする必要はありません。

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
