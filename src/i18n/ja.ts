import type { MessageDict } from './keys';

/** 日本語辞書（v1 は日本語のみ。N-9） */
export const ja: MessageDict = {
  appName: 'BrowserMoji',
  appDescription:
    '背面カメラの映像を、日本語の全角文字でできたアスキーアートとしてリアルタイムに表示します。列数・濃さ・エッジの強さは画面から調整できます。',
  privacyNotice: '映像はこの端末の外へ送信されません（すべての処理は端末内で完結します）',
  startButton: '開始',
  startingCamera: 'カメラを起動しています…',
  errorTitle: 'カメラを開始できませんでした',
  errorPermissionDenied:
    'カメラの権限が拒否されました。ブラウザの設定でこのページのカメラ利用を許可してから、ページを再読み込みしてください。',
  errorCameraNotFound:
    'カメラが見つかりませんでした。カメラが接続されているかを確認し、ページを再読み込みしてください。',
  errorCameraBusy:
    'カメラをほかのアプリが使用しています。ほかのアプリを閉じてから、ページを再読み込みしてください。',
  errorUnsupported:
    'このブラウザ・環境ではカメラを利用できません。HTTPS で開いた最新のブラウザ（iOS Safari・Android Chrome など）をお使いください。',
  errorUnknown: '不明なエラーが発生しました。ページを再読み込みしてください。',
  // 描画ループ（tick）内で回復できない例外が起きたときの表示（F-9）
  errorRenderLoopTitle: '描画中にエラーが発生しました',
  errorRenderLoopBody:
    '表示が停止しました。ページを再読み込みしてください。設定の「描画方式」を「Canvas 2D」に変更してから再読み込みすると解消することがあります。',
  settingsToggle: '設定',
  settingRenderer: '描画方式',
  settingRendererCanvas2d: 'Canvas 2D',
  settingRendererWebgl2: 'WebGL2',
  settingRendererUnsupported: 'この環境では WebGL2 を利用できません',
  settingMode: '文字選択方式',
  settingModeClassic: 'クラシック（EXP-2/3 適用前）',
  settingModeSelectorA: 'Selector A（基準実装準拠）',
  settingColumns: '列数',
  settingContrast: 'コントラスト',
  settingEdgeThreshold: 'エッジのしきい値',
  settingEdgePriority: 'エッジの強さ',
  settingInvert: '白黒反転',
  settingInvertLuminance: '輝度反転',
  settingMirror: '左右反転',
  cameraSwitch: 'カメラ切替',
  settingEdgeOnly: 'エッジのみ描画',
  settingCmatrixBg: 'cmatrix風背景',
  settingFillerChars: 'フィラー文字',
  settingFillerCharsReset: '既定に戻す',
  settingShowFps: 'fps 表示',
  // 最初のフレームが完了するまでの間の fps オーバーレイの表示
  fpsMeasuring: '計測中…',
  fpsLabel: 'fps',
  msLabel: 'ms',
  // オーバーレイの行ラベル（EXP-1 の計測用。英語略称のまま、文言は辞書で持つ）
  fpsAvg: 'avg',
  fpsMin: 'min',
  fpsCam: 'cam',
  fpsPre: 'pre',
  fpsRead: 'read',
  fpsFeat: 'feat',
  fpsSel: 'sel',
  fpsDraw: 'draw',
  fpsCols: 'cols',
  fpsNotAvailable: '—',
  captureCopy: 'コピー',
  captureCopied: 'コピー済み',
  captureCopyFailed: 'コピー失敗',
  captureScreenshot: '撮影',
  captureRecordStart: '録画',
  captureRecordStop: '停止',
  captureRecordUnsupported: '非対応',
  languageSelect: '言語を選択',
};
