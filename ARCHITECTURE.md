# Astro Stacker アーキテクチャドキュメント

天体写真スタックアプリケーションの構成、データ構造、モジュール設計について解説します。
copilot作成です。全てに目を通していないので間違ってたらすいません。

---

## 目次

1. [プロジェクト概要](#プロジェクト概要)
2. [フォルダ構成](#フォルダ構成)
3. [コア データ構造](#コアデータ構造)
4. [モジュール説明](#モジュール説明)
5. [処理フロー](#処理フロー)
6. [メモリ管理](#メモリ管理)
7. [拡張性](#拡張性)

---

## プロジェクト概要

**Astro Stacker** は、天体写真の位置合わせ、キャリブレーション、スタック処理を行うデスクトップアプリケーションです。

### 主な特徴

- **複数ファイル形式対応**: RAW、FITS、JPEG、PNG、TIFF
- **メモリ効率**: 大量の画像を扱うため、遅延読み込みと自動メモリ管理
- **多機能な位置合わせ**: 星検出による自動位置合わせ、複数統計方法
- **キャリブレーション**: Dark、Bias、Flat、Flat-Dark フレームの適用
- **画質評価**: 星の数、FWHM、背景ノイズなどに基づくスコアリング
- **国際化**: 日本語・英語対応

---

## フォルダ構成

```
src/astro_stacker/
├── __init__.py
├── app.py                   # エントリーポイント
├── core/                    #
│   └── provider.py          # フレームプロバイダーインターフェース
├── alignment/               # 画像位置合わせ
│   ├── aligner.py           # 位置合わせ実行エンジン
│   ├── matcher.py           # 星マッチング
│   ├── apply.py             # 変換適用
│   └── alignment_data.py    # 結果データ構造
├── calibration/             # キャリブレーション処理
│   └── calibration.py       # Master フレーム適用
├── core/                    # コア機能（予約）
├── drizzle/                 # ドリズル処理
├── i18n/                    # 国際化/多言語
├── io/                      # 入出力
│   ├── loader.py            # 統一ローダーインターフェース
│   ├── fits_loader.py       # FITS ファイル読み込み
│   ├── raw_loader.py        # RAW ファイル読み込み
│   ├── standard_loader.py   # PNG/JPEG/TIFF 読み込み
│   ├── saver.py             # ファイル保存
│   ├── image_data.py        # データクラス定義
│   ├── image_manager.py     # メモリ管理
│   └── image_manager.py     # メモリ管理
├── logging/                 # ロギング機能
├── metadata/                # メタデータ処理
├── platesolve/              # Plate Solve（天体位置決定）
├── quality/                 # 画質評価
├── stacking/                # スタック処理
│   ├── combiner.py       # 複数統計方法の実装
├── stars/                   # 星検出・分析
│   ├── detector.py          # 星検出（photutils）
│   ├── star_data.py         # 星データクラス
│   ├── fwhm.py              # FWHM 測定
│   └── quality.py           # 画質スコアリング
└── ui/                      # ユーザーインターフェース
```

---

## コア データ構造

### 1. AstroImage（画像コンテナ）

```python
@dataclass
class AstroImage:
    info: AstroImageInfo      # メタデータ
    image: np.ndarray | None  # ピクセルデータ（遅延読み込み）
```

**特徴**:
- ピクセルデータはデマンド読み込み
- `is_loaded` プロパティで読み込み状態確認
- `load()` / `unload()` メソッドで明示的制御

### 2. AstroImageInfo（メタデータ）

```python
@dataclass
class AstroImageInfo:
    path: Path                        # ファイルパス
    shape: ImageShape                 # 寸法
    bit_depth: int                    # ビット深度
    exposure_time: float | None       # 露出時間（秒）
    iso: int | None                   # ISO 感度
    f_number: float | None            # F 値
    exif: dict | None                 # EXIF メタデータ
    wcs: WCSData = ...                # 天体座標
    score_data: ScoreData = ...       # 画質スコア
    transform: TransformData = ...    # 位置合わせ変換
    alignment_data: AlignmentData = ... # マッチング統計
    enabled: bool = True              # 使用フラグ
```

### 3. ImageShape（寸法）

```python
@dataclass
class ImageShape:
    width: int      # ピクセル幅
    height: int     # ピクセル高さ
    channels: int   # チャネル数（1=グレー, 3=RGB）
```

### 4. TransformData（位置合わせ変換）

```python
@dataclass
class TransformData:
    dx: float = 0.0           # X シフト（ピクセル）
    dy: float = 0.0           # Y シフト（ピクセル）
    rotation: float = 0.0     # 回転角度（度）
    scale: float = 1.0        # スケール係数
    matrix: np.ndarray | None # 3x3 変換行列（オプション）
```

### 5. ScoreData（画質メトリクス）

```python
@dataclass
class ScoreData:
    score: float | None           # 総合スコア（star_count / fwhm）
    star_count: int | None        # 検出星数
    fwhm: float | None            # 平均 FWHM（ピクセル）
    ellipticity: float | None     # 楕円度
    background_noise: float | None # 背景ノイズ
    cloud_score: float | None     # 雲検出スコア
```

### 6. WCSData（天体座標）

```python
@dataclass
class WCSData:
    ra: float | None              # 赤経（度）
    dec: float | None             # 赤緯（度）
    pixel_scale: float | None     # スケール（弧秒/px）
    rotation: float | None        # 回転角度（度）
```

### 7. Star & StarCatalog（星検出）

```python
@dataclass
class Star:
    x: float                    # X 中心座標
    y: float                    # Y 中心座標
    flux: float                 # 総フラックス
    peak: float                 # ピークピクセル値
    sharpness: float | None     # 鋭度（0-1）
    roundness: float | None     # 円形度（0=円形）
    fwhm: float | None          # FWHM（ピクセル）
    ellipticity: float | None   # 楕円度

@dataclass
class StarCatalog:
    stars: list[Star]
    
    def brightest(self, n: int) -> list[Star]:
        """最も明るい N 個の星を取得"""
```

---

## モジュール説明

### io（入出力）

#### loader.py - 統一読み込みインターフェース
- 複数ファイル形式の自動検出
- `load_info(path)`: メタデータのみ読み込み（高速）
- `load_image(astro_image)`: ピクセルデータ読み込み

**サポート形式**:
- RAW: `.cr2`, `.nef`, `.arw`, `.dng` など（rawpy）
- FITS: `.fits`, `.fit`, `.fts`（astropy）
- 標準: `.png`, `.jpg`, `.tiff`（PIL）

#### image_manager.py - メモリ管理
- **LRU キャッシュ**: 最近使用順で画像を追跡
- **自動削除**: メモリ上限超過時に最も古い画像をアンロード
- `get_image()`: 必要に応じてロード＆キャッシュ
- `unload()`: 明示的なアンロード

```python
manager = ImageManager(max_loaded_image_count=5)
data = manager.get_image(astro_img)  # 自動ロード
manager.unload(astro_img)            # 明示的アンロード
```

### alignment（位置合わせ）

#### detector.py - 星検出
- **photutils.DAOStarFinder** を使用
- パラメータ: FWHM（星サイズ）、閾値（Sigma）
- 出力: `StarCatalog`

```python
catalog = detect_stars(image, fwhm=4.0, sigma=5.0)
```

#### matcher.py - 星マッチング
- **astroalign** ライブラリで座標マッチング
- 参照画像と対象画像の星を対応付け
- 出力: 変換行列と一致統計

#### aligner.py - 位置合わせ実行
- 2 つの星カタログから変換を計算
- `align_catalogs()`: `AlignmentResult` を返す
- RMS エラーと一致数を記録

#### apply.py - 変換適用
- `apply_transform()`: 画像に変換を適用
- scikit-image の `warp()` を使用

### combination（スタック）

#### combiner.py - 複数統計方法
- **mean**: シンプル平均（外れ値に弱い）
- **median**: 中央値（外れ値ロバスト）
- **sigma_clip**: Sigma クリッピング（宇宙線除去）
- **add**: 加算（露出合成用）

メモリ効率: チャンク単位で処理

```python
combiner = ImageCombiner(provider)
result = combiner.combine(images, method="median")
```

### calibration（キャリブレーション）

#### calibration.py - フレーム適用
処理順序:
1. Dark フレーム: 熱ノイズ除去
2. Bias フレーム: DC オフセット除去
3. Flat フレーム: ビネット・ダスト補正

```python
calibrator = Calibrator(master_frames, pipeline)
calibrated = calibrator.calibrate(light_frame)
```

### stars（星分析）

#### detector.py
- DAO Star Finder で星を検出
- FWHM、シャープネス、丸さを計算

#### fwhm.py
- 星周辺の 2D ガウシアンフィッティング
- FWHM = 2.355 × σ

#### quality.py
- `QualityAnalyzer.analyze()`: スコア計算
- **スコア = star_count / (median_fwhm + 1e-6)**
- より多くの星でシャープ = 高スコア

---

## 処理フロー

### 典型的な処理フロー

```
1. ファイル読み込み
   ├─ loader.load_info() → AstroImage（メタデータのみ）
   └─ ImageManager.get_image() → ピクセルデータ読み込み

2. キャリブレーション
   ├─ Master フレーム生成（Dark, Flat など）
   └─ Calibrator.calibrate() → キャリブレーション済み画像

3. 星検出 & 位置合わせ
   ├─ detect_stars() → 参照画像カタログ
   ├─ detect_stars() → 対象画像カタログ
   ├─ find_transform() → 星マッチング
   └─ apply_transform() → 位置合わせ

4. 品質評価
   ├─ QualityAnalyzer.analyze() → ScoreData
   └─ スコアに基づく選別

5. スタック
   ├─ ImageCombiner.combine() → 合成画像
   └─ save_tiff() → ファイル出力
```

---

## メモリ管理

### 設計原則

1. **遅延読み込み**: ピクセルデータはデマンド時のみロード
2. **LRU キャッシュ**: 最近使用画像を優先的に保持
3. **自動削除**: キャッシュ超過時に古いデータをアンロード
4. **明示的制御**: `load()` / `unload()` で細粒度制御も可能

### 実装例

```python
# ImageManager 設定
manager = ImageManager(max_loaded_image_count=5)

# 自動ロード＆キャッシュ
data1 = manager.get_image(img1)
data2 = manager.get_image(img2)
# ... img1 が自動的に LRU キューの最後へ

# 明示的アンロード
manager.unload(img1)

# 全削除
manager.unload_all()
```

### メモリ計算

```
メモリ ≈ num_loaded × (width × height × channels × 4 bytes)

例: 3000×2000×3 channels × 5 images × 4 bytes = 360 MB
```

---

## 拡張性

### 新しいローダーの追加

1. 新しい`*_loader.py` ファイル作成:
```python
def load_custom_info(path: Path) -> AstroImage:
    """メタデータのみ読み込み"""
    ...

def load_custom_image(path: Path) -> np.ndarray:
    """ピクセルデータ読み込み"""
    ...
```

2. `loader.py` で登録:
```python
LOADERS = {
    'custom': ({'.custom'}, load_custom_info, load_custom_image),
    ...
}
```

### 新しいスタック方法の追加

```python
class ImageCombiner:
    def combine(self, images, method="mean"):
        if method == "custom":
            return self._custom(images)
        ...
    
    def _custom(self, images: Iterable[AstroImage]) -> np.ndarray:
        """カスタム統計方法"""
        ...
```

### Protocol による拡張

```python
# FrameProvider を実装すれば、
# 任意のソースから画像を取得可能

class CustomProvider:
    def get_image(self, astro_image: AstroImage) -> np.ndarray:
        # カスタム読み込みロジック
        ...
```

---

## 命名規則

### ファイル・フォルダ

- フォルダ: スネークケース（`alignment`, `combination`）
- モジュール: スネークケース（`image_manager.py`）
- クラス: パスカルケース（`ImageManager`, `AstroImage`）
- 関数: スネークケース（`load_image()`, `detect_stars()`）
- 定数: 大文字スネークケース（`RAW_EXTENSIONS`）

### 変数

- プロパティ: スネークケース（`exposure_time`, `star_count`）
- プライベート: ダブルアンダースコア（`__loaded_images`）

---

## 依存関係

### 主要ライブラリ

| 名前 | 用途 | バージョン |
|------|------|-----------|
| numpy | 数値計算 | ≥2.0 |
| scipy | 科学計算 | ≥1.14 |
| astropy | 天文学 (FITS, WCS) | ≥7.0 |
| photutils | 星検出 | ≥2.0 |
| rawpy | RAW 読み込み | ≥0.24 |
| opencv-python | 画像処理 | ≥4.11 |
| astroalign | 座標マッチング | ≥2.6.2 |
| scikit-image | 画像変換 | ≥0.25 |
| Pillow | 標準画像形式 | ≥11.0 |

---

## トラブルシューティング

### メモリ不足エラー

**症状**: `MemoryError` または動作が遅い

**対策**:
1. `ImageManager` の `max_loaded_image_count` を減らす
2. チャンク単位処理を有効にする
3. 不要な画像を明示的に `unload()` する

### 位置合わせ失敗

**症状**: `AlignmentResult` で `matched_star_count` が 0

**対策**:
1. `detect_stars()` の `sigma` パラメータを調整
2. 参照・対象画像の星が十分か確認
3. 回転が大きすぎないか確認

### ファイル読み込み失敗

**症状**: `FileNotFoundError` または形式認識失敗

**対策**:
1. ファイル拡張子が正しいか確認
2. サポート形式か確認 (`loader.LOADERS`)
3. ファイルが破損していないか確認

---

## 参考資料

- [README.md](README.md) - 機能概要
- [docs/algorithms.md](docs/algorithms.md) - アルゴリズム詳細
- [docs/specification.md](docs/specification.md) - 仕様書
- [docs/file_formats.md](docs/file_formats.md) - 対応ファイル形式

---

**最終更新**: 2026-06-07
