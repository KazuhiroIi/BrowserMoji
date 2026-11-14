/** F-9 のエラー種別。表示文言（対処法）は i18n 側で持つ */
export type CameraErrorCode = 'permissionDenied' | 'cameraNotFound' | 'cameraBusy' | 'unsupported';

export class CameraError extends Error {
  constructor(public readonly code: CameraErrorCode, message?: string) {
    super(message ?? code);
    this.name = 'CameraError';
  }
}

/**
 * カメラ取得（architecture.md §6、F-1）。
 * - getUserMedia は利用者の操作（開始ボタン押下）の後に呼ぶ
 * - 背面カメラを要求し（facingMode: 'environment'）、失敗時は制約なし → 'user' にフォールバックする
 * - video 要素は playsinline + muted（iOS Safari 対策）
 * - 要求した解像度と実際の解像度は異なることがあるため、videoWidth/Height を読んでから処理に渡す
 */
export class CameraSource {
  async start(): Promise<HTMLVideoElement> {
    if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== 'function') {
      throw new CameraError('unsupported');
    }
    if (!window.isSecureContext) {
      // カメラは HTTPS（または localhost）でしか使えない（E-3）
      throw new CameraError('unsupported');
    }

    const stream = await this.openStream();

    const video = document.createElement('video');
    video.playsInline = true;
    video.muted = true;
    video.autoplay = true;
    video.setAttribute('playsinline', ''); // iOS Safari は属性での指定が必要
    video.srcObject = stream;
    await video.play().catch(() => {
      // play() が中断された場合も読み込み完了を待って続行する
    });
    await this.waitReady(video);
    return video;
  }

  private async openStream(): Promise<MediaStream> {
    const constraints: MediaStreamConstraints[] = [
      { video: { facingMode: { ideal: 'environment' } }, audio: false }, // 既定は背面カメラ（F-1）
      { video: true, audio: false }, // フォールバック: 制約なし
      { video: { facingMode: { ideal: 'user' } }, audio: false }, // フォールバック: 前面
    ];
    let lastError: unknown;
    for (const constraint of constraints) {
      try {
        return await navigator.mediaDevices.getUserMedia(constraint);
      } catch (e) {
        lastError = e;
        if (isPermissionError(e)) {
          // 権限拒否はフォールバックで解消しないので即時に中断する
          throw new CameraError('permissionDenied', String(e));
        }
      }
    }
    throw toCameraError(lastError);
  }

  /**
   * drawImage で描けるようになるまで待つ（§6 の「実際の値を読み取ってから処理」）。
   * 解像度が読めても readyState が HAVE_CURRENT_DATA 未満だと drawImage が何も描かず、
   * 最初のフレームが「全セルが最も濃い文字」の出力（黒い画面）になるため、
   * 最初のフレームのデータが到着するまで待つ（D-011）
   */
  private waitReady(video: HTMLVideoElement): Promise<void> {
    const hasFrame = (): boolean =>
      video.videoWidth > 0 && video.videoHeight > 0 && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA;
    if (hasFrame()) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const cleanup = (): void => {
        window.clearTimeout(timeout);
        video.removeEventListener('loadeddata', check);
        video.removeEventListener('canplay', check);
        video.removeEventListener('loadedmetadata', check);
        video.removeEventListener('error', onError);
      };
      const timeout = window.setTimeout(() => {
        cleanup();
        if (video.videoWidth > 0) {
          // メタデータは得られている: 従来どおり進める（環境差で待ち続けるより安全）
          resolve();
        } else {
          reject(new CameraError('cameraNotFound'));
        }
      }, 10000);
      const check = (): void => {
        if (hasFrame()) {
          cleanup();
          resolve();
        }
      };
      const onError = (): void => {
        cleanup();
        reject(new CameraError('cameraNotFound'));
      };
      video.addEventListener('loadeddata', check);
      video.addEventListener('canplay', check);
      video.addEventListener('loadedmetadata', check); // readyState が先に進んでいる環境の保険
      video.addEventListener('error', onError);
      check(); // 呼び出し時点で用意できている場合の保険
    });
  }
}

function isPermissionError(e: unknown): boolean {
  return e instanceof DOMException && (e.name === 'NotAllowedError' || e.name === 'SecurityError');
}

function toCameraError(e: unknown): CameraError {
  if (e instanceof DOMException) {
    switch (e.name) {
      case 'NotAllowedError':
      case 'SecurityError':
        return new CameraError('permissionDenied');
      case 'NotFoundError':
      case 'DevicesNotFoundError':
      case 'OverconstrainedError':
        return new CameraError('cameraNotFound');
      case 'NotReadableError':
      case 'TrackStartError':
      case 'AbortError':
        return new CameraError('cameraBusy');
      default:
        break;
    }
  }
  return new CameraError('unsupported');
}
