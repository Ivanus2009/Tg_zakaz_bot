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

/** Сырая строка initData — в части клиентов может быть init_data (snake_case) */
function getInitDataString(): string | undefined {
  if (typeof window === 'undefined') return undefined;
  const w = (window as unknown as { Telegram?: { WebApp?: { initData?: string; init_data?: string } } }).Telegram?.WebApp;
  return w?.initData ?? w?.init_data;
}

/** Парсим user из сырой строки initData */
function parseUserFromInitData(initData: string | undefined): WebAppUser {
  if (!initData || typeof initData !== 'string') return undefined;
  try {
    const params = new URLSearchParams(initData);
    let userStr = params.get('user') ?? '';
    if (!userStr) return undefined;
    try {
      JSON.parse(userStr);
    } catch {
      userStr = decodeURIComponent(userStr);
    }
    const parsed = JSON.parse(userStr) as { id?: number; first_name?: string; last_name?: string; username?: string; language_code?: string };
    return parsed?.id != null ? { id: parsed.id, first_name: parsed.first_name, last_name: parsed.last_name, username: parsed.username, language_code: parsed.language_code } : undefined;
  } catch {
    return undefined;
  }
}

/** Всегда читает актуального user из Telegram (ленивое чтение при каждом обращении) */
function getTelegramUser(): WebAppUser {
  if (typeof window === 'undefined') return undefined;
  const tg = window.Telegram?.WebApp;
  if (!tg) return undefined;
  const fromUnsafe = tg.initDataUnsafe?.user;
  if (fromUnsafe?.id != null) return fromUnsafe;
  return parseUserFromInitData(getInitDataString());
}

export function useTelegram() {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;

  if (tg) {
    tg.ready();
    tg.expand();
  }

  const user = getTelegramUser();

  return {
    tg,
    user,
    /** Актуальный user при каждом вызове (для проверки перед отправкой заказа) */
    getTelegramUser,
    showAlert: (msg: string) => tg?.showAlert(msg),
    showConfirm: (msg: string, cb: (ok: boolean) => void) => tg?.showConfirm(msg, cb),
    sendData: (data: object) => tg?.sendData(JSON.stringify(data)),
    /** Закрыть Mini App (после sendData данные в части клиентов доставляются только после close) */
    close: () => tg?.close?.(),
    /** true только когда приложение открыто внутри Telegram (есть sendData в бота) */
    canSendToBot: typeof tg?.sendData === 'function',
  };
}
