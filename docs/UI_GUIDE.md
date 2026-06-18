# Astro Stacker UI実装ガイド

## 画面構成

- `MainWindow`: ツールバー、メニュー、左右上下スプリッター、進捗バーを持つメイン画面。
- `ProjectTree`: ライト、ダーク、フラット、バイアス、フラットダークの件数を表示するプロジェクトツリー。
- `FrameTable`: `Lights / Darks / Flats / Bias / Flat Darks` のタブ付きフレーム一覧。チェック状態は `AstroImage.info.enabled` と同期する。
- `ImageViewer`: 選択画像またはスタック結果を自動ストレッチして表示する。
- `LogPanel`: Python `logging` のレコードをQtシグナル経由で表示する。INFOは白、WARNINGは黄、ERRORは赤。
- `InfoPanel`: 画像情報表示用の予約パネル。

## 操作フロー

1. ツールバーの「フレーム追加」またはメニューから画像を追加する。フレーム一覧へのドラッグ&ドロップにも対応。
2. フレーム一覧で使用する画像にチェックを入れる。マスターフレームはファイル名の先頭に `★` が付く。
3. 「位置合わせ」を押すと `AlignmentSettingsDialog` が開く。設定確定後、別スレッドで位置合わせを実行する。
4. 「スタック」を押すと `StackingSettingsDialog` が開く。設定確定後、キャリブレーション、位置合わせ、スタックを実行する。
5. スタック完了後、ライトフレームのフォルダへ `stacked.fits` を自動保存する。
6. 「保存」ボタンから、FITS/TIFF/PNG/JPEGを任意の場所へ別名保存する。

## ダイアログ

- `AlignmentSettingsDialog`
  - キャリブレーション適用タイミング: 位置合わせ前 / 後
  - 使用する補正フレーム: Dark / Bias / Flat / FlatDark
  - 参照画像: 中央 / 最高品質 / 手動選択
  - 星検出感度 `sigma`: 3.0から10.0
  - 最大星数 `max_stars`
- `StackingSettingsDialog`
  - スタック方法: Mean / Median / Sigma Clipping / Add
  - Sigma値と繰り返し回数
- `SaveDialog`
  - 保存形式、ビット深度、JPEG品質、保存先を指定する。
- `ErrorDialog`
  - 例外メッセージを表示し、詳細欄にスタックトレースを表示する。

## シグナル/スロット

- `ProjectController.category_count_changed(FrameType, int)` -> `ProjectTree.set_count`
- `ProjectController.all_frames_changed(dict)` -> `FrameTable.set_frames`
- `ProjectTree.frame_type_selected(FrameType)` -> `FrameTable` の表示タブ切り替え
- `FrameTable.files_dropped(FrameType, list[Path])` -> `ProjectController.add_files`
- `FrameTable.frame_selected(AstroImage)` -> `MainWindow._preview_frame`
- `FrameTable.enabled_changed(AstroImage, bool)` -> ボタン状態更新
- `QtLogHandler.emitter.message(int, str)` -> `LogPanel.append_log`

## QSettings

- `window/geometry`: メインウィンドウ位置とサイズ
- `window/state`: ツールバーなどの状態
- `ui/language`: `ja` または `en`
- `alignment/calibrate_before`
- `alignment/reference`
- `alignment/sigma`
- `alignment/max_stars`
- `calibration/use_darks`
- `calibration/use_biases`
- `calibration/use_flats`
- `calibration/use_flat_darks`
- `stacking/method`
- `stacking/sigma`
- `stacking/iterations`

## 将来実装予定

- Plate Solveパネルとastrometry.net連携
- Drizzle倍率、クロップ、ホットピクセル除去の設定UI
- InfoPanelの詳細メタデータ表示
- 言語切り替えの即時反映
- 位置合わせのみ実行時のキャリブレーション完全反映
