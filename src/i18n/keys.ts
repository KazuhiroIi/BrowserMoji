/**
 * UI 文言のキー一覧（N-9）。
 * 文言をコンポーネントに直書きしない。言語を追加するときは
 * 同じキーの辞書を 1 つ足すだけで済むようにする。
 */
export const messageKeys = [
  'appName',
  'appDescription',
  'privacyNotice',
  'startButton',
  'startingCamera',
  'errorTitle',
  'errorPermissionDenied',
  'errorCameraNotFound',
  'errorCameraBusy',
  'errorUnsupported',
  'errorUnknown',
  'errorRenderLoopTitle',
  'errorRenderLoopBody',
  'settingsToggle',
  'settingRenderer',
  'settingRendererCanvas2d',
  'settingRendererWebgl2',
  'settingRendererUnsupported',
  'settingColumns',
  'settingContrast',
  'settingEdgeThreshold',
  'settingEdgePriority',
  'settingInvert',
  'settingShowFps',
  'fpsLabel',
  'msLabel',
  'fpsAvg',
  'fpsMin',
  'fpsCam',
  'fpsPre',
  'fpsRead',
  'fpsFeat',
  'fpsSel',
  'fpsDraw',
  'fpsCols',
  'fpsNotAvailable',
] as const;

export type MessageKey = (typeof messageKeys)[number];
export type MessageDict = Record<MessageKey, string>;
