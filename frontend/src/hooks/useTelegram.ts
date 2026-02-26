declare global {
  interface Window {
    Telegram?: {
      WebApp: {
        ready: () => void;
        expand: () => void;
        showAlert: (message: string) => void;
        showConfirm: (message: string, callback: (confirmed: boolean) => void) => void;
        showPopup: (params: { title: string; message: string; buttons?: { type: string }[] }) => void;
        sendData: (data: string) => void;
        close: () => void;
        initData?: string;
        initDataUnsafe?: {
          user?: {
            id?: number;
            first_name?: string;
            last_name?: string;
            username?: string;
            language_code?: string;
            phone?: string;
          };
        };
      };
    };
  }
}

type WebAppUser = NonNullable<NonNullable<Window['Telegram']>['WebApp']['initDataUnsafe']>['user'];

/** Парсим user из сырой строки initData (fallback, если initDataUnsafe.user пустой) */
function parseUserFromInitData(initData: string | undefined): WebAppUser {
  if (!initData || typeof initData !== 'string') return undefined;
  try {
    const params = new URLSearchParams(initData);
    const userStr = params.get('user');
    if (!userStr) return undefined;
    const parsed = JSON.parse(decodeURIComponent(userStr)) as { id?: number; first_name?: string; last_name?: string; username?: string; language_code?: string };
    return parsed?.id != null ? { id: parsed.id, first_name: parsed.first_name, last_name: parsed.last_name, username: parsed.username, language_code: parsed.language_code } : undefined;
  } catch {
    return undefined;
  }
}

export function useTelegram() {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;

  if (tg) {
    tg.ready();
    tg.expand();
  }

  const userFromUnsafe = tg?.initDataUnsafe?.user;
  const userFromRaw = userFromUnsafe ?? parseUserFromInitData(tg?.initData);

  return {
    tg,
    user: userFromRaw,
    showAlert: (msg: string) => tg?.showAlert(msg),
    showConfirm: (msg: string, cb: (ok: boolean) => void) => tg?.showConfirm(msg, cb),
    sendData: (data: object) => tg?.sendData(JSON.stringify(data)),
    /** Закрыть Mini App (после sendData данные в части клиентов доставляются только после close) */
    close: () => tg?.close?.(),
    /** true только когда приложение открыто внутри Telegram (есть sendData в бота) */
    canSendToBot: typeof tg?.sendData === 'function',
  };
}
