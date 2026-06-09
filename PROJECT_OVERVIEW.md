# Astro Stacker プロジェクト詳細概要

## 目次
1. [プロジェクト概要](#プロジェクト概要)
2. [アーキテクチャ](#アーキテクチャ)
3. [画像処理パイプライン](#画像処理パイプライン)
4. [主要クラス一覧](#主要クラス一覧)
5. [設計思想](#設計思想)
6. [実装済み機能](#実装済み機能)
7. [未実装または今後実装予定の機能](#未実装または今後実装予定の機能)
8. [開発者向け要約](#開発者向け要約)
9. [既知の設計上の検討事項](#既知の設計上の検討事項)
10. [修正履歴](#修正履歴)

---

## プロジェクト概要

### このソフトウェアの目的

**Astro Stacker** は、天体写真の位置合わせ、キャリブレーション、スタッキング処理を行うデスクトップアプリケーションです。

天文愛好家や天体写真家が複数の天体写真画像を撮影した際に、これらの画像を自動的に位置合わせし、統計的に合成することで、ノイズを低減し、信号対雑音比（Signal-to-Noise Ratio, SNR）を大幅に改善した最終画像を生成することを目的としています。

### 解決したい課題

天体写真の撮影には以下の課題があります：

1. **ノイズ問題**：暗い被写体を撮影する際、高ISO感度やロングシャッター使用により、電子ノイズ（dark thermal noise）やショットノイズが増加する
2. **環境変動**：同じ被写体であっても、焦点距離のズレ、大気の揺らぎ、雲の影響により、個々の画像の品質がばらつく
3. **手動処理の煩雑性**：複数画像の位置合わせを手動で行うのは時間がかかり、誤差も大きい
4. **メモリ効率**：数十～数百枚の高解像度RAW画像を扱う際に、メモリ不足が問題になりやすい
5. **キャリブレーションの複雑性**：Dark フレーム、Bias フレーム、Flat フレームなど複数の補正画像を適切に組み合わせる必要がある

### 想定ユーザー

- **天文愛好家**：アマチュア天体写真家で、天体撮影の成果物を自分で処理したい人
- **天体写真研究者**：研究目的で天体画像処理を行う学生や研究者
- **観測施設スタッフ**：公開天文台などで撮影画像の一次処理を行う人

### 主な機能

#### 1. 位置合わせ（Alignment）
- **星ベースの自動位置合わせ**：検出した恒星の位置を基準に、複数画像を自動的に位置合わせ
- **複数の変換パラメータ対応**：並進（dx, dy）、回転、スケール変更に対応
- **マッチング統計情報**：参照画像との一致星数、RMS誤差などを記録
- **柔軟な参照画像選択**：デフォルトは中央画像、手動選択も可能（将来実装予定）

#### 2. キャリブレーション（Calibration）
- **Dark フレーム**：熱ノイズ除去
- **Bias フレーム**：DC オフセット除去
- **Flat フレーム**：光学系による不均一性補正（ビネッティング、ダストスポット除去）
- **Flat-Dark フレーム**：Flat フレーム自体のノイズ補正
- **選択的適用**：各フレームタイプは独立して有効/無効を切り替え可能
- **マスターフレーム生成**：複数のキャリブレーション画像から統計的にマスターフレームを作成

#### 3. スタッキング（Stacking）
複数の位置合わせ済み画像を統計的に合成：

- **Mean（平均）**：最も単純で高速、外れ値に弱い
- **Median（中央値）**：外れ値に強く、実用的
- **Sigma Clipping**：統計的に外れ値を除去（実装予定）
- **Winsorized Sigma Clipping**：Sigma Clipping の変種（実装予定）
- **Add（加算）**：全フレームの単純加算、結果は非常に明るい

#### 4. 画質評価（Quality Assessment）
- **検出星数**：画像内で検出された恒星の数（多いほど高品質）
- **FWHM 測定**：星の Full Width at Half Maximum。星像が鋭いほど低い値（低いほど高品質）
- **楕円度**：星の形状の崩れ（低いほど高品質）
- **背景ノイズレベル**：背景のノイズ標準偏差
- **雲検出スコア**：薄雲の影響を検出（将来実装予定）

画質スコア = 星数 / (FWHM + 1e-6) で計算

#### 5. 複数ファイル形式対応
**読み込み対応**：
- RAW フォーマット：Canon CR2、CR3、Nikon NEF、Sony ARW、Fujifilm RAF など
- FITS フォーマット：天文学標準フォーマット
- 標準フォーマット：PNG、JPEG、TIFF

**出力対応**：
- FITS、TIFF、PNG、JPEG

#### 6. Plate Solve（将来実装予定）
- astrometry.net CLI との連携による天体座標決定
- WCS（World Coordinate System）情報の取得
- RA/Dec グリッド表示
- 天体名表示（メシエ天体、NGC 天体、IC 天体）

#### 7. Drizzle 処理（将来実装予定）
サブピクセル精度での画像拡大縮小：
- 1.5倍、2倍、4倍での補間処理

#### 8. その他の機能
- **ホットピクセル除去**（実装予定）
- **クロップ範囲選択**（実装予定）
- **ログ出力**：処理過程の詳細ログ記録
- **キャッシュ処理**：再計算の回避
- **国際化対応**：日本語・英語
- **EXIF/メタデータ継承**：出力画像にメタデータを埋め込み

---

## アーキテクチャ

### 1. ディレクトリ構成と各モジュールの責務

```
src/astro_stacker/
├── app.py                          # アプリケーション エントリーポイント
├── core/
│   └── provider.py                 # FrameProvider プロトコル定義
├── alignment/                      # 画像位置合わせモジュール
│   ├── aligner.py                  # 位置合わせ実行エンジン
│   ├── matcher.py                  # 星マッチング (astroalign 利用)
│   ├── alignment_data.py           # AlignmentResult データクラス
│   └── transform.py                # 変換適用と AlignedFrameProvider
├── calibration/                    # キャリブレーション処理
│   ├── calibration.py              # Calibrator と MasterFrameBuilder
│   └── provider.py                 # CalibratedFrameProvider
├── io/                             # 入出力
│   ├── loader.py                   # 統一ローダーインターフェース
│   ├── fits_loader.py              # FITS ファイル読み込み
│   ├── raw_loader.py               # RAW ファイル読み込み (rawpy)
│   ├── standard_loader.py          # PNG/JPEG/TIFF 読み込み (PIL)
│   ├── saver.py                    # ファイル保存
│   ├── image_data.py               # コアデータクラス群
│   └── image_manager.py            # メモリ管理（LRU キャッシュ）
├── logging/                        # ログ機能（将来実装）
├── metadata/                       # メタデータ処理（将来実装）
├── pipeline/                       # 処理パイプライン
│   ├── processing_pipeline.py      # 全体のオーケストレーション
│   ├── alignment_pipeline.py       # 位置合わせパイプライン
│   ├── stacking_pipeline.py        # スタッキングパイプライン
│   └── result_data.py              # 処理結果データクラス
├── project/                        # プロジェクト管理
│   ├── project.py                  # Project、ProjectSettings クラス
│   └── settings.py                 # 各種処理設定クラス
├── quality/                        # （モジュール存在、内容未実装）
├── stacking/                       # スタッキング処理
│   └── combiner.py                 # ImageCombiner（複数統計手法）
├── stars/                          # 星検出・分析
│   ├── detector.py                 # 星検出（DAOStarFinder 利用）
│   ├── star_data.py                # Star、StarCatalog データクラス
│   ├── fwhm.py                     # FWHM 測定
│   └── quality.py                  # QualityAnalyzer
├── platesolve/                     # Plate Solve（モジュール未実装）
├── drizzle/                        # Drizzle 処理（モジュール未実装）
├── i18n/                           # 国際化（モジュール未実装）
├── ui/                             # UI レイヤー（モジュール未実装）
└── __init__.py
```

### 2. モジュール間の依存関係

```
FrameProvider (プロトコル)
├── ImageManagerProvider
│   └── CalibratedFrameProvider
│       └── AlignedFrameProvider
└── CalibratedFrameProvider
    └── AlignedFrameProvider
```

**依存フロー**：
- `ProcessingPipeline` は `ImageManager` を使って `ImageManagerProvider` を作成
- キャリブレーション前に適用する場合、`ImageManagerProvider` を `CalibratedFrameProvider` でラップ
- `AlignmentPipeline` は `FrameProvider` から星検出用画像を取得
- `StackingPipeline` は `AlignedFrameProvider` でラップされた provider から位置合わせ済み画像を取得

この **Decorator パターン** 的な設計により、処理の各段階を柔軟に組み合わせ可能。

### 3. コアデータ構造

#### AstroImage と AstroImageInfo

```
AstroImage
├── info: AstroImageInfo           # メタデータ（常にメモリ内）
│   ├── path: Path                 # ファイルパス
│   ├── shape: ImageShape          # 画像寸法
│   ├── bit_depth: int             # ビット深度
│   ├── exposure_time: float       # 露出時間（秒）
│   ├── iso: int                   # ISO 感度
│   ├── f_number: float            # F 値
│   ├── exif: dict                 # EXIF データ
│   ├── wcs: WCSData               # 天体座標系情報
│   ├── score_data: ScoreData      # 画質メトリクス
│   ├── transform: TransformData   # 位置合わせ変換情報
│   ├── alignment_data: AlignmentData # マッチング統計
│   └── enabled: bool              # 使用フラグ
└── image: np.ndarray | None       # ピクセルデータ（遅延読み込み）
```

**設計の特徴**：
- `image` は遅延読み込み（lazy loading）で メモリ効率化
- `info` は常にメモリ内に保持（メタデータは小さい）
- `ImageManager` で `image` の自動ロード/アンロードを管理

#### TransformData

位置合わせの結果：
```
TransformData
├── dx: float                      # X シフト（ピクセル）
├── dy: float                      # Y シフト（ピクセル）
├── rotation: float                # 回転角度（度）
├── scale: float                   # スケール係数
└── matrix: np.ndarray             # 3×3 同次座標変換行列
```

#### ScoreData

画質評価結果：
```
ScoreData
├── score: float                   # 総合スコア
├── star_count: int                # 検出星数
├── fwhm: float                    # 平均 FWHM（ピクセル）
├── ellipticity: float             # 楕円度
├── background_noise: float        # 背景ノイズ標準偏差
└── cloud_score: float             # 雲検出スコア
```

#### AlignmentData

星マッチング統計：
```
AlignmentData
├── reference_star_count: int      # 参照画像内の星数
├── matched_star_count: int        # マッチした星数
└── rms_error: float               # RMS 誤差（ピクセル）
```

#### Star と StarCatalog

```
Star
├── x: float                       # X 座標（ピクセル）
├── y: float                       # Y 座標（ピクセル）
├── flux: float                    # 総フラックス
├── peak: float                    # ピークピクセル値
├── sharpness: float               # 鋭度メトリクス
├── roundness: float               # 円形度メトリクス
├── fwhm: float                    # FWHM（後計算）
└── ellipticity: float             # 楕円度（後計算）

StarCatalog
└── stars: list[Star]              # 検出された星の一覧
    └── brightest(n): list[Star]   # N 番目までの明るい星を取得
```

### 4. データフロー

```
ファイルシステム
    ↓
loader.load_info() → AstroImage (info のみ)
    ↓
Project (light_frames, calibration_frames)
    ↓
ProcessingPipeline.run()
    ├─→ MasterFrameBuilder
    │   ├─→ ImageManager.get_image() [ローディング]
    │   └─→ ImageCombiner.combine() [統計処理]
    │       → master_calibration_frames
    ├─→ AlignmentPipeline.run()
    │   ├─→ ImageManager.get_image() [ローディング]
    │   ├─→ detect_stars() [photutils]
    │   ├─→ align_catalogs() [astroalign]
    │   └─→ AstroImage.info.transform = TransformData
    └─→ StackingPipeline.run()
        ├─→ AlignedFrameProvider
        │   ├─→ CalibratedFrameProvider（オプション）
        │   │   └─→ ImageManager.get_image()
        │   └─→ ImageTransformer.apply_transform()
        └─→ ImageCombiner.combine()
            → Project.result.stacked_image
```

---

## 画像処理パイプライン

### 処理の全体フロー

```
1. 画像ファイルの読み込み
   ├─ loader.load_info(path): メタデータのみ読み込み
   └─ 結果: Project.light_frames に AstroImage を追加

2. マスターキャリブレーションフレーム生成
   ├─ Dark、Bias、Flat、Flat-Dark フレームがあれば
   ├─ MasterFrameBuilder が各グループを統計合成
   └─ 結果: Project.master_calibration_frames

3. 位置合わせ（AlignmentPipeline）
   ├─ 参照画像の選択（デフォルト: 中央)
   ├─ 全ての light frame について:
   │  ├─ ImageManager.get_image() でピクセルデータをロード
   │  ├─ detect_stars() で恒星を検出（photutils）
   │  └─ align_catalogs() で参照画像との星マッチング
   │     └─ astroalign で相似変換を計算
   ├─ 各 AstroImage.info.transform に変換情報を保存
   └─ 結果: TransformData（dx, dy, rotation, scale, matrix）

4. スタッキング（StackingPipeline）
   ├─ AlignedFrameProvider でラップ
   │  └─ 各フレームに対して transform を自動適用
   ├─ ImageCombiner.combine() で統計合成
   │  ├─ Mean: 平均値
   │  ├─ Median: 中央値
   │  ├─ Sigma Clip: 外れ値除去
   │  └─ Add: 加算
   └─ 結果: Project.result.stacked_image

5. 出力
   └─ save_preview_tiff() などで結果を保存
```

### 各段階の詳細

#### 段階1: 画像読み込み

```python
# tests/test.py の例
project.light_frames = load_folder(test_dir / "lights")
# → loader.load_info(file) を各ファイルに対して実行
# → AstroImage オブジェクトを生成（image フィールドは None）
```

利点：
- メモリ効率：ファイルメタデータのみ読み込み
- 高速：処理前に全画像のメタデータが利用可能

#### 段階2: マスターキャリブレーションフレーム生成

```python
# ProcessingPipeline._build_master_frames()
builder = MasterFrameBuilder(provider)
project.master_calibration_frames.dark = builder.build(
    project.calibration_frames.darks,
    project.settings.dark_frame.method  # デフォルト: "median"
)
```

特徴：
- 複数の Dark フレームを統計的に合成（ノイズを低減）
- 各フレームタイプは独立して生成
- combine() で統計手法を選択可能

#### 段階3: 位置合わせ

```python
# AlignmentPipeline.run()
reference_image = provider.get_image(reference)  # ピクセルデータをロード
reference_catalog = detect_stars(reference_image)  # 恒星検出

for astro_image in project.light_frames:
    image = provider.get_image(astro_image)  # ピクセルデータをロード
    catalog = detect_stars(image)
    result = align_catalogs(reference_catalog, catalog)
    # → AlignmentResult(transform, alignment_data)
    astro_image.info.transform = result.transform
    astro_image.info.alignment_data = result.info
```

**使用技術**：
- **photutils.DAOStarFinder**: DAO（Difference of Gaussian）アルゴリズムで恒星検出
- **astroalign**: 2つの星カタログから最適な相似変換（平行移動、回転、スケール）を計算

**出力**：
- `TransformData`: 変換行列とパラメータ
- `AlignmentData`: マッチング統計（一致星数、RMS誤差）

#### 段階4: スタッキング

```python
# StackingPipeline.run()
aligned_provider = AlignedFrameProvider(provider, ImageTransformer())
combiner = ImageCombiner(aligned_provider)
result = combiner.combine(
    project.light_frames,
    settings.method  # "mean", "median", "sigma_clip", "add"
)
```

**スタッキング方法**：

| 方法 | 説明 | 強み | 弱み |
|------|------|------|------|
| Mean | 全フレームの平均 | 高速、シンプル | 外れ値に弱い |
| Median | 全フレームの中央値 | 外れ値に強い | やや遅い |
| Sigma Clip | N-sigma 外の値を除去してから平均 | バランス型（実装予定） | パラメータ調整が必要 |
| Add | 全フレームを加算 | 信号最大化 | 結果が非常に明るい |

#### 段階5: 出力

```python
# tests/test.py
save_preview_tiff(result, output_path)
```

出力形式：
- FITS: 天文学標準、メタデータ豊富
- TIFF: 汎用、色深度保持
- PNG / JPEG: Web 表示用

---

## 主要クラス一覧

### コアクラス

#### 1. AstroImage / AstroImageInfo

**ファイル**: [io/image_data.py](src/astro_stacker/io/image_data.py)

**役割**: 天体画像とそのメタデータを表現

| 項目 | 内容 |
|------|------|
| 入力 | ファイルパス、メタデータ |
| 出力 | AstroImage オブジェクト |
| 他クラスとの関係 | `ImageManager` が管理、`Pipeline` が処理 |
| 責務 | 遅延読み込み、メタデータ保持、変換情報の記録 |

**主要プロパティ**：
- `info`: メタデータ（常にメモリ内）
- `image`: ピクセルデータ（遅延読み込み）
- `is_loaded`: ロード状態の確認

**メソッド**：
- `load()`: ピクセルデータをディスクから読み込み
- `unload()`: ピクセルデータをメモリから削除

#### 2. Project / ProjectSettings

**ファイル**: [project/project.py](src/astro_stacker/project/project.py), [project/settings.py](src/astro_stacker/project/settings.py)

**役割**: 処理対象の全画像とその設定を管理

| 項目 | 内容 |
|------|------|
| 入力 | 画像ファイルリスト、設定パラメータ |
| 出力 | 処理結果（スタック画像） |
| 他クラスとの関係 | `Pipeline` の入力、全体の統合点 |
| 責務 | 画像グループ管理、処理設定の保持 |

**主要フィールド**：
- `light_frames`: 対象画像リスト
- `calibration_frames`: キャリブレーション画像グループ
- `master_calibration_frames`: 生成されたマスターフレーム
- `reference_image`: 位置合わせの参照画像
- `settings`: 各種処理設定
- `result`: 処理結果

---

### 入出力（IO）

#### 3. ImageManager

**ファイル**: [io/image_manager.py](src/astro_stacker/io/image_manager.py)

**役割**: メモリ効率的な画像データ管理

| 項目 | 内容 |
|------|------|
| 入力 | AstroImage、メモリ上限 |
| 出力 | ピクセルデータ（np.ndarray） |
| 他クラスとの関係 | `Pipeline` から呼び出し、`FrameProvider` の実装 |
| 責務 | LRU キャッシュ、自動メモリ管理 |

**主要メソッド**：
- `get_image(image)`: 画像をロード＆キャッシュ（LRU 管理）
- `load(image)`: 明示的ロード
- `unload(image)`: 明示的アンロード
- `is_loaded(image)`: ロード状態確認
- `loaded_count()`: 現在ロード中の画像数

**メモリ管理戦略**：
- OrderedDict で LRU 順序を追跡
- `max_loaded_image_count` を超えると最も古い画像を自動アンロード
- デフォルト: 5枚（大容量メモリでは増加推奨）

#### 4. ImageCombiner

**ファイル**: [stacking/combiner.py](src/astro_stacker/stacking/combiner.py)

**役割**: 複数画像を統計的に合成

| 項目 | 内容 |
|------|------|
| 入力 | AstroImage リスト、統計方法 |
| 出力 | 合成画像（np.ndarray） |
| 他クラスとの関係 | `StackingPipeline` と `MasterFrameBuilder` で使用 |
| 責務 | 統計合成の実行 |

**主要メソッド**：
- `combine(images, method)`: 指定方法で合成
  - `"mean"`: 平均
  - `"median"`: 中央値
  - `"add"`: 加算
  - `"sigma_clip"`: シグマクリッピング（実装予定）

**実装**：
```python
def _mean(self, images):
    acc = None
    count = 0
    for img in images:
        arr = self.provider.get_image(img).astype(np.float32)
        if acc is None:
            acc = np.zeros_like(arr, dtype=np.float32)
        acc += arr
        count += 1
    return acc / count
```

---

### 位置合わせ（Alignment）

#### 5. StarCatalog / Star

**ファイル**: [stars/star_data.py](src/astro_stacker/stars/star_data.py)

**役割**: 検出された恒星と その集合を表現

| 項目 | 内容 |
|------|------|
| 入力 | photutils の検出結果 |
| 出力 | Star オブジェクトのリスト |
| 他クラスとの関係 | `detect_stars()` が生成、`align_catalogs()` で比較 |
| 責務 | 星データの標準化 |

**Star の属性**：
- `x, y`: 中心座標（ピクセル）
- `flux`: 総フラックス
- `peak`: ピークピクセル値
- `sharpness, roundness`: メトリクス
- `fwhm, ellipticity`: 後計算値

**StarCatalog のメソッド**：
- `brightest(n)`: N 個の最も明るい星を取得

#### 6. detect_stars() 関数

**ファイル**: [stars/detector.py](src/astro_stacker/stars/detector.py)

**役割**: 画像から恒星を自動検出

| 項目 | 内容 |
|------|------|
| 入力 | 画像（np.ndarray）、FWHM、検出閾値 |
| 出力 | StarCatalog オブジェクト |
| 技術 | photutils.DAOStarFinder |
| 責務 | 恒星検出アルゴリズムの実行 |

**アルゴリズム**：
```
1. Sigma-clipped 統計で背景と ノイズレベルを推定
2. DAOStarFinder (DAO algorithm) で局所最大値を検出
3. 設定 threshold = sigma * std を超えた点を星候補
4. 各候補の形状メトリクス（sharpness, roundness）を計算
```

**パラメータ**：
- `fwhm` (デフォルト 4.0): 予想される星像の Full Width at Half Maximum
- `sigma` (デフォルト 5.0): 検出閾値（背景ノイズの N 倍）

#### 7. align_catalogs() 関数

**ファイル**: [alignment/aligner.py](src/astro_stacker/alignment/aligner.py)

**役割**: 2つの星カタログを比較して位置合わせ変換を計算

| 項目 | 内容 |
|------|------|
| 入力 | reference_catalog, target_catalog |
| 出力 | AlignmentResult（transform + alignment_data） |
| 技術 | astroalign ライブラリ |
| 責務 | 星マッチングと変換計算 |

**処理フロー**：
```python
1. 各 StarCatalog から座標配列を抽出
2. astroalign.find_transform() で星をマッチング
   └─ 複数の相似変換を試行して最適なものを選択
3. 計算された変換を使って、src 座標を予測
4. RMS 誤差を計算
5. AlignmentResult に詰めて返す
```

**出力の AlignmentResult**：
```python
@dataclass
class AlignmentResult:
    transform: TransformData  # 変換行列とパラメータ
    info: AlignmentData       # マッチング統計
```

#### 8. AlignedFrameProvider

**ファイル**: [alignment/transform.py](src/astro_stacker/alignment/transform.py)

**役割**: 位置合わせ変換を自動適用するプロバイダー

| 項目 | 内容 |
|------|------|
| 入力 | base_provider（FrameProvider）、ImageTransformer |
| 出力 | 位置合わせ済み画像 |
| 他クラスとの関係 | FrameProvider デコレータパターン |
| 責務 | 透過的に変換適用 |

**特徴**：
- Decorator パターンで他の provider をラップ
- `get_image()` 時に自動的に `ImageTransformer.apply_transform()` を呼び出し
- 元の provider には影響しない

---

### キャリブレーション（Calibration）

#### 9. Calibrator

**ファイル**: [calibration/calibration.py](src/astro_stacker/calibration/calibration.py)

**役割**: 天体画像に キャリブレーションフレームを適用

| 項目 | 内容 |
|------|------|
| 入力 | 画像（np.ndarray）、マスターフレーム |
| 出力 | キャリブレーション済み画像 |
| 他クラスとの関係 | CalibratedFrameProvider から呼び出し |
| 責務 | キャリブレーション処理の実行 |

**処理の順序**：
```
1. Dark 減算:    image -= dark         (熱ノイズ除去)
2. Bias 減算:    image -= bias         (DC オフセット除去)
3. Flat 除算:    image /= normalized_flat (不均一性補正)
   (Flat-Dark があれば先に減算)
```

**実装**：
```python
def calibrate(self, image: np.ndarray) -> np.ndarray:
    image = image.astype(np.float32)
    
    if self.settings.use_darks and self.master.dark is not None:
        image -= self.master.dark
    
    if self.settings.use_biases and self.master.bias is not None:
        image -= self.master.bias
    
    if self.settings.use_flats and self.master.flat is not None:
        flat = self.master.flat
        if self.settings.use_flat_darks and self.master.flat_dark is not None:
            flat -= self.master.flat_dark
        flat = flat / np.mean(flat)  # 正規化
        image /= flat
    
    return image
```

#### 10. MasterFrameBuilder

**ファイル**: [calibration/calibration.py](src/astro_stacker/calibration/calibration.py)

**役割**: 複数のキャリブレーションフレームからマスターフレームを生成

| 項目 | 内容 |
|------|------|
| 入力 | AstroImage リスト、統計方法 |
| 出力 | マスターフレーム（np.ndarray） |
| 他クラスとの関係 | ProcessingPipeline から呼び出し |
| 責務 | マスターフレーム生成 |

**実装**：
```python
class MasterFrameBuilder:
    def __init__(self, provider: FrameProvider):
        self.provider = provider
        self.combiner = ImageCombiner(provider)
    
    def build(self, images: Iterable[AstroImage], method: Method = "median") -> np.ndarray:
        return self.combiner.combine(images, method)
```

事実上、`ImageCombiner.combine()` をラップしているだけ。

#### 11. CalibratedFrameProvider

**ファイル**: [calibration/provider.py](src/astro_stacker/calibration/provider.py)

**役割**: キャリブレーションを透過的に適用するプロバイダー

| 項目 | 内容 |
|------|------|
| 入力 | base_provider、Calibrator |
| 出力 | キャリブレーション済み画像 |
| 他クラスとの関係 | FrameProvider デコレータパターン |
| 責務 | 透過的にキャリブレーション適用 |

```python
class CalibratedFrameProvider:
    def __init__(self, base_provider: FrameProvider, calibrator: Calibrator):
        self.base_provider = base_provider
        self.calibrator = calibrator

    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        image = self.base_provider.get_image(astro_image)
        return self.calibrator.calibrate(image)
```

---

### 品質評価（Quality）

#### 12. QualityAnalyzer

**ファイル**: [stars/quality.py](src/astro_stacker/stars/quality.py)

**役割**: 画像品質をスコアリング

| 項目 | 内容 |
|------|------|
| 入力 | 画像（np.ndarray） |
| 出力 | ScoreData（品質メトリクス） |
| 他クラスとの関係 | 将来的にフレーム選別で使用予定 |
| 責務 | 品質評価の実行 |

**スコアリング式**：
```
score = star_count / (median_fwhm + 1e-6)
```

**計算内容**：
- 星検出 → star_count
- 上位 50 個の星について FWHM 計測 → median_fwhm
- 背景ノイズレベルを計測 → background_noise

#### 13. measure_fwhm() 関数

**ファイル**: [stars/fwhm.py](src/astro_stacker/stars/fwhm.py)

**役割**: 個々の星の FWHM を測定

| 項目 | 内容 |
|------|------|
| 入力 | 画像、Star オブジェクト |
| 出力 | FWHM（ピクセル）または None |
| 技術 | 2D Gaussian フィッティング |
| 責務 | FWHM 計測 |

**アルゴリズム**：
```
1. 星の中心周辺 (15×15 ピクセル) を切り出し
2. 2D Gaussian 関数をフィッティング
3. 得られた sigma から FWHM = 2.355 * sigma で計算
4. フィッティング失敗時は None を返す
```

---

### パイプライン

#### 14. ProcessingPipeline

**ファイル**: [pipeline/processing_pipeline.py](src/astro_stacker/pipeline/processing_pipeline.py)

**役割**: 全体のオーケストレーション

| 項目 | 内容 |
|------|------|
| 入力 | Project オブジェクト |
| 出力 | 処理済み Project（result フィールドが設定） |
| 他クラスとの関係 | アプリケーション起点 |
| 責備 | 各パイプラインの組み合わせ |

**処理フロー**：
```python
def run(self, project: Project) -> None:
    provider = ImageManagerProvider(self.manager)
    builder = MasterFrameBuilder(provider)
    
    # 1. マスターフレーム生成
    self._build_master_frames(project, builder)
    
    # 2. キャリブレーション適用（オプション）
    calibrator = Calibrator(project, project.settings.calibration)
    if CALIBRATE_BEFORE_ALIGN:
        provider = CalibratedFrameProvider(provider, calibrator)
    
    # 3. 位置合わせ
    alignment_pipeline = AlignmentPipeline(provider)
    alignment_pipeline.run(project, project.settings.alignment)
    
    # 4. キャリブレーション適用（オプション、後処理）
    if not CalibratedFrameProvider:  # この条件は怪しい（後述）
        provider = CalibratedFrameProvider(provider, calibrator)
    
    # 5. スタッキング
    stacking_pipeline = StackingPipeline(provider)
    stacking_pipeline.run(project, project.settings.light_frame)
```

#### 15. AlignmentPipeline

**ファイル**: [pipeline/alignment_pipeline.py](src/astro_stacker/pipeline/alignment_pipeline.py)

**役割**: 位置合わせパイプライン

| 項目 | 内容 |
|------|------|
| 入力 | Project、FrameProvider、AlignmentSettings |
| 出力 | Project.light_frames に transform を追加 |
| 他クラスとの関係 | ProcessingPipeline から呼び出し |
| 責備 | 位置合わせの実行 |

**実装**：
```python
def run(self, project: Project, settings: AlignmentSettings):
    if not project.light_frames:
        raise ValueError("No light frames")
    
    # 参照画像の選択
    if project.reference_image is None:
        project.reference_image = project.light_frames[len(project.light_frames) // 2]
    
    reference = project.reference_image
    reference_image = self.provider.get_image(reference)
    reference_catalog = detect_stars(reference_image)
    
    # 全フレームを位置合わせ
    for astro_image in project.light_frames:
        if astro_image is reference:
            astro_image.info.transform = TransformData()  # 参照画像は恒等変換
            continue
        
        image = self.provider.get_image(astro_image)
        catalog = detect_stars(image)
        result = align_catalogs(reference_catalog, catalog)
        astro_image.info.transform = result.transform
        astro_image.info.alignment_data = result.info
```

#### 16. StackingPipeline

**ファイル**: [pipeline/stacking_pipeline.py](src/astro_stacker/pipeline/stacking_pipeline.py)

**役割**: スタッキングパイプライン

| 項目 | 内容 |
|------|------|
| 入力 | Project、FrameProvider、StackingSettings |
| 出力 | Project.result.stacked_image |
| 他クラスとの関係 | ProcessingPipeline から呼び出し |
| 責備 | スタッキングの実行 |

**実装**：
```python
def run(self, project: Project, settings: StackingSettings) -> None:
    aligned_provider = AlignedFrameProvider(self.provider, ImageTransformer())
    combiner = ImageCombiner(aligned_provider)
    
    result = combiner.combine(
        project.light_frames,
        settings.method
    )
    
    project.result.stacked_image = result
```

---

### FrameProvider プロトコル

#### 17. FrameProvider（プロトコル定義）

**ファイル**: [core/provider.py](src/astro_stacker/core/provider.py)

**役割**: 画像データ取得の抽象インターフェース

| 項目 | 内容 |
|------|------|
| 入力 | AstroImage オブジェクト |
| 出力 | ピクセルデータ（np.ndarray） |
| 他クラスとの関係 | すべてのプロバイダーが実装 |
| 責備 | 抽象インターフェース定義 |

```python
@runtime_checkable
class FrameProvider(Protocol):
    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        ...
```

**実装クラス**：
1. `ImageManagerProvider`: ImageManager でロード
2. `CalibratedFrameProvider`: キャリブレーション適用
3. `AlignedFrameProvider`: 位置合わせ変換適用

---

## 設計思想

### 1. 責務分離（Separation of Concerns）

各モジュールが明確に 1 つの責務を持つ：

| モジュール | 責務 |
|-----------|------|
| `io/` | ファイル形式の多様性を吸収、メモリ管理 |
| `stars/` | 星検出、FWHM 計測、品質評価 |
| `alignment/` | 星マッチング、変換計算 |
| `calibration/` | キャリブレーション処理 |
| `stacking/` | 統計合成 |
| `pipeline/` | 全体のオーケストレーション |
| `project/` | 状態管理 |

**利点**：
- テスト容易性：各モジュールを独立してテスト可能
- 再利用性：各モジュールを他のアプリケーションでも利用可能
- 保守性：変更の影響範囲が限定される

### 2. 依存関係の方向

```
高層（ビジネスロジック）
  ↓
pipeline/
  ↓
alignment/, stacking/, calibration/
  ↓
io/, stars/, core/
  ↓
低層（技術詳細：numpy, photutils, astroalign, etc.）
```

**特徴**：
- 上位層は下位層に依存（従属）
- 下位層は上位層に依存しない
- 結果：変更の波及範囲を制限

### 3. FrameProvider パターン（Decorator Pattern）

複数の処理ステップを柔軟に組み合わせ：

```
AlignedFrameProvider
  ↓
CalibratedFrameProvider
  ↓
ImageManagerProvider
  ↓
ImageManager + ローダー
  ↓
ファイルシステム
```

**特徴**：
- 各プロバイダーは独立した `get_image()` メソッドを持つ
- 新しい処理ステップの追加が容易（新クラス追加だけ）
- 処理順序の変更が簡単（プロバイダーの組み立て順を変更）

**例**：キャリブレーション前後の切り替え
```python
# 前処理としてキャリブレーション
provider = CalibratedFrameProvider(
    ImageManagerProvider(manager),
    calibrator
)

# 後処理としてキャリブレーション
provider = CalibratedFrameProvider(
    AlignedFrameProvider(
        ImageManagerProvider(manager),
        transformer
    ),
    calibrator
)
```

### 4. パイプライン設計（Pipeline Pattern）

```
ProcessingPipeline
  ├─ MasterFrameBuilder
  ├─ AlignmentPipeline
  └─ StackingPipeline
```

**特徴**：
- 各パイプラインが独立して実行可能
- 処理ステップが明確に分離
- 中間結果（Project オブジェクト）を通じて情報受け渡し

**利点**：
- 部分的な再処理が可能（例：位置合わせだけやり直す）
- 各ステップを別スレッドで実行可能（将来）
- プログレス表示が容易

### 5. メモリ管理戦略

#### 遅延読み込み（Lazy Loading）
```python
# 読み込み時点では image フィールドは None
astro_image = loader.load_info(path)
assert astro_image.image is None  # メモリに未読み込み

# 必要な時点で読み込み
provider.get_image(astro_image)  # この時点で初めてロード
```

**利点**：
- 起動時間高速化
- ユーザーは全フレームのメタデータをすぐ操作可能
- 後から選別可能

#### LRU キャッシュ
```python
# ImageManager が max_loaded_image_count を超える画像を自動アンロード
manager = ImageManager(max_loaded_image_count=5)
```

**利点**：
- 予測可能なメモリ使用量
- 大量画像の処理が可能
- ユーザーが意識的にメモリ管理不要

#### 変換情報の保存
```python
# ピクセルデータの代わりに、変換行列を保存
astro_image.info.transform = TransformData(matrix=..., dx=..., dy=..., ...)
# → ピクセルデータは元画像のまま、変換は分離保存
```

**利点**：
- メモリ効率化（ピクセルデータ複製不要）
- 逆変換が容易
- 変換パラメータの検査・編集可能

### 6. テスト容易性

各層がインターフェース（プロトコル）に依存：

```python
# テスト時はモック FrameProvider を注入可能
class MockFrameProvider:
    def get_image(self, image: AstroImage) -> np.ndarray:
        return np.random.rand(100, 100)  # テスト用ダミー画像

pipeline = AlignmentPipeline(MockFrameProvider())
```

**特徴**：
- 外部ファイルシステム・ライブラリに依存しない
- 高速テスト
- 重い処理（star detection）をスキップ可能

---

## 実装済み機能

### ✅ コア機能（実装済み）

1. **画像読み込み**
   - ✅ FITS フォーマット対応
   - ✅ RAW フォーマット対応（rawpy）
   - ✅ PNG / JPEG / TIFF 対応
   - ✅ メタデータ読み込み（EXIF 等）
   - ✅ 遅延読み込み機構

2. **位置合わせ**
   - ✅ 星検出（photutils.DAOStarFinder）
   - ✅ 星マッチング（astroalign）
   - ✅ 相似変換計算（平行移動、回転、スケール）
   - ✅ RMS 誤差計算
   - ✅ マッチング統計情報

3. **キャリブレーション**
   - ✅ Dark フレーム適用
   - ✅ Bias フレーム適用
   - ✅ Flat フレーム適用
   - ✅ Flat-Dark フレーム適用
   - ✅ マスターフレーム生成（統計合成）

4. **スタッキング**
   - ✅ Mean（平均）
   - ✅ Median（中央値）
   - ✅ Add（加算）
   - ✅ AlignedFrameProvider による自動変換適用

5. **画質評価**
   - ✅ 検出星数
   - ✅ FWHM 計測
   - ✅ 背景ノイズレベル
   - ✅ 総合スコア計算

6. **その他**
   - ✅ プロジェクト管理（Project クラス）
   - ✅ メモリ効率化（LRU キャッシュ）
   - ✅ 処理パイプライン設計
   - ✅ 複数ファイル形式統一インターフェース
   - ✅ テスト基盤（tests/ ディレクトリ）

---

## 未実装または今後実装予定の機能

### 🔲 Plate Solve

**目的**：画像の天体座標（RA/Dec）を自動決定

**実装予定**：
- astrometry.net CLI との連携
- WCS（World Coordinate System）情報の抽出
- 画像にメタデータとして埋め込み

**関連ファイル**：`platesolve/` ディレクトリ（未実装）

### 🔲 Drizzle 処理

**目的**：サブピクセル精度での画像拡大縮小（1.5倍、2倍、4倍）

**利点**：
- 単純な拡大（最近傍補間）より高品質
- スタッキング後の解像度向上

**実装予定**：`drizzle/` ディレクトリに実装予定

### 🔲 Sigma Clipping

**目的**：外れ値を除去してからスタッキング

**アルゴリズム**：
```
1. 各ピクセルについて、全フレームの値のセットから
   mean ± N*sigma の範囲外の値を除去
2. 残った値で平均を計算
3. → Median より堅牢、Mean より計算量少ない
```

**実装場所**：`stacking/combiner.py` の `_sigma_clip()` メソッド

### 🔲 Winsorized Sigma Clipping

**目的**：Sigma Clipping の変種で、外れ値を除去ではなく上限値に置換

**利点**：
- 天体などの非対称的な外れ値に強い
- 比較明合成の代替になり得る

### 🔲 ホットピクセル除去

**目的**：CCD/CMOS カメラのホットピクセル（常に明るいピクセル）を除去

**実装方法**：
- Dark フレームを解析してホットピクセルを特定
- 補間などで置換

### 🔲 クロップ範囲選択

**目的**：最終結果をトリミング

**用途**：
- 位置合わせのズレで端が黒くなるのを除去
- ユーザーが関心領域を指定

### 🔲 品質ベースのフレーム選別

**目的**：画質スコアが低いフレームを自動除外

**実装方法**：
```python
# QualityAnalyzer が既に ScoreData を計算
# これを使ってフレームをフィルタ
high_quality_frames = [
    f for f in project.light_frames
    if f.info.score_data.score > threshold
]
```

**関連**: `stars/quality.py` の `QualityAnalyzer` が基礎を実装済み

### 🔲 重み付きスタッキング

**目的**：高品質フレームを重視してスタッキング

```python
weights = [f.info.score_data.score for f in frames]
weights = np.array(weights) / np.sum(weights)

weighted_result = np.sum([
    frame_data * w for frame_data, w in zip(frames, weights)
], axis=0)
```

### 🔲 ログ出力機構

**目的**：処理過程を詳細に記録

**関連ディレクトリ**：`logging/` （モジュール枠組みのみ存在）

**想定される記録項目**：
- 各処理段階のタイミング
- 検出星数、RMS 誤差などの中間結果
- エラーや警告

### 🔲 国際化対応の拡張

**現状**：`i18n/` ディレクトリが存在するが未実装

**今後の実装**：
- UI テキストの多言語対応
- 現在は README で日本語対応を謳っているが、コード層の実装は不十分

### 🔲 UI（ユーザーインターフェース）

**現状**：`ui/` ディレクトリが存在するが未実装

**想定される機能**：
- PyQt6 ベースの GUI
- 画像プレビュー
- パラメータ調整 UI
- プログレス表示
- ログビューア

---

## 開発者向け要約

### 起動方法

```bash
# 環境設定（仮想環境作成）
python3 -m venv .venv
source .venv/bin/activate

# 依存パッケージインストール
pip install -e .

# テスト実行
python tests/test.py
```

### コード構成の 5 分理解

1. **入出力層**（`io/`）
   - 複数ファイル形式を統一インターフェースで扱う
   - `ImageManager` で遅延読み込み＆LRU キャッシュ

2. **星検出層**（`stars/`）
   - `detect_stars()` で恒星を自動検出（photutils）
   - FWHM や楕円度などのメトリクスを計算

3. **位置合わせ層**（`alignment/`）
   - `align_catalogs()` で 2 つの星カタログをマッチング（astroalign）
   - 相似変換パラメータを計算・保存

4. **キャリブレーション層**（`calibration/`）
   - Dark/Bias/Flat フレームをマスターフレームに合成
   - 透過的に適用（CalibratedFrameProvider）

5. **スタッキング層**（`stacking/`）
   - `ImageCombiner` で複数画像を統計合成
   - Mean / Median / Add など複数手法をサポート

6. **パイプライン層**（`pipeline/`）
   - 上記 5 層を組み合わせて全体を制御
   - `ProcessingPipeline` がエントリーポイント

### 重要な設計パターン

#### Pattern 1: FrameProvider（Strategy + Decorator）
```python
provider = ImageManagerProvider(manager)
provider = CalibratedFrameProvider(provider, calibrator)  # デコレータ
provider = AlignedFrameProvider(provider, transformer)    # デコレータ

# 全層を透過的に適用
image = provider.get_image(astro_image)  # キャリブレーション＆変換済み
```

#### Pattern 2: Project としての状態管理
```python
project = Project()
project.light_frames = [image1, image2, ...]  # 入力
pipeline.run(project)  # 処理
result = project.result.stacked_image  # 出力
```

#### Pattern 3: メタデータ保持
```python
# ピクセルデータとメタデータを分離
astro_image.image     # ピクセル（遅延読み込み）
astro_image.info      # メタデータ（常にメモリ内）
astro_image.info.transform   # 変換情報（別途保持）
```

### テストの実行

```bash
# 基本的なテスト
cd /path/to/astroStacker
python tests/test.py

# テスト画像の準備
# test_images/ ディレクトリに以下を配置：
# - lights/: スタック対象画像
# - darks/, flats/, biases/, flat_darks/: キャリブレーション画像

# テスト実行後、result:
# processing_result.tif が test_images/ に生成
```

### コード探索のポイント

**全処理フロー**：
- `tests/test.py` → main() → ProcessingPipeline.run()

**各ステップの実装**：
- キャリブレーション: [calibration/calibration.py](src/astro_stacker/calibration/calibration.py)
- 位置合わせ: [alignment/aligner.py](src/astro_stacker/alignment/aligner.py)
- スタッキング: [stacking/combiner.py](src/astro_stacker/stacking/combiner.py)

**重要なデータクラス**：
- [io/image_data.py](src/astro_stacker/io/image_data.py): AstroImage、TransformData など

**FrameProvider の実装**：
- [core/provider.py](src/astro_stacker/core/provider.py): プロトコル定義
- [calibration/provider.py](src/astro_stacker/calibration/provider.py): CalibratedFrameProvider
- [alignment/transform.py](src/astro_stacker/alignment/transform.py): AlignedFrameProvider

### 主要な外部ライブラリ

| ライブラリ | 用途 |
|-----------|------|
| `numpy` | 数値計算 |
| `scipy` | 科学計算（補間など） |
| `photutils` | 星検出（DAOStarFinder） |
| `astroalign` | 星マッチング |
| `astropy` | FITS 読み込み、WCS 処理 |
| `opencv-python` | 画像処理（将来） |
| `scikit-image` | 画像処理 |
| `rawpy` | RAW ファイル読み込み |
| `pillow` | PNG/JPEG/TIFF 読み込み |
| `pyqt6` | GUI（未実装） |

---

## 既知の設計上の検討事項

### 🔍 Issue 1: ProcessingPipeline.run() の怪しい条件

**ファイル**: [pipeline/processing_pipeline.py](src/astro_stacker/pipeline/processing_pipeline.py#L36-L40)

```python
if not CalibratedFrameProvider:  # ← 常に False
    provider = CalibratedFrameProvider(provider, calibrator)
```

**問題**：
- `CalibratedFrameProvider` はクラスなので、`if not` は常に False
- 意図は「キャリブレーションを後処理で適用」だったと思われるが、実装されていない

**推奨修正**：
```python
CALIBRATE_BEFORE_ALIGN = True
CALIBRATE_AFTER_ALIGN = False

if not CALIBRATE_BEFORE_ALIGN and CALIBRATE_AFTER_ALIGN:
    provider = CalibratedFrameProvider(provider, calibrator)
```

### 🔍 Issue 2: FWHM 計測の None 値処理

**ファイル**: [stars/quality.py](src/astro_stacker/stars/quality.py#L35)

```python
fwhms = fwhm[fwhms != None]  # ← 要素ごとの比較（要注意）
```

**問題**：
- `None` は numpy 配列内の None 値と比較できず、警告が出る可能性
- `np.array.dtype` が object の場合のみ機能

**推奨修正**：
```python
fwhms = np.array([f for f in fwhms if f is not None])
# または
fwhms = fwhms[~np.isnan(fwhms)] if fwhms.dtype != object else fwhms
```

### 🔍 Issue 3: スタッキング方法の不完全実装

**ファイル**: [stacking/combiner.py](src/astro_stacker/stacking/combiner.py#L48)

```python
# TODO: 軽量化する
def _median(...):
```

**現状**：
- Median 実装に TODO コメント
- 計算量削減（タイル処理など）が検討中

**将来実装予定**：
- タイル単位での処理で メモリ消費を削減
- または CuPy での GPU 加速

### 🔍 Issue 4: 並列処理の未検討

**現状**：
- 各フレームの位置合わせは逐次処理
- スタッキングも逐次処理（`for` ループ）

**改善案**：
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

# 位置合わせの並列化
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [
        executor.submit(align_frame, frame)
        for frame in project.light_frames
    ]
    for future in as_completed(futures):
        # 結果を project に記録
```

**制約**：
- numpy の GIL（Global Interpreter Lock）の制約
- multiprocessing の方が適切だが、fork() の安全性が問題
- asyncio ベースの設計に移行する方が良い（将来）

### 🔍 Issue 5: エラーハンドリングの不十分さ

**例**：
```python
# AlignmentPipeline.run() で
if not project.light_frames:
    raise ValueError("No light frames")
```

**問題**：
- エラーメッセージが簡潔すぎて、ユーザーには何が悪いのか不明確
- カスタム例外クラスがない

**推奨改善**：
```python
class AstroStackerError(Exception):
    """Astro Stacker 共通例外"""
    pass

class NoLightFramesError(AstroStackerError):
    """Light frames が存在しない"""
    def __init__(self):
        super().__init__(
            "Light frames が見つかりません。"
            "test_images/lights/ にスタック対象画像を配置してください。"
        )
```

### 🔍 Issue 6: 設定クラスの設計

**ファイル**: [project/settings.py](src/astro_stacker/project/settings.py)

```python
@dataclass
class StackingSettings:
    method: Method = "mean"

@dataclass
class AlignmentSettings:
    max_stars: int = 500  # ← 使用されていない

@dataclass
class CalibrationSettings:
    use_darks: bool = False
    use_flats: bool = False
    # ...
```

**問題**：
- `AlignmentSettings.max_stars` が実装されていない
- 星検出の `sigma` パラメータが設定可能でない（ハードコード）

**推奨改善**：
```python
@dataclass
class AlignmentSettings:
    max_stars: int = 500           # ← 実装する
    star_detection_sigma: float = 5.0
    star_fwhm: float = 4.0
    # ...
```

### 🔍 Issue 7: ログ機構の欠落

**現状**：
- ロギング機能が実装されていない
- `logging/` ディレクトリは空

**改善案**：
```python
import logging

logger = logging.getLogger("astro_stacker")

# ProcessingPipeline.run() に追加
logger.info(f"Detected {len(reference_catalog.stars)} stars in reference image")
logger.info(f"Matched {result.info.matched_star_count} stars with target image")
logger.info(f"RMS error: {result.info.rms_error:.3f} pixels")
```

### 🔍 Issue 8: メタデータ継承の不完全さ

**現状**：
- AstroImage.info の EXIF/メタデータが読み込まれるが、最終出力に反映されない

**改善案**：
```python
# result を FITS で保存する際、元画像の EXIF を埋め込み
def save_result_fits(result, astro_image, output_path):
    hdul = fits.HDUList([fits.PrimaryHDU(result)])
    
    # メタデータコピー
    if astro_image.info.exif:
        for key, value in astro_image.info.exif.items():
            hdul[0].header[key] = value
    
    hdul.writeto(output_path, overwrite=True)
```

### 🔍 Issue 9: 参照画像選択の硬直性

**現状**：
```python
if project.reference_image is None:
    project.reference_image = project.light_frames[len(project.light_frames) // 2]
```

**問題**：
- 常に中央の画像を選択
- ユーザーが品質ベースで選択できない

**改善案**：
```python
# 品質スコアに基づいて参照画像を選択
if project.reference_image is None:
    best_image = max(
        project.light_frames,
        key=lambda img: img.info.score_data.score or -float('inf')
    )
    project.reference_image = best_image
    logger.info(f"Selected reference image: {best_image.info.path.name}")
```

### 🔍 Issue 10: テストの限定的さ

**現状**：
- [tests/test.py](tests/test.py) は統合テストのみ
- ユニットテスト不足

**改善案**：
```
tests/
├── test.py                    # 統合テスト
├── unit/
│   ├── test_star_detector.py  # 星検出の単体テスト
│   ├── test_aligner.py        # 位置合わせの単体テスト
│   ├── test_combiner.py       # スタッキングの単体テスト
│   └── ...
└── fixtures/                  # テスト用ダミーデータ
```

---

## 修正履歴

このドキュメント作成時に、コードレビューを実施して以下のバグを検出・修正しました。

### ✅ 修正済みバグ

#### 1. **ProcessingPipeline.py - 条件チェックのロジックエラー**

**ファイル**: [pipeline/processing_pipeline.py](src/astro_stacker/pipeline/processing_pipeline.py#L59)

**修正前**:
```python
if not CalibratedFrameProvider:  # ← クラス判定のため常に False
    provider = CalibratedFrameProvider(provider, calibrator)
```

**修正後**:
```python
if not CALIBRATE_BEFORE_ALIGN:  # ← 設定フラグで判定
    provider = CalibratedFrameProvider(provider, calibrator)
```

**問題**：`CalibratedFrameProvider` はクラスなので、`if not` は常に False になり、条件が実行されない

**影響度**：⚠️ **中** - キャリブレーションの後処理オプション機能が無効

---

#### 2. **Quality.py - NumPy 配列内の None 値フィルタリング**

**ファイル**: [stars/quality.py](src/astro_stacker/stars/quality.py#L37)

**修正前**:
```python
fwhms = np.array([measure_fwhm(image, c) for c in top_catalog])
fwhms = fwhms[fwhms != None]  # ← NumPy 比較で警告が出る可能性
```

**修正後**:
```python
fwhms = np.array([measure_fwhm(image, c) for c in top_catalog], dtype=object)
# Filter out None values
fwhms = np.array([f for f in fwhms if f is not None], dtype=np.float32)
```

**問題**：NumPy 配列の `!=` 演算子では None を正しく比較できず、RuntimeWarning が発生する可能性

**影響度**：⚠️ **低** - 警告は出るが機能は動作

---

#### 3. **Calibration.py - マスターフレームの破壊的変更**

**ファイル**: [calibration/calibration.py](src/astro_stacker/calibration/calibration.py#L62)

**修正前**:
```python
flat = self.master.flat  # ← 参照を保持
if self.settings.use_flat_darks and self.master.flat_dark is not None:
    flat -= flat_dark  # ← マスターフレームをインプレース変更
```

**修正後**:
```python
flat = self.master.flat.copy()  # ← コピーを作成
if self.settings.use_flat_darks and self.master.flat_dark is not None:
    flat -= flat_dark  # ← コピーを変更
```

**問題**：マスターフレーム（キャッシュされた共有データ）をインプレース演算で破壊。複数の画像処理で累積エラーが発生

**影響度**：🔴 **高** - キャリブレーション結果が繰り返し処理で劣化

---

### 📋 既知の設計上の問題（修正未実施）

以下の設計上の課題は、仕様レベルの検討が必要なため、このリリースでは修正していません：

1. **AlignmentSettings.max_stars の未実装**
   - 定義されているが使用されない設定
   - 実装予定

2. **並列処理の欠落**
   - 位置合わせとスタッキングが逐次処理
   - パフォーマンス最適化は将来の課題

3. **エラーメッセージの不足**
   - 汎用 ValueError が使われている
   - カスタム例外クラスの導入検討中

4. **ログ機構の欠落**
   - `logging/` ディレクトリが空
   - UI 実装と同時に検討予定

詳細は [既知の設計上の検討事項](#既知の設計上の検討事項) セクションを参照してください。

---

## 結論

**Astro Stacker** は、天体写真処理における複雑な要件を、モジュール分離、デザインパターン、遅延読み込み、プロバイダーパターンなどを駆使して実装した、良く設計されたシステムです。

**強み**：
- 拡張性に富んだアーキテクチャ
- メモリ効率的な設計
- 責務の明確な分離
- テスト容易性

**改善点**：
- 並列処理への対応
- ロギング機構の実装
- エラーハンドリングの強化
- UI の実装
- 未実装機能の補完

今後の開発では、これらの改善点を段階的に対応することで、プロダクション品質のアプリケーションへ進化していくでしょう。
