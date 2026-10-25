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
  settingsToggle: '設定',
  settingColumns: '列数',
  settingContrast: 'コントラスト',
  settingEdgeThreshold: 'エッジのしきい値',
  settingEdgePriority: 'エッジの強さ',
  settingInvert: '白黒反転',
  settingShowFps: 'fps 表示',
  fpsLabel: 'fps',
};
