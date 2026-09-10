# Astro Stacker

Astro Stacker は、天体写真・星景写真・新星景写真・移動天体・HDR・タイムラプス素材を、
共通パイプラインで処理する Python / PySide6 製デスクトップアプリです。

まずは[詳しい使い方](docs/USER_GUIDE.md)を参照してください。開発者向けの詳細は
`PROJECT_GUIDE.md`、リリース前レビューは `RELEASE_REVIEW.md`、処理仕様は `docs/SPEC.md` にあります。

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
- Average / Median / Add / Sigma Clipping / 比較明 / 比較暗 / 最大・最小除外平均スタック
- float32 Weight Mask、位置合わせ無効領域の除外、品質重み付きスタック
- 露出時間・背景の正規化と品質スコアによる自動フレーム選別
- 位置合わせ済み全画像、星マスク、編集可能な地上マスクの書き出し
- 共通座標の露出別スタック、線形HDR Merge、Global / Local / Log Tone Mapping
- 星空・地上・マスク・光害フレームを個別出力できる新星景処理
- 地上固定Alignment、手動Polygon編集、移動方向の解析と時間グループ分割
- Sliding Window対応のタイムラプス用n枚スタック
- 2x / 3x Drizzle（Pixfrac指定、Average / Add）
- Hot / Cold Pixel・異常列を検出するBad Pixel Map生成とCFA対応補正
- 手動Polyline／半自動候補検出による電線・電柱・局所障害物のWeight Mask除外
- FITS WCSによる高速位置合わせと、画像準備のメモリ制限付き並列先読み
- 容量制限付き画像キャッシュと、RAM / 一時 memmap を使い分けるスタック処理
- スタック結果の `stacked*.fits` 自動保存
- 画像プレビュー、ズーム、検出星の表示
- QThread による pipeline の非同期実行
- Python logging を GUI ログパネルへ表示

## プロジェクト保存とEXIF

「ファイル → プロジェクトを保存」で、画像一覧・使用チェック・位置合わせ・Plate Solve・処理設定・表示状態を `.astrostacker` に保存できます。画像ごとの解析履歴は隣の `.astrostacker.json` に自動保存し、再読込時に利用します。

スタック出力には総露出時間、最頻値のISO・F値と、混在条件の内訳を記録します。操作と復元条件は[プロジェクト保存とメタデータ](docs/PROJECTS_AND_METADATA.md)を参照してください。

## 主な制限

- クロップ範囲選択
- 元画像のMakerNoteなど独自EXIFの完全継承
- 言語切り替えの即時反映
- RAW以外を含む非線形画像での露出正規化は、入力の現像状態に依存する
- DrizzleはMedian / Sigma Clipping / 比較明暗では使用できない
- 電線などで全フレームの同一出力画素が隠れる場合は生成補完せず無効画素になる

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

1. ツールバーの「フレーム追加」からLightフレームを追加する。
2. 必要に応じて Dark / Flat / Flat Dark / Bias を追加する。
3. 使用するフレームにチェックを入れる。
4. 「位置合わせ」または「スタック」を実行する。
5. スタック完了後、Light フレームのフォルダに `stacked.fits`, `stacked2.fits` のように自動保存される。
6. 「保存」から任意形式で別名保存できる。

プロジェクトの読込・保存はツールバーから直接実行できます。HDR、新星景、星マスク、地上マスク、
タイムラプス、Bad Pixel Map、位置合わせ済み画像の出力は「追加処理」ボタンにまとめています。
スタック設定は「基本」「正規化・選別」「Drizzle・補正」のタブに分かれ、電線・電柱マスクも
「Drizzle・補正」タブから作成して、そのままスタックに使用できます。
ファイル選択画面は最後に使用したフォルダから開きます。

## Plate Solve と移動天体スタック

Plate SolveにはPythonパッケージとは別に、ローカルのAstrometry.net本体と撮影画角に合う
indexファイルが必要です。`solve-field` がPATHにない場合は、スタック設定内の
「solve-field」欄に実行ファイルの絶対パスを指定できます。

1. Lightフレームを追加して「位置合わせしてスタック」を選ぶ。
2. スタック設定の「移動天体基準」を選び、「赤経・赤緯 / カタログ / Plate Solve 設定...」を開く。
3. 先頭画像の撮影開始時刻だけを必要に応じて修正する。元の時刻が揃っていれば各画像の実間隔を維持し、欠損時は指定した一定間隔で全画像を自動補完する。
4. 次のどちらかで天体位置を設定する。
   - 手入力: 先頭・末尾など2枚以上にICRS/J2000赤経・赤緯（度）を入力する。
   - カタログ: NASA/JPL SBDBから彗星・小惑星を検索し、Horizonsで全露光中央時刻の見かけ位置を計算する（インターネット接続が必要）。
5. 中央付近の位置合わせ参照画像を選び、「基準画像をPlate Solve（推奨設定）」を実行する。天体位置が計算済みなら8度の探索範囲ヒントを使う。
6. 移動天体を固定したい時刻の画像を選び、設定を確定してスタックを開始する。

ツールバーの「Plate Solve」からも、フレーム一覧で現在選択中の1枚を実行できます。
Plate Solveしていないフレームは、恒星位置合わせの変換行列と参照画像のWCSから座標を求めるため、
全画像をPlate Solveする必要はありません。
星マーカーを表示すると、全星/位置合わせ星に加えて予測された移動天体位置がシアンの十字円で表示されます。手入力とカタログの両モードに対応します。

## 開発環境

依存関係と仮想環境は [uv](https://docs.astral.sh/uv/getting-started/installation/) で管理します。
uv をインストール後、プロジェクトのルートで実行してください。
標準の Python バージョンは `.python-version` で 3.12 に指定しています。

```bash
uv sync --locked
uv run astro-stacker
```

`uv sync --locked` は `uv.lock` に固定された依存関係と開発用ツールを `.venv` にインストールします。
Python 3.12 が見つからない場合は uv が自動で取得します。
仮想環境の手動有効化や `PYTHONPATH` の設定は不要です。
モジュール形式で起動する場合は `uv run python -m astro_stacker` も使えます。

アプリの実行用依存関係だけをインストールする場合:

```bash
uv sync --locked --no-dev
uv run --no-dev astro-stacker
```

開発用コマンド:

```bash
uv run pytest
uv run ruff check src
uv run black --check src
uv run mypy src
```

依存関係の追加は `uv add パッケージ名`、開発用は `uv add --dev パッケージ名` を使います。
`pyproject.toml` を直接編集した場合は `uv lock` でロックファイルを更新し、`uv sync --locked` で反映してください。
`pyproject.toml`、`uv.lock`、`.python-version` は一緒にバージョン管理します。

## 開発者向けメモ

- 現行のロード責務は `AstroImage.load()` ではなく `ImageManager.get_image()` にあります。
- 画像配列は原則 `np.float32` かつ非負値です。
- 画像キャッシュは256MiB、スタック一時ファイルは最大8GiB・SSD空き8GiB確保が既定値です。[処理速度とリソース設定](docs/PERFORMANCE.md)を参照してください。
- `docs/specification.md` は古い仕様メモです。現行仕様は `docs/SPEC.md` を優先してください。
- `uv run pytest` は外部画像不要の `tests/regression/` を実行します。従来のローカル画像依存スクリプトは自動収集対象外です。

## ライセンス

MIT
