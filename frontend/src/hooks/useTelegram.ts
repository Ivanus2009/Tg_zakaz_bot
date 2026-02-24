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

export function useTelegram() {
  const tg = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;

  if (tg) {
    tg.ready();
    tg.expand();
  }

  return {
    tg,
    user: tg?.initDataUnsafe?.user,
    showAlert: (msg: string) => tg?.showAlert(msg),
    showConfirm: (msg: string, cb: (ok: boolean) => void) => tg?.showConfirm(msg, cb),
    sendData: (data: object) => tg?.sendData(JSON.stringify(data)),
  };
}
