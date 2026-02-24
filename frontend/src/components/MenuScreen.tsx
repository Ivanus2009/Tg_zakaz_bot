import type { MenuItem } from "../types";
import { getTypeList } from "../types";

interface MenuScreenProps {
  items: MenuItem[];
  loading: boolean;
  error: string | null;
  onSelectItem: (item: MenuItem) => void;
}

export function MenuScreen({
  items,
  loading,
  error,
  onSelectItem,
}: MenuScreenProps) {
  if (loading) {
    return (
      <div className="screen active">
        <div className="loading">
          <div className="loading-spinner" />
          Загрузка меню...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="screen active">
        <div className="loading">{error}</div>
      </div>
    );
  }

  return (
    <div className="screen active">
      <div className="menu-grid">
        {items.map((item, index) => {
          const typeList = getTypeList(item);
          const minPrice = typeList[0]?.price ?? 0;

          return (
            <button
              key={item.guid}
              type="button"
              className="menu-card"
              style={{ animationDelay: `${index * 0.03}s` }}
              onClick={() => onSelectItem(item)}
            >
              <div className="menu-card-name">{item.name}</div>
              <div className="menu-card-price">от {minPrice} ₽</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
