const TITLES: Record<string, string> = {
  menu: "☕ Меню",
  size: "Размер",
  supplements: "Добавки",
  profile: "Профиль",
};

const STEP_HINT: Record<string, string> = {
  menu: "",
  size: "Меню → Размер",
  supplements: "Меню → Добавки",
  profile: "",
};

interface NavBarProps {
  screen: string;
  cartCount: number;
  onBack: () => void;
  onProfile: () => void;
  onCart: () => void;
  siteUser?: { name?: string | null; phone: string } | null;
  onLoginClick: () => void;
  onLogout: () => void;
}

export function NavBar({
  screen,
  cartCount,
  onBack,
  onProfile,
  onCart,
  siteUser,
  onLoginClick,
  onLogout,
}: NavBarProps) {
  const showBack = ["size", "supplements", "profile"].includes(screen);

  const stepHint = STEP_HINT[screen];

  return (
    <nav className="nav-bar">
      <button
        type="button"
        className={`nav-btn nav-back ${showBack ? "visible" : ""}`}
        onClick={onBack}
        title="Назад"
        aria-label="Назад"
      >
        ←
      </button>
      <div className="nav-title-wrap">
        <div className="nav-title">{TITLES[screen] ?? "☕ Меню"}</div>
        {stepHint ? <div className="nav-step">{stepHint}</div> : null}
      </div>
      <div className="nav-buttons">
        {siteUser ? (
          <>
            <span className="nav-auth-btn" title={siteUser.phone}>
              {siteUser.name || siteUser.phone}
            </span>
            <button type="button" className="nav-btn nav-auth-btn" onClick={onLogout} title="Выйти">
              Выйти
            </button>
          </>
        ) : (
          <button type="button" className="nav-btn nav-auth-btn" onClick={onLoginClick} title="Войти">
            Войти
          </button>
        )}
        <button type="button" className="nav-btn" onClick={onProfile} title="Профиль">
          👤
        </button>
        <div className="cart-btn-wrapper">
          <button
            type="button"
            className="nav-btn"
            onClick={onCart}
            title="Корзина"
          >
            🛒
          </button>
          {cartCount > 0 && (
            <span className="cart-badge bump" key={cartCount}>
              {cartCount}
            </span>
          )}
        </div>
      </div>
    </nav>
  );
}
