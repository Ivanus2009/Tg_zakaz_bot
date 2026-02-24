const TITLES: Record<string, string> = {
  menu: "☕ Меню",
  size: "Выбор размера",
  supplements: "Добавки",
  profile: "Профиль",
};

interface NavBarProps {
  screen: string;
  cartCount: number;
  onBack: () => void;
  onProfile: () => void;
  onCart: () => void;
}

export function NavBar({
  screen,
  cartCount,
  onBack,
  onProfile,
  onCart,
}: NavBarProps) {
  const showBack = ["size", "supplements", "profile"].includes(screen);

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
      <div className="nav-title">{TITLES[screen] ?? "☕ Меню"}</div>
      <div className="nav-buttons">
        <button
          type="button"
          className="nav-btn"
          onClick={onProfile}
          title="Профиль"
        >
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
