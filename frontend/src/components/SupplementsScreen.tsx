import type { SupplementCategory } from "../types";

interface SupplementsScreenProps {
  itemName: string;
  categories: SupplementCategory[];
  selectedSupplements: Record<string, boolean>;
  onToggleSupplement: (guid: string) => void;
  onAddToCart: () => void;
}

export function SupplementsScreen({
  itemName,
  categories,
  selectedSupplements,
  onToggleSupplement,
  onAddToCart,
}: SupplementsScreenProps) {
  const hasCategories = categories.length > 0;

  return (
    <div className="screen active">
      <div className="supplements-screen">
        <div className="item-header">
          <div className="item-header-name">{itemName}</div>
        </div>
        <div id="supplements-list">
          {!hasCategories && (
            <div className="empty-state">Добавки не доступны</div>
          )}
          {categories.map((category) => (
            <div key={category.guid} className="supplement-group">
              <div className="supplement-group-title">{category.name}</div>
              {category.itemList?.map((supplement) => {
                const checked = selectedSupplements[supplement.guid] ?? false;
                return (
                  <button
                    key={supplement.guid}
                    type="button"
                    className={`supplement-item ${checked ? "selected" : ""}`}
                    onClick={() => onToggleSupplement(supplement.guid)}
                  >
                    <input
                      type="checkbox"
                      className="supplement-checkbox"
                      readOnly
                      checked={checked}
                      data-supplement-guid={supplement.guid}
                      data-price={supplement.defaultPrice ?? 0}
                    />
                    <span className="supplement-name">{supplement.name}</span>
                    <span className="supplement-price">
                      {supplement.defaultPrice ?? 0} ₽
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <button type="button" className="btn-primary" onClick={onAddToCart}>
          Добавить в корзину
        </button>
      </div>
    </div>
  );
}
